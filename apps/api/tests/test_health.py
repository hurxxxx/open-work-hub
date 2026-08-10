from fastapi.testclient import TestClient

from open_work_hub_api.version import RUNTIME_REVISION, VERSION


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == VERSION
    assert payload["runtime_revision"] == RUNTIME_REVISION


def test_healthz_preserves_inbound_trace_id(client: TestClient) -> None:
    trace_id = "abcdef1234567890abcdef1234567890"
    response = client.get(
        "/healthz",
        headers={"traceparent": f"00-{trace_id}-1234567890abcdef-01"},
    )
    assert response.status_code == 200
    assert response.headers["X-Open-Work-Hub-Trace-Id"] == trace_id


def test_auth_bootstrap_and_protected_search(client: TestClient) -> None:
    status_response = client.get("/api/v1/auth/bootstrap-status")
    assert status_response.status_code == 200
    assert status_response.json() == {
        "requires_setup": True,
        "dev_admin_login_available": True,
        "dev_login_accounts": [],
    }

    unauthenticated = client.post(
        "/api/v1/workspaces/administrator/search/documents",
        json={"query": "compressor specification"},
    )
    assert unauthenticated.status_code == 401

    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open Work Hub Admin",
            "email": "admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201
    auth_payload = setup_response.json()
    assert "platform_admin" in auth_payload["user"]["system_roles"]
    assert auth_payload["user"]["theme_preference"] == "system"
    assert auth_payload["user"]["locale"] == "ko-KR"
    assert auth_payload["user"]["time_zone"] == "Asia/Seoul"
    assert auth_payload["user"]["date_format"] == "korean"
    assert auth_payload["user"]["app_bar_layout"] == {
        "pinned_app_ids": ["pms", "docs", "whiteboard"],
    }
    assert auth_payload["user"]["default_workspace_id"] is None
    assert auth_payload["user"]["login_id"] == "admin"
    assert auth_payload["user"]["workspaces"]
    assert any(item["role"] == "admin" for item in auth_payload["user"]["workspaces"])
    assert "workspace_roles" not in auth_payload["user"]
    assert "app_access" not in auth_payload["user"]
    token = auth_payload["token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "admin@open-work-hub.local"

    search_response = client.post(
        "/api/v1/workspaces/administrator/search/documents",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "compressor specification"},
    )
    assert search_response.status_code == 200
    payload = search_response.json()
    assert payload["scenario_id"] == "documents-demo"
    assert payload["hits"]

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_response.status_code == 204

    expired_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert expired_response.status_code == 401


def test_auth_login_success_and_invalid_password(client: TestClient) -> None:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open Work Hub Admin",
            "login_id": "admin",
            "email": "admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "ADMIN",
            "password": "supersecret123",
        },
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["email"] == "admin@open-work-hub.local"
    assert "platform_admin" in login_response.json()["user"]["system_roles"]
    assert login_response.json()["token"]

    invalid_password_response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "admin",
            "password": "wrongpass123",
        },
    )
    assert invalid_password_response.status_code == 401


def test_auth_preferences_manage_default_workspace(client: TestClient) -> None:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open Work Hub Admin",
            "login_id": "admin",
            "email": "admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201
    setup_payload = setup_response.json()
    admin_token = setup_payload["token"]
    first_workspace = setup_payload["user"]["workspaces"][0]

    update_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"default_workspace_id": first_workspace["id"]},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["default_workspace_id"] == first_workspace["id"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["default_workspace_id"] == first_workspace["id"]

    create_member_response = client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": "Pending Member",
            "login_id": "pending-member",
            "email": "pending@open-work-hub.local",
            "temporary_password": "memberpass123",
        },
    )
    assert create_member_response.status_code == 201, create_member_response.text
    login_member_response = client.post(
        "/api/v1/auth/login",
        json={"login_id": "pending-member", "password": "memberpass123"},
    )
    assert login_member_response.status_code == 200, login_member_response.text
    member_token = login_member_response.json()["token"]

    forbidden_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"default_workspace_id": first_workspace["id"]},
    )
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["code"] == "workspace.membership_required"

    clear_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"default_workspace_id": None},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["default_workspace_id"] is None


