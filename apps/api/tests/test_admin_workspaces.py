from __future__ import annotations

from fastapi.testclient import TestClient

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.docs.app_catalog import DOCS_WORKSPACE_APP


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
    key: str | None = None,
) -> dict:
    payload = {"name": name, "description": description}
    if key is not None:
        payload["key"] = key
    response = client.post(
        "/api/v1/admin/workspaces",
        headers=_auth_headers(admin_token),
        json=payload,
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


def test_replace_workspace_bindings_rejects_actor_self_removal_atomically(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Keep The Admin")

    response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
        json={"users": []},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "admin.self_workspace_remove_denied"
    bindings = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
    )
    assert bindings.status_code == 200
    assert [(item["subject_id"], item["role"]) for item in bindings.json()] == [
        (admin["user"]["id"], "admin")
    ]


def test_replace_workspace_bindings_rejects_actor_self_demotion_atomically(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Keep The Role")

    response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
        json={
            "users": [
                {"subject_id": admin["user"]["id"], "role": "member"},
            ]
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "admin.self_role_change_denied"
    bindings = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
    )
    assert bindings.status_code == 200
    assert [(item["subject_id"], item["role"]) for item in bindings.json()] == [
        (admin["user"]["id"], "admin")
    ]


def test_replace_workspace_bindings_rejects_unknown_user_atomically(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Known Members Only")
    member = _create_user(
        client,
        token,
        email="known@open-work-hub.local",
        full_name="Known Member",
    )
    added = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(token),
        json={
            "subject_id": member["id"],
            "subject_type": "user",
            "role": "member",
        },
    )
    assert added.status_code == 201

    response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
        json={
            "users": [
                {"subject_id": admin["user"]["id"], "role": "admin"},
                {"subject_id": member["id"], "role": "admin"},
                {
                    "subject_id": "00000000-0000-0000-0000-000000000000",
                    "role": "member",
                },
            ]
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "auth.user_not_found"
    bindings = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
    )
    assert bindings.status_code == 200
    roles_by_user_id = {item["subject_id"]: item["role"] for item in bindings.json()}
    assert roles_by_user_id == {
        admin["user"]["id"]: "admin",
        member["id"]: "member",
    }


def test_replace_workspace_bindings_rejects_all_admin_removal_atomically(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Always Administered")
    second_platform_admin = _create_user_with_password(
        client,
        token,
        email="second-platform@open-work-hub.local",
        full_name="Second Platform Admin",
        password="Open Work Hub!platform2",
    )
    promoted = client.patch(
        f"/api/v1/admin/users/{second_platform_admin['user']['id']}",
        headers=_auth_headers(token),
        json={"system_roles": ["platform_admin"]},
    )
    assert promoted.status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "second-platform",
            "password": "Open Work Hub!platform2",
        },
    )
    assert login.status_code == 200, login.text

    response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(login.json()["token"]),
        json={
            "users": [
                {"subject_id": admin["user"]["id"], "role": "member"},
            ]
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "admin.invalid_workspace_role"
    bindings = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
    )
    assert bindings.status_code == 200
    assert [(item["subject_id"], item["role"]) for item in bindings.json()] == [
        (admin["user"]["id"], "admin")
    ]


def test_replace_workspace_bindings_keeps_valid_replace_behavior(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Valid Replacement")
    existing_member = _create_user(
        client,
        token,
        email="existing@open-work-hub.local",
        full_name="Existing Member",
    )
    new_member = _create_user(
        client,
        token,
        email="new@open-work-hub.local",
        full_name="New Member",
    )
    added = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(token),
        json={
            "subject_id": existing_member["id"],
            "subject_type": "user",
            "role": "member",
        },
    )
    assert added.status_code == 201

    response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
        json={
            "users": [
                {"subject_id": admin["user"]["id"], "role": "admin"},
                {"subject_id": existing_member["id"], "role": "admin"},
                {"subject_id": new_member["id"], "role": "member"},
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert {item["subject_id"]: item["role"] for item in response.json()} == {
        admin["user"]["id"]: "admin",
        existing_member["id"]: "admin",
        new_member["id"]: "member",
    }


def test_create_workspace_defaults_key_to_id_when_key_omitted(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    first = _create_workspace(client, token, name="기술연구소")
    second = _create_workspace(client, token, name="기술연구소")

    assert first["name"] == "기술연구소"
    assert second["name"] == "기술연구소"
    assert first["key"] == first["id"]
    assert second["key"] == second["id"]
    assert first["key"] != second["key"]


def test_create_workspace_preserves_explicit_key(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    workspace = _create_workspace(client, token, name="기술센터", key="engineering-center")

    assert workspace["name"] == "기술센터"
    assert workspace["key"] == "engineering-center"
    assert workspace["key"] != workspace["id"]


def test_app_bar_categories_are_admin_managed_presentation_groups(
    client: TestClient,
) -> None:
    get_settings.cache_clear()
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(
        client,
        token,
        name="App Bar Workspace",
        key="app-bar-workspace",
    )

    list_response = client.get(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    payload = list_response.json()
    assert payload["categories"] == []
    available_app_ids = {item["app_id"] for item in payload["available_apps"]}
    assert {DOCS_WORKSPACE_APP.app_id, "pms"} <= available_app_ids
    assert {"home", "extensions"}.isdisjoint(available_app_ids)

    create_response = client.post(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
        json={"title": "Field Ops", "icon_key": "microscope"},
    )
    assert create_response.status_code == 200, create_response.text
    created = next(
        item for item in create_response.json()["categories"] if item["title"] == "Field Ops"
    )
    assert created["key"] != "field-ops"
    assert created["icon_key"] == "microscope"

    layout_response = client.put(
        "/api/v1/admin/app-bar-categories/layout",
        headers=_auth_headers(token),
        json={
            "categories": [
                {
                    "id": created["id"],
                    "title": "Field tools",
                    "icon_key": "history",
                    "app_ids": ["docs", "pms"],
                }
            ]
        },
    )
    assert layout_response.status_code == 200, layout_response.text
    updated = next(
        item for item in layout_response.json()["categories"] if item["id"] == created["id"]
    )
    assert updated["title"] == "Field tools"
    assert updated["icon_key"] == "history"
    assert [item["app_id"] for item in updated["items"]] == [
        "docs",
        "pms",
    ]

    bootstrap_response = client.get(
        f"/api/v1/workspaces/{workspace['key']}/bootstrap",
        headers=_auth_headers(token),
    )
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    bootstrap = bootstrap_response.json()
    assert len(bootstrap["app_bar_categories"]) == 1
    bootstrap_category = bootstrap["app_bar_categories"][0]
    assert {
        "id": bootstrap_category["id"],
        "key": bootstrap_category["key"],
        "title": bootstrap_category["title"],
        "icon_key": bootstrap_category["icon_key"],
    } == {
        "id": updated["id"],
        "key": updated["key"],
        "title": "Field tools",
        "icon_key": "history",
    }
    assert [item["app_id"] for item in bootstrap_category["items"]] == [
        "docs",
        "pms",
    ]

    invalid_icon_response = client.post(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
        json={"title": "Invalid Icon", "icon_key": "../bad"},
    )
    assert invalid_icon_response.status_code == 400
    assert invalid_icon_response.json()["code"] == "admin.invalid_app_bar_icon"

    delete_response = client.delete(
        f"/api/v1/admin/app-bar-categories/{created['id']}",
        headers=_auth_headers(token),
    )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["categories"] == []

    reread_response = client.get(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
    )
    assert reread_response.status_code == 200, reread_response.text
    assert reread_response.json()["categories"] == []
    get_settings.cache_clear()


def test_company_app_control_disables_workspace_app(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(
        client,
        token,
        name="Company Control Workspace",
        key="company-control-workspace",
    )

    list_response = client.get(
        "/api/v1/admin/apps/company-controls",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    items = list_response.json()["items"]
    app_ids = {item["app_id"] for item in items}
    assert {"ai", "collaboration", "business"}.isdisjoint(app_ids)
    assert "home" in app_ids
    docs_item = next(item for item in items if item["app_id"] == "docs")
    assert docs_item["execution_context_kind"] == "workspace"
    assert docs_item["enabled"] is True

    update_response = client.patch(
        "/api/v1/admin/apps/company-controls",
        headers=_auth_headers(token),
        json={"items": [{"app_id": "docs", "enabled": False}]},
    )
    assert update_response.status_code == 200, update_response.text
    docs_item = next(item for item in update_response.json()["items"] if item["app_id"] == "docs")
    assert docs_item["enabled"] is False
    assert docs_item["runtime_enabled"] is False

    bootstrap_response = client.get(
        f"/api/v1/workspaces/{workspace['key']}/bootstrap",
        headers=_auth_headers(token),
    )
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    bootstrap = bootstrap_response.json()
    assert "docs" not in {item["app_id"] for item in bootstrap["apps"]}
    assert "docs" not in {item["app_id"] for item in bootstrap["nav"]}
    assert "platform_visible_app_ids" not in bootstrap


def test_company_master_cannot_be_bypassed_by_workspace_override(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(
        client,
        token,
        name="Override Boundary Workspace",
        key="override-boundary-workspace",
    )
    workspace_id = workspace["id"]
    company_response = client.patch(
        "/api/v1/admin/apps/company-controls",
        headers=_auth_headers(token),
        json={"items": [{"app_id": "docs", "enabled": False}]},
    )
    assert company_response.status_code == 200, company_response.text

    list_response = client.get(
        f"/api/v1/admin/workspaces/{workspace_id}/app-overrides",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    docs_item = next(item for item in list_response.json()["items"] if item["app_id"] == "docs")
    assert docs_item["company_enabled"] is False
    assert docs_item["default_enabled"] is True
    assert docs_item["override_enabled"] is None
    assert docs_item["effective_enabled"] is False

    override_response = client.patch(
        f"/api/v1/admin/workspaces/{workspace_id}/app-overrides",
        headers=_auth_headers(token),
        json={"items": [{"app_id": "docs", "enabled": True}]},
    )
    assert override_response.status_code == 200, override_response.text
    docs_item = next(item for item in override_response.json()["items"] if item["app_id"] == "docs")
    assert docs_item["override_enabled"] is True
    assert docs_item["effective_enabled"] is False
    assert docs_item["runtime_enabled"] is False

    bootstrap_response = client.get(
        f"/api/v1/workspaces/{workspace['key']}/bootstrap",
        headers=_auth_headers(token),
    )
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    bootstrap = bootstrap_response.json()
    assert "docs" not in {item["app_id"] for item in bootstrap["apps"]}


def test_platform_personal_tool_workspace_override_is_rejected(
    client: TestClient,
) -> None:
    platform_admin = _bootstrap_admin_session(client)
    platform_token = platform_admin["token"]
    workspace = _create_workspace(client, platform_token, name="Management")
    workspace_admin_payload = _create_user_with_password(
        client,
        platform_token,
        email="workspaceadmin@open-work-hub.local",
        full_name="Workspace Admin",
        password="Open Work Hub!workspace1",
    )
    add_response = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(platform_token),
        json={
            "subject_id": workspace_admin_payload["user"]["id"],
            "subject_type": "user",
            "role": "admin",
        },
    )
    assert add_response.status_code == 201, add_response.text

    login = client.post(
        "/api/v1/auth/login",
        json={"login_id": "workspaceadmin", "password": "Open Work Hub!workspace1"},
    )
    assert login.status_code == 200, login.text
    for token in (login.json()["token"], platform_token):
        response = client.patch(
            f"/api/v1/admin/workspaces/{workspace['id']}/app-overrides",
            headers=_auth_headers(token),
            json={"items": [{"app_id": "planner", "enabled": True}]},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "admin.unknown_workspace_app"


def test_platform_apps_are_excluded_from_workspace_controls_and_categories(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace_id = _create_workspace(
        client,
        token,
        name="Workspace App Controls",
    )["id"]

    company_response = client.get(
        "/api/v1/admin/apps/company-controls",
        headers=_auth_headers(token),
    )
    defaults_response = client.get(
        "/api/v1/admin/apps/workspace-defaults",
        headers=_auth_headers(token),
    )
    overrides_response = client.get(
        f"/api/v1/admin/workspaces/{workspace_id}/app-overrides",
        headers=_auth_headers(token),
    )
    categories_response = client.get(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
    )

    assert company_response.status_code == 200, company_response.text
    assert defaults_response.status_code == 200, defaults_response.text
    assert overrides_response.status_code == 200, overrides_response.text
    assert categories_response.status_code == 200, categories_response.text
    company_items = {item["app_id"]: item for item in company_response.json()["items"]}
    default_app_ids = {item["app_id"] for item in defaults_response.json()["items"]}
    override_app_ids = {item["app_id"] for item in overrides_response.json()["items"]}
    category_app_ids = {item["app_id"] for item in categories_response.json()["available_apps"]}
    assert {"community", "mail", "planner", "docs"} <= company_items.keys()
    assert all(
        company_items[app_id]["availability_scope"] == "platform"
        for app_id in ("community", "mail", "planner")
    )
    assert company_items["docs"]["availability_scope"] == "workspace"
    assert company_items["community"]["execution_context_kind"] == "company"
    assert all(
        company_items[app_id]["execution_context_kind"] == "personal"
        for app_id in ("mail", "planner")
    )
    assert {"community", "mail", "planner"}.isdisjoint(default_app_ids)
    assert {"community", "mail", "planner"}.isdisjoint(override_app_ids)
    assert "docs" in default_app_ids
    assert "docs" in override_app_ids
    assert {"mail", "planner"}.isdisjoint(category_app_ids)
    assert {"community", "docs"} <= category_app_ids


def test_workspace_app_override_can_return_to_workspace_default(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace_id = _create_workspace(
        client,
        token,
        name="Workspace Override Inheritance",
    )["id"]

    disabled_response = client.patch(
        f"/api/v1/admin/workspaces/{workspace_id}/app-overrides",
        headers=_auth_headers(token),
        json={"items": [{"app_id": "docs", "enabled": False}]},
    )
    assert disabled_response.status_code == 200, disabled_response.text

    inherit_response = client.patch(
        f"/api/v1/admin/workspaces/{workspace_id}/app-overrides",
        headers=_auth_headers(token),
        json={"items": [{"app_id": "docs", "enabled": None}]},
    )
    assert inherit_response.status_code == 200, inherit_response.text
    docs_item = next(item for item in inherit_response.json()["items"] if item["app_id"] == "docs")
    assert docs_item["company_enabled"] is True
    assert docs_item["default_enabled"] is True
    assert docs_item["override_enabled"] is None
    assert docs_item["effective_enabled"] is True


def test_add_remove_member_endpoints(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="People Hub")
    other_user = _create_user(client, token, email="alice@open-work-hub.local", full_name="Alice")

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


def test_workspace_membership_changes_reach_open_sessions_and_match_auth_me(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace = _create_workspace(client, admin_token, name="Realtime Access")
    member_payload = _create_user_with_password(
        client,
        admin_token,
        email="realtime-member@open-work-hub.local",
        full_name="Realtime Member",
        password="Open Work Hub!realtime12",
    )
    member_id = member_payload["user"]["id"]
    login = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "realtime-member",
            "password": "Open Work Hub!realtime12",
        },
    )
    assert login.status_code == 200, login.text
    member_token = login.json()["token"]

    def assert_access_changed(websocket, reason: str) -> None:
        event = websocket.receive_json()
        assert event["type"] == "auth.access.changed"
        assert event["data"] == {"reason": reason}
        assert event["topic"] == f"user:{member_id}"
        assert event["event_id"]

    def current_workspace_role() -> str | None:
        response = client.get(
            "/api/v1/auth/me",
            headers=_auth_headers(member_token),
        )
        assert response.status_code == 200, response.text
        current = next(
            (item for item in response.json()["workspaces"] if item["id"] == workspace["id"]),
            None,
        )
        return current["role"] if current else None

    def current_app_ids() -> set[str]:
        response = client.get(
            "/api/v1/apps/bootstrap",
            headers=_auth_headers(member_token),
        )
        assert response.status_code == 200, response.text
        return {item["app_id"] for item in response.json()["apps"]}

    with client.websocket_connect("/api/v1/realtime/ws") as websocket:
        websocket.send_json({"type": "auth", "token": member_token})
        assert websocket.receive_json() == {
            "type": "realtime.auth.ok",
            "data": {},
        }
        assert websocket.receive_json()["type"] == "notification.snapshot"

        added = client.post(
            f"/api/v1/admin/workspaces/{workspace['id']}/members",
            headers=_auth_headers(admin_token),
            json={
                "subject_id": member_id,
                "subject_type": "user",
                "role": "member",
            },
        )
        assert added.status_code == 201, added.text
        assert_access_changed(websocket, "workspace_membership")
        assert current_workspace_role() == "member"

        company_disabled = client.patch(
            "/api/v1/admin/apps/company-controls",
            headers=_auth_headers(admin_token),
            json={"items": [{"app_id": "planner", "enabled": False}]},
        )
        assert company_disabled.status_code == 200, company_disabled.text
        assert_access_changed(websocket, "app_availability")
        assert "planner" not in current_app_ids()

        company_restored = client.patch(
            "/api/v1/admin/apps/company-controls",
            headers=_auth_headers(admin_token),
            json={"items": [{"app_id": "planner", "enabled": True}]},
        )
        assert company_restored.status_code == 200, company_restored.text
        assert_access_changed(websocket, "app_availability")
        assert "planner" in current_app_ids()

        default_disabled = client.patch(
            "/api/v1/admin/apps/workspace-defaults",
            headers=_auth_headers(admin_token),
            json={"items": [{"app_id": "docs", "enabled": False}]},
        )
        assert default_disabled.status_code == 200, default_disabled.text
        assert_access_changed(websocket, "app_availability")
        assert "docs" not in current_app_ids()

        default_restored = client.patch(
            "/api/v1/admin/apps/workspace-defaults",
            headers=_auth_headers(admin_token),
            json={"items": [{"app_id": "docs", "enabled": True}]},
        )
        assert default_restored.status_code == 200, default_restored.text
        assert_access_changed(websocket, "app_availability")
        assert "docs" in current_app_ids()

        override_disabled = client.patch(
            f"/api/v1/admin/workspaces/{workspace['id']}/app-overrides",
            headers=_auth_headers(admin_token),
            json={"items": [{"app_id": "docs", "enabled": False}]},
        )
        assert override_disabled.status_code == 200, override_disabled.text
        assert_access_changed(websocket, "app_availability")
        assert "docs" not in current_app_ids()

        override_restored = client.patch(
            f"/api/v1/admin/workspaces/{workspace['id']}/app-overrides",
            headers=_auth_headers(admin_token),
            json={"items": [{"app_id": "docs", "enabled": None}]},
        )
        assert override_restored.status_code == 200, override_restored.text
        assert_access_changed(websocket, "app_availability")
        assert "docs" in current_app_ids()

        archived = client.patch(
            f"/api/v1/admin/workspaces/{workspace['id']}",
            headers=_auth_headers(admin_token),
            json={
                "key": workspace["key"],
                "name": workspace["name"],
                "description": workspace["description"],
                "active": False,
            },
        )
        assert archived.status_code == 200, archived.text
        assert_access_changed(websocket, "workspace_membership")
        assert current_workspace_role() is None

        restored = client.patch(
            f"/api/v1/admin/workspaces/{workspace['id']}",
            headers=_auth_headers(admin_token),
            json={
                "key": workspace["key"],
                "name": workspace["name"],
                "description": workspace["description"],
                "active": True,
            },
        )
        assert restored.status_code == 200, restored.text
        assert_access_changed(websocket, "workspace_membership")
        assert current_workspace_role() == "member"

        role_changed = client.patch(
            f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{member_id}",
            headers=_auth_headers(admin_token),
            json={"role": "admin"},
        )
        assert role_changed.status_code == 200, role_changed.text
        assert_access_changed(websocket, "workspace_membership")
        assert current_workspace_role() == "admin"

        removed = client.delete(
            f"/api/v1/admin/workspaces/{workspace['id']}/members/user/{member_id}",
            headers=_auth_headers(admin_token),
        )
        assert removed.status_code == 204, removed.text
        assert_access_changed(websocket, "workspace_membership")
        assert current_workspace_role() is None
        websocket.close()


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
        email="intruder@open-work-hub.local",
        full_name="Intruder",
        password="Open Work Hub!intruder1",
    )
    intruder = intruder_payload["user"]

    login = client.post(
        "/api/v1/auth/login",
        json={"login_id": "intruder", "password": "Open Work Hub!intruder1"},
    )
    assert login.status_code == 200, login.text
    intruder_token = login.json()["token"]

    response = client.post(
        f"/api/v1/admin/workspaces/{workspace['id']}/members",
        headers=_auth_headers(intruder_token),
        json={"subject_id": intruder["id"], "subject_type": "user", "role": "member"},
    )
    assert response.status_code in {403, 404}


def test_hard_delete_workspace_is_disabled_and_archive_is_preserved(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Archive Only")
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

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    workspace_path = openapi.json()["paths"]["/api/v1/admin/workspaces/{workspace_id}"]
    assert "delete" not in workspace_path

    blocked = client.delete(
        f"/api/v1/admin/workspaces/{workspace['id']}",
        headers=_auth_headers(token),
    )

    assert blocked.status_code == 405
    workspaces = client.get(
        "/api/v1/admin/workspaces?include_archived=true",
        headers=_auth_headers(token),
    )
    assert workspaces.status_code == 200
    assert workspace["id"] in {item["id"] for item in workspaces.json()}


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
            email=f"user{i}@open-work-hub.local",
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
    assert search_filter["items"][0]["subject_secondary"] == "user2@open-work-hub.local"


def test_bulk_member_endpoint_partial_failure(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    workspace = _create_workspace(client, token, name="Bulk Lab")

    user_a = _create_user(client, token, email="alice@open-work-hub.local", full_name="Alice")
    user_b = _create_user(client, token, email="bob@open-work-hub.local", full_name="Bob")

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
        email="second@open-work-hub.local",
        full_name="Second Admin",
        password="Open Work Hub!second12",
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
        json={"login_id": "second", "password": "Open Work Hub!second12"},
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
