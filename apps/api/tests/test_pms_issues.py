from datetime import UTC, date, datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError, Event, Lock

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.pms.models import CustomFieldValue, TaskActivityLog
from open_work_hub_api.domains.pms import service as pms_service
from open_work_hub_api.domains.search import outbox as search_outbox
from dev_accounts import create_workspace_user_session, dev_login
from test_docs_hub import (
    _create_doc_page,
    _create_space_doc,
    _list_doc_pages,
    _list_space_docs,
)


@pytest.fixture(autouse=True)
def _isolate_search_index_publication_from_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_outbox, "_publish_job", lambda *, job_id: None)


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def test_issue_list_archived_filters_and_bulk_restore(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)

    active_issue = _create_issue(client, token, task_list["id"], title="Active issue")
    archived_issue = _create_issue(client, token, task_list["id"], title="Archived issue")

    archive_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{archived_issue['id']}",
        headers=_auth_headers(token),
        json={"archived": True},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["archived"] is True

    active_only_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        params={"archived": "false"},
    )
    assert active_only_response.status_code == 200
    assert [item["id"] for item in active_only_response.json()["items"]] == [active_issue["id"]]

    archived_only_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        params={"archived": "true"},
    )
    assert archived_only_response.status_code == 200
    assert [item["id"] for item in archived_only_response.json()["items"]] == [archived_issue["id"]]

    restore_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks/bulk",
        headers=_auth_headers(token),
        json={"task_ids": [archived_issue["id"]], "archived": False},
    )
    assert restore_response.status_code == 200
    assert restore_response.json() == {"updated_count": 1, "deleted_count": 0}

    archived_after_restore_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        params={"archived": "true"},
    )
    assert archived_after_restore_response.status_code == 200
    assert archived_after_restore_response.json()["items"] == []

    active_after_restore_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        params={"archived": "false"},
    )
    assert active_after_restore_response.status_code == 200
    assert [item["id"] for item in active_after_restore_response.json()["items"]] == [
        active_issue["id"],
        archived_issue["id"],
    ]


def test_status_change_preserves_manual_board_position(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)
    first = _create_issue(client, token, task_list["id"], title="First task")
    _create_issue(client, token, task_list["id"], title="Second task")

    response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{first['id']}",
        headers=_auth_headers(token),
        json={"status": "done"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["board_position"] == first["board_position"]


def test_issue_list_sorts_by_task_dates_and_creation_date(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)
    first = _create_issue(
        client,
        token,
        task_list["id"],
        title="First task",
        start_date="2026-07-20",
        due_date="2026-07-30",
    )
    second = _create_issue(
        client,
        token,
        task_list["id"],
        title="Second task",
        start_date="2026-07-10",
        due_date="2026-08-01",
    )
    third = _create_issue(client, token, task_list["id"], title="Undated task")
    for task_id, completed_date in (
        (first["id"], "2026-07-16"),
        (second["id"], "2026-07-15"),
    ):
        response = client.patch(
            f"/api/v1/workspaces/administrator/pms/tasks/{task_id}",
            headers=_auth_headers(token),
            json={"completed_date": completed_date},
        )
        assert response.status_code == 200, response.text

    expected_orders = {
        ("completed_date", "asc"): [second["id"], first["id"], third["id"]],
        ("completed_date", "desc"): [first["id"], second["id"], third["id"]],
        ("created_at", "desc"): [third["id"], second["id"], first["id"]],
        ("due_date", "asc"): [first["id"], second["id"], third["id"]],
        ("due_date", "desc"): [second["id"], first["id"], third["id"]],
        ("start_date", "asc"): [second["id"], first["id"], third["id"]],
    }
    for (sort_by, sort_dir), expected_ids in expected_orders.items():
        response = client.get(
            f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
            headers=_auth_headers(token),
            params={"sort_by": sort_by, "sort_dir": sort_dir},
        )
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()["items"]] == expected_ids


def test_bulk_update_assigns_and_updates_labels_with_activity(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)
    teammate = _create_user(
        client,
        token,
        email="bulk-assignee@open-work-hub.local",
        full_name="Bulk Assignee",
    )
    _add_task_list_member(client, token, task_list["id"], teammate["user"]["id"], "member")

    labels_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/labels",
        headers=_auth_headers(token),
    )
    assert labels_response.status_code == 200
    labels_by_name = {item["name"]: item for item in labels_response.json()["items"]}

    issue_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        json={
            "title": "Bulk assign and labels",
            "description": "",
            "status": "todo",
            "priority": "medium",
            "label_ids": [labels_by_name["review"]["id"]],
        },
    )
    assert issue_response.status_code == 201
    issue = issue_response.json()

    bulk_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks/bulk",
        headers=_auth_headers(token),
        json={
            "task_ids": [issue["id"]],
            "assignee_id": teammate["user"]["id"],
            "add_label_ids": [labels_by_name["blocked"]["id"]],
            "remove_label_ids": [labels_by_name["review"]["id"]],
        },
    )
    assert bulk_response.status_code == 200
    assert bulk_response.json() == {"updated_count": 1, "deleted_count": 0}

    detail_response = client.get(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}",
        headers=_auth_headers(token),
    )
    assert detail_response.status_code == 200
    task_payload = detail_response.json()["task"]
    assert task_payload["assignee_id"] == teammate["user"]["id"]
    assert task_payload["assignee_ids"] == [teammate["user"]["id"]]
    assert {label["name"] for label in task_payload["labels"]} == {"blocked"}

    with get_session_factory()() as db:
        assignee_log = db.scalar(
            select(TaskActivityLog).where(
                TaskActivityLog.task_id == issue["id"],
                TaskActivityLog.field_name == "assignee",
            )
        )
    assert assignee_log is not None


def test_task_update_reuses_existing_label_links(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)
    labels_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/labels",
        headers=_auth_headers(token),
    )
    assert labels_response.status_code == 200
    label_id = labels_response.json()["items"][0]["id"]
    issue_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        json={
            "title": "Keep existing label",
            "description": "",
            "status": "todo",
            "priority": "medium",
            "label_ids": [label_id],
        },
    )
    assert issue_response.status_code == 201

    response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue_response.json()['id']}",
        headers=_auth_headers(token),
        json={"label_ids": [label_id]},
    )

    assert response.status_code == 200, response.text
    assert [label["id"] for label in response.json()["labels"]] == [label_id]


def test_task_update_logs_more_than_six_assignees(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)
    assignee_ids: list[str] = []
    for index in range(7):
        teammate = _create_user(
            client,
            token,
            email=f"many-assignees-{index}@open-work-hub.local",
            full_name=f"Many Assignees {index}",
        )
        assignee_id = teammate["user"]["id"]
        _add_task_list_member(client, token, task_list["id"], assignee_id, "member")
        assignee_ids.append(assignee_id)
    issue = _create_issue(client, token, task_list["id"], title="Many assignees")

    response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}",
        headers=_auth_headers(token),
        json={"assignee_ids": assignee_ids},
    )

    assert response.status_code == 200, response.text
    assert response.json()["assignee_ids"] == assignee_ids
    with get_session_factory()() as db:
        activity = db.scalar(
            select(TaskActivityLog).where(
                TaskActivityLog.task_id == issue["id"],
                TaskActivityLog.field_name == "assignee_ids",
            )
        )
    assert activity is not None
    assert activity.to_value == ",".join(assignee_ids)