def test_auth_preferences_manage_app_bar_layout(client: TestClient) -> None:
    token = _bootstrap_admin(client)

    update_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "app_bar_layout": {
                "pinned_app_ids": ["home", "files", "docs", "docs", "pms"],
            },
        },
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["app_bar_layout"] == {
        "pinned_app_ids": ["files", "docs", "pms"],
    }

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["app_bar_layout"] == {
        "pinned_app_ids": ["files", "docs", "pms"],
    }

    custom_feature_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "app_bar_layout": {
                "pinned_app_ids": ["diagrams", "docs", "docs"],
            },
        },
    )
    assert custom_feature_response.status_code == 200, custom_feature_response.text
    assert custom_feature_response.json()["app_bar_layout"] == {
        "pinned_app_ids": ["diagrams", "docs"],
    }

    overflow_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "app_bar_layout": {
                "pinned_app_ids": [
                    "home",
                    "docs",
                    "community",
                    "mail",
                    "whiteboard",
                    "video-chat",
                    "recording",
                    "diagrams",
                    "files",
                ],
            },
        },
    )
    assert overflow_response.status_code == 200, overflow_response.text
    assert overflow_response.json()["app_bar_layout"] == {
        "pinned_app_ids": [
            "docs",
            "community",
            "whiteboard",
            "video-chat",
            "recording",
            "diagrams",
            "files",
        ],
    }

    retired_category_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"app_bar_layout": {"pinned_app_ids": ["ai", "business"]}},
    )
    assert retired_category_response.status_code == 422
    assert retired_category_response.json()["code"] == "auth.invalid_app_bar_layout"

    invalid_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ko-KR"},
        json={"app_bar_layout": {"pinned_app_ids": ["home", "unknown-app"]}},
    )
    assert invalid_response.status_code == 422
    assert invalid_response.json()["code"] == "auth.invalid_app_bar_layout"
    assert invalid_response.json()["detail"] == "앱바 구성이 올바르지 않습니다."

    reset_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"app_bar_layout": None},
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["app_bar_layout"] == {
        "pinned_app_ids": ["pms", "docs", "whiteboard"],
    }


def test_auth_signup_creates_local_member_after_setup(client: TestClient) -> None:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open Work Hub Admin",
            "email": "admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201

    signup_response = client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": "New Member",
            "login_id": "new-member",
            "email": "NEW@open-work-hub.local",
            "password": "memberpass123",
            "password_confirm": "memberpass123",
        },
    )
    assert signup_response.status_code == 201, signup_response.text
    signup_body = signup_response.json()
    assert signup_body["user"]["login_id"] == "new-member"
    assert signup_body["user"]["email"] == "new@open-work-hub.local"
    assert signup_body["user"]["system_roles"] == []
    assert signup_body["user"]["workspaces"][0]["slug"] == "general"

    login_response = client.post(
        "/api/v1/auth/login",
        json={"login_id": "new-member", "password": "memberpass123"},
    )
    assert login_response.status_code == 200, login_response.text


def test_auth_signup_requires_setup_and_validates_duplicates_and_passwords(
    client: TestClient,
) -> None:
    disabled_before_setup_response = client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": "Early Member",
            "login_id": "early",
            "email": "early@open-work-hub.local",
            "password": "memberpass123",
            "password_confirm": "memberpass123",
        },
    )
    assert disabled_before_setup_response.status_code == 409
    assert disabled_before_setup_response.json()["code"] == "auth.setup_required"

    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open Work Hub Admin",
            "email": "admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201

    disabled_after_setup_response = client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": "Duplicate Admin",
            "login_id": "duplicate-admin",
            "email": "ADMIN@open-work-hub.local",
            "password": "memberpass123",
            "password_confirm": "memberpass123",
        },
    )
    assert disabled_after_setup_response.status_code == 409
    assert disabled_after_setup_response.json()["code"] == "auth.user_already_exists"

    mismatch_response = client.post(
        "/api/v1/auth/signup",
        headers={"Accept-Language": "ko-KR"},
        json={
            "full_name": "Mismatch Member",
            "login_id": "mismatch",
            "email": "mismatch@open-work-hub.local",
            "password": "memberpass123",
            "password_confirm": "different123",
        },
    )
    assert mismatch_response.status_code == 422
    assert mismatch_response.json()["code"] == "auth.password_confirmation_mismatch"
    assert mismatch_response.json()["detail"] == "비밀번호 확인이 일치하지 않습니다."


