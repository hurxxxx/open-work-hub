from fastapi.testclient import TestClient


def test_docs_native_docs_and_direct_user_share_grant_docs_access(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(client, admin["token"], email="docs-owner@aidoo.local", full_name="Docs Owner")
    owner_id = owner["user"]["id"]
    _grant_workspace_access(client, admin["token"], owner_id, "docs")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    me_response = client.get("/api/v1/auth/me", headers=_auth_headers(owner_token))
    assert me_response.status_code == 200
    me_payload = me_response.json()
    assert any(item["app"] == "docs" for item in me_payload["app_access"])
    assert all(item["app"] != "pms" for item in me_payload["app_access"])

    empty_hub_response = client.get("/api/v1/docs/hub", headers=_auth_headers(owner_token))
    assert empty_hub_response.status_code == 200
    assert empty_hub_response.json()["items"] == []

    create_doc_response = client.post(
        "/api/v1/docs/native-docs",
        headers=_auth_headers(owner_token),
        json={"title": "Private Plan"},
    )
    assert create_doc_response.status_code == 201
    native_doc = create_doc_response.json()
    assert native_doc["source_type"] == "native_doc"
    assert native_doc["can_edit"] is True
    assert native_doc["can_share"] is True
    assert native_doc["is_private"] is True

    pages_response = client.get(
        f"/api/v1/docs/items/{native_doc['id']}/pages",
        headers=_auth_headers(owner_token),
    )
    assert pages_response.status_code == 200
    page = pages_response.json()["items"][0]

    shared_user = _create_user(
        client,
        admin["token"],
        email="docs-shared@aidoo.local",
        full_name="Docs Shared User",
    )
    shared_user_id = shared_user["user"]["id"]
    shared_user_token = _login(client, shared_user["user"]["email"], shared_user["temporary_password"])

    share_response = client.put(
        f"/api/v1/docs/items/{native_doc['id']}/sharing/users/{shared_user_id}",
        headers=_auth_headers(owner_token),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200
    assert share_response.json()["users"][0]["access_level"] == "read"

    shared_me_response = client.get("/api/v1/auth/me", headers=_auth_headers(shared_user_token))
    assert shared_me_response.status_code == 200
    assert any(item["app"] == "docs" for item in shared_me_response.json()["app_access"])

    shared_hub_response = client.get("/api/v1/docs/hub", headers=_auth_headers(shared_user_token))
    assert shared_hub_response.status_code == 200
    shared_items = shared_hub_response.json()["items"]
    assert [item["id"] for item in shared_items] == [native_doc["id"]]
    assert shared_items[0]["can_edit"] is False
    assert shared_items[0]["can_share"] is False

    shared_page_update_response = client.patch(
        f"/api/v1/docs/pages/{page['id']}",
        headers=_auth_headers(shared_user_token),
        json={"content_blocks": [{"type": "paragraph", "content": "blocked"}]},
    )
    assert shared_page_update_response.status_code == 403


def test_docs_hub_reuses_pms_acl_and_blocks_resharing_of_source_docs(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    project = _create_project(client, admin["token"], key="DOCS", name="Docs Source Project")

    space_doc_response = client.post(
        f"/api/v1/pms/spaces/{project['team_id']}/docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Space Handbook"},
    )
    assert space_doc_response.status_code == 201
    space_doc = space_doc_response.json()

    create_page_response = client.post(
        f"/api/v1/pms/spaces/{project['team_id']}/docs/pages",
        headers=_auth_headers(admin["token"]),
        json={"title": "Overview", "space_doc_id": space_doc["id"], "content_blocks": []},
    )
    assert create_page_response.status_code == 201
    original_space_page = create_page_response.json()

    viewer = _create_user(client, admin["token"], email="docs-viewer@aidoo.local", full_name="Docs Viewer")
    _grant_workspace_access(client, admin["token"], viewer["user"]["id"], "docs")
    _grant_workspace_access(client, admin["token"], viewer["user"]["id"], "pms")
    _add_project_member(client, admin["token"], project["id"], viewer["user"]["id"], "viewer")
    viewer_token = _login(client, viewer["user"]["email"], viewer["temporary_password"])

    viewer_hub_response = client.get("/api/v1/docs/hub", headers=_auth_headers(viewer_token))
    assert viewer_hub_response.status_code == 200
    viewer_items = {item["title"]: item for item in viewer_hub_response.json()["items"]}
    assert viewer_items["Space Handbook"]["can_edit"] is False
    assert viewer_items["Space Handbook"]["can_manage"] is False

    viewer_pages_response = client.get(
        f"/api/v1/docs/items/{viewer_items['Space Handbook']['id']}/pages",
        headers=_auth_headers(viewer_token),
    )
    assert viewer_pages_response.status_code == 200
    viewer_page = viewer_pages_response.json()["items"][0]
    assert viewer_page["can_edit"] is False

    viewer_page_update_response = client.patch(
        f"/api/v1/docs/pages/{viewer_page['id']}",
        headers=_auth_headers(viewer_token),
        json={"content_blocks": [{"type": "paragraph", "content": "blocked"}]},
    )
    assert viewer_page_update_response.status_code == 403

    viewer_share_response = client.get(
        f"/api/v1/docs/items/{viewer_items['Space Handbook']['id']}/sharing",
        headers=_auth_headers(viewer_token),
    )
    assert viewer_share_response.status_code == 404

    member = _create_user(client, admin["token"], email="docs-member@aidoo.local", full_name="Docs Member User")
    _grant_workspace_access(client, admin["token"], member["user"]["id"], "docs")
    _grant_workspace_access(client, admin["token"], member["user"]["id"], "pms")
    _add_project_member(client, admin["token"], project["id"], member["user"]["id"], "member")
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    member_hub_response = client.get("/api/v1/docs/hub", headers=_auth_headers(member_token))
    assert member_hub_response.status_code == 200
    member_items = {item["title"]: item for item in member_hub_response.json()["items"]}
    assert member_items["Space Handbook"]["can_edit"] is True
    assert member_items["Space Handbook"]["can_manage"] is False

    member_create_page_response = client.post(
        f"/api/v1/docs/items/{member_items['Space Handbook']['id']}/pages",
        headers=_auth_headers(member_token),
        json={"title": "Member Page"},
    )
    assert member_create_page_response.status_code == 201

    member_delete_space_doc_response = client.delete(
        f"/api/v1/docs/items/{member_items['Space Handbook']['id']}",
        headers=_auth_headers(member_token),
    )
    assert member_delete_space_doc_response.status_code == 403

    original_space_page_lookup_response = client.get(
        f"/api/v1/docs/items/{member_items['Space Handbook']['id']}/pages",
        headers=_auth_headers(member_token),
    )
    assert original_space_page_lookup_response.status_code == 200
    overview_page = next(
        item for item in original_space_page_lookup_response.json()["items"]
        if item["source_page_id"] == original_space_page["id"]
    )

    update_space_page_response = client.patch(
        f"/api/v1/docs/pages/{overview_page['id']}",
        headers=_auth_headers(member_token),
        json={"content_blocks": [{"type": "paragraph", "content": "space edit"}]},
    )
    assert update_space_page_response.status_code == 200


def test_internal_shared_links_require_auth_and_honor_read_vs_edit(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(client, admin["token"], email="share-owner@aidoo.local", full_name="Share Owner")
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "docs")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    recipient = _create_user(client, admin["token"], email="share-recipient@aidoo.local", full_name="Share Recipient")
    recipient_token = _login(client, recipient["user"]["email"], recipient["temporary_password"])

    create_doc_response = client.post(
        "/api/v1/docs/native-docs",
        headers=_auth_headers(owner_token),
        json={"title": "Shared Draft"},
    )
    assert create_doc_response.status_code == 201
    doc = create_doc_response.json()

    pages_response = client.get(
        f"/api/v1/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
    )
    assert pages_response.status_code == 200
    page = pages_response.json()["items"][0]

    enable_read_link_response = client.put(
        f"/api/v1/docs/items/{doc['id']}/sharing/link",
        headers=_auth_headers(owner_token),
        json={"access_level": "read", "active": True},
    )
    assert enable_read_link_response.status_code == 200
    share_token = enable_read_link_response.json()["link_share"]["token"]

    unauthenticated_response = client.get(f"/api/v1/docs/shared-links/{share_token}")
    assert unauthenticated_response.status_code == 401

    resolve_read_link_response = client.get(
        f"/api/v1/docs/shared-links/{share_token}",
        headers=_auth_headers(recipient_token),
    )
    assert resolve_read_link_response.status_code == 200
    assert resolve_read_link_response.json()["item"]["can_edit"] is False

    read_edit_attempt_response = client.patch(
        f"/api/v1/docs/pages/{page['id']}?share_token={share_token}",
        headers=_auth_headers(recipient_token),
        json={"content_blocks": [{"type": "paragraph", "content": "blocked"}]},
    )
    assert read_edit_attempt_response.status_code == 403

    enable_edit_link_response = client.put(
        f"/api/v1/docs/items/{doc['id']}/sharing/link",
        headers=_auth_headers(owner_token),
        json={"access_level": "edit", "active": True},
    )
    assert enable_edit_link_response.status_code == 200
    updated_share_token = enable_edit_link_response.json()["link_share"]["token"]

    resolve_edit_link_response = client.get(
        f"/api/v1/docs/shared-links/{updated_share_token}",
        headers=_auth_headers(recipient_token),
    )
    assert resolve_edit_link_response.status_code == 200
    assert resolve_edit_link_response.json()["item"]["can_edit"] is True

    edit_via_link_response = client.patch(
        f"/api/v1/docs/pages/{page['id']}?share_token={updated_share_token}",
        headers=_auth_headers(recipient_token),
        json={"content_blocks": [{"type": "paragraph", "content": "allowed"}]},
    )
    assert edit_via_link_response.status_code == 200


def test_duplicate_native_doc_clones_pages_into_new_private_doc(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(client, admin["token"], email="dup-owner@aidoo.local", full_name="Dup Owner")
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "docs")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    create_doc_response = client.post(
        "/api/v1/docs/native-docs",
        headers=_auth_headers(owner_token),
        json={"title": "Original Doc"},
    )
    assert create_doc_response.status_code == 201
    original = create_doc_response.json()

    # Add a child page so we can verify hierarchy is preserved.
    pages_response = client.get(
        f"/api/v1/docs/items/{original['id']}/pages",
        headers=_auth_headers(owner_token),
    )
    root_page = pages_response.json()["items"][0]
    child_response = client.post(
        f"/api/v1/docs/items/{original['id']}/pages",
        headers=_auth_headers(owner_token),
        json={"title": "Child", "parent_id": root_page["id"]},
    )
    assert child_response.status_code == 201

    # Duplicate as the owner.
    duplicate_response = client.post(
        f"/api/v1/docs/items/{original['id']}/duplicate",
        headers=_auth_headers(owner_token),
    )
    assert duplicate_response.status_code == 201
    duplicate = duplicate_response.json()
    assert duplicate["id"] != original["id"]
    assert duplicate["title"] == "Original Doc (copy)"
    assert duplicate["can_manage"] is True
    assert duplicate["is_private"] is True

    duplicate_pages_response = client.get(
        f"/api/v1/docs/items/{duplicate['id']}/pages",
        headers=_auth_headers(owner_token),
    )
    assert duplicate_pages_response.status_code == 200
    duplicate_pages = duplicate_pages_response.json()["items"]
    assert len(duplicate_pages) == 2
    titles = sorted(page["title"] for page in duplicate_pages)
    assert titles == ["Child", "Original Doc"]
    # Hierarchy preserved: child page references a new parent id, not the original.
    new_child = next(page for page in duplicate_pages if page["title"] == "Child")
    assert new_child["parent_id"] is not None
    assert new_child["parent_id"] != root_page["id"]


def test_duplicate_doc_via_read_share_creates_private_copy_for_recipient(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(client, admin["token"], email="dup-share-owner@aidoo.local", full_name="Owner")
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "docs")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    recipient = _create_user(client, admin["token"], email="dup-share-recipient@aidoo.local", full_name="Recipient")
    _grant_workspace_access(client, admin["token"], recipient["user"]["id"], "docs")
    recipient_token = _login(client, recipient["user"]["email"], recipient["temporary_password"])

    create_doc_response = client.post(
        "/api/v1/docs/native-docs",
        headers=_auth_headers(owner_token),
        json={"title": "Shared Plan"},
    )
    original = create_doc_response.json()

    share_response = client.put(
        f"/api/v1/docs/items/{original['id']}/sharing/users/{recipient['user']['id']}",
        headers=_auth_headers(owner_token),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200

    # Recipient with read access can duplicate even though they cannot manage.
    duplicate_response = client.post(
        f"/api/v1/docs/items/{original['id']}/duplicate",
        headers=_auth_headers(recipient_token),
    )
    assert duplicate_response.status_code == 201
    duplicate = duplicate_response.json()
    assert duplicate["title"] == "Shared Plan (copy)"
    assert duplicate["can_manage"] is True  # recipient is now the owner of the copy
    assert duplicate["is_private"] is True


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
    return response.json()


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


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
    workspace = next(item for item in workspaces_response.json() if item["key"] == workspace_key)

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
    group_bindings = [
        {"subject_id": item["subject_id"], "role": item["role"]}
        for item in bindings
        if item["subject_type"] == "group"
    ]
    user_bindings = [
        item
        for item in user_bindings
        if item["subject_id"] != user_id
    ] + [{"subject_id": user_id, "role": role}]

    update_response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
        json={"users": user_bindings, "groups": group_bindings},
    )
    assert update_response.status_code == 200


def _create_project(
    client: TestClient,
    token: str,
    *,
    key: str,
    name: str,
) -> dict:
    response = client.post(
        "/api/v1/pms/projects",
        headers=_auth_headers(token),
        json={
            "key": key,
            "name": name,
            "description": f"{name} description",
        },
    )
    assert response.status_code == 201
    return response.json()


def _add_project_member(client: TestClient, token: str, project_id: str, user_id: str, role: str) -> dict:
    response = client.post(
        f"/api/v1/pms/projects/{project_id}/members",
        headers=_auth_headers(token),
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