def test_concurrent_assignee_updates_are_idempotent(
    client: TestClient,
    monkeypatch,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)
    teammate = _create_user(
        client,
        token,
        email="concurrent-assignee@open-work-hub.local",
        full_name="Concurrent Assignee",
    )
    assignee_id = teammate["user"]["id"]
    _add_task_list_member(client, token, task_list["id"], assignee_id, "member")
    issue = _create_issue(client, token, task_list["id"], title="Concurrent assignee")

    original_get_task_for_user = pms_service._get_task_for_user
    readers_ready = Barrier(2)

    def synchronized_get_task_for_user(*args, **kwargs):
        result = original_get_task_for_user(*args, **kwargs)
        try:
            readers_ready.wait(timeout=0.5)
        except BrokenBarrierError:
            pass
        return result

    monkeypatch.setattr(
        pms_service,
        "_get_task_for_user",
        synchronized_get_task_for_user,
    )

    def assign_task():
        try:
            return client.patch(
                f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}",
                headers=_auth_headers(token),
                json={"assignee_ids": [assignee_id]},
            )
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: assign_task(), range(2)))

    assert all(getattr(result, "status_code", None) == 200 for result in results), results


def test_task_reorder_updates_positions_and_parent_in_one_request(
    client: TestClient,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="REORDER", name="Reorder List")
    first = _create_issue(client, token, task_list["id"], title="First task")
    second = _create_issue(client, token, task_list["id"], title="Second task")
    third = _create_issue(client, token, task_list["id"], title="Third task")

    response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks/reorder",
        headers=_auth_headers(token),
        json={
            "items": [
                {"task_id": third["id"], "board_position": 1000},
                {"task_id": first["id"], "board_position": 2000},
                {
                    "task_id": second["id"],
                    "board_position": 1000,
                    "parent_id": third["id"],
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["updated_count"] == 3
    returned_by_id = {item["id"]: item for item in payload["items"]}
    assert returned_by_id[third["id"]]["board_position"] == 1000
    assert returned_by_id[third["id"]]["parent_id"] is None
    assert returned_by_id[first["id"]]["board_position"] == 2000
    assert returned_by_id[first["id"]]["parent_id"] is None
    assert returned_by_id[second["id"]]["board_position"] == 1000
    assert returned_by_id[second["id"]]["parent_id"] == third["id"]

    list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    listed_by_id = {item["id"]: item for item in list_response.json()["items"]}
    assert listed_by_id[third["id"]]["board_position"] == 1000
    assert listed_by_id[first["id"]]["board_position"] == 2000
    assert listed_by_id[second["id"]]["parent_id"] == third["id"]


def test_task_reorder_rejects_parent_cycles_without_partial_write(
    client: TestClient,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="REORDCYC", name="Reorder Cycle List")
    parent = _create_issue(client, token, task_list["id"], title="Parent task")
    child = _create_issue(
        client,
        token,
        task_list["id"],
        title="Child task",
        parent_id=parent["id"],
    )

    response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks/reorder",
        headers=_auth_headers(token),
        json={
            "items": [
                {
                    "task_id": parent["id"],
                    "board_position": 9000,
                    "parent_id": child["id"],
                },
                {"task_id": child["id"], "board_position": 8000},
            ],
        },
    )

    assert response.status_code == 409, response.text
    list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    listed_by_id = {item["id"]: item for item in list_response.json()["items"]}
    assert listed_by_id[parent["id"]]["parent_id"] is None
    assert listed_by_id[parent["id"]]["board_position"] == parent["board_position"]
    assert listed_by_id[child["id"]]["parent_id"] == parent["id"]
    assert listed_by_id[child["id"]]["board_position"] == child["board_position"]


def test_task_reorder_rejects_duplicate_task_ids_without_partial_write(
    client: TestClient,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="REORDDUP", name="Reorder Duplicate List")
    first = _create_issue(client, token, task_list["id"], title="First duplicate task")
    second = _create_issue(client, token, task_list["id"], title="Second duplicate task")

    response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks/reorder",
        headers=_auth_headers(token),
        json={
            "items": [
                {"task_id": first["id"], "board_position": 9000},
                {"task_id": first["id"], "board_position": 8000},
                {"task_id": second["id"], "board_position": 7000},
            ],
        },
    )

    assert response.status_code == 400, response.text
    list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    listed_by_id = {item["id"]: item for item in list_response.json()["items"]}
    assert listed_by_id[first["id"]]["board_position"] == first["board_position"]
    assert listed_by_id[second["id"]]["board_position"] == second["board_position"]


def test_unlinking_subtask_places_it_after_its_former_parent(
    client: TestClient,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="UNLINKPOS", name="Unlink Position List")
    first = _create_issue(client, token, task_list["id"], title="First root")
    parent = _create_issue(client, token, task_list["id"], title="Parent root")
    next_root = _create_issue(client, token, task_list["id"], title="Next root")
    child = _create_issue(client, token, task_list["id"], title="Moved child")

    nest_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks/reorder",
        headers=_auth_headers(token),
        json={
            "items": [
                {
                    "task_id": child["id"],
                    "board_position": 1000,
                    "parent_id": parent["id"],
                }
            ],
        },
    )
    assert nest_response.status_code == 200, nest_response.text

    unlink_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{child['id']}",
        headers=_auth_headers(token),
        json={"parent_id": None},
    )
    assert unlink_response.status_code == 200, unlink_response.text
    assert unlink_response.json()["parent_id"] is None

    list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    root_ids = [item["id"] for item in list_response.json()["items"] if item["parent_id"] is None]
    assert root_ids == [first["id"], parent["id"], child["id"], next_root["id"]]


def test_concurrent_subtask_unlinks_keep_root_positions_consistent(
    client: TestClient,
    monkeypatch,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="UNLINKRACE", name="Unlink Race List")
    first_parent = _create_issue(client, token, task_list["id"], title="First parent")
    first_child = _create_issue(client, token, task_list["id"], title="First child")
    second_parent = _create_issue(client, token, task_list["id"], title="Second parent")
    second_child = _create_issue(client, token, task_list["id"], title="Second child")
    nest_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks/reorder",
        headers=_auth_headers(token),
        json={
            "items": [
                {
                    "task_id": first_child["id"],
                    "board_position": 1000,
                    "parent_id": first_parent["id"],
                },
                {
                    "task_id": second_child["id"],
                    "board_position": 1000,
                    "parent_id": second_parent["id"],
                },
            ],
        },
    )
    assert nest_response.status_code == 200, nest_response.text

    original_get_task_for_user = pms_service._get_task_for_user
    readers_ready = Barrier(2)

    def synchronized_get_task_for_user(*args, **kwargs):
        result = original_get_task_for_user(*args, **kwargs)
        try:
            readers_ready.wait(timeout=0.5)
        except BrokenBarrierError:
            pass
        return result

    monkeypatch.setattr(
        pms_service,
        "_get_task_for_user",
        synchronized_get_task_for_user,
    )

    def unlink_task(task_id: str):
        return client.patch(
            f"/api/v1/workspaces/administrator/pms/tasks/{task_id}",
            headers=_auth_headers(token),
            json={"parent_id": None},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(unlink_task, [first_child["id"], second_child["id"]]))
    assert all(response.status_code == 200 for response in responses)

    list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    roots = [item for item in list_response.json()["items"] if item["parent_id"] is None]
    assert [item["id"] for item in roots] == [
        first_parent["id"],
        first_child["id"],
        second_parent["id"],
        second_child["id"],
    ]
    assert len({item["board_position"] for item in roots}) == len(roots)