def test_auth_error_messages_are_localized(client: TestClient) -> None:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open Work Hub Admin",
            "email": "admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201

    english_response = client.post(
        "/api/v1/auth/login",
        headers={"Accept-Language": "en-US"},
        json={
            "login_id": "admin",
            "password": "wrongpass123",
        },
    )
    assert english_response.status_code == 401
    assert english_response.json()["detail"] == "ID or password is invalid."
    assert english_response.json()["code"] == "auth.invalid_credentials"
    assert english_response.headers["X-Open-Work-Hub-Error-Code"] == "auth.invalid_credentials"

    korean_response = client.post(
        "/api/v1/auth/login",
        headers={"Accept-Language": "ko-KR"},
        json={
            "login_id": "admin",
            "password": "wrongpass123",
        },
    )
    assert korean_response.status_code == 401
    assert korean_response.json()["detail"] == "ID 또는 비밀번호가 올바르지 않습니다."
    assert korean_response.json()["code"] == "auth.invalid_credentials"

    explicit_locale_response = client.get(
        "/api/v1/auth/me",
        headers={
            "Accept-Language": "en-US",
            "X-Open-Work-Hub-Locale": "ko-KR",
        },
    )
    assert explicit_locale_response.status_code == 401
    assert explicit_locale_response.json()["detail"] == "인증이 필요합니다."
    assert explicit_locale_response.json()["code"] == "auth.required"


def test_auth_validation_error_is_localized(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        headers={"Accept-Language": "ko-KR"},
        json={
            "login_id": "not@email",
            "password": "wrongpass123",
        },
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["detail"] == "ID는 영문 소문자, 숫자, 점, 밑줄, 하이픈으로 3~40자여야 합니다."
    assert body["code"] == "auth.valid_login_id_required"
    assert body["validation"][0]["loc"] == ["body", "login_id"]


def test_generic_request_validation_error_is_localized(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        headers={"Accept-Language": "ko-KR"},
        json={"login_id": "admin"},
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["detail"] == "요청 값이 올바르지 않습니다."
    assert body["code"] == "validation.request_invalid"
    assert body["validation"] == [
        {
            "loc": ["body", "password"],
            "type": "missing",
            "message": "필수 값입니다.",
        }
    ]


def test_generic_request_validation_error_preserves_dynamic_constraints(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        headers={"Accept-Language": "en-US"},
        json={"login_id": "admin", "password": "short"},
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["detail"] == "Request validation failed."
    assert body["code"] == "validation.request_invalid"
    assert body["validation"][0]["loc"] == ["body", "password"]
    assert body["validation"][0]["type"] == "string_too_short"
    assert body["validation"][0]["message"] == "Value is too short. Minimum length: 8"


def test_auth_preferences_password_and_sessions(client: TestClient) -> None:
    token = _bootstrap_admin(client)

    preferences_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "display_name": "Portal Admin",
            "theme_preference": "light",
            "locale": "en-US",
            "time_zone": "America/New_York",
            "date_format": "iso",
        },
    )
    assert preferences_response.status_code == 200
    assert preferences_response.json()["display_name"] == "Portal Admin"
    assert preferences_response.json()["theme_preference"] == "light"
    assert preferences_response.json()["locale"] == "en-US"
    assert preferences_response.json()["time_zone"] == "America/New_York"
    assert preferences_response.json()["date_format"] == "iso"

    invalid_locale_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ko-KR"},
        json={"locale": "fr-FR"},
    )
    assert invalid_locale_response.status_code == 422
    assert invalid_locale_response.json()["code"] == "auth.invalid_locale"
    assert invalid_locale_response.json()["detail"] == "locale이 올바르지 않습니다."

    invalid_timezone_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "en-US"},
        json={"time_zone": "Not/AZone"},
    )
    assert invalid_timezone_response.status_code == 422
    assert invalid_timezone_response.json()["code"] == "auth.invalid_time_zone"
    assert invalid_timezone_response.json()["detail"] == "Invalid time zone."

    invalid_date_format_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ko-KR"},
        json={"date_format": "quarterly"},
    )
    assert invalid_date_format_response.status_code == 422
    assert invalid_date_format_response.json()["code"] == "auth.invalid_date_format"
    assert invalid_date_format_response.json()["detail"] == "날짜 형식이 올바르지 않습니다."

    sessions_response = client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sessions_response.status_code == 200
    session_id = sessions_response.json()["items"][0]["id"]
    assert sessions_response.json()["items"][0]["is_current"] is True

    revoke_response = client.post(
        f"/api/v1/auth/sessions/{session_id}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoke_response.status_code == 204

    revoked_me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoked_me_response.status_code == 401

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "admin",
            "password": "supersecret123",
        },
    )
    assert login_response.status_code == 200
    replacement_token = login_response.json()["token"]

    password_response = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {replacement_token}"},
        json={
            "current_password": "supersecret123",
            "new_password": "newsupersecret123",
        },
    )
    assert password_response.status_code == 204

    old_login_response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "admin",
            "password": "supersecret123",
        },
    )
    assert old_login_response.status_code == 401

    new_login_response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "admin",
            "password": "newsupersecret123",
        },
    )
    assert new_login_response.status_code == 200


