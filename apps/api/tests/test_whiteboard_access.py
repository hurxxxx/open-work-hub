from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import CompanyAppControl



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

    recipient_patch = client.patch(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}",
        headers=_auth_headers(recipient["token"]),
        json={"scene": {"elements": [{"id": "user-read-blocked"}], "appState": {}, "files": {}}},
    )
    assert recipient_patch.status_code == 403
    assert recipient_patch.json()["code"] == "whiteboard.edit_access_required"

    read_link_response = client.put(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}/sharing/link",
        headers=_auth_headers(owner["token"]),
        json={"access_level": "read"},
    )
    assert read_link_response.status_code == 200, read_link_response.text
    read_share_token = read_link_response.json()["link_share"]["token"]
    assert read_link_response.json()["link_share"]["share_path"] == (
        f"/apps/whiteboard/shared/{read_share_token}"
    )

    read_link_patch = client.patch(
        f"/api/v1/whiteboard/shared-links/{read_share_token}/item",
        headers=_auth_headers(recipient["token"]),
        json={"scene": {"elements": [{"id": "link-read-blocked"}], "appState": {}, "files": {}}},
    )
    assert read_link_patch.status_code == 403
    assert read_link_patch.json()["code"] == "whiteboard.edit_access_required"

    link_response = client.put(
        f"/api/v1/workspaces/delivery-hub/whiteboard/items/{whiteboard['id']}/sharing/link",
        headers=_auth_headers(owner["token"]),
        json={"access_level": "edit", "regenerate_token": True},
    )
    assert link_response.status_code == 200, link_response.text
    share_token = link_response.json()["link_share"]["token"]
    assert share_token != read_share_token

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

    with get_session_factory()() as db:
        control = db.get(CompanyAppControl, "whiteboard")
        assert control is not None
        control.enabled = False
        db.add(control)
        db.commit()

    disabled_response = client.get(
        f"/api/v1/whiteboard/shared-links/{share_token}",
        headers=_auth_headers(recipient["token"]),
    )
    assert disabled_response.status_code == 403
    assert disabled_response.json()["code"] == "workspace.app_disabled"


def _create_space_whiteboard(client: TestClient, token: str, space_id: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/delivery-hub/whiteboard/items",
        headers=_auth_headers(token),
        json={
            "title": "ACL Board",
            "source_app": "pms",
            "source_kind": "manual",
            "primary_target": {
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
    return dev_login(client, account_key)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