def test_unlink_and_root_reorder_do_not_deadlock(
    client: TestClient,
    monkeypatch,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="UNLINKLOCK", name="Unlink Lock List")
    parent = _create_issue(client, token, task_list["id"], title="Parent")
    root_to_move = _create_issue(client, token, task_list["id"], title="Other root")
    child = _create_issue(client, token, task_list["id"], title="Child")
    nest_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks/reorder",
        headers=_auth_headers(token),
        json={
            "items": [
                {
                    "task_id": child["id"],
                    "board_position": 1000,
                    "parent_id": parent["id"],
                }
            ],
        },
    )
    assert nest_response.status_code == 200, nest_response.text

    task_rows_locked = Barrier(2)
    unlink_list_locked = Event()
    role_assignment_lock = Lock()
    roles_by_session: dict[int, str] = {}
    unassigned_lock_calls = 0
    original_get_task_for_user = pms_service._get_task_for_user
    original_lock_task_list_order = pms_service._lock_task_list_order

    def synchronized_get_task_for_user(db, user, task_id, **kwargs):
        if task_id == child["id"]:
            roles_by_session[id(db)] = "unlink"
        elif task_id == root_to_move["id"]:
            roles_by_session[id(db)] = "root"
        result = original_get_task_for_user(db, user, task_id, **kwargs)
        try:
            task_rows_locked.wait(timeout=0.5)
        except BrokenBarrierError:
            pass
        return result

    def synchronized_lock_task_list_order(db, list_id):
        nonlocal unassigned_lock_calls
        role = roles_by_session.get(id(db))
        if role is None:
            with role_assignment_lock:
                role = "unlink" if unassigned_lock_calls == 0 else "root"
                unassigned_lock_calls += 1
        if role == "unlink":
            result = original_lock_task_list_order(db, list_id)
            unlink_list_locked.set()
            return result
        if role == "root":
            assert unlink_list_locked.wait(timeout=2)
        return original_lock_task_list_order(db, list_id)

    monkeypatch.setattr(
        pms_service,
        "_get_task_for_user",
        synchronized_get_task_for_user,
    )
    monkeypatch.setattr(
        pms_service,
        "_lock_task_list_order",
        synchronized_lock_task_list_order,
    )

    def patch_task(task_id: str, payload: dict):
        try:
            return client.patch(
                f"/api/v1/workspaces/administrator/pms/tasks/{task_id}",
                headers=_auth_headers(token),
                json=payload,
            )
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        unlink_future = executor.submit(patch_task, child["id"], {"parent_id": None})
        reorder_future = executor.submit(
            patch_task,
            root_to_move["id"],
            {"board_position": root_to_move["board_position"] + 500},
        )
        results = [unlink_future.result(), reorder_future.result()]

    assert all(getattr(result, "status_code", None) == 200 for result in results), results


def test_viewer_cannot_modify_issue_comment_or_folder(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    issue = _create_issue(client, admin_session["token"], task_list["id"], title="Protected issue")

    viewer = _create_user(
        client, admin_session["token"], email="viewer@open-work-hub.local", full_name="Viewer User"
    )
    _add_task_list_member(
        client, admin_session["token"], task_list["id"], viewer["user"]["id"], "viewer"
    )
    viewer_token = _login(client, viewer["user"]["email"], viewer["temporary_password"])

    update_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}",
        headers=_auth_headers(viewer_token),
        json={"title": "Viewer edit attempt"},
    )
    assert update_response.status_code == 403

    comment_response = client.post(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}/comments",
        headers=_auth_headers(viewer_token),
        json={"body": "viewer comment"},
    )
    assert comment_response.status_code == 403

    folder_response = client.post(
        "/api/v1/workspaces/administrator/pms/folders",
        headers=_auth_headers(viewer_token),
        json={"name": "Viewer folder", "team_id": task_list["team_id"]},
    )
    assert folder_response.status_code == 403

    space_doc_response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(viewer_token),
        json={
            "title": "Viewer collection",
            "source_app": "pms",
            "source_kind": "manual",
            "primary_target": {
                "app": "pms",
                "type": "space",
                "id": task_list["team_id"],
            },
        },
    )
    assert space_doc_response.status_code == 403


def test_task_comment_mention_notification_identifies_task(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    issue = _create_issue(
        client,
        admin_session["token"],
        task_list["id"],
        title="Mention target task",
    )
    mentioned = _create_user(
        client,
        admin_session["token"],
        email="mentioned-pms-member@open-work-hub.local",
        full_name="Mentioned Member",
    )
    _add_task_list_member(
        client, admin_session["token"], task_list["id"], mentioned["user"]["id"], "member"
    )

    comment_response = client.post(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}/comments",
        headers=_auth_headers(admin_session["token"]),
        json={
            "body": "Please check @Mentioned Member - Product",
            "body_blocks": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Please check ", "styles": {}},
                        {
                            "type": "mention",
                            "props": {
                                "userId": mentioned["user"]["id"],
                                "displayName": "Mentioned Member - Product",
                            },
                        },
                    ],
                }
            ],
        },
    )
    assert comment_response.status_code == 201

    mentioned_token = _login(client, mentioned["user"]["email"], mentioned["temporary_password"])
    notifications_response = client.get(
        "/api/v1/notifications", headers=_auth_headers(mentioned_token)
    )
    assert notifications_response.status_code == 200, notifications_response.text
    notification = notifications_response.json()["items"][0]
    assert notification["type"] == "mentioned"
    assert notification["title"] == "Mentioned in Mention target task"
    assert issue["reference"] not in notification["title"]
    assert "Mention target task" in notification["title"]
    assert "Mention target task" in notification["body"]
    assert issue["reference"] in notification["body"]
    assert notification["source_type"] == "pms_task"
    assert notification["source_id"] == issue["id"]
    assert notification["origin_app_id"] == "pms"
    assert notification["origin_workspace_id"] == admin_session["user"]["workspaces"][0]["id"]
    assert (
        notification["action_url"]
        == f"/apps/pms/workspaces/administrator/lists/{task_list['id']}?task={issue['id']}"
    )


def test_task_comment_notification_identifies_task_by_title(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    assignee = _create_user(
        client,
        admin_session["token"],
        email="comment-notification-member@open-work-hub.local",
        full_name="Comment Notification Member",
    )
    _add_task_list_member(
        client, admin_session["token"], task_list["id"], assignee["user"]["id"], "member"
    )
    issue = _create_issue(
        client,
        admin_session["token"],
        task_list["id"],
        title="Comment target task",
        assignee_id=assignee["user"]["id"],
    )

    comment_response = client.post(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}/comments",
        headers=_auth_headers(admin_session["token"]),
        json={"body": "please review"},
    )
    assert comment_response.status_code == 201, comment_response.text

    assignee_token = _login(client, assignee["user"]["email"], assignee["temporary_password"])
    notifications_response = client.get(
        "/api/v1/notifications", headers=_auth_headers(assignee_token)
    )
    assert notifications_response.status_code == 200, notifications_response.text
    notification = notifications_response.json()["items"][0]
    assert notification["type"] == "commented"
    assert notification["title"] == "New comment on Comment target task"
    assert issue["reference"] not in notification["title"]
    assert "Comment target task" in notification["body"]
    assert issue["reference"] in notification["body"]


def test_task_assignment_notification_identifies_task_by_title(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"], key="SMART", name="Smart Lab")
    assignee = _create_user(
        client,
        admin_session["token"],
        email="assignment-notification-member@open-work-hub.local",
        full_name="Assignment Notification Member",
    )
    _add_task_list_member(
        client, admin_session["token"], task_list["id"], assignee["user"]["id"], "member"
    )
    issue = _create_issue(
        client,
        admin_session["token"],
        task_list["id"],
        title="AI 서버 근크림 그리기",
    )

    assign_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}",
        headers=_auth_headers(admin_session["token"]),
        json={"assignee_id": assignee["user"]["id"]},
    )
    assert assign_response.status_code == 200, assign_response.text

    assignee_token = _login(client, assignee["user"]["email"], assignee["temporary_password"])
    notifications_response = client.get(
        "/api/v1/notifications", headers=_auth_headers(assignee_token)
    )
    assert notifications_response.status_code == 200, notifications_response.text
    notification = notifications_response.json()["items"][0]
    assert notification["type"] == "assigned"
    assert notification["title"] == "AI 서버 근크림 그리기 assigned to you"
    assert issue["reference"] not in notification["title"]
    assert notification["body"].startswith("Open Work Hub Admin assigned AI 서버 근크림 그리기")
    assert notification["source_type"] == "pms_task"
    assert notification["source_id"] == issue["id"]
    assert notification["origin_app_id"] == "pms"
    assert notification["origin_workspace_id"] == admin_session["user"]["workspaces"][0]["id"]