def _bootstrap_admin(client: TestClient) -> str:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open Work Hub Admin",
            "email": "admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201
    return setup_response.json()["token"]


def _replace_workspace_user_bindings(
    client: TestClient,
    *,
    workspace_id: str,
    headers: dict[str, str],
    changes: dict[str, str | None],
):
    current_response = client.get(
        f"/api/v1/admin/workspaces/{workspace_id}/bindings",
        headers=headers,
    )
    assert current_response.status_code == 200, current_response.text
    roles_by_user_id = {
        item["subject_id"]: item["role"]
        for item in current_response.json()
        if item["subject_type"] == "user"
    }
    for user_id, role in changes.items():
        if role is None:
            roles_by_user_id.pop(user_id, None)
        else:
            roles_by_user_id[user_id] = role
    return client.put(
        f"/api/v1/admin/workspaces/{workspace_id}/bindings",
        headers=headers,
        json={
            "users": [
                {"subject_id": user_id, "role": role} for user_id, role in roles_by_user_id.items()
            ],
        },
    )


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"login_id": email.split("@", 1)[0].lower(), "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


def _create_direct_user(
    *,
    email: str,
    full_name: str,
    password: str = "supersecret123",
    is_admin: bool = False,
    system_roles: tuple[str, ...] = (),
    workspace_keys: tuple[str, ...] = (),
) -> tuple[str, str]:
    from sqlalchemy import select

    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.models import (
        AuthSession,
        User,
        UserSystemRole,
        Workspace,
        WorkspaceUserBinding,
    )
    from open_work_hub_api.domains.auth.security import (
        hash_password,
        issue_session_token,
        new_id,
        normalize_email,
    )

    session_token = issue_session_token(ttl_hours=1)
    user_id = new_id()
    db = get_session_factory()()
    try:
        db.add(
            User(
                id=user_id,
                login_id=normalize_email(email).split("@", 1)[0],
                email=normalize_email(email),
                full_name=full_name,
                display_name=full_name,
                password_hash=hash_password(password),
                status="active",
                is_admin=is_admin,
            )
        )
        for role in {*(system_roles or ()), *(("platform_admin",) if is_admin else ())}:
            db.add(
                UserSystemRole(
                    id=new_id(),
                    user_id=user_id,
                    role=role,
                )
            )
        bound_workspace_ids: set[str] = set()
        for workspace_key in workspace_keys:
            workspace = db.scalar(select(Workspace).where(Workspace.key == workspace_key))
            if workspace is None:
                continue
            bound_workspace_ids.add(workspace.id)
        for workspace_id in bound_workspace_ids:
            db.add(
                WorkspaceUserBinding(
                    id=new_id(),
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role="member",
                )
            )
        db.add(
            AuthSession(
                id=new_id(),
                user_id=user_id,
                token_hash=session_token.token_hash,
                expires_at=session_token.expires_at,
            )
        )
        db.commit()
    finally:
        db.close()

    return user_id, session_token.plain_text


