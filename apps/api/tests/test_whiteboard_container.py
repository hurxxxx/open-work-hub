from __future__ import annotations

from fastapi.testclient import TestClient

from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data


def test_whiteboard_pms_space_container_link_filters_and_sort_order(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    task_list = _create_task_list(client, token, key="WBS", name="Whiteboard Space")
    space_id = task_list["team_id"]

    first = _create_space_whiteboard(client, token, space_id, title="Second", sort_order=20)
    second = _create_space_whiteboard(client, token, space_id, title="First", sort_order=10)

    list_response = client.get(
        "/api/v1/workspaces/delivery-hub/whiteboard/hub",
        headers=_auth_headers(token),
        params={
            "container_app": "pms",
            "container_type": "space",
            "container_id": space_id,
            "sort_by": "container_sort_order",
            "sort_dir": "asc",
        },
    )
    assert list_response.status_code == 200, list_response.text
    assert [item["id"] for item in list_response.json()["items"]] == [second["id"], first["id"]]

    update_response = client.put(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{first['id']}/container",
        headers=_auth_headers(token),
        json={
            "app": "pms",
            "type": "space",
            "id": space_id,
            "sort_order": 0,
        },
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["primary_container"]["sort_order"] == 0

    unlink_response = client.delete(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{first['id']}/container",
        headers=_auth_headers(token),
    )
    assert unlink_response.status_code == 200, unlink_response.text
    assert unlink_response.json()["primary_container"] is None


def _create_space_whiteboard(
    client: TestClient,
    token: str,
    space_id: str,
    *,
    title: str,
    sort_order: int,
) -> dict:
    response = client.post(
        "/api/v1/workspaces/delivery-hub/whiteboard/items",
        headers=_auth_headers(token),
        json={
            "title": title,
            "source_app": "pms",
            "source_kind": "manual",
            "primary_container": {
                "app": "pms",
                "type": "space",
                "id": space_id,
                "sort_order": sort_order,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task_list(client: TestClient, token: str, *, key: str, name: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={
            "key": key,
            "name": name,
            "description": f"{name} description",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