def test_explicit_null_clears_nullable_issue_fields(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    issue = _create_issue(
        client,
        admin_session["token"],
        task_list["id"],
        title="Clear me",
        assignee_id=admin_session["user"]["id"],
        start_date="2026-04-01",
        due_date="2026-04-10",
        recurrence_rule="FREQ=DAILY",
    )

    clear_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}",
        headers=_auth_headers(admin_session["token"]),
        json={
            "assignee_id": None,
            "start_date": None,
            "due_date": None,
            "recurrence_rule": None,
        },
    )
    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["assignee_id"] is None
    assert payload["start_date"] is None
    assert payload["due_date"] is None
    assert payload["recurrence_rule"] is None


def test_issue_assignees_reject_non_members(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    issue = _create_issue(client, admin_session["token"], task_list["id"], title="Assignee guard")
    outsider = _create_user(
        client, admin_session["token"], email="outsider@open-work-hub.local", full_name="Outsider User"
    )

    response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}/assignees",
        headers=_auth_headers(admin_session["token"]),
        json={"user_ids": [outsider["user"]["id"]]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "pms.assignees_task_list_members_required"
    assert response.json()["detail"] == "담당자들은 태스크 리스트 멤버여야 합니다."


def test_issue_user_roles_support_assignees_and_followers(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    teammate = _create_user(
        client,
        admin_session["token"],
        email="role-assignee@open-work-hub.local",
        full_name="Role Assignee",
    )
    follower = _create_user(
        client,
        admin_session["token"],
        email="role-follower@open-work-hub.local",
        full_name="Role Follower",
    )
    outsider = _create_user(
        client,
        admin_session["token"],
        email="role-outsider@open-work-hub.local",
        full_name="Role Outsider",
    )
    _add_task_list_member(
        client, admin_session["token"], task_list["id"], teammate["user"]["id"], "member"
    )
    _add_task_list_member(
        client, admin_session["token"], task_list["id"], follower["user"]["id"], "member"
    )
    issue = _create_issue(
        client, admin_session["token"], task_list["id"], title="Role mapped issue"
    )

    assignee_response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}/assignees",
        headers=_auth_headers(admin_session["token"]),
        json={"user_ids": [admin_session["user"]["id"], teammate["user"]["id"]]},
    )
    assert assignee_response.status_code == 200
    assert [item["user_id"] for item in assignee_response.json()] == [
        admin_session["user"]["id"],
        teammate["user"]["id"],
    ]

    follower_response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}/followers",
        headers=_auth_headers(admin_session["token"]),
        json={"user_ids": [follower["user"]["id"]]},
    )
    assert follower_response.status_code == 200
    assert follower_response.json() == [
        {"user_id": follower["user"]["id"], "full_name": "Role Follower"}
    ]

    detail_response = client.get(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert detail_response.status_code == 200
    detail_issue = detail_response.json()["task"]
    assert detail_issue["assignee_ids"] == [admin_session["user"]["id"], teammate["user"]["id"]]
    assert detail_issue["assignee_id"] == admin_session["user"]["id"]
    assert detail_issue["follower_ids"] == [follower["user"]["id"]]

    teammate_token = _login(client, teammate["user"]["email"], teammate["temporary_password"])
    assigned_response = client.get(
        "/api/v1/workspaces/administrator/pms/tasks/assigned",
        headers=_auth_headers(teammate_token),
    )
    assert assigned_response.status_code == 200
    assert issue["id"] in {item["id"] for item in assigned_response.json()["items"]}

    legacy_assignee_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}",
        headers=_auth_headers(admin_session["token"]),
        json={"assignee_id": teammate["user"]["id"]},
    )
    assert legacy_assignee_response.status_code == 200
    compatibility_issue = legacy_assignee_response.json()
    assert compatibility_issue["assignee_id"] == teammate["user"]["id"]
    assert compatibility_issue["assignee_ids"] == [teammate["user"]["id"]]

    outsider_response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}/followers",
        headers=_auth_headers(admin_session["token"]),
        json={"user_ids": [outsider["user"]["id"]]},
    )
    assert outsider_response.status_code == 400
    assert outsider_response.json()["code"] == "pms.followers_task_list_members_required"


def test_pms_user_directory_only_returns_workspace_members(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    teammate = _create_user(
        client,
        admin_session["token"],
        email="pms-scope-member@open-work-hub.local",
        full_name="PMS Scoped Same Workspace",
    )
    outsider = create_workspace_user_session(
        client,
        workspace_key="pms-other-workspace",
        login_id="pmsotherscope",
        email="pms-other-scope@open-work-hub.local",
        full_name="PMS Scoped Other Workspace",
    )

    response = client.get(
        "/api/v1/workspaces/administrator/pms/users",
        headers=_auth_headers(admin_session["token"]),
    )

    assert response.status_code == 200, response.text
    item_ids = {item["id"] for item in response.json()}
    assert teammate["user"]["id"] in item_ids
    assert outsider["user"]["id"] not in item_ids


def test_workspace_scoped_default_pms_space_stays_inside_requested_workspace(
    client: TestClient,
) -> None:
    admin_session = _bootstrap_admin_session(client)
    _dev_login(client, "delivery-hub-admin")
    workspace_admin = _create_workspace_admin(
        client,
        admin_session["token"],
        email="administrator-context-admin@open-work-hub.local",
        full_name="Administrator Context Admin",
    )

    admin_token = _login(
        client,
        workspace_admin["user"]["email"],
        workspace_admin["temporary_password"],
    )

    before_admin_spaces = client.get(
        "/api/v1/workspaces/administrator/pms/spaces",
        headers=_auth_headers(admin_token),
    )
    assert before_admin_spaces.status_code == 200
    assert before_admin_spaces.json() == []

    before_delivery_spaces = client.get(
        "/api/v1/workspaces/delivery-hub/pms/spaces",
        headers=_auth_headers(admin_token),
    )
    assert before_delivery_spaces.status_code == 403

    create_list_response = client.post(
        "/api/v1/workspaces/administrator/pms/lists",
        headers=_auth_headers(admin_token),
        json={
            "key": "ADMINCTX",
            "name": "Administrator Context List",
            "description": "Should bind to Administrator default space",
        },
    )
    assert create_list_response.status_code == 201, create_list_response.text
    created_list = create_list_response.json()

    after_admin_spaces = client.get(
        "/api/v1/workspaces/administrator/pms/spaces",
        headers=_auth_headers(admin_token),
    )
    assert after_admin_spaces.status_code == 200
    assert {item["id"] for item in after_admin_spaces.json()} == {created_list["team_id"]}

    create_folder_response = client.post(
        "/api/v1/workspaces/administrator/pms/folders",
        headers=_auth_headers(admin_token),
        json={"name": "Administrator Context Folder"},
    )
    assert create_folder_response.status_code == 201, create_folder_response.text
    created_folder = create_folder_response.json()
    assert created_folder["team_id"] == created_list["team_id"]


def test_workspace_admin_needs_direct_pms_space_membership(
    client: TestClient,
) -> None:
    admin_session = _bootstrap_admin_session(client)
    workspace_admin = _create_workspace_admin(
        client,
        admin_session["token"],
        email="administrator-pms-admin@open-work-hub.local",
        full_name="Administrator PMS Admin",
    )
    workspace_admin_token = _login(
        client,
        workspace_admin["user"]["email"],
        workspace_admin["temporary_password"],
    )
    workspace_member = _create_user(
        client,
        admin_session["token"],
        email="administrator-pms-member@open-work-hub.local",
        full_name="Administrator PMS Member",
    )

    create_space_response = client.post(
        "/api/v1/workspaces/administrator/pms/spaces",
        headers=_auth_headers(admin_session["token"]),
        json={"name": "Workspace Admin Managed Space"},
    )
    assert create_space_response.status_code == 201, create_space_response.text
    space = create_space_response.json()

    create_list_response = client.post(
        "/api/v1/workspaces/administrator/pms/lists",
        headers=_auth_headers(admin_session["token"]),
        json={
            "key": "WADM",
            "name": "Workspace Admin Visible List",
            "team_id": space["id"],
        },
    )
    assert create_list_response.status_code == 201, create_list_response.text
    task_list = create_list_response.json()

    spaces_response = client.get(
        "/api/v1/workspaces/administrator/pms/spaces",
        headers=_auth_headers(workspace_admin_token),
    )
    assert spaces_response.status_code == 200
    assert space["id"] not in {item["id"] for item in spaces_response.json()}

    lists_response = client.get(
        "/api/v1/workspaces/administrator/pms/lists",
        headers=_auth_headers(workspace_admin_token),
    )
    assert lists_response.status_code == 200
    assert task_list["id"] not in {item["id"] for item in lists_response.json()["items"]}

    list_detail_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}",
        headers=_auth_headers(workspace_admin_token),
    )
    assert list_detail_response.status_code == 403
    assert list_detail_response.json()["code"] == "pms.task_list_access_required"

    add_member_response = client.post(
        f"/api/v1/workspaces/administrator/pms/spaces/{space['id']}/members",
        headers=_auth_headers(workspace_admin_token),
        json={"user_id": workspace_member["user"]["id"], "role": "member"},
    )
    assert add_member_response.status_code == 403
    assert add_member_response.json()["code"] == "pms.space_access_required"

    grant_space_admin_response = client.post(
        f"/api/v1/workspaces/administrator/pms/spaces/{space['id']}/members",
        headers=_auth_headers(admin_session["token"]),
        json={"user_id": workspace_admin["user"]["id"], "role": "owner"},
    )
    assert grant_space_admin_response.status_code == 201, grant_space_admin_response.text

    spaces_after_grant_response = client.get(
        "/api/v1/workspaces/administrator/pms/spaces",
        headers=_auth_headers(workspace_admin_token),
    )
    assert spaces_after_grant_response.status_code == 200
    visible_space = next(
        item for item in spaces_after_grant_response.json() if item["id"] == space["id"]
    )
    assert visible_space["current_user_role"] == "owner"

    lists_after_grant_response = client.get(
        "/api/v1/workspaces/administrator/pms/lists",
        headers=_auth_headers(workspace_admin_token),
    )
    assert lists_after_grant_response.status_code == 200
    assert any(item["id"] == task_list["id"] for item in lists_after_grant_response.json()["items"])

    add_member_response = client.post(
        f"/api/v1/workspaces/administrator/pms/spaces/{space['id']}/members",
        headers=_auth_headers(workspace_admin_token),
        json={"user_id": workspace_member["user"]["id"], "role": "member"},
    )
    assert add_member_response.status_code == 201, add_member_response.text
    assert add_member_response.json()["user_id"] == workspace_member["user"]["id"]