def _create_pms_task_list(
    client: TestClient,
    token: str,
    *,
    key: str,
    name: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/workspaces/administrator/pms/lists",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key": key,
            "name": name,
            "description": f"{name} description",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_pms_task(
    client: TestClient,
    token: str,
    list_id: str,
    *,
    title: str,
    parent_id: str | None = None,
    status: str = "todo",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{list_id}/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": title,
            "description": f"{title} description",
            "status": status,
            "priority": "medium",
            "parent_id": parent_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_admin_identity_management_endpoints(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    removed_groups_response = client.get("/api/v1/admin/groups", headers=headers)
    assert removed_groups_response.status_code == 404

    legacy_group_field_response = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "legacy-group-field@open-work-hub.local",
            "full_name": "Legacy Group Field",
            "group_ids": [],
        },
    )
    assert legacy_group_field_response.status_code == 422

    create_user_response = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "member@open-work-hub.local",
            "full_name": "Open Work Hub Member",
            "display_name": "Member",
            "system_roles": ["platform_admin"],
        },
    )
    assert create_user_response.status_code == 201
    created_user = create_user_response.json()["user"]
    temporary_password = create_user_response.json()["temporary_password"]
    assert created_user["email"] == "member@open-work-hub.local"
    assert created_user["must_change_password"] is True
    assert temporary_password

    list_users_response = client.get("/api/v1/admin/users", headers=headers)
    assert list_users_response.status_code == 200
    list_users_payload = list_users_response.json()
    assert len(list_users_payload["items"]) == 2
    assert list_users_payload["total"] == 2
    assert list_users_payload["page"] == 1
    assert list_users_payload["page_size"] == 20
    listed_user = next(
        item for item in list_users_payload["items"] if item["id"] == created_user["id"]
    )
    assert listed_user["display_name"] == "Member"

    paged_users_response = client.get(
        "/api/v1/admin/users",
        headers=headers,
        params={"page": 1, "page_size": 1},
    )
    assert paged_users_response.status_code == 200
    paged_users_payload = paged_users_response.json()
    assert len(paged_users_payload["items"]) == 1
    assert paged_users_payload["total"] == 2

    searched_users_response = client.get(
        "/api/v1/admin/users",
        headers=headers,
        params={"q": "member"},
    )
    assert searched_users_response.status_code == 200
    searched_users_payload = searched_users_response.json()
    assert len(searched_users_payload["items"]) == 1
    assert searched_users_payload["total"] == 1

    update_user_response = client.patch(
        f"/api/v1/admin/users/{created_user['id']}",
        headers=headers,
        json={
            "full_name": "Open Work Hub Member Updated",
            "display_name": "Updated Member",
            "status": "active",
            "system_roles": ["platform_admin"],
        },
    )
    assert update_user_response.status_code == 200
    assert update_user_response.json()["full_name"] == "Open Work Hub Member Updated"
    assert update_user_response.json()["display_name"] == "Updated Member"
    assert update_user_response.json()["system_roles"] == ["platform_admin"]

    delete_user_response = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "delete-me@open-work-hub.local",
            "full_name": "Delete Me",
            "display_name": "Delete Me",
        },
    )
    assert delete_user_response.status_code == 201
    delete_user_id = delete_user_response.json()["user"]["id"]

    me_response = client.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["login_id"] == "admin"
    self_delete_response = client.delete(
        f"/api/v1/admin/users/{me_response.json()['id']}",
        headers=headers,
    )
    assert self_delete_response.status_code == 400

    deleted_user_response = client.delete(
        f"/api/v1/admin/users/{delete_user_id}",
        headers=headers,
    )
    assert deleted_user_response.status_code == 204

    deleted_user_get_response = client.get(
        f"/api/v1/admin/users/{delete_user_id}",
        headers=headers,
    )
    assert deleted_user_get_response.status_code == 404

    workspace_response = client.post(
        "/api/v1/admin/workspaces",
        headers=headers,
        json={
            "name": "Supplier Portal",
            "description": "External supplier collaboration surface",
        },
    )
    assert workspace_response.status_code == 201
    workspace_id = workspace_response.json()["id"]

    legacy_group_bindings_response = client.put(
        f"/api/v1/admin/workspaces/{workspace_id}/bindings",
        headers=headers,
        json={
            "users": [],
            "groups": [],
        },
    )
    assert legacy_group_bindings_response.status_code == 422

    bindings_response = _replace_workspace_user_bindings(
        client,
        workspace_id=workspace_id,
        headers=headers,
        changes={created_user["id"]: "member"},
    )
    assert bindings_response.status_code == 200
    assert len(bindings_response.json()) == 2

    team_response = client.post(
        f"/api/v1/admin/workspaces/{workspace_id}/teams",
        headers=headers,
        json={
            "name": "Cross Functional Squad",
            "description": "Shared delivery team",
        },
    )
    assert team_response.status_code == 201
    team_id = team_response.json()["id"]

    team_members_response = client.put(
        f"/api/v1/admin/teams/{team_id}/members",
        headers=headers,
        json={"user_ids": [created_user["id"]]},
    )
    assert team_members_response.status_code == 200
    assert team_members_response.json()[0]["email"] == "member@open-work-hub.local"

    audit_logs_response = client.get("/api/v1/admin/audit-logs", headers=headers)
    assert audit_logs_response.status_code == 200
    assert audit_logs_response.json()


