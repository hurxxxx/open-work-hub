from __future__ import annotations

from fastapi.testclient import TestClient

from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data


def test_whiteboard_create_update_reload_and_archive(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    create_response = client.post(
        "/api/v1/workspaces/delivery-hub/whiteboard/items",
        headers=_auth_headers(token),
        json={
            "title": "Launch Map",
            "primary_container": {
                "app": "whiteboard",
                "type": "workspace_sidebar",
                "id": session["user"]["workspaces"][0]["id"],
            },
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["title"] == "Launch Map"
    assert created["scene"] == {"elements": [], "appState": {}, "files": {}}
    assert created["primary_container"]["app"] == "whiteboard"
    assert created["can_edit"] is True

    scene = {
        "elements": [{"id": "text-1", "type": "text", "text": "hello"}],
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }
    update_response = client.patch(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
        json={"title": "Launch Map v2", "scene": scene},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["title"] == "Launch Map v2"
    assert update_response.json()["scene"] == scene

    reload_response = client.get(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
    )
    assert reload_response.status_code == 200
    assert reload_response.json()["scene"] == scene

    view_response = client.post(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{created['id']}/view",
        headers=_auth_headers(token),
    )
    assert view_response.status_code == 204

    recent_response = client.get(
        "/api/v1/workspaces/delivery-hub/whiteboard/hub",
        headers=_auth_headers(token),
        params={"view": "recent"},
    )
    assert recent_response.status_code == 200
    assert [item["id"] for item in recent_response.json()["items"]] == [created["id"]]

    delete_response = client.delete(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
    )
    assert delete_response.status_code == 204

    normal_hub_response = client.get(
        "/api/v1/workspaces/delivery-hub/whiteboard/hub",
        headers=_auth_headers(token),
    )
    assert normal_hub_response.status_code == 200
    assert created["id"] not in {item["id"] for item in normal_hub_response.json()["items"]}

    archived_response = client.get(
        "/api/v1/workspaces/delivery-hub/whiteboard/hub",
        headers=_auth_headers(token),
        params={"view": "archived"},
    )
    assert archived_response.status_code == 200
    assert [item["id"] for item in archived_response.json()["items"]] == [created["id"]]


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
