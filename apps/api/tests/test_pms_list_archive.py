from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.auth.models import Workspace
from ai_do_api.domains.pms.models import TaskUserAccess
from ai_do_api.domains.pms.search_projection import (
    load_pms_task_search_document,
    load_workspace_pms_task_search_documents,
)
from ai_do_api.domains.rag.pms_projection import load_task_projection
from test_pms_issues import (
    _add_task_list_member,
    _auth_headers,
    _bootstrap_admin_session,
    _create_issue,
    _create_task_list,
    _create_user,
    _grant_workspace_access,
    _login,
)


BASE_PATH = "/api/v1/workspaces/administrator/pms"


def _update_list(
    client: TestClient,
    token: str,
    list_id: str,
    payload: dict[str, object],
    *,
    workspace_slug: str = "administrator",
):
    return client.patch(
        f"/api/v1/workspaces/{workspace_slug}/pms/lists/{list_id}",
        headers=_auth_headers(token),
        json=payload,
    )


def test_list_archive_restore_filters_preserve_state_and_gate_writes(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    task_list = _create_task_list(client, token, key="ARCH", name="Archive contract")

    folder_response = client.post(
        f"{BASE_PATH}/folders",
        headers=_auth_headers(token),
        json={"name": "Archive source folder", "team_id": task_list["team_id"]},
    )
    assert folder_response.status_code == 201, folder_response.text
    folder = folder_response.json()

    configured_response = _update_list(
        client,
        token,
        task_list["id"],
        {"folder_id": folder["id"], "sort_order": 37, "status": "on_hold"},
    )
    assert configured_response.status_code == 200, configured_response.text
    task = _create_issue(
        client,
        token,
        task_list["id"],
        title="Preserved archived task",
        assignee_id=admin["user"]["id"],
        due_date="2026-07-17",
    )
    linked_doc_response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(token),
        json={"title": "Preserved archived task doc"},
    )
    assert linked_doc_response.status_code == 201, linked_doc_response.text
    linked_doc = linked_doc_response.json()
    link_doc_response = client.post(
        f"{BASE_PATH}/tasks/{task['id']}/docs",
        headers=_auth_headers(token),
        json={"doc_id": linked_doc["id"]},
    )
    assert link_doc_response.status_code == 201, link_doc_response.text

    active_delete_response = client.delete(
        f"{BASE_PATH}/lists/{task_list['id']}",
        headers=_auth_headers(token),
    )
    assert active_delete_response.status_code == 409
    assert active_delete_response.json()["code"] == "pms.task_list_archive_before_delete"

    for _ in range(2):
        archive_response = _update_list(client, token, task_list["id"], {"archived": True})
        assert archive_response.status_code == 200, archive_response.text
        assert archive_response.json()["archived"] is True

    active_lists_response = client.get(
        f"{BASE_PATH}/lists",
        headers=_auth_headers(token),
        params={"archived": "false", "page_size": 100},
    )
    assert active_lists_response.status_code == 200
    assert task_list["id"] not in {item["id"] for item in active_lists_response.json()["items"]}

    archived_lists_response = client.get(
        f"{BASE_PATH}/lists",
        headers=_auth_headers(token),
        params={"archived": "true", "page_size": 100},
    )
    assert archived_lists_response.status_code == 200
    assert [
        item["id"]
        for item in archived_lists_response.json()["items"]
        if item["id"] == task_list["id"]
    ] == [task_list["id"]]

    archived_detail_response = client.get(
        f"{BASE_PATH}/lists/{task_list['id']}",
        headers=_auth_headers(token),
    )
    assert archived_detail_response.status_code == 200
    archived_detail = archived_detail_response.json()
    assert archived_detail["folder_id"] == folder["id"]
    assert archived_detail["sort_order"] == 37
    assert archived_detail["status"] == "on_hold"

    archived_tasks_response = client.get(
        f"{BASE_PATH}/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
    )
    assert archived_tasks_response.status_code == 200
    assert task["id"] in {item["id"] for item in archived_tasks_response.json()["items"]}

    create_response = client.post(
        f"{BASE_PATH}/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        json={"title": "Blocked create"},
    )
    update_response = client.patch(
        f"{BASE_PATH}/tasks/{task['id']}",
        headers=_auth_headers(token),
        json={"title": "Blocked update"},
    )
    delete_task_response = client.delete(
        f"{BASE_PATH}/tasks/{task['id']}",
        headers=_auth_headers(token),
    )
    for response in (create_response, update_response, delete_task_response):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "pms.task_list_archived_read_only"

    new_doc_response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(token),
        json={"title": "Blocked archived task doc"},
    )
    assert new_doc_response.status_code == 201, new_doc_response.text
    docs_side_link_response = client.post(
        f"/api/v1/workspaces/administrator/docs/items/{new_doc_response.json()['id']}/pms-tasks",
        headers=_auth_headers(token),
        json={"task_id": task["id"]},
    )
    docs_side_unlink_response = client.delete(
        f"/api/v1/workspaces/administrator/docs/items/{linked_doc['id']}/pms-tasks/{task['id']}",
        headers=_auth_headers(token),
    )
    for response in (docs_side_link_response, docs_side_unlink_response):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "pms.task_list_archived_read_only"

    owner_write_responses = (
        _update_list(
            client,
            token,
            task_list["id"],
            {"name": "Blocked archived rename"},
        ),
        client.post(
            f"{BASE_PATH}/lists/{task_list['id']}/milestones",
            headers=_auth_headers(token),
            json={"title": "Blocked milestone"},
        ),
        client.post(
            f"{BASE_PATH}/lists/{task_list['id']}/labels",
            headers=_auth_headers(token),
            json={"name": "Blocked label"},
        ),
        client.post(
            f"{BASE_PATH}/lists/{task_list['id']}/custom-fields",
            headers=_auth_headers(token),
            json={"name": "Blocked field", "field_type": "text"},
        ),
        client.post(
            f"{BASE_PATH}/lists/{task_list['id']}/statuses",
            headers=_auth_headers(token),
            json={"name": "Blocked status"},
        ),
        client.patch(
            f"{BASE_PATH}/lists/{task_list['id']}/status-mode",
            headers=_auth_headers(token),
            json={"mode": "inherit"},
        ),
        client.patch(
            f"{BASE_PATH}/spaces/{task_list['team_id']}/lists/reorder",
            headers=_auth_headers(token),
            json={
                "items": [
                    {
                        "id": task_list["id"],
                        "folder_id": folder["id"],
                        "sort_order": 99,
                    }
                ]
            },
        ),
        client.delete(
            f"{BASE_PATH}/folders/{folder['id']}",
            headers=_auth_headers(token),
        ),
    )
    for response in owner_write_responses:
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "pms.task_list_archived_read_only"

    for _ in range(2):
        restore_response = _update_list(client, token, task_list["id"], {"archived": False})
        assert restore_response.status_code == 200, restore_response.text
        restored = restore_response.json()
        assert restored["archived"] is False
        assert restored["folder_id"] == folder["id"]
        assert restored["sort_order"] == 37
        assert restored["status"] == "on_hold"

    restored_task_response = client.get(
        f"{BASE_PATH}/tasks/{task['id']}",
        headers=_auth_headers(token),
    )
    assert restored_task_response.status_code == 200
    assert restored_task_response.json()["task"]["title"] == "Preserved archived task"

    assert _update_list(client, token, task_list["id"], {"archived": True}).status_code == 200
    archived_delete_response = client.delete(
        f"{BASE_PATH}/lists/{task_list['id']}",
        headers=_auth_headers(token),
    )
    assert archived_delete_response.status_code == 204, archived_delete_response.text