def test_workspace_scoped_team_management_requires_workspace_admin_role(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    workspace_response = client.post(
        "/api/v1/admin/workspaces",
        headers=admin_headers,
        json={
            "name": "Scoped Workspace",
            "description": "Workspace for scoped team management tests",
        },
    )
    assert workspace_response.status_code == 201
    workspace_id = workspace_response.json()["id"]

    second_workspace_response = client.post(
        "/api/v1/admin/workspaces",
        headers=admin_headers,
        json={
            "name": "Another Workspace",
            "description": "Second workspace for negative coverage",
        },
    )
    assert second_workspace_response.status_code == 201
    second_workspace_id = second_workspace_response.json()["id"]

    scoped_user_response = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": "scoped-manager@open-work-hub.local",
            "full_name": "Scoped Manager",
        },
    )
    assert scoped_user_response.status_code == 201
    scoped_user = scoped_user_response.json()["user"]
    scoped_user_token = _login(
        client,
        scoped_user["email"],
        scoped_user_response.json()["temporary_password"],
    )
    scoped_headers = {"Authorization": f"Bearer {scoped_user_token}"}

    inaccessible_workspaces_response = client.get(
        "/api/v1/admin/workspaces", headers=scoped_headers
    )
    assert inaccessible_workspaces_response.status_code == 200
    assert inaccessible_workspaces_response.json() == []

    create_team_without_scope_response = client.post(
        f"/api/v1/admin/workspaces/{workspace_id}/teams",
        headers=scoped_headers,
        json={"name": "Forbidden Team", "description": "Should be blocked"},
    )
    assert create_team_without_scope_response.status_code == 403

    bind_workspace_response = _replace_workspace_user_bindings(
        client,
        workspace_id=workspace_id,
        headers=admin_headers,
        changes={scoped_user["id"]: "admin"},
    )
    assert bind_workspace_response.status_code == 200

    visible_workspaces_response = client.get("/api/v1/admin/workspaces", headers=scoped_headers)
    assert visible_workspaces_response.status_code == 200
    assert [item["id"] for item in visible_workspaces_response.json()] == [workspace_id]

    create_team_with_scope_response = client.post(
        f"/api/v1/admin/workspaces/{workspace_id}/teams",
        headers=scoped_headers,
        json={"name": "Scoped Team", "description": "Allowed via workspace role"},
    )
    assert create_team_with_scope_response.status_code == 201
    created_team = create_team_with_scope_response.json()

    visible_teams_response = client.get(
        "/api/v1/admin/teams",
        headers=scoped_headers,
        params={"workspace_id": workspace_id},
    )
    assert visible_teams_response.status_code == 200
    visible_team_ids = {item["id"] for item in visible_teams_response.json()}
    assert created_team["id"] in visible_team_ids

    create_team_other_workspace_response = client.post(
        f"/api/v1/admin/workspaces/{second_workspace_id}/teams",
        headers=scoped_headers,
        json={"name": "Forbidden Elsewhere", "description": "No scope here"},
    )
    assert create_team_other_workspace_response.status_code == 403


def test_non_workspace_routes_require_workspace_membership(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    workspaces_response = client.get("/api/v1/admin/workspaces", headers=admin_headers)
    assert workspaces_response.status_code == 200
    hq_workspace = next(
        item for item in workspaces_response.json() if item["key"] == "administrator"
    )

    user_response = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": "docs-user@open-work-hub.local",
            "full_name": "Docs User",
        },
    )
    assert user_response.status_code == 201
    user = user_response.json()["user"]
    user_token = _login(client, user["email"], user_response.json()["temporary_password"])
    user_headers = {"Authorization": f"Bearer {user_token}"}

    documents_forbidden_response = client.post(
        "/api/v1/workspaces/administrator/search/documents",
        headers=user_headers,
        json={"query": "compressor specification"},
    )
    assert documents_forbidden_response.status_code == 403

    wiki_forbidden_response = client.get(
        "/api/v1/workspaces/administrator/wiki/pages", headers=user_headers
    )
    assert wiki_forbidden_response.status_code == 403

    ocr_forbidden_response = client.post(
        "/api/v1/workspaces/administrator/connectors/ocr/route",
        headers=user_headers,
        json={"asset_uri": "file://scan.pdf"},
    )
    assert ocr_forbidden_response.status_code == 403

    bind_docs_workspace_response = _replace_workspace_user_bindings(
        client,
        workspace_id=hq_workspace["id"],
        headers=admin_headers,
        changes={user["id"]: "member"},
    )
    assert bind_docs_workspace_response.status_code == 200

    documents_allowed_response = client.post(
        "/api/v1/workspaces/administrator/search/documents",
        headers=user_headers,
        json={"query": "compressor specification"},
    )
    assert documents_allowed_response.status_code == 200

    wiki_allowed_response = client.get(
        "/api/v1/workspaces/administrator/wiki/pages", headers=user_headers
    )
    assert wiki_allowed_response.status_code == 200

    ocr_allowed_response = client.post(
        "/api/v1/workspaces/administrator/connectors/ocr/route",
        headers=user_headers,
        json={"asset_uri": "file://scan.pdf"},
    )
    assert ocr_allowed_response.status_code == 200