def test_task_list_can_be_renamed_and_deleted_with_tasks_and_custom_fields(
    client: TestClient,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="DEL", name="Delete Me")

    rename_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}",
        headers=_auth_headers(token),
        json={"name": "Renamed List"},
    )
    assert rename_response.status_code == 200, rename_response.text
    assert rename_response.json()["name"] == "Renamed List"

    task = _create_issue(client, token, task_list["id"], title="Delete with list")
    field_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/custom-fields",
        headers=_auth_headers(token),
        json={"name": "Impact", "field_type": "text", "sort_order": 0},
    )
    assert field_response.status_code == 201, field_response.text
    field = field_response.json()
    value_response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}/custom-field-values",
        headers=_auth_headers(token),
        json={"field_id": field["id"], "value": "High"},
    )
    assert value_response.status_code == 200, value_response.text

    archive_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}",
        headers=_auth_headers(token),
        json={"archived": True},
    )
    assert archive_response.status_code == 200, archive_response.text

    delete_response = client.delete(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}",
        headers=_auth_headers(token),
    )
    assert delete_response.status_code == 204, delete_response.text

    get_list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}",
        headers=_auth_headers(token),
    )
    assert get_list_response.status_code == 404

    get_task_response = client.get(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}",
        headers=_auth_headers(token),
    )
    assert get_task_response.status_code == 404

    lists_response = client.get(
        "/api/v1/workspaces/administrator/pms/lists",
        headers=_auth_headers(token),
    )
    assert lists_response.status_code == 200
    assert task_list["id"] not in {item["id"] for item in lists_response.json()["items"]}

    with get_session_factory()() as db:
        custom_value = db.scalar(
            select(CustomFieldValue).where(CustomFieldValue.field_id == field["id"])
        )
    assert custom_value is None


def test_task_list_member_cannot_delete_task_list(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="NODEL", name="Protected List")
    member = _create_user(
        client,
        token,
        email="list-delete-member@open-work-hub.local",
        full_name="List Delete Member",
    )
    _grant_workspace_access(client, token, member["user"]["id"], "administrator")
    _add_task_list_member(client, token, task_list["id"], member["user"]["id"], "member")
    member_token = _login(
        client,
        member["user"]["email"],
        member["temporary_password"],
    )

    response = client.delete(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}",
        headers=_auth_headers(member_token),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "pms.task_list_owner_admin_required"


