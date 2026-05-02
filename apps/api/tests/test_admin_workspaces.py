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


def test_create_workspace_includes_creator_as_admin_and_count_fields(
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

    bindings = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
    ).json()
    user_bindings = [b for b in bindings if b["subject_type"] == "user"]
    assert len(user_bindings) == 1
    assert user_bindings[0]["subject_id"] == admin["user"]["id"]
    assert user_bindings[0]["role"] == "admin"


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
    assert duplicate.json()["code"] == "admin.user_already_workspace_member"

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
    assert missing_remove.json()["code"] == "admin.workspace_member_not_found"


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
    assert response.json()["code"] == "auth.user_not_found"


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
    assert blocked.json()["code"] == "admin.workspace_archive_before_delete"


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
    assert blocked.json()["code"] == "admin.workspace_contains_content"
    assert blocked.json()["params"]["space_count"] >= 1


def test_paginated_members_endpoint_filter_search_and_role_counts(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Big Place")

    # Create 6 users with deterministic names so we can sort/filter
    user_ids: list[str] = []
    for i in range(6):
        u = _create_user(
            client,
            token,
            email=f"user{i}@aidoo.local",
            full_name=f"User {i}",
        )
        user_ids.append(u["id"])

    roles_to_assign = ["admin", "admin", "member", "member", "member", "viewer"]
    for user_id, role in zip(user_ids, roles_to_assign):
        resp = client.post(
            f"/api/v1/admin/workspaces/{workspace['id']}/members",
            headers=_auth_headers(token),
            json={"subject_id": user_id, "subject_type": "user", "role": role},
        )
        assert resp.status_code == 201, resp.text

    page1 = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/members?page=1&page_size=3",
        headers=_auth_headers(token),
    ).json()
    assert page1["total"] == 7  # 6 added + creator admin
    assert len(page1["items"]) == 3
    assert page1["role_counts"] == {"admin": 3, "member": 4}
    assert page1["user_count"] == 7
    assert page1["group_count"] == 0
    assert page1["pending_count"] == 0

    page2 = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/members?page=2&page_size=3",
        headers=_auth_headers(token),
    ).json()
    assert page2["page"] == 2
    assert len(page2["items"]) == 3

    role_filter = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/members?role=admin",
        headers=_auth_headers(token),
    ).json()
    assert role_filter["total"] == 3
    assert all(item["role"] == "admin" for item in role_filter["items"])

    search_filter = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/members?q=user%202",
        headers=_auth_headers(token),
    ).json()
    assert search_filter["total"] == 1
    assert search_filter["items"][0]["subject_secondary"] == "user2@aidoo.local"


def test_bulk_member_endpoint_partial_failure(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Bulk Lab")

    user_a = _create_user(client, token, email="alice@aidoo.local", full_name="Alice")
    user_b = _create_user(client, token, email="bob@aidoo.local", full_name="Bob")

    response = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/bulk",
        headers=_auth_headers(token),
        json={
            "action": "add",
            "subjects": [
                {"subject_type": "user", "subject_id": user_a["id"], "role": "member"},
                {"subject_type": "user", "subject_id": user_b["id"], "role": "member"},
                {
                    "subject_type": "user",
                    "subject_id": "00000000-0000-0000-0000-000000000000",
                    "role": "member",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["succeeded"] == 2
    assert len(payload["failed"]) == 1
    assert payload["failed"][0]["code"] == "auth.user_not_found"

    listing = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(token),
    ).json()
    assert listing["total"] == 3  # creator + 2 added

    bulk_remove = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/bulk",
        headers=_auth_headers(token),
        json={
            "action": "remove",
            "subjects": [
                {"subject_type": "user", "subject_id": user_a["id"]},
                {"subject_type": "user", "subject_id": user_b["id"]},
            ],
        },
    )
    assert bulk_remove.status_code == 200
    assert bulk_remove.json()["succeeded"] == 2


def test_other_admin_can_demote_and_remove_admin(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    admin_user_id = admin["user"]["id"]
    workspace = _create_workspace(client, token, name="Admin Handoff")

    # Create another admin so we can verify workspace admin handoff without
    # relying on the removed workspace-owner concept.
    second_payload = _create_user_with_password(
        client,
        token,
        email="second@aidoo.local",
        full_name="Second Admin",
        password="Aidoo!second12",
    )
    second_id = second_payload["user"]["id"]

    add_resp = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(token),
        json={"subject_id": second_id, "subject_type": "user", "role": "admin"},
    )
    assert add_resp.status_code == 201

    # Login as the second admin and try to remove the only owner.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "second@aidoo.local", "password": "Aidoo!second12"},
    )
    assert login.status_code == 200, login.text
    second_token = login.json()["token"]

    demote_admin = client.patch(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{admin_user_id}",
        headers=_auth_headers(second_token),
        json={"role": "member"},
    )
    assert demote_admin.status_code == 200, demote_admin.text
    assert demote_admin.json()["role"] == "member"

    remove_admin = client.delete(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{admin_user_id}",
        headers=_auth_headers(second_token),
    )
    assert remove_admin.status_code == 204, remove_admin.text


def test_self_role_change_and_self_remove_blocked(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    admin_user_id = admin["user"]["id"]
    workspace = _create_workspace(client, token, name="Self Service")

    self_demote = client.patch(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{admin_user_id}",
        headers=_auth_headers(token),
        json={"role": "member"},
    )
    # Self role change is blocked even without the old workspace-owner model.
    assert self_demote.status_code == 409
    assert self_demote.json()["code"] == "admin.self_role_change_denied"

    self_remove = client.delete(
        f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{admin_user_id}",
        headers=_auth_headers(token),
    )
    assert self_remove.status_code == 409
    assert self_remove.json()["code"] == "admin.self_workspace_remove_denied"


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