def test_pms_membership_permissions(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    outsider_id, outsider_token = _create_direct_user(
        email="member@open-work-hub.local",
        full_name="List Member",
        workspace_keys=("administrator",),
    )

    task_list_response = client.post(
        "/api/v1/workspaces/administrator/pms/lists",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "key": "PERM",
            "name": "Permissions list",
            "description": "Membership checks",
        },
    )
    task_list = task_list_response.json()
    list_id = task_list["id"]
    space_id = task_list["team_id"]

    forbidden_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{list_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert forbidden_response.status_code == 403

    add_member_response = client.post(
        f"/api/v1/workspaces/administrator/pms/spaces/{space_id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_id": outsider_id, "role": "member"},
    )
    assert add_member_response.status_code == 201
    assert add_member_response.json()["role"] == "member"

    member_list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{list_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert member_list_response.status_code == 200
    assert member_list_response.json()["role"] == "member"


def test_pms_space_members_still_need_workspace_membership(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    member_id, member_token = _create_direct_user(
        email="space-only@open-work-hub.local",
        full_name="Space Only Member",
    )

    task_list_response = client.post(
        "/api/v1/workspaces/administrator/pms/lists",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "key": "SPACEONLY",
            "name": "Space-only list",
            "description": "App access guard",
        },
    )
    assert task_list_response.status_code == 201
    task_list = task_list_response.json()
    list_id = task_list["id"]
    space_id = task_list["team_id"]

    add_member_response = client.post(
        f"/api/v1/workspaces/administrator/pms/spaces/{space_id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_id": member_id, "role": "member"},
    )
    assert add_member_response.status_code == 201

    task_list_detail_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{list_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert task_list_detail_response.status_code == 403


def test_pms_space_creator_becomes_owner_and_last_manager_is_protected(client: TestClient) -> None:
    _bootstrap_admin(client)
    creator_id, creator_token = _create_direct_user(
        email="space-creator@open-work-hub.local",
        full_name="Space Creator",
        workspace_keys=("administrator",),
    )

    create_space_response = client.post(
        "/api/v1/workspaces/administrator/pms/spaces",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"name": "Operations", "description": "Owner bootstrap"},
    )
    assert create_space_response.status_code == 201
    space = create_space_response.json()

    members_response = client.get(
        f"/api/v1/workspaces/administrator/pms/spaces/{space['id']}/members",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert members_response.status_code == 200
    assert members_response.json()["items"][0]["user_id"] == creator_id
    assert members_response.json()["items"][0]["role"] == "owner"

    demote_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/spaces/{space['id']}/members/{creator_id}",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"role": "member"},
    )
    assert demote_response.status_code == 409

    remove_response = client.delete(
        f"/api/v1/workspaces/administrator/pms/spaces/{space['id']}/members/{creator_id}",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert remove_response.status_code == 409


def test_platform_admin_without_workspace_membership_cannot_view_pms_spaces(
    client: TestClient,
) -> None:
    admin_token = _bootstrap_admin(client)
    task_list_response = client.post(
        "/api/v1/workspaces/administrator/pms/lists",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"key": "PLATADM", "name": "Platform Admin List", "description": "Visibility"},
    )
    assert task_list_response.status_code == 201

    _, platform_admin_token = _create_direct_user(
        email="platform-admin@open-work-hub.local",
        full_name="Platform Admin",
        system_roles=("platform_admin",),
    )

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {platform_admin_token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["workspaces"] == []
    assert "app_access" not in me_response.json()

    spaces_response = client.get(
        "/api/v1/workspaces/administrator/pms/spaces",
        headers={"Authorization": f"Bearer {platform_admin_token}"},
    )
    assert spaces_response.status_code == 403


def test_workspace_bindings_grant_and_revoke_effective_workspace_access(
    client: TestClient,
) -> None:
    admin_token = _bootstrap_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    workspace_response = client.post(
        "/api/v1/admin/workspaces",
        headers=admin_headers,
        json={
            "name": "Operations Workspace",
            "description": "Directly managed workspace",
        },
    )
    assert workspace_response.status_code == 201
    workspace = workspace_response.json()

    create_user_response = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": "workspace-operator@open-work-hub.local",
            "full_name": "Workspace Operator",
        },
    )
    assert create_user_response.status_code == 201
    created_user = create_user_response.json()["user"]
    user_token = _login(
        client,
        created_user["email"],
        create_user_response.json()["temporary_password"],
    )
    user_headers = {"Authorization": f"Bearer {user_token}"}

    me_before_binding_response = client.get("/api/v1/auth/me", headers=user_headers)
    assert me_before_binding_response.status_code == 200
    assert me_before_binding_response.json()["workspaces"] == []

    bind_workspace_response = _replace_workspace_user_bindings(
        client,
        workspace_id=workspace["id"],
        headers=admin_headers,
        changes={created_user["id"]: "admin"},
    )
    assert bind_workspace_response.status_code == 200

    me_response = client.get("/api/v1/auth/me", headers=user_headers)
    assert me_response.status_code == 200
    bound_workspace = next(
        item for item in me_response.json()["workspaces"] if item["id"] == workspace["id"]
    )
    assert bound_workspace["role"] == "admin"
    assert bound_workspace["slug"] == workspace["key"]

    visible_workspaces_response = client.get("/api/v1/admin/workspaces", headers=user_headers)
    assert visible_workspaces_response.status_code == 200
    assert [item["id"] for item in visible_workspaces_response.json()] == [workspace["id"]]

    remove_binding_response = _replace_workspace_user_bindings(
        client,
        workspace_id=workspace["id"],
        headers=admin_headers,
        changes={created_user["id"]: None},
    )
    assert remove_binding_response.status_code == 200

    me_after_removal_response = client.get("/api/v1/auth/me", headers=user_headers)
    assert me_after_removal_response.status_code == 200
    assert all(
        item["id"] != workspace["id"] for item in me_after_removal_response.json()["workspaces"]
    )