def test_space_docs_collection_permissions_and_soft_delete(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    space_id = task_list["team_id"]
    assert space_id is not None

    collection = _create_space_doc(
        client,
        admin_session["token"],
        space_id,
        title="Engineering Handbook",
    )

    first_page = _create_doc_page(
        client,
        admin_session["token"],
        collection["id"],
        title="Overview",
    )

    child_page = _create_doc_page(
        client,
        admin_session["token"],
        collection["id"],
        title="Checklist",
        parent_id=first_page["id"],
    )

    outsider = _create_user(
        client,
        admin_session["token"],
        email="space-outsider@open-work-hub.local",
        full_name="Space Outsider",
    )
    outsider_token = _login(client, outsider["user"]["email"], outsider["temporary_password"])

    outsider_list_response = client.get(
        "/api/v1/workspaces/administrator/docs/hub",
        headers=_auth_headers(outsider_token),
        params={"space_id": space_id},
    )
    assert outsider_list_response.status_code == 200
    assert outsider_list_response.json()["items"] == []

    outsider_create_response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(outsider_token),
        json={
            "title": "Forbidden",
            "source_app": "pms",
            "source_kind": "manual",
            "primary_target": {"app": "pms", "type": "space", "id": space_id},
        },
    )
    assert outsider_create_response.status_code == 403

    task_list_editor = _create_user(
        client,
        admin_session["token"],
        email="space-editor@open-work-hub.local",
        full_name="Task List Editor",
    )
    _add_task_list_member(
        client, admin_session["token"], task_list["id"], task_list_editor["user"]["id"], "member"
    )
    task_list_editor_token = _login(
        client,
        task_list_editor["user"]["email"],
        task_list_editor["temporary_password"],
    )

    editor_docs = _list_space_docs(client, task_list_editor_token, space_id)
    assert [item["id"] for item in editor_docs] == [collection["id"]]

    member_collection = _create_space_doc(
        client,
        task_list_editor_token,
        space_id,
        title="Task List Notes",
    )
    assert member_collection["created_by_id"] == task_list_editor["user"]["id"]

    member_page = _create_doc_page(
        client,
        task_list_editor_token,
        collection["id"],
        title="Member page",
    )
    assert member_page["doc_id"] == collection["id"]

    member_folder_response = client.post(
        "/api/v1/workspaces/administrator/pms/folders",
        headers=_auth_headers(task_list_editor_token),
        json={"name": "Member folder", "team_id": space_id},
    )
    assert member_folder_response.status_code == 201
    member_folder = member_folder_response.json()
    assert member_folder["team_id"] == space_id

    second_collection = _create_space_doc(
        client,
        admin_session["token"],
        space_id,
        title="Admin Notes",
    )

    cross_collection_parent_response = client.post(
        f"/api/v1/workspaces/administrator/docs/items/{second_collection['id']}/pages",
        headers=_auth_headers(admin_session["token"]),
        json={
            "title": "Invalid child",
            "parent_id": first_page["id"],
        },
    )
    assert cross_collection_parent_response.status_code == 404
    assert cross_collection_parent_response.json()["code"] == "docs.parent_page_not_found"

    delete_collection_response = client.delete(
        f"/api/v1/workspaces/administrator/docs/items/{collection['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert delete_collection_response.status_code == 204

    visible_ids = sorted(
        item["id"] for item in _list_space_docs(client, admin_session["token"], space_id)
    )
    assert visible_ids == sorted([member_collection["id"], second_collection["id"]])

    deleted_collection_response = client.get(
        f"/api/v1/workspaces/administrator/docs/items/{collection['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert deleted_collection_response.status_code == 200
    assert deleted_collection_response.json()["trashed_at"] is not None

    deleted_page_response = client.get(
        f"/api/v1/workspaces/administrator/docs/pages/{first_page['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert deleted_page_response.status_code == 403

    deleted_child_response = client.get(
        f"/api/v1/workspaces/administrator/docs/pages/{child_page['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert deleted_child_response.status_code == 403

    deleted_collection_pages = _list_doc_pages(client, admin_session["token"], collection["id"])
    assert deleted_collection_pages == []


def test_task_list_member_api_grants_space_scope_for_task_list_resources(
    client: TestClient,
) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    space_id = task_list["team_id"]
    assert space_id is not None

    issue = _create_issue(client, admin_session["token"], task_list["id"], title="List-only issue")

    task_list_member = _create_user(
        client,
        admin_session["token"],
        email="task-list-member@open-work-hub.local",
        full_name="Task List Member",
    )
    _add_task_list_member(
        client, admin_session["token"], task_list["id"], task_list_member["user"]["id"], "member"
    )
    task_list_member_token = _login(
        client,
        task_list_member["user"]["email"],
        task_list_member["temporary_password"],
    )

    task_list_detail_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}",
        headers=_auth_headers(task_list_member_token),
    )
    assert task_list_detail_response.status_code == 200

    task_list_issue_detail_response = client.get(
        f"/api/v1/workspaces/administrator/pms/tasks/{issue['id']}",
        headers=_auth_headers(task_list_member_token),
    )
    assert task_list_issue_detail_response.status_code == 200

    space_lists_response = client.get(
        f"/api/v1/workspaces/administrator/pms/spaces/{space_id}/lists",
        headers=_auth_headers(task_list_member_token),
    )
    assert space_lists_response.status_code == 200
    assert any(item["id"] == task_list["id"] for item in space_lists_response.json()["items"])

    space_folders_response = client.get(
        "/api/v1/workspaces/administrator/pms/folders",
        headers=_auth_headers(task_list_member_token),
        params={"team_id": space_id},
    )
    assert space_folders_response.status_code == 200

    space_docs_response = client.get(
        "/api/v1/workspaces/administrator/docs/hub",
        headers=_auth_headers(task_list_member_token),
        params={"space_id": space_id},
    )
    assert space_docs_response.status_code == 200


def test_media_linking_follows_parent_resource_acl(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    space_id = task_list["team_id"]
    assert space_id is not None

    issue = _create_issue(client, admin_session["token"], task_list["id"], title="Media ACL issue")

    collection = _create_space_doc(
        client,
        admin_session["token"],
        space_id,
        title="Space Collection",
    )
    page = _create_doc_page(
        client,
        admin_session["token"],
        collection["id"],
        title="Space Page",
    )

    project_member = _create_user(
        client,
        admin_session["token"],
        email="media-task-list-member@open-work-hub.local",
        full_name="Media Task List Member",
    )
    _add_task_list_member(
        client, admin_session["token"], task_list["id"], project_member["user"]["id"], "member"
    )
    project_member_token = _login(
        client,
        project_member["user"]["email"],
        project_member["temporary_password"],
    )

    issue_media = _create_unlinked_media(project_member["user"]["id"])
    issue_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(project_member_token),
        json={
            "media_ids": [issue_media["id"]],
            "resource_type": "task",
            "resource_id": issue["id"],
        },
    )
    assert issue_link_response.status_code == 204

    removed_doc_media = _create_unlinked_media(project_member["user"]["id"])
    removed_doc_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(project_member_token),
        json={
            "media_ids": [removed_doc_media["id"]],
            "resource_type": "doc",
            "resource_id": issue["id"],
        },
    )
    assert removed_doc_link_response.status_code == 400

    forbidden_space_media = _create_unlinked_media(project_member["user"]["id"])
    forbidden_space_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(project_member_token),
        json={
            "media_ids": [forbidden_space_media["id"]],
            "resource_type": "docs_native_page",
            "resource_id": page["id"],
        },
    )
    assert forbidden_space_link_response.status_code == 204

    space_member = _create_user(
        client,
        admin_session["token"],
        email="media-space-member@open-work-hub.local",
        full_name="Media Space Member",
    )
    _add_team_member(client, admin_session["token"], space_id, space_member["user"]["id"])
    space_member_token = _login(
        client,
        space_member["user"]["email"],
        space_member["temporary_password"],
    )

    page_media = _create_unlinked_media(space_member["user"]["id"])
    page_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(space_member_token),
        json={
            "media_ids": [page_media["id"]],
            "resource_type": "docs_native_page",
            "resource_id": page["id"],
        },
    )
    assert page_link_response.status_code == 204


