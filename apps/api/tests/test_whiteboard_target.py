from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from dev_accounts import dev_login


def test_whiteboard_pms_space_target_link_filters_and_sort_order(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    task_list = _create_task_list(client, token, key="WBS", name="Whiteboard Space")
    space_id = task_list["team_id"]

    first = _create_space_whiteboard(client, token, space_id, title="Second", sort_order=20)
    second = _create_space_whiteboard(client, token, space_id, title="First", sort_order=10)
    assert first["source_deeplink"] == f"/apps/pms/spaces/{space_id}/whiteboards/{first['id']}"

    list_response = client.get(
        "/api/v1/whiteboard/hub",
        headers=_auth_headers(token),
        params={
            "space_id": space_id,
            "sort_by": "target_sort_order",
            "sort_dir": "asc",
        },
    )
    assert list_response.status_code == 200, list_response.text
    assert [item["id"] for item in list_response.json()["items"]] == [second["id"], first["id"]]

    update_response = client.put(
        f"/api/v1/whiteboard/items/{first['id']}/target",
        headers=_auth_headers(token),
        json={
            "app": "pms",
            "type": "space",
            "id": space_id,
            "sort_order": 0,
        },
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["primary_target"]["sort_order"] == 0

    unlink_response = client.delete(
        f"/api/v1/whiteboard/items/{first['id']}/target",
        headers=_auth_headers(token),
    )
    assert unlink_response.status_code == 200, unlink_response.text
    assert unlink_response.json()["primary_target"] is None


def test_whiteboard_context_slots_are_singleton_for_pms_task_lists_and_meetings(
    client: TestClient,
) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    task_list = _create_task_list(client, token, key="WBSLOT", name="Whiteboard Slot")

    first_list_board = _create_task_list_slot(client, token, task_list["id"], "List Board 1")
    second_list_board = _create_task_list_slot(client, token, task_list["id"], "List Board 2")
    assert first_list_board["id"] != second_list_board["id"]

    list_slot_response = client.get(
        "/api/v1/whiteboard/contexts/slot",
        headers=_auth_headers(token),
        params={"app": "pms", "type": "task_list", "id": task_list["id"]},
    )
    assert list_slot_response.status_code == 200, list_slot_response.text
    assert list_slot_response.json()["item"]["id"] == second_list_board["id"]

    first_reload = client.get(
        f"/api/v1/whiteboard/items/{first_list_board['id']}",
        headers=_auth_headers(token),
    )
    assert first_reload.status_code == 200, first_reload.text
    assert all(target["type"] != "task_list" for target in first_reload.json()["targets"])

    meeting = _create_meeting(client, token, title="Whiteboard Meeting")
    meeting_board = _create_meeting_slot(client, token, meeting["id"], "Meeting Board")

    meeting_detail_response = client.get(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(token),
    )
    assert meeting_detail_response.status_code == 200, meeting_detail_response.text
    assert meeting_detail_response.json()["whiteboard_link"]["whiteboard_id"] == meeting_board["id"]


def _create_space_whiteboard(
    client: TestClient,
    token: str,
    space_id: str,
    *,
    title: str,
    sort_order: int,
) -> dict:
    response = client.post(
        "/api/v1/whiteboard/items",
        headers=_auth_headers(token),
        json={
            "title": title,
            "source_app": "pms",
            "source_kind": "manual",
            "primary_target": {
                "company_admin_read_acknowledged": True,
                "app": "pms",
                "type": "space",
                "id": space_id,
                "sort_order": sort_order,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task_list_slot(
    client: TestClient,
    token: str,
    task_list_id: str,
    title: str,
) -> dict:
    response = client.post(
        "/api/v1/whiteboard/contexts/slot",
        headers=_auth_headers(token),
        json={
            "app": "pms",
            "type": "task_list",
            "id": task_list_id,
            "title": title,
            "company_admin_read_acknowledged": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_meeting_slot(
    client: TestClient,
    token: str,
    meeting_id: str,
    title: str,
) -> dict:
    response = client.post(
        "/api/v1/whiteboard/contexts/slot",
        headers=_auth_headers(token),
        json={
            "app": "meeting",
            "type": "meeting",
            "id": meeting_id,
            "title": title,
            "company_admin_read_acknowledged": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_meeting(client: TestClient, token: str, *, title: str) -> dict:
    start = datetime(2031, 1, 1, 10, 0, 0)
    response = client.post(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": title,
            "agenda": "",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "attendees": [],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task_list(client: TestClient, token: str, *, key: str, name: str) -> dict:
    from test_meeting import _create_task_list as create_pms_list

    return create_pms_list(client, token, key=key, name=name)


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
