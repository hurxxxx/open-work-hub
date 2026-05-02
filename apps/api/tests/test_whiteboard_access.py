from __future__ import annotations

from fastapi.testclient import TestClient

from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data


def test_whiteboard_reuses_pms_space_acl(client: TestClient) -> None:
    admin = _dev_login(client, "delivery-hub-admin")
    admin_token = admin["token"]
    task_list = _create_task_list(client, admin_token, key="WBACL", name="Whiteboard ACL")
    space_id = task_list["team_id"]
    whiteboard = _create_space_whiteboard(client, admin_token, space_id)

    viewer = _dev_login(client, "delivery-hub-member")
    viewer_token = viewer["token"]
    _add_space_member(client, admin_token, space_id, viewer["user"]["id"], "viewer")

    viewer_get = client.get(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}",
        headers=_auth_headers(viewer_token),
    )
    assert viewer_get.status_code == 200, viewer_get.text
    assert viewer_get.json()["can_edit"] is False

    viewer_patch = client.patch(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}",
        headers=_auth_headers(viewer_token),
        json={"scene": {"elements": [{"id": "blocked"}], "appState": {}, "files": {}}},
    )
    assert viewer_patch.status_code == 403
    assert viewer_patch.json()["code"] == "whiteboard.edit_access_required"

    _add_space_member(client, admin_token, space_id, viewer["user"]["id"], "member")
    member_patch = client.patch(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}",
        headers=_auth_headers(viewer_token),
        json={"scene": {"elements": [{"id": "allowed"}], "appState": {}, "files": {}}},
    )
    assert member_patch.status_code == 200, member_patch.text
    assert member_patch.json()["scene"]["elements"][0]["id"] == "allowed"


def test_private_whiteboard_is_owner_only(client: TestClient) -> None:
    owner = _dev_login(client, "delivery-hub-admin")
    recipient = _dev_login(client, "delivery-hub-member")

    create_response = client.post(
        "/api/v1/workspaces/delivery-hub/whiteboard/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "Private Board"},
    )
    assert create_response.status_code == 201, create_response.text
    whiteboard = create_response.json()
    assert whiteboard["is_private"] is True

    blocked_response = client.get(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}",
        headers=_auth_headers(recipient["token"]),
    )
    assert blocked_response.status_code == 404
    assert blocked_response.json()["code"] == "whiteboard.not_found"


def test_whiteboard_user_and_link_shares_grant_access(client: TestClient) -> None:
    owner = _dev_login(client, "delivery-hub-admin")
    recipient = _dev_login(client, "delivery-hub-member")

    create_response = client.post(
        "/api/v1/workspaces/delivery-hub/whiteboard/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "Shared Board"},
    )
    assert create_response.status_code == 201, create_response.text
    whiteboard = create_response.json()

    share_response = client.put(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}/sharing/users/{recipient['user']['id']}",
        headers=_auth_headers(owner["token"]),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200, share_response.text

    recipient_get = client.get(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}",
        headers=_auth_headers(recipient["token"]),
    )
    assert recipient_get.status_code == 200, recipient_get.text
    assert recipient_get.json()["can_edit"] is False

    link_response = client.put(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}/sharing/link",
        headers=_auth_headers(owner["token"]),
        json={"access_level": "edit"},
    )
    assert link_response.status_code == 200, link_response.text
    share_token = link_response.json()["link_share"]["token"]

    resolve_response = client.get(
        f"/api/v1/whiteboard/shared-links/{share_token}",
        headers=_auth_headers(recipient["token"]),
    )
    assert resolve_response.status_code == 200, resolve_response.text
    assert resolve_response.json()["item"]["id"] == whiteboard["id"]

    shared_patch = client.patch(
        f"/api/v1/whiteboard/shared-links/{share_token}/item",
        headers=_auth_headers(recipient["token"]),
        json={"scene": {"elements": [{"id": "via-link"}], "appState": {}, "files": {}}},
    )
    assert shared_patch.status_code == 200, shared_patch.text
    assert shared_patch.json()["scene"]["elements"][0]["id"] == "via-link"


def _create_space_whiteboard(client: TestClient, token: str, space_id: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/delivery-hub/whiteboard/items",
        headers=_auth_headers(token),
        json={
            "title": "ACL Board",
            "source_app": "pms",
            "source_kind": "manual",
            "primary_container": {
                "app": "pms",
                "type": "space",
                "id": space_id,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task_list(client: TestClient, token: str, *, key: str, name: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": key, "name": name, "description": f"{name} description"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_space_member(
    client: TestClient,
    token: str,
    space_id: str,
    user_id: str,
    role: str,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/delivery-hub/pms/spaces/{space_id}/members",
        headers=_auth_headers(token),
        json={"user_id": user_id, "role": role},
    )
    if response.status_code == 409:
        response = client.patch(
            f"/api/v1/workspaces/delivery-hub/pms/spaces/{space_id}/members/{user_id}",
            headers=_auth_headers(token),
            json={"role": role},
        )
        assert response.status_code == 200, response.text
        return response.json()
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