def test_team_soft_delete_hides_space_data_and_untrashes_default_space(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    headers = _auth_headers(admin_session["token"])
    task_list = _create_task_list(client, admin_session["token"])
    space_id = task_list["team_id"]
    assert space_id is not None

    workspaces_response = client.get("/api/v1/admin/workspaces", headers=headers)
    assert workspaces_response.status_code == 200
    pms_workspace = next(
        item for item in workspaces_response.json() if item["key"] == "administrator"
    )
    assert pms_workspace["team_count"] == 1

    folder_response = client.post(
        "/api/v1/workspaces/administrator/pms/folders",
        headers=headers,
        json={"name": "Operations", "team_id": space_id},
    )
    assert folder_response.status_code == 201

    collection = _create_space_doc(client, admin_session["token"], space_id, title="Runbook")
    page = _create_doc_page(client, admin_session["token"], collection["id"], title="Overview")

    delete_response = client.delete(
        f"/api/v1/admin/teams/{space_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204

    teams_response = client.get(
        "/api/v1/admin/teams",
        headers=headers,
        params={"workspace_id": pms_workspace["id"]},
    )
    assert teams_response.status_code == 200
    assert teams_response.json() == []

    deleted_team_update_response = client.patch(
        f"/api/v1/admin/teams/{space_id}",
        headers=headers,
        json={"name": "Archived Space", "description": ""},
    )
    assert deleted_team_update_response.status_code == 404

    deleted_team_members_response = client.get(
        f"/api/v1/admin/teams/{space_id}/members",
        headers=headers,
    )
    assert deleted_team_members_response.status_code == 404

    visible_lists_response = client.get(
        "/api/v1/workspaces/administrator/pms/lists",
        headers=headers,
    )
    assert visible_lists_response.status_code == 200
    assert [
        item for item in visible_lists_response.json()["items"] if item["team_id"] == space_id
    ] == []

    deleted_space_lists_response = client.get(
        "/api/v1/workspaces/administrator/pms/lists",
        headers=headers,
        params={"team_id": space_id},
    )
    assert deleted_space_lists_response.status_code == 404

    deleted_space_folders_response = client.get(
        "/api/v1/workspaces/administrator/pms/folders",
        headers=headers,
        params={"team_id": space_id},
    )
    assert deleted_space_folders_response.status_code == 404

    deleted_space_docs_response = client.get(
        "/api/v1/workspaces/administrator/docs/hub",
        headers=headers,
        params={"space_id": space_id},
    )
    assert deleted_space_docs_response.status_code == 200
    assert [item["id"] for item in deleted_space_docs_response.json()["items"]] == [
        collection["id"]
    ]

    deleted_page_response = client.get(
        f"/api/v1/workspaces/administrator/docs/pages/{page['id']}",
        headers=headers,
    )
    assert deleted_page_response.status_code == 200

    workspaces_after_delete_response = client.get("/api/v1/admin/workspaces", headers=headers)
    assert workspaces_after_delete_response.status_code == 200
    pms_workspace_after_delete = next(
        item for item in workspaces_after_delete_response.json() if item["key"] == "administrator"
    )
    assert pms_workspace_after_delete["team_count"] == 0

    recreated_task_list_response = client.post(
        "/api/v1/workspaces/administrator/pms/lists",
        headers=headers,
        json={
            "key": "PMS2",
            "name": "Recovered List",
            "description": "List after untrash",
        },
    )
    assert recreated_task_list_response.status_code == 201
    recreated_task_list = recreated_task_list_response.json()
    assert recreated_task_list["team_id"] == space_id

    teams_after_restore_response = client.get(
        "/api/v1/admin/teams",
        headers=headers,
        params={"workspace_id": pms_workspace["id"]},
    )
    assert teams_after_restore_response.status_code == 200
    assert [item["id"] for item in teams_after_restore_response.json()] == [space_id]

    workspaces_after_restore_response = client.get("/api/v1/admin/workspaces", headers=headers)
    assert workspaces_after_restore_response.status_code == 200
    pms_workspace_after_restore = next(
        item for item in workspaces_after_restore_response.json() if item["key"] == "administrator"
    )
    assert pms_workspace_after_restore["team_count"] == 1


def _bootstrap_admin(client: TestClient) -> str:
    return _bootstrap_admin_session(client)["token"]


def test_assigned_issues_returns_only_current_users_open_issues(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin["token"], key="ASGN", name="Assigned List")

    teammate = _create_user(
        client, admin["token"], email="assigned-teammate@open-work-hub.local", full_name="Teammate"
    )
    _add_task_list_member(client, admin["token"], task_list["id"], teammate["user"]["id"], "member")

    _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Assigned to admin (due soon)",
        assignee_id=admin["user"]["id"],
        due_date="2026-04-20",
    )
    _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Assigned to admin (no due)",
        assignee_id=admin["user"]["id"],
    )
    teammate_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Assigned to teammate",
        assignee_id=teammate["user"]["id"],
    )
    unassigned_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Unassigned issue",
    )

    closed_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Closed assigned issue",
        assignee_id=admin["user"]["id"],
    )
    close_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{closed_issue['id']}",
        headers=_auth_headers(admin["token"]),
        json={"status": "done"},
    )
    assert close_response.status_code == 200

    response = client.get(
        "/api/v1/workspaces/administrator/pms/tasks/assigned",
        headers=_auth_headers(admin["token"]),
    )
    assert response.status_code == 200
    payload = response.json()
    titles = [item["title"] for item in payload["items"]]
    assert titles == [
        "Assigned to admin (due soon)",
        "Assigned to admin (no due)",
    ]
    assert teammate_issue["id"] not in {item["id"] for item in payload["items"]}
    assert unassigned_issue["id"] not in {item["id"] for item in payload["items"]}


def test_issue_list_paginates_beyond_one_hundred_tasks(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="PAGE", name="Paged List")

    created_ids = [
        _create_issue(client, token, task_list["id"], title=f"Paged task {index:03d}")["id"]
        for index in range(105)
    ]

    first_page_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        params={"page": 1, "page_size": 100},
    )
    assert first_page_response.status_code == 200
    first_page = first_page_response.json()
    assert first_page["total"] == 105
    assert len(first_page["items"]) == 100

    second_page_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        params={"page": 2, "page_size": 100},
    )
    assert second_page_response.status_code == 200
    second_page = second_page_response.json()
    assert second_page["total"] == 105
    assert [item["id"] for item in second_page["items"]] == created_ids[100:]


def test_assigned_issues_support_paged_reads(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin["token"], key="APAGE", name="Assigned Paged List")

    for index in range(55):
        _create_issue(
            client,
            admin["token"],
            task_list["id"],
            title=f"Assigned paged task {index:03d}",
            assignee_id=admin["user"]["id"],
        )

    response = client.get(
        "/api/v1/workspaces/administrator/pms/tasks/assigned",
        headers=_auth_headers(admin["token"]),
        params={"page": 2, "page_size": 50},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 55
    assert payload["page"] == 2
    assert payload["page_size"] == 50
    assert len(payload["items"]) == 5


def test_personal_pms_widget_aggregates_open_tasks_across_workspaces(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    administrator_list = _create_task_list(
        client,
        admin["token"],
        key="PWADMIN",
        name="Personal Widget Administrator",
    )
    general_list = _create_task_list(
        client,
        admin["token"],
        key="PWAI",
        name="Personal Widget General Workspace",
        workspace_slug="general",
    )
    administrator_task = _create_issue(
        client,
        admin["token"],
        administrator_list["id"],
        title="Administrator widget task",
        assignee_id=admin["user"]["id"],
    )
    general_task = _create_issue(
        client,
        admin["token"],
        general_list["id"],
        title="General Workspace widget task",
        assignee_id=admin["user"]["id"],
        workspace_slug="general",
    )

    response = client.get(
        "/api/v1/personal-widgets/pms/tasks/assigned",
        headers=_auth_headers(admin["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    tasks_by_id = {item["id"]: item for item in payload["items"]}
    assert tasks_by_id[administrator_task["id"]]["workspace"]["slug"] == "administrator"
    assert tasks_by_id[general_task["id"]]["workspace"]["slug"] == "general"
    assert {item["slug"] for item in payload["workspaces"]} >= {
        "administrator",
        "general",
    }


def test_today_overdue_tasks_return_only_current_users_due_open_tasks(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin["token"], key="DUE", name="Due List")

    teammate = _create_user(
        client,
        admin["token"],
        email="today-overdue-teammate@open-work-hub.local",
        full_name="Today Overdue Teammate",
    )
    _add_task_list_member(client, admin["token"], task_list["id"], teammate["user"]["id"], "member")

    overdue_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Admin overdue",
        assignee_id=admin["user"]["id"],
        due_date="2026-07-08",
    )
    today_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Admin today",
        assignee_id=admin["user"]["id"],
        due_date="2026-07-09",
    )
    multi_assignee_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Admin multi-assignee today",
        assignee_id=teammate["user"]["id"],
        due_date="2026-07-09",
    )
    assignee_response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{multi_assignee_issue['id']}/assignees",
        headers=_auth_headers(admin["token"]),
        json={"user_ids": [teammate["user"]["id"], admin["user"]["id"]]},
    )
    assert assignee_response.status_code == 200

    future_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Admin future",
        assignee_id=admin["user"]["id"],
        due_date="2026-07-10",
    )
    teammate_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Teammate overdue",
        assignee_id=teammate["user"]["id"],
        due_date="2026-07-08",
    )
    unassigned_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Unassigned overdue",
        due_date="2026-07-08",
    )
    archived_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Archived overdue",
        assignee_id=admin["user"]["id"],
        due_date="2026-07-08",
    )
    archive_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{archived_issue['id']}",
        headers=_auth_headers(admin["token"]),
        json={"archived": True},
    )
    assert archive_response.status_code == 200
    done_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Done overdue",
        assignee_id=admin["user"]["id"],
        due_date="2026-07-08",
    )
    close_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{done_issue['id']}",
        headers=_auth_headers(admin["token"]),
        json={"status": "done"},
    )
    assert close_response.status_code == 200

    response = client.get(
        "/api/v1/workspaces/administrator/pms/tasks/today-overdue",
        headers=_auth_headers(admin["token"]),
        params={"today": "2026-07-09", "page": 1, "page_size": 50},
    )
    assert response.status_code == 200
    payload = response.json()
    returned_ids = {item["id"] for item in payload["items"]}
    assert returned_ids == {overdue_issue["id"], today_issue["id"], multi_assignee_issue["id"]}
    assert future_issue["id"] not in returned_ids
    assert teammate_issue["id"] not in returned_ids
    assert unassigned_issue["id"] not in returned_ids
    assert archived_issue["id"] not in returned_ids
    assert done_issue["id"] not in returned_ids
    assert payload["total"] == 3


