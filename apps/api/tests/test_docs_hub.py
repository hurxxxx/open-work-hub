from fastapi.testclient import TestClient


def _dev_login(client: TestClient, account_key: str) -> dict:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": account_key},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_docs_native_docs_and_direct_user_share_grant_docs_access(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(client, admin["token"], email="docs-owner@aidoo.local", full_name="Docs Owner")
    owner_id = owner["user"]["id"]
    _grant_workspace_access(client, admin["token"], owner_id, "docs")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    me_response = client.get("/api/v1/auth/me", headers=_auth_headers(owner_token))
    assert me_response.status_code == 200
    me_payload = me_response.json()
    assert len(me_payload["workspaces"]) == 1

    empty_hub_response = client.get("/api/v1/workspaces/hq/docs/hub", headers=_auth_headers(owner_token))
    assert empty_hub_response.status_code == 200
    assert empty_hub_response.json()["items"] == []

    create_doc_response = client.post(
        "/api/v1/workspaces/hq/docs/items",
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
        f"/api/v1/workspaces/hq/docs/items/{native_doc['id']}/pages",
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
    _grant_workspace_access(client, admin["token"], shared_user_id, "docs")
    shared_user_token = _login(client, shared_user["user"]["email"], shared_user["temporary_password"])

    share_response = client.put(
        f"/api/v1/workspaces/hq/docs/items/{native_doc['id']}/sharing/users/{shared_user_id}",
        headers=_auth_headers(owner_token),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200
    assert share_response.json()["users"][0]["access_level"] == "read"

    shared_me_response = client.get("/api/v1/auth/me", headers=_auth_headers(shared_user_token))
    assert shared_me_response.status_code == 200
    assert len(shared_me_response.json()["workspaces"]) == 1

    shared_hub_response = client.get("/api/v1/workspaces/hq/docs/hub", headers=_auth_headers(shared_user_token))
    assert shared_hub_response.status_code == 200
    shared_items = shared_hub_response.json()["items"]
    assert [item["id"] for item in shared_items] == [native_doc["id"]]
    assert shared_items[0]["can_edit"] is False
    assert shared_items[0]["can_share"] is False

    shared_page_update_response = client.patch(
        f"/api/v1/workspaces/hq/docs/pages/{page['id']}",
        headers=_auth_headers(shared_user_token),
        json={"content_blocks": [{"type": "paragraph", "content": "blocked"}]},
    )
    assert shared_page_update_response.status_code == 403


def test_docs_hub_reuses_pms_acl_and_blocks_resharing_of_source_docs(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    task_list = _create_task_list(client, admin["token"], key="DOCS", name="Docs Source List")

    space_doc = _create_space_doc(client, admin["token"], task_list["team_id"], title="Space Handbook")
    original_space_page = _create_doc_page(
        client,
        admin["token"],
        space_doc["id"],
        title="Overview",
        content_blocks=[],
    )

    viewer = _create_user(client, admin["token"], email="docs-viewer@aidoo.local", full_name="Docs Viewer")
    _grant_workspace_access(client, admin["token"], viewer["user"]["id"], "docs")
    _grant_workspace_access(client, admin["token"], viewer["user"]["id"], "pms")
    _add_task_list_member(client, admin["token"], task_list["id"], viewer["user"]["id"], "viewer")
    viewer_token = _login(client, viewer["user"]["email"], viewer["temporary_password"])

    viewer_hub_response = client.get("/api/v1/workspaces/hq/docs/hub", headers=_auth_headers(viewer_token))
    assert viewer_hub_response.status_code == 200
    viewer_items = {item["title"]: item for item in viewer_hub_response.json()["items"]}
    assert viewer_items["Space Handbook"]["source_app"] == "pms"
    assert viewer_items["Space Handbook"]["primary_container"]["app"] == "pms"
    assert viewer_items["Space Handbook"]["primary_container"]["type"] == "space"
    assert viewer_items["Space Handbook"]["primary_container"]["id"] == task_list["team_id"]
    assert viewer_items["Space Handbook"]["can_edit"] is False
    assert viewer_items["Space Handbook"]["can_manage"] is False

    viewer_pages_response = client.get(
        f"/api/v1/workspaces/hq/docs/items/{viewer_items['Space Handbook']['id']}/pages",
        headers=_auth_headers(viewer_token),
    )
    assert viewer_pages_response.status_code == 200
    viewer_page = viewer_pages_response.json()["items"][0]
    assert viewer_page["can_edit"] is False

    viewer_page_update_response = client.patch(
        f"/api/v1/workspaces/hq/docs/pages/{viewer_page['id']}",
        headers=_auth_headers(viewer_token),
        json={"content_blocks": [{"type": "paragraph", "content": "blocked"}]},
    )
    assert viewer_page_update_response.status_code == 403

    viewer_share_response = client.get(
        f"/api/v1/workspaces/hq/docs/items/{viewer_items['Space Handbook']['id']}/sharing",
        headers=_auth_headers(viewer_token),
    )
    assert viewer_share_response.status_code == 403

    member = _create_user(client, admin["token"], email="docs-user@aidoo.local", full_name="Docs User")
    _grant_workspace_access(client, admin["token"], member["user"]["id"], "docs")
    _grant_workspace_access(client, admin["token"], member["user"]["id"], "pms")
    _add_task_list_member(client, admin["token"], task_list["id"], member["user"]["id"], "member")
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    member_hub_response = client.get("/api/v1/workspaces/hq/docs/hub", headers=_auth_headers(member_token))
    assert member_hub_response.status_code == 200
    member_items = {item["title"]: item for item in member_hub_response.json()["items"]}
    assert member_items["Space Handbook"]["can_edit"] is True
    assert member_items["Space Handbook"]["can_manage"] is False

    member_create_page_response = client.post(
        f"/api/v1/workspaces/hq/docs/items/{member_items['Space Handbook']['id']}/pages",
        headers=_auth_headers(member_token),
        json={"title": "Member Page"},
    )
    assert member_create_page_response.status_code == 201

    member_delete_space_doc_response = client.delete(
        f"/api/v1/workspaces/hq/docs/items/{member_items['Space Handbook']['id']}",
        headers=_auth_headers(member_token),
    )
    assert member_delete_space_doc_response.status_code == 403

    original_space_page_lookup_response = client.get(
        f"/api/v1/workspaces/hq/docs/items/{member_items['Space Handbook']['id']}/pages",
        headers=_auth_headers(member_token),
    )
    assert original_space_page_lookup_response.status_code == 200
    overview_page = next(
        item for item in original_space_page_lookup_response.json()["items"]
        if item["source_page_id"] == original_space_page["id"]
    )

    update_space_page_response = client.patch(
        f"/api/v1/workspaces/hq/docs/pages/{overview_page['id']}",
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
        "/api/v1/workspaces/hq/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Shared Draft"},
    )
    assert create_doc_response.status_code == 201
    doc = create_doc_response.json()

    pages_response = client.get(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
    )
    assert pages_response.status_code == 200
    page = pages_response.json()["items"][0]

    enable_read_link_response = client.put(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/sharing/link",
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
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/sharing/link",
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


def test_workspace_scoped_shareable_users_stay_in_requested_docs_workspace(
    client: TestClient,
) -> None:
    _bootstrap_admin_session(client)

    hq_member = _dev_login(client, "hq-member")
    hq_member_token = hq_member["token"]

    scoped_response = client.get(
        "/api/v1/workspaces/hq/docs/shareable-users",
        headers=_auth_headers(hq_member_token),
        params={"q": "Admin"},
    )
    assert scoped_response.status_code == 200
    scoped_emails = {item["email"] for item in scoped_response.json()}
    assert "hq-admin@aidoo.local" in scoped_emails
    assert "innovation-lab-admin@aidoo.local" not in scoped_emails

    legacy_response = client.get(
        "/api/v1/workspaces/hq/docs/shareable-users",
        headers=_auth_headers(hq_member_token),
        params={"q": "Admin"},
    )
    assert legacy_response.status_code == 200
    legacy_emails = {item["email"] for item in legacy_response.json()}
    assert "hq-admin@aidoo.local" in legacy_emails
    assert "innovation-lab-admin@aidoo.local" not in legacy_emails


def test_duplicate_native_doc_clones_pages_into_new_private_doc(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(client, admin["token"], email="dup-owner@aidoo.local", full_name="Dup Owner")
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "docs")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    create_doc_response = client.post(
        "/api/v1/workspaces/hq/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Original Doc"},
    )
    assert create_doc_response.status_code == 201
    original = create_doc_response.json()

    # Add a child page so we can verify hierarchy is preserved.
    pages_response = client.get(
        f"/api/v1/workspaces/hq/docs/items/{original['id']}/pages",
        headers=_auth_headers(owner_token),
    )
    root_page = pages_response.json()["items"][0]
    child_response = client.post(
        f"/api/v1/workspaces/hq/docs/items/{original['id']}/pages",
        headers=_auth_headers(owner_token),
        json={"title": "Child", "parent_id": root_page["id"]},
    )
    assert child_response.status_code == 201

    # Duplicate as the owner.
    duplicate_response = client.post(
        f"/api/v1/workspaces/hq/docs/items/{original['id']}/duplicate",
        headers=_auth_headers(owner_token),
    )
    assert duplicate_response.status_code == 201
    duplicate = duplicate_response.json()
    assert duplicate["id"] != original["id"]
    assert duplicate["title"] == "Original Doc Copy"
    assert duplicate["can_manage"] is True
    assert duplicate["is_private"] is True

    duplicate_pages_response = client.get(
        f"/api/v1/workspaces/hq/docs/items/{duplicate['id']}/pages",
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


def test_native_doc_page_patch_reorders_and_moves_parent(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    owner = _create_user(client, admin["token"], email="reorder-owner@aidoo.local", full_name="Reorder Owner")
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "docs")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    doc = client.post(
        "/api/v1/workspaces/hq/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Reorder Plan"},
    ).json()

    # Initial doc already contains a root page; add three more siblings.
    root_pages = client.get(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
    ).json()["items"]
    assert len(root_pages) == 1

    def _create_page(title: str, parent_id: str | None = None) -> dict:
        response = client.post(
            f"/api/v1/workspaces/hq/docs/items/{doc['id']}/pages",
            headers=_auth_headers(owner_token),
            json={"title": title, "parent_id": parent_id},
        )
        assert response.status_code == 201, response.text
        return response.json()

    page_a = _create_page("Alpha")
    page_b = _create_page("Bravo")
    page_c = _create_page("Charlie")

    # Reorder: drop C before A by setting explicit sort_order gaps.
    client.patch(
        f"/api/v1/workspaces/hq/docs/pages/{page_a['id']}",
        headers=_auth_headers(owner_token),
        json={"sort_order": 1000},
    )
    client.patch(
        f"/api/v1/workspaces/hq/docs/pages/{page_b['id']}",
        headers=_auth_headers(owner_token),
        json={"sort_order": 2000},
    )
    patch_c = client.patch(
        f"/api/v1/workspaces/hq/docs/pages/{page_c['id']}",
        headers=_auth_headers(owner_token),
        json={"sort_order": 0},
    )
    assert patch_c.status_code == 200
    assert patch_c.json()["sort_order"] == 0

    listing = client.get(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
    ).json()["items"]
    siblings_order = [
        page["title"]
        for page in listing
        if page["parent_id"] is None and page["title"] in {"Alpha", "Bravo", "Charlie"}
    ]
    # API sorts by (parent_id, sort_order, created_at) — grouping by parent.
    assert siblings_order == ["Charlie", "Alpha", "Bravo"]

    # Move: nest Bravo under Alpha.
    move_b = client.patch(
        f"/api/v1/workspaces/hq/docs/pages/{page_b['id']}",
        headers=_auth_headers(owner_token),
        json={"parent_id": page_a["id"], "sort_order": 0},
    )
    assert move_b.status_code == 200
    assert move_b.json()["parent_id"] == page_a["id"]

    listing = client.get(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
    ).json()["items"]
    bravo_after = next(page for page in listing if page["id"] == page_b["id"])
    assert bravo_after["parent_id"] == page_a["id"]


def test_native_doc_page_patch_rejects_cycle(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    owner = _create_user(client, admin["token"], email="cycle-owner@aidoo.local", full_name="Cycle Owner")
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "docs")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    doc = client.post(
        "/api/v1/workspaces/hq/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Cycle Plan"},
    ).json()

    parent = client.post(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
        json={"title": "Parent"},
    ).json()
    child = client.post(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
        json={"title": "Child", "parent_id": parent["id"]},
    ).json()

    # Attempt to move Parent underneath Child — should be rejected as a cycle.
    reject = client.patch(
        f"/api/v1/workspaces/hq/docs/pages/{parent['id']}",
        headers=_auth_headers(owner_token),
        json={"parent_id": child["id"]},
    )
    assert reject.status_code == 409
    assert "cycle" in reject.json()["detail"].lower()


def test_duplicate_doc_via_read_share_creates_private_copy_for_recipient(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(client, admin["token"], email="dup-share-owner@aidoo.local", full_name="Owner")
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "docs")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    recipient = _create_user(client, admin["token"], email="dup-share-recipient@aidoo.local", full_name="Recipient")
    _grant_workspace_access(client, admin["token"], recipient["user"]["id"], "docs")
    recipient_token = _login(client, recipient["user"]["email"], recipient["temporary_password"])

    create_doc_response = client.post(
        "/api/v1/workspaces/hq/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Shared Plan"},
    )
    original = create_doc_response.json()

    share_response = client.put(
        f"/api/v1/workspaces/hq/docs/items/{original['id']}/sharing/users/{recipient['user']['id']}",
        headers=_auth_headers(owner_token),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200

    # Recipient with read access can duplicate even though they cannot manage.
    duplicate_response = client.post(
        f"/api/v1/workspaces/hq/docs/items/{original['id']}/duplicate",
        headers=_auth_headers(recipient_token),
    )
    assert duplicate_response.status_code == 201
    duplicate = duplicate_response.json()
    assert duplicate["title"] == "Shared Plan Copy"
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
    workspace = next(
        (item for item in workspaces_response.json() if item["key"] == workspace_key),
        None,
    )
    if workspace is None:
        workspace = next(iter(workspaces_response.json()), None)
    assert workspace is not None

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


def _create_task_list(
    client: TestClient,
    token: str,
    *,
    key: str,
    name: str,
) -> dict:
    response = client.post(
        "/api/v1/workspaces/hq/pms/lists",
        headers=_auth_headers(token),
        json={
            "key": key,
            "name": name,
            "description": f"{name} description",
        },
    )
    assert response.status_code == 201
    return response.json()


def _add_task_list_member(client: TestClient, token: str, list_id: str, user_id: str, role: str) -> dict:
    list_response = client.get(
        f"/api/v1/workspaces/hq/pms/lists/{list_id}",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200

    response = client.post(
        f"/api/v1/workspaces/hq/pms/spaces/{list_response.json()['team_id']}/members",
        headers=_auth_headers(token),
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201
    return response.json()


def _create_space_doc(client: TestClient, token: str, space_id: str, *, title: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/hq/docs/items",
        headers=_auth_headers(token),
        json={
            "title": title,
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


def _list_space_docs(client: TestClient, token: str, space_id: str) -> list[dict]:
    response = client.get(
        "/api/v1/workspaces/hq/docs/hub",
        headers=_auth_headers(token),
        params={
            "view": "all",
            "container_app": "pms",
            "container_type": "space",
            "container_id": space_id,
            "sort_by": "container_sort_order",
            "sort_dir": "asc",
            "page_size": 200,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _update_space_doc_sort_order(client: TestClient, token: str, doc_id: str, *, space_id: str, sort_order: int) -> dict:
    response = client.put(
        f"/api/v1/workspaces/hq/docs/items/{doc_id}/container",
        headers=_auth_headers(token),
        json={
            "app": "pms",
            "type": "space",
            "id": space_id,
            "sort_order": sort_order,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_doc_page(
    client: TestClient,
    token: str,
    doc_id: str,
    *,
    title: str,
    parent_id: str | None = None,
    content_blocks: list[dict] | None = None,
    sort_order: int | None = None,
) -> dict:
    payload: dict[str, object] = {"title": title}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    if content_blocks is not None:
        payload["content_blocks"] = content_blocks
    if sort_order is not None:
        payload["sort_order"] = sort_order
    response = client.post(
        f"/api/v1/workspaces/hq/docs/items/{doc_id}/pages",
        headers=_auth_headers(token),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _list_doc_pages(client: TestClient, token: str, doc_id: str) -> list[dict]:
    response = client.get(
        f"/api/v1/workspaces/hq/docs/items/{doc_id}/pages",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