def test_list_archive_permissions_and_workspace_isolation(client: TestClient) -> None:
    owner = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, owner["token"], key="AROLE", name="Archive roles")
    role_sessions: dict[str, str] = {}
    for role in ("admin", "member", "viewer"):
        account = _create_user(
            client,
            owner["token"],
            email=f"archive-{role}@ai-do.local",
            full_name=f"Archive {role.title()}",
        )
        _add_task_list_member(
            client,
            owner["token"],
            task_list["id"],
            account["user"]["id"],
            role,
        )
        role_sessions[role] = _login(
            client,
            account["user"]["email"],
            account["temporary_password"],
        )

    admin_archive_response = _update_list(
        client,
        role_sessions["admin"],
        task_list["id"],
        {"archived": True},
    )
    assert admin_archive_response.status_code == 200, admin_archive_response.text

    for role in ("member", "viewer"):
        denied_response = _update_list(
            client,
            role_sessions[role],
            task_list["id"],
            {"archived": False},
        )
        assert denied_response.status_code == 403
        assert denied_response.json()["code"] == "pms.task_list_owner_admin_required"

    owner_restore_response = _update_list(
        client,
        owner["token"],
        task_list["id"],
        {"archived": False},
    )
    assert owner_restore_response.status_code == 200, owner_restore_response.text
    same_workspace_task = _create_issue(
        client,
        owner["token"],
        task_list["id"],
        title="Same-workspace grant link",
    )

    other_workspace_list = _create_task_list(
        client,
        owner["token"],
        key="ARISO",
        name="Archive isolated workspace",
        workspace_slug="ai-tft",
    )
    other_workspace_task = _create_issue(
        client,
        owner["token"],
        other_workspace_list["id"],
        title="Cross-workspace link guard",
        workspace_slug="ai-tft",
    )
    grant_reader = _create_user(
        client,
        owner["token"],
        email="archive-grant-reader@ai-do.local",
        full_name="Archive Grant Reader",
    )
    _grant_workspace_access(
        client,
        owner["token"],
        grant_reader["user"]["id"],
        "administrator",
    )
    grant_reader_token = _login(
        client,
        grant_reader["user"]["email"],
        grant_reader["temporary_password"],
    )
    with get_session_factory()() as db:
        db.add_all(
            [
                TaskUserAccess(
                    id=new_id(),
                    task_id=same_workspace_task["id"],
                    user_id=grant_reader["user"]["id"],
                    granted_by_user_id=owner["user"]["id"],
                    access_level="read",
                ),
                TaskUserAccess(
                    id=new_id(),
                    task_id=other_workspace_task["id"],
                    user_id=grant_reader["user"]["id"],
                    granted_by_user_id=owner["user"]["id"],
                    access_level="read",
                ),
            ]
        )
        db.commit()
    local_doc_response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(grant_reader_token),
        json={"title": "Administrator workspace doc"},
    )
    assert local_doc_response.status_code == 201, local_doc_response.text
    same_workspace_link_response = client.post(
        f"/api/v1/workspaces/administrator/docs/items/{local_doc_response.json()['id']}/pms-tasks",
        headers=_auth_headers(grant_reader_token),
        json={"task_id": same_workspace_task["id"]},
    )
    assert same_workspace_link_response.status_code == 201, same_workspace_link_response.text
    cross_workspace_link_response = client.post(
        f"/api/v1/workspaces/administrator/docs/items/{local_doc_response.json()['id']}/pms-tasks",
        headers=_auth_headers(grant_reader_token),
        json={"task_id": other_workspace_task["id"]},
    )
    assert cross_workspace_link_response.status_code == 403
    assert cross_workspace_link_response.json()["code"] == "pms.task_access_required"
    assert (
        _update_list(
            client,
            owner["token"],
            other_workspace_list["id"],
            {"archived": True},
            workspace_slug="ai-tft",
        ).status_code
        == 200
    )

    administrator_archive_response = client.get(
        f"{BASE_PATH}/lists",
        headers=_auth_headers(owner["token"]),
        params={"archived": "true", "page_size": 100},
    )
    assert administrator_archive_response.status_code == 200
    assert other_workspace_list["id"] not in {
        item["id"] for item in administrator_archive_response.json()["items"]
    }
    cross_workspace_detail_response = client.get(
        f"{BASE_PATH}/lists/{other_workspace_list['id']}",
        headers=_auth_headers(owner["token"]),
    )
    assert cross_workspace_detail_response.status_code == 404
    assert cross_workspace_detail_response.json()["code"] == "pms.task_list_not_found"