def test_assigned_issues_honors_workspace_scoped_route(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    _dev_login(client, "delivery-hub-admin")
    workspace_admin = _create_workspace_admin(
        client,
        admin_session["token"],
        email="administrator-assigned-admin@open-work-hub.local",
        full_name="Administrator Assigned Admin",
    )
    workspace_admin_token = _login(
        client,
        workspace_admin["user"]["email"],
        workspace_admin["temporary_password"],
    )

    task_list = _create_task_list(
        client,
        workspace_admin_token,
        key="ADMINASGN",
        name="Administrator Assigned Route",
    )
    _create_issue(
        client,
        workspace_admin_token,
        task_list["id"],
        title="Administrator scoped assigned issue",
        assignee_id=workspace_admin["user"]["id"],
    )

    response = client.get(
        "/api/v1/workspaces/administrator/pms/tasks/assigned",
        headers=_auth_headers(workspace_admin_token),
    )
    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == [
        "Administrator scoped assigned issue"
    ]

    denied_response = client.get(
        "/api/v1/workspaces/delivery-hub/pms/tasks/assigned",
        headers=_auth_headers(workspace_admin_token),
    )
    assert denied_response.status_code == 403


def test_task_completed_date_can_be_edited_and_cleared(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="CMPEDIT", name="Completion Edit List")
    task = _create_issue(client, token, task_list["id"], title="Manual completion date")
    assert task["completed_date"] is None

    manual_completed_date = "2026-07-07"
    update_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}",
        headers=_auth_headers(token),
        json={"completed_date": manual_completed_date},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["completed_date"] == manual_completed_date

    clear_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}",
        headers=_auth_headers(token),
        json={"completed_date": None},
    )
    assert clear_response.status_code == 200, clear_response.text
    assert clear_response.json()["completed_date"] is None


def test_task_completion_status_sets_missing_completed_date_for_custom_done_status(
    client: TestClient,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="CMPAUTO", name="Completion Auto List")
    custom_status_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/statuses",
        headers=_auth_headers(token),
        json={
            "name": "QA Done",
            "color": "#22c55e",
            "category": "done",
            "sort_order": 10,
        },
    )
    assert custom_status_response.status_code == 201, custom_status_response.text
    done_status = custom_status_response.json()["slug"]
    task = _create_issue(client, token, task_list["id"], title="Auto completion date")
    assert task["completed_date"] is None

    before_update = datetime.now(UTC).date()
    update_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}",
        headers=_auth_headers(token),
        json={"status": done_status},
    )
    after_update = datetime.now(UTC).date()
    assert update_response.status_code == 200, update_response.text
    payload = update_response.json()
    assert payload["status"] == done_status
    completed_date = date.fromisoformat(payload["completed_date"])
    assert before_update <= completed_date <= after_update


def test_bulk_completion_status_sets_missing_completed_date(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="CMPBULK", name="Completion Bulk List")
    task = _create_issue(client, token, task_list["id"], title="Bulk completion date")

    before_update = datetime.now(UTC).date()
    bulk_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/tasks/bulk",
        headers=_auth_headers(token),
        json={"task_ids": [task["id"]], "status": "done"},
    )
    after_update = datetime.now(UTC).date()
    assert bulk_response.status_code == 200, bulk_response.text
    assert bulk_response.json() == {"updated_count": 1, "deleted_count": 0}

    detail_response = client.get(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}",
        headers=_auth_headers(token),
    )
    assert detail_response.status_code == 200, detail_response.text
    completed_date = date.fromisoformat(detail_response.json()["task"]["completed_date"])
    assert before_update <= completed_date <= after_update


def _bootstrap_admin_session(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open Work Hub Admin",
            "email": "admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_task_list(
    client: TestClient,
    token: str,
    *,
    key: str = "PMS",
    name: str = "PMS List",
    workspace_slug: str = "administrator",
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/pms/lists",
        headers=_auth_headers(token),
        json={
            "key": key,
            "name": name,
            "description": "List for PMS issue tests",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_issue(
    client: TestClient,
    token: str,
    list_id: str,
    *,
    title: str,
    status: str = "todo",
    assignee_id: str | None = None,
    parent_id: str | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
    recurrence_rule: str | None = None,
    workspace_slug: str = "administrator",
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/pms/lists/{list_id}/tasks",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": "",
            "status": status,
            "priority": "medium",
            "assignee_id": assignee_id,
            "milestone_id": None,
            "parent_id": parent_id,
            "start_date": start_date,
            "due_date": due_date,
            "recurrence_rule": recurrence_rule,
            "label_ids": [],
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_user(client: TestClient, token: str, *, email: str, full_name: str) -> dict:
    response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        json={
            "email": email,
            "full_name": full_name,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    _grant_workspace_access(client, token, payload["user"]["id"], "administrator")
    return payload


def _create_workspace_admin(client: TestClient, token: str, *, email: str, full_name: str) -> dict:
    payload = _create_user(client, token, email=email, full_name=full_name)
    _grant_workspace_access(client, token, payload["user"]["id"], "administrator", role="admin")
    return payload


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"login_id": email.split("@", 1)[0].lower(), "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


def _add_task_list_member(
    client: TestClient, token: str, list_id: str, user_id: str, role: str
) -> dict:
    list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{list_id}",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200

    response = client.post(
        f"/api/v1/workspaces/administrator/pms/spaces/{list_response.json()['team_id']}/members",
        headers=_auth_headers(token),
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201
    return response.json()


def _add_team_member(client: TestClient, token: str, team_id: str, user_id: str) -> list[dict]:
    current_members_response = client.get(
        f"/api/v1/admin/teams/{team_id}/members",
        headers=_auth_headers(token),
    )
    assert current_members_response.status_code == 200
    current_member_ids = [item["id"] for item in current_members_response.json()]

    response = client.put(
        f"/api/v1/admin/teams/{team_id}/members",
        headers=_auth_headers(token),
        json={"user_ids": sorted({*current_member_ids, user_id})},
    )
    assert response.status_code == 200
    return response.json()


def _grant_workspace_access(
    client: TestClient,
    token: str,
    user_id: str,
    workspace_key: str,
    role: str = "member",
) -> None:
    workspaces_response = client.get(
        "/api/v1/admin/workspaces",
        headers=_auth_headers(token),
    )
    assert workspaces_response.status_code == 200
    workspace = next(
        (item for item in workspaces_response.json() if item["key"] == workspace_key),
        None,
    )
    if workspace is None:
        workspace = next(iter(workspaces_response.json()), None)
    assert workspace is not None

    bindings_response = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
    )
    assert bindings_response.status_code == 200
    bindings = bindings_response.json()

    user_bindings = [
        {"subject_id": item["subject_id"], "role": item["role"]}
        for item in bindings
        if item["subject_type"] == "user"
    ]
    user_bindings = [item for item in user_bindings if item["subject_id"] != user_id] + [
        {"subject_id": user_id, "role": role}
    ]

    update_response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
        json={"users": user_bindings},
    )
    assert update_response.status_code == 200


def _create_unlinked_media(uploaded_by_id: str) -> dict[str, str]:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.media.models import MediaFile
    from open_work_hub_api.domains.auth.security import new_id

    media_id = new_id()
    db = get_session_factory()()
    try:
        db.add(
            MediaFile(
                id=media_id,
                storage_key=f"media/{uploaded_by_id}/{media_id}/fixture.png",
                filename="fixture.png",
                content_type="image/png",
                size_bytes=128,
                uploaded_by_id=uploaded_by_id,
            )
        )
        db.commit()
    finally:
        db.close()

    return {"id": media_id}


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
