from fastapi.testclient import TestClient
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.pms.models import ChecklistItem, TaskActivityLog
from test_pms_issues import _auth_headers, _bootstrap_admin, _create_issue, _create_task_list


def test_checklist_completed_toggle_records_activity_action(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="WICL1", name="Work Item Checklist")
    task = _create_issue(client, token, task_list["id"], title="Checklist activity")

    create_response = client.post(
        f"/api/v1/pms/tasks/{task['id']}/checklist",
        headers=_auth_headers(token),
        json={"text": "Confirm toggle action", "sort_order": 0},
    )
    assert create_response.status_code == 201, create_response.text
    item = create_response.json()

    checked_response = client.patch(
        f"/api/v1/pms/checklist/{item['id']}",
        headers=_auth_headers(token),
        json={"completed": True},
    )
    assert checked_response.status_code == 200, checked_response.text
    assert checked_response.json()["completed"] is True

    unchecked_response = client.patch(
        f"/api/v1/pms/checklist/{item['id']}",
        headers=_auth_headers(token),
        json={"completed": False},
    )
    assert unchecked_response.status_code == 200, unchecked_response.text
    assert unchecked_response.json()["completed"] is False

    with get_session_factory()() as db:
        actions = list(
            db.scalars(
                select(TaskActivityLog.action)
                .where(TaskActivityLog.task_id == task["id"])
                .order_by(TaskActivityLog.created_at)
            )
        )

    assert "checklist_checked" in actions
    assert "checklist_unchecked" in actions


def test_reorder_checklist_ignores_unknown_ids_and_preserves_omitted_sort_order(
    client: TestClient,
) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token, key="WICL2", name="Work Item Reorder")
    task = _create_issue(client, token, task_list["id"], title="Checklist reorder")

    items = []
    for text, sort_order in (
        ("First", 10),
        ("Second", 20),
        ("Third", 30),
    ):
        response = client.post(
            f"/api/v1/pms/tasks/{task['id']}/checklist",
            headers=_auth_headers(token),
            json={"text": text, "sort_order": sort_order},
        )
        assert response.status_code == 201, response.text
        items.append(response.json())

    reorder_response = client.patch(
        f"/api/v1/pms/tasks/{task['id']}/checklist/reorder",
        headers=_auth_headers(token),
        json={"item_ids": [items[2]["id"], "missing-checklist-item", items[0]["id"]]},
    )
    assert reorder_response.status_code == 204, reorder_response.text

    with get_session_factory()() as db:
        persisted = {
            item.id: item.sort_order
            for item in db.scalars(select(ChecklistItem).where(ChecklistItem.task_id == task["id"]))
        }

    assert persisted[items[2]["id"]] == 0
    assert persisted[items[0]["id"]] == 2
    assert persisted[items[1]["id"]] == 20