def test_pms_parent_issue_validation_and_label_conflicts(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    primary_list = _create_pms_task_list(client, token, key="PARENT", name="Parent List")
    secondary_list = _create_pms_task_list(client, token, key="OTHER", name="Other List")

    parent_issue = _create_pms_task(client, token, str(primary_list["id"]), title="Parent issue")
    child_issue = _create_pms_task(
        client,
        token,
        str(primary_list["id"]),
        title="Child issue",
        parent_id=str(parent_issue["id"]),
    )
    assert child_issue["parent_id"] == parent_issue["id"]

    detail_response = client.get(
        f"/api/v1/workspaces/administrator/pms/tasks/{parent_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_response.status_code == 200
    assert len(detail_response.json()["subtasks"]) == 1

    self_parent_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{child_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"parent_id": child_issue["id"]},
    )
    assert self_parent_response.status_code == 409

    cycle_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/tasks/{parent_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"parent_id": child_issue["id"]},
    )
    assert cycle_response.status_code == 409

    cross_list_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{secondary_list['id']}/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Cross-list child",
            "description": "Should fail",
            "status": "todo",
            "priority": "medium",
            "parent_id": parent_issue["id"],
        },
    )
    assert cross_list_response.status_code == 400

    labels_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{primary_list['id']}/labels",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert labels_response.status_code == 200
    labels = labels_response.json()["items"]
    rename_conflict_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/labels/{labels[0]['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": labels[1]["name"]},
    )
    assert rename_conflict_response.status_code == 409


def test_pms_task_board_positions_are_scoped_to_sibling_level(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_pms_task_list(client, token, key="POS", name="Position List")

    parent = _create_pms_task(
        client,
        token,
        str(task_list["id"]),
        title="Parent",
        status="in_progress",
    )
    child = _create_pms_task(
        client,
        token,
        str(task_list["id"]),
        title="Child",
        parent_id=str(parent["id"]),
        status="in_progress",
    )
    later_root = _create_pms_task(
        client,
        token,
        str(task_list["id"]),
        title="Later root",
        status="todo",
    )

    assert parent["board_position"] == 1
    assert child["board_position"] == 1
    assert later_root["board_position"] == 2
