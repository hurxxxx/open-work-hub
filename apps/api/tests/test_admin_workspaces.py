from __future__ import annotations

from fastapi.testclient import TestClient


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_admin_session(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_user(client: TestClient, admin_token: str, *, email: str, full_name: str) -> dict:
    response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(admin_token),
        json={"email": email, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def _create_user_with_password(
    client: TestClient,
    admin_token: str,
    *,
    email: str,
    full_name: str,
    password: str,
) -> dict:
    response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(admin_token),
        json={"email": email, "full_name": full_name, "temporary_password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_workspace(
    client: TestClient,
    admin_token: str,
    *,
    name: str,
    description: str = "",
) -> dict:
    response = client.post(
        "/api/v1/admin/workspaces",
        headers=_auth_headers(admin_token),
        json={"name": name, "description": description},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_workspace_includes_creator_as_owner_and_count_fields(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Demo Workspace")

    assert workspace["member_count"] == 1
    assert workspace["meeting_count"] == 0
    assert workspace["doc_count"] == 0
    assert workspace["created_at"] is not None
    assert workspace["updated_at"] is not None
    assert "ai" in workspace["enabled_apps"]

    bindings = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
    ).json()
    user_bindings = [b for b in bindings if b["subject_type"] == "user"]
    assert len(user_bindings) == 1
    assert user_bindings[0]["subject_id"] == admin["user"]["id"]
    assert user_bindings[0]["role"] == "owner"


def test_add_remove_member_endpoints(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="People Hub")
    other_user = _create_user(client, token, email="alice@aidoo.local", full_name="Alice")

    add_response = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(token),
        json={"subject_id": other_user["id"], "subject_type": "user", "role": "member"},
    )
    assert add_response.status_code == 201, add_response.text
    item = add_response.json()
    assert item["subject_type"] == "user"
    assert item["subject_id"] == other_user["id"]
    assert item["role"] == "member"

    duplicate = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(token),
        json={"subject_id": other_user["id"], "subject_type": "user", "role": "member"},
    )
    assert duplicate.status_code == 409

    role_response = client.patch(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{other_user['id']}",
        headers=_auth_headers(token),
        json={"role": "admin"},
    )
    assert role_response.status_code == 200
    assert role_response.json()["role"] == "admin"

    invalid_role = client.patch(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{other_user['id']}",
        headers=_auth_headers(token),
        json={"role": "supreme-leader"},
    )
    assert invalid_role.status_code == 422

    remove_response = client.delete(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{other_user['id']}",
        headers=_auth_headers(token),
    )
    assert remove_response.status_code == 204

    missing_remove = client.delete(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{other_user['id']}",
        headers=_auth_headers(token),
    )
    assert missing_remove.status_code == 404


def test_add_member_rejects_unknown_user(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Ghosts")
    response = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(token),
        json={
            "subject_id": "00000000-0000-0000-0000-000000000000",
            "subject_type": "user",
            "role": "member",
        },
    )
    assert response.status_code == 404


def test_member_endpoints_require_workspace_admin(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace = _create_workspace(client, admin_token, name="Closed Doors")

    intruder_payload = _create_user_with_password(
        client,
        admin_token,
        email="intruder@aidoo.local",
        full_name="Intruder",
        password="Aidoo!intruder1",
    )
    intruder = intruder_payload["user"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "intruder@aidoo.local", "password": "Aidoo!intruder1"},
    )
    assert login.status_code == 200, login.text
    intruder_token = login.json()["token"]

    response = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(intruder_token),
        json={"subject_id": intruder["id"], "subject_type": "user", "role": "member"},
    )
    assert response.status_code in {403, 404}


def test_delete_workspace_requires_archive_first(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Active Place")

    blocked = client.delete(
        f"/api/v1/admin/workspaces/{workspace['id']}",
        headers=_auth_headers(token),
    )
    assert blocked.status_code == 409


def test_delete_workspace_blocked_when_team_present(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Team Holder")
    # workspace was created with a default Team Space, so team_count >= 1

    archive = client.patch(
        f"/api/v1/admin/workspaces/{workspace['id']}",
        headers=_auth_headers(token),
        json={
            "name": workspace["name"],
            "description": workspace["description"],
            "active": False,
        },
    )
    assert archive.status_code == 200

    blocked = client.delete(
        f"/api/v1/admin/workspaces/{workspace['id']}",
        headers=_auth_headers(token),
    )
    assert blocked.status_code == 409
    assert "space" in blocked.json()["detail"]


def test_list_workspaces_includes_archived_with_query_param(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="To Be Archived")

    archive = client.patch(
        f"/api/v1/admin/workspaces/{workspace['id']}",
        headers=_auth_headers(token),
        json={
            "name": workspace["name"],
            "description": workspace["description"],
            "active": False,
        },
    )
    assert archive.status_code == 200

    active_only = client.get(
        "/api/v1/admin/workspaces",
        headers=_auth_headers(token),
    )
    assert active_only.status_code == 200
    assert workspace["id"] not in {w["id"] for w in active_only.json()}

    with_archived = client.get(
        "/api/v1/admin/workspaces?include_archived=true",
        headers=_auth_headers(token),
    )
    assert with_archived.status_code == 200
    assert workspace["id"] in {w["id"] for w in with_archived.json()}