def test_archived_list_tasks_leave_active_projections(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    task_list = _create_task_list(client, token, key="APROJ", name="Archive projection")
    task = _create_issue(
        client,
        token,
        task_list["id"],
        title="Archived projection task",
        assignee_id=admin["user"]["id"],
        due_date="2026-07-17",
    )

    assigned_path = f"{BASE_PATH}/tasks/assigned"
    today_path = f"{BASE_PATH}/tasks/today-overdue"
    dashboard_path = f"{BASE_PATH}/dashboard/summary"
    ai_search_path = "/api/v1/workspaces/administrator/chatbot/tools/pms.search_tasks/invoke"

    assert task["id"] in {
        item["id"]
        for item in client.get(
            assigned_path, headers=_auth_headers(token), params={"page": 1}
        ).json()["items"]
    }
    assert task["id"] in {
        item["id"]
        for item in client.get(
            today_path,
            headers=_auth_headers(token),
            params={"today": date(2026, 7, 17).isoformat()},
        ).json()["items"]
    }
    ai_search_response = client.post(
        ai_search_path,
        headers=_auth_headers(token),
        json={"arguments": {"q": "Archived projection task", "limit": 10}},
    )
    assert ai_search_response.status_code == 200, ai_search_response.text
    assert task["id"] in {item["id"] for item in ai_search_response.json()["result"]["items"]}

    assert _update_list(client, token, task_list["id"], {"archived": True}).status_code == 200

    for response in (
        client.get(assigned_path, headers=_auth_headers(token), params={"page": 1}),
        client.get(
            today_path,
            headers=_auth_headers(token),
            params={"today": date(2026, 7, 17).isoformat()},
        ),
        client.get(
            "/api/v1/personal-widgets/pms/tasks/assigned",
            headers=_auth_headers(token),
        ),
    ):
        assert response.status_code == 200, response.text
        assert task["id"] not in {item["id"] for item in response.json()["items"]}

    dashboard_response = client.get(dashboard_path, headers=_auth_headers(token))
    assert dashboard_response.status_code == 200, dashboard_response.text
    assert task_list["id"] not in {item["list_id"] for item in dashboard_response.json()["lists"]}

    calendar_response = client.get(
        "/api/v1/calendar/events",
        headers=_auth_headers(token),
        params={"from": "2026-07-17", "to": "2026-07-18", "sources": "pms_due"},
    )
    assert calendar_response.status_code == 200, calendar_response.text
    assert task["id"] not in {item.get("task_id") for item in calendar_response.json()["items"]}

    archived_ai_search_response = client.post(
        ai_search_path,
        headers=_auth_headers(token),
        json={"arguments": {"q": "Archived projection task", "limit": 10}},
    )
    assert archived_ai_search_response.status_code == 200, archived_ai_search_response.text
    assert task["id"] not in {
        item["id"] for item in archived_ai_search_response.json()["result"]["items"]
    }

    ai_list_path = "/api/v1/workspaces/administrator/chatbot/tools/pms.list_task_lists/invoke"
    active_ai_lists_response = client.post(
        ai_list_path,
        headers=_auth_headers(token),
        json={"arguments": {"page_size": 100}},
    )
    assert active_ai_lists_response.status_code == 200, active_ai_lists_response.text
    assert task_list["id"] not in {
        item["id"] for item in active_ai_lists_response.json()["result"]["items"]
    }
    archived_ai_lists_response = client.post(
        ai_list_path,
        headers=_auth_headers(token),
        json={"arguments": {"archived": True, "page_size": 100}},
    )
    assert archived_ai_lists_response.status_code == 200, archived_ai_lists_response.text
    assert task_list["id"] in {
        item["id"] for item in archived_ai_lists_response.json()["result"]["items"]
    }

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "administrator"))
        assert workspace is not None
        assert load_pms_task_search_document(db, task_id=task["id"]) is None
        assert load_task_projection(db, task_id=task["id"]) is None
        assert task["id"] not in {
            item["entity_id"]
            for item in load_workspace_pms_task_search_documents(db, workspace=workspace)
        }

    archived_detail_response = client.get(
        f"{BASE_PATH}/tasks/{task['id']}", headers=_auth_headers(token)
    )
    assert archived_detail_response.status_code == 200
