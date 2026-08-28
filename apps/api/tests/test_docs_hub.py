from fastapi.testclient import TestClient

from dev_accounts import dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import CompanyAppControl


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def test_docs_native_docs_and_direct_user_share_grant_docs_access(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(
        client, admin["token"], email="docs-owner@open-work-hub.local", full_name="Docs Owner"
    )
    owner_id = owner["user"]["id"]
    _grant_workspace_access(client, admin["token"], owner_id, "administrator")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    me_response = client.get("/api/v1/auth/me", headers=_auth_headers(owner_token))
    assert me_response.status_code == 200
    me_payload = me_response.json()
    assert len(me_payload["workspaces"]) == 1

    empty_hub_response = client.get(
        "/api/v1/workspaces/administrator/docs/hub", headers=_auth_headers(owner_token)
    )
    assert empty_hub_response.status_code == 200
    assert empty_hub_response.json()["items"] == []

    create_doc_response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
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
        f"/api/v1/workspaces/administrator/docs/items/{native_doc['id']}/pages",
        headers=_auth_headers(owner_token),
    )
    assert pages_response.status_code == 200
    page = pages_response.json()["items"][0]

    shared_user = _create_user(
        client,
        admin["token"],
        email="docs-shared@open-work-hub.local",
        full_name="Docs Shared User",
    )
    shared_user_id = shared_user["user"]["id"]
    _grant_workspace_access(client, admin["token"], shared_user_id, "administrator")
    shared_user_token = _login(
        client, shared_user["user"]["email"], shared_user["temporary_password"]
    )

    share_response = client.put(
        f"/api/v1/workspaces/administrator/docs/items/{native_doc['id']}/sharing/users/{shared_user_id}",
        headers=_auth_headers(owner_token),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200
    assert share_response.json()["users"][0]["access_level"] == "read"

    shared_me_response = client.get("/api/v1/auth/me", headers=_auth_headers(shared_user_token))
    assert shared_me_response.status_code == 200
    assert len(shared_me_response.json()["workspaces"]) == 1

    shared_hub_response = client.get(
        "/api/v1/workspaces/administrator/docs/hub", headers=_auth_headers(shared_user_token)
    )
    assert shared_hub_response.status_code == 200
    shared_items = shared_hub_response.json()["items"]
    assert [item["id"] for item in shared_items] == [native_doc["id"]]
    assert shared_items[0]["can_edit"] is False
    assert shared_items[0]["can_share"] is False

    shared_page_update_response = client.patch(
        f"/api/v1/workspaces/administrator/docs/pages/{page['id']}",
        headers=_auth_headers(shared_user_token),
        json={"content_blocks": [{"type": "paragraph", "content": "blocked"}]},
    )
    assert shared_page_update_response.status_code == 403


def test_docs_hub_reuses_pms_acl_and_blocks_resharing_of_source_docs(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    task_list = _create_task_list(client, admin["token"], key="DOCS", name="Docs Source List")

    space_doc = _create_space_doc(
        client, admin["token"], task_list["team_id"], title="Space Handbook"
    )
    original_space_page = _create_doc_page(
        client,
        admin["token"],
        space_doc["id"],
        title="Overview",
        content_blocks=[],
    )

    viewer = _create_user(
        client, admin["token"], email="docs-viewer@open-work-hub.local", full_name="Docs Viewer"
    )
    _grant_workspace_access(client, admin["token"], viewer["user"]["id"], "administrator")
    _add_task_list_member(client, admin["token"], task_list["id"], viewer["user"]["id"], "viewer")
    viewer_token = _login(client, viewer["user"]["email"], viewer["temporary_password"])

    viewer_hub_response = client.get(
        "/api/v1/workspaces/administrator/docs/hub", headers=_auth_headers(viewer_token)
    )
    assert viewer_hub_response.status_code == 200
    viewer_items = {item["title"]: item for item in viewer_hub_response.json()["items"]}
    assert viewer_items["Space Handbook"]["source_app"] == "pms"
    assert viewer_items["Space Handbook"]["primary_target"]["app"] == "pms"
    assert viewer_items["Space Handbook"]["primary_target"]["type"] == "space"
    assert viewer_items["Space Handbook"]["primary_target"]["id"] == task_list["team_id"]
    assert viewer_items["Space Handbook"]["can_edit"] is False
    assert viewer_items["Space Handbook"]["can_manage"] is False

    viewer_pages_response = client.get(
        f"/api/v1/workspaces/administrator/docs/items/{viewer_items['Space Handbook']['id']}/pages",
        headers=_auth_headers(viewer_token),
    )
    assert viewer_pages_response.status_code == 200
    viewer_page = viewer_pages_response.json()["items"][0]
    assert viewer_page["can_edit"] is False

    viewer_page_update_response = client.patch(
        f"/api/v1/workspaces/administrator/docs/pages/{viewer_page['id']}",
        headers=_auth_headers(viewer_token),
        json={"content_blocks": [{"type": "paragraph", "content": "blocked"}]},
    )
    assert viewer_page_update_response.status_code == 403

    viewer_share_response = client.get(
        f"/api/v1/workspaces/administrator/docs/items/{viewer_items['Space Handbook']['id']}/sharing",
        headers=_auth_headers(viewer_token),
    )
    assert viewer_share_response.status_code == 403

    member = _create_user(
        client, admin["token"], email="docs-user@open-work-hub.local", full_name="Docs User"
    )
    _grant_workspace_access(client, admin["token"], member["user"]["id"], "administrator")
    _add_task_list_member(client, admin["token"], task_list["id"], member["user"]["id"], "member")
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    member_hub_response = client.get(
        "/api/v1/workspaces/administrator/docs/hub", headers=_auth_headers(member_token)
    )
    assert member_hub_response.status_code == 200
    member_items = {item["title"]: item for item in member_hub_response.json()["items"]}
    assert member_items["Space Handbook"]["can_edit"] is True
    assert member_items["Space Handbook"]["can_manage"] is False

    member_create_page_response = client.post(
        f"/api/v1/workspaces/administrator/docs/items/{member_items['Space Handbook']['id']}/pages",
        headers=_auth_headers(member_token),
        json={"title": "Member Page"},
    )
    assert member_create_page_response.status_code == 201
    member_created_page = member_create_page_response.json()
    assert member_created_page["created_by_id"] == member["user"]["id"]
    assert member_created_page["created_by_name"] == "Docs User"

    member_delete_space_doc_response = client.delete(
        f"/api/v1/workspaces/administrator/docs/items/{member_items['Space Handbook']['id']}",
        headers=_auth_headers(member_token),
    )
    assert member_delete_space_doc_response.status_code == 403

    original_space_page_lookup_response = client.get(
        f"/api/v1/workspaces/administrator/docs/items/{member_items['Space Handbook']['id']}/pages",
        headers=_auth_headers(member_token),
    )
    assert original_space_page_lookup_response.status_code == 200
    overview_page = next(
        item
        for item in original_space_page_lookup_response.json()["items"]
        if item["source_page_id"] == original_space_page["id"]
    )

    update_space_page_response = client.patch(
        f"/api/v1/workspaces/administrator/docs/pages/{overview_page['id']}",
        headers=_auth_headers(member_token),
        json={"content_blocks": [{"type": "paragraph", "content": "space edit"}]},
    )
    assert update_space_page_response.status_code == 200


def test_space_docs_filter_includes_readable_task_linked_docs(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    task_list = _create_task_list(client, admin["token"], key="AGG", name="Aggregate List")
    other_space = _create_space(client, admin["token"], name="Outside Space")
    other_task_list = _create_task_list(
        client,
        admin["token"],
        key="OUT",
        name="Outside List",
        team_id=other_space["id"],
    )
    space_id = task_list["team_id"]

    task = _create_task(client, admin["token"], task_list["id"], title="Aggregate task")
    other_task = _create_task(client, admin["token"], other_task_list["id"], title="Outside task")

    direct_space_doc = _create_space_doc(
        client,
        admin["token"],
        space_id,
        title="Direct Space Doc",
    )
    linked_doc = _create_native_doc(client, admin["token"], title="Linked Task Doc")
    deduped_doc = _create_space_doc(
        client,
        admin["token"],
        space_id,
        title="Direct And Linked Doc",
    )
    secondary_space_doc = _create_space_doc(
        client,
        admin["token"],
        space_id,
        title="Secondary Space Doc",
    )
    _update_doc_target(client, admin["token"], secondary_space_doc["id"], other_space["id"])
    outside_doc = _create_native_doc(client, admin["token"], title="Outside Task Doc")

    _attach_task_doc(client, admin["token"], task["id"], linked_doc["id"])
    _attach_task_doc(client, admin["token"], task["id"], deduped_doc["id"])
    _attach_task_doc(client, admin["token"], other_task["id"], outside_doc["id"])

    admin_items = _list_space_docs(client, admin["token"], space_id)
    admin_titles = [item["title"] for item in admin_items]
    assert direct_space_doc["title"] in admin_titles
    assert linked_doc["title"] in admin_titles
    assert admin_titles.count(deduped_doc["title"]) == 1
    assert secondary_space_doc["title"] in admin_titles
    assert outside_doc["title"] not in admin_titles

    viewer = _create_user(
        client,
        admin["token"],
        email="task-linked-doc-viewer@open-work-hub.local",
        full_name="Task Linked Doc Viewer",
    )
    _grant_workspace_access(client, admin["token"], viewer["user"]["id"], "administrator")
    viewer_token = _login(client, viewer["user"]["email"], viewer["temporary_password"])

    share_response = client.put(
        f"/api/v1/workspaces/administrator/docs/items/{linked_doc['id']}/sharing/users/{viewer['user']['id']}",
        headers=_auth_headers(admin["token"]),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200

    viewer_without_task_access = _list_space_docs(client, viewer_token, space_id)
    assert viewer_without_task_access == []

    _add_task_list_member(client, admin["token"], task_list["id"], viewer["user"]["id"], "viewer")

    viewer_items = _list_space_docs(client, viewer_token, space_id)
    viewer_titles = [item["title"] for item in viewer_items]
    assert direct_space_doc["title"] in viewer_titles
    assert linked_doc["title"] in viewer_titles
    assert secondary_space_doc["title"] in viewer_titles
    assert outside_doc["title"] not in viewer_titles


def test_internal_shared_links_require_auth_and_honor_read_vs_edit(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(
        client, admin["token"], email="share-owner@open-work-hub.local", full_name="Share Owner"
    )
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "administrator")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    recipient = _create_user(
        client, admin["token"], email="share-recipient@open-work-hub.local", full_name="Share Recipient"
    )
    recipient_token = _login(client, recipient["user"]["email"], recipient["temporary_password"])

    create_doc_response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Shared Draft"},
    )
    assert create_doc_response.status_code == 201
    doc = create_doc_response.json()

    pages_response = client.get(
        f"/api/v1/workspaces/administrator/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
    )
    assert pages_response.status_code == 200
    page = pages_response.json()["items"][0]

    enable_read_link_response = client.put(
        f"/api/v1/workspaces/administrator/docs/items/{doc['id']}/sharing/link",
        headers=_auth_headers(owner_token),
        json={"access_level": "read", "active": True},
    )
    assert enable_read_link_response.status_code == 200
    share_token = enable_read_link_response.json()["link_share"]["token"]
    assert enable_read_link_response.json()["link_share"]["share_path"] == (
        f"/apps/docs/shared/{share_token}"
    )

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
        f"/api/v1/workspaces/administrator/docs/items/{doc['id']}/sharing/link",
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

    with get_session_factory()() as db:
        control = db.get(CompanyAppControl, "docs")
        assert control is not None
        control.enabled = False
        db.add(control)
        db.commit()

    disabled_response = client.get(
        f"/api/v1/docs/shared-links/{updated_share_token}",
        headers=_auth_headers(recipient_token),
    )
    assert disabled_response.status_code == 403
    assert disabled_response.json()["code"] == "workspace.app_disabled"


def test_workspace_scoped_shareable_users_stay_in_requested_docs_workspace(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)

    member = _create_user(
        client,
        admin["token"],
        email="administrator-docs-member@open-work-hub.local",
        full_name="Administrator Docs Member",
    )
    _grant_workspace_access(client, admin["token"], member["user"]["id"], "administrator")
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    response = client.get(
        "/api/v1/workspaces/administrator/docs/shareable-users",
        headers=_auth_headers(member_token),
        params={"q": "Admin"},
    )
    assert response.status_code == 200
    emails = {item["email"] for item in response.json()}
    assert "admin@open-work-hub.local" in emails
    assert "innovation-lab-admin@open-work-hub.local" not in emails


def test_native_doc_page_patch_rejects_cycle(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    owner = _create_user(
        client, admin["token"], email="cycle-owner@open-work-hub.local", full_name="Cycle Owner"
    )
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "administrator")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    doc = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Cycle Plan"},
    ).json()

    parent = client.post(
        f"/api/v1/workspaces/administrator/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
        json={"title": "Parent"},
    ).json()
    child = client.post(
        f"/api/v1/workspaces/administrator/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner_token),
        json={"title": "Child", "parent_id": parent["id"]},
    ).json()

    # Attempt to move Parent underneath Child — should be rejected as a cycle.
    reject = client.patch(
        f"/api/v1/workspaces/administrator/docs/pages/{parent['id']}",
        headers=_auth_headers(owner_token),
        json={"parent_id": child["id"]},
    )
    assert reject.status_code == 409
    assert reject.json()["code"] == "docs.page_parent_cycle"
    assert reject.json()["detail"] == "페이지 부모 관계에 순환이 포함될 수 없습니다."

    missing_parent = client.post(
        f"/api/v1/workspaces/administrator/docs/items/{doc['id']}/pages",
        headers={**_auth_headers(owner_token), "Accept-Language": "en-US"},
        json={"title": "Invalid child", "parent_id": "missing-parent"},
    )
    assert missing_parent.status_code == 404
    assert missing_parent.json()["code"] == "docs.parent_page_not_found"
    assert missing_parent.json()["detail"] == "Parent page not found."


def test_duplicate_doc_via_read_share_creates_private_copy_for_recipient(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)

    owner = _create_user(
        client, admin["token"], email="dup-share-owner@open-work-hub.local", full_name="Owner"
    )
    _grant_workspace_access(client, admin["token"], owner["user"]["id"], "administrator")
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    recipient = _create_user(
        client, admin["token"], email="dup-share-recipient@open-work-hub.local", full_name="Recipient"
    )
    _grant_workspace_access(client, admin["token"], recipient["user"]["id"], "administrator")
    recipient_token = _login(client, recipient["user"]["email"], recipient["temporary_password"])

    create_doc_response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Shared Plan"},
    )
    original = create_doc_response.json()

    share_response = client.put(
        f"/api/v1/workspaces/administrator/docs/items/{original['id']}/sharing/users/{recipient['user']['id']}",
        headers=_auth_headers(owner_token),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200

    # Recipient with read access can duplicate even though they cannot manage.
    duplicate_response = client.post(
        f"/api/v1/workspaces/administrator/docs/items/{original['id']}/duplicate",
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
            "full_name": "Open Work Hub Admin",
            "email": "admin@open-work-hub.local",
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
        json={"login_id": email.split("@", 1)[0].lower(), "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


def _first_workspace_slug(client: TestClient, token: str) -> str:
    response = client.get(
        "/api/v1/admin/workspaces",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    workspaces = response.json()
    assert workspaces
    return workspaces[0]["key"]


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
    assert workspace is not None, f"Unknown workspace key: {workspace_key}"

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
    user_bindings = [item for item in user_bindings if item["subject_id"] != user_id] + [
        {"subject_id": user_id, "role": role}
    ]

    update_response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
        json={"users": user_bindings},
    )
    assert update_response.status_code == 200


def _create_task_list(
    client: TestClient,
    token: str,
    *,
    key: str,
    name: str,
    team_id: str | None = None,
) -> dict:
    payload = {
        "key": key,
        "name": name,
        "description": f"{name} description",
    }
    if team_id is not None:
        payload["team_id"] = team_id
    response = client.post(
        "/api/v1/workspaces/administrator/pms/lists",
        headers=_auth_headers(token),
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def _create_space(client: TestClient, token: str, *, name: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/administrator/pms/spaces",
        headers=_auth_headers(token),
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task(
    client: TestClient,
    token: str,
    list_id: str,
    *,
    title: str,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{list_id}/tasks",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": "",
            "status": "todo",
            "priority": "medium",
            "assignee_id": None,
            "milestone_id": None,
            "parent_id": None,
            "label_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_task_list_member(
    client: TestClient, token: str, list_id: str, user_id: str, role: str
) -> dict:
    list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{list_id}",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200

    response = client.post(
        f"/api/v1/workspaces/administrator/pms/spaces/{list_response.json()['team_id']}/members",
        headers=_auth_headers(token),
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201
    return response.json()


def _create_space_doc(client: TestClient, token: str, space_id: str, *, title: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(token),
        json={
            "title": title,
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


def _create_native_doc(client: TestClient, token: str, *, title: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/administrator/docs/items",
        headers=_auth_headers(token),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _attach_task_doc(client: TestClient, token: str, task_id: str, doc_id: str) -> None:
    response = client.post(
        f"/api/v1/workspaces/administrator/pms/tasks/{task_id}/docs",
        headers=_auth_headers(token),
        json={"doc_id": doc_id},
    )
    assert response.status_code == 201, response.text


def _update_doc_target(client: TestClient, token: str, doc_id: str, space_id: str) -> None:
    response = client.put(
        f"/api/v1/workspaces/administrator/docs/items/{doc_id}/target",
        headers=_auth_headers(token),
        json={
            "app": "pms",
            "type": "space",
            "id": space_id,
        },
    )
    assert response.status_code == 200, response.text


def _list_space_docs(client: TestClient, token: str, space_id: str) -> list[dict]:
    response = client.get(
        "/api/v1/workspaces/administrator/docs/hub",
        headers=_auth_headers(token),
        params={
            "view": "all",
            "space_id": space_id,
            "sort_by": "target_sort_order",
            "sort_dir": "asc",
            "page_size": 200,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


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
        f"/api/v1/workspaces/administrator/docs/items/{doc_id}/pages",
        headers=_auth_headers(token),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _list_doc_pages(client: TestClient, token: str, doc_id: str) -> list[dict]:
    response = client.get(
        f"/api/v1/workspaces/administrator/docs/items/{doc_id}/pages",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _get_doc_item(
    client: TestClient,
    token: str,
    doc_id: str,
    *,
    workspace_slug: str = "administrator",
) -> dict:
    response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc_id}",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
