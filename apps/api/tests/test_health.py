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


def test_auth_bootstrap_and_protected_retrieval(client: TestClient) -> None:
    status_response = client.get("/api/v1/auth/bootstrap-status")
    assert status_response.status_code == 200
    assert status_response.json() == {
        "requires_setup": True,
        "dev_admin_login_available": True,
        "dev_login_accounts": [],
    }

    unauthenticated = client.get("/api/v1/retrieval/sources")
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
    assert "default_workspace_id" not in auth_payload["user"]
    assert auth_payload["user"]["login_id"] == "admin"
    assert "workspaces" not in auth_payload["user"]
    _assert_user_has_no_business_memberships(auth_payload["user"]["id"])
    assert "workspace_roles" not in auth_payload["user"]
    assert "app_access" not in auth_payload["user"]
    token = auth_payload["token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "admin@open-work-hub.local"

    denied_retrieval_response = client.get(
        "/api/v1/retrieval/sources",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied_retrieval_response.status_code == 403

    from dev_accounts import configure_company_app_access
    from open_work_hub_api.core.db import get_session_factory

    with get_session_factory()() as db:
        configure_company_app_access(db)
    retrieval_response = client.get(
        "/api/v1/retrieval/sources",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert retrieval_response.status_code == 200
    assert isinstance(retrieval_response.json()["sources"], list)

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


def test_auth_signup_creates_company_user_without_workspace_membership(
    client: TestClient,
) -> None:
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
    assert "workspaces" not in signup_body["user"]
    _assert_user_has_no_business_memberships(signup_body["user"]["id"])

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
            "new_password_confirm": "newsupersecret123",
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


def test_auth_change_password_validates_confirmation(client: TestClient) -> None:
    token = _bootstrap_admin(client)

    mismatch_response = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "supersecret123",
            "new_password": "newsupersecret123",
            "new_password_confirm": "differentsecret123",
        },
    )

    assert mismatch_response.status_code == 422
    assert mismatch_response.json()["code"] == "auth.password_confirmation_mismatch"
    assert mismatch_response.json()["detail"] == "비밀번호 확인이 일치하지 않습니다."

    original_login_response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "admin",
            "password": "supersecret123",
        },
    )
    assert original_login_response.status_code == 200


def _bootstrap_admin(client: TestClient) -> str:
    from test_meeting import _bootstrap_admin_session

    return _bootstrap_admin_session(client)["token"]


def _assert_user_has_no_business_memberships(user_id: str) -> None:
    from sqlalchemy import select
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.pms.space_models import TeamMember
    from open_work_hub_api.domains.groups.models import GroupMember

    with get_session_factory()() as db:
        assert db.scalar(select(TeamMember.id).where(TeamMember.user_id == user_id)) is None
        assert db.scalar(select(GroupMember.user_id).where(GroupMember.user_id == user_id)) is None


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
) -> tuple[str, str]:

    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.models import AuthSession, User, UserSystemRole
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
    space = client.post(
        "/api/v1/pms/spaces", headers={"Authorization": f"Bearer {token}"}, json={"name": name}
    )
    assert space.status_code == 201, space.text
    response = client.post(
        "/api/v1/pms/lists",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "team_id": space.json()["id"],
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
        f"/api/v1/pms/lists/{list_id}/tasks",
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
    assert removed_groups_response.status_code == 200

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

    group_response = client.post(
        "/api/v1/admin/groups", headers=headers, json={"name": "Partner Group"}
    )
    assert group_response.status_code == 201, group_response.text
    members_response = client.put(
        f"/api/v1/admin/groups/{group_response.json()['id']}/members",
        headers=headers,
        json={"user_ids": [created_user["id"]]},
    )
    assert members_response.status_code == 200, members_response.text
    assert members_response.json()["user_ids"] == [created_user["id"]]
    audit_logs_response = client.get("/api/v1/admin/audit-logs", headers=headers)
    assert audit_logs_response.status_code == 200
    assert audit_logs_response.json()


def test_pms_space_owner_has_no_company_group_administration(client: TestClient) -> None:
    _bootstrap_admin(client)
    user_id, token = _create_direct_user(email="space-owner@example.test", full_name="Space Owner")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v1/pms/spaces", headers=headers, json={"name": "Project Space"})
    assert response.status_code == 201, response.text
    assert response.json()["current_user_role"] == "owner"
    denied = client.post(
        "/api/v1/admin/groups", headers=headers, json={"name": "Unauthorised company group"}
    )
    assert denied.status_code == 403, denied.text
    denied = client.get("/api/v1/admin/users", headers=headers)
    assert denied.status_code == 403, denied.text


def test_company_app_grant_does_not_grant_other_apps(client: TestClient) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy, AppUserGrant

    _bootstrap_admin(client)
    user_id, token = _create_direct_user(
        email="selected-user@example.test", full_name="Selected User"
    )
    with get_session_factory()() as db:
        for app_id in ("docs", "whiteboard"):
            db.get(AppAccessPolicy, app_id).audience = "selected"
        db.add(AppUserGrant(app_id="docs", user_id=user_id))
        db.commit()
    headers = {"Authorization": f"Bearer {token}"}
    allowed = client.get("/api/v1/docs/hub", headers=headers)
    denied = client.get("/api/v1/whiteboard/hub", headers=headers)
    assert allowed.status_code == 200, allowed.text
    assert denied.status_code == 403, denied.text


def test_pms_membership_permissions(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    outsider_id, outsider_token = _create_direct_user(
        email="member@open-work-hub.local",
        full_name="List Member",
    )

    task_list = _create_pms_task_list(client, admin_token, key="PERM", name="Permissions list")
    list_id = task_list["id"]
    space_id = task_list["team_id"]

    forbidden_response = client.get(
        f"/api/v1/pms/lists/{list_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert forbidden_response.status_code == 403

    add_member_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_id": outsider_id, "role": "member"},
    )
    assert add_member_response.status_code == 201
    assert add_member_response.json()["role"] == "member"

    member_list_response = client.get(
        f"/api/v1/pms/lists/{list_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert member_list_response.status_code == 200
    assert member_list_response.json()["role"] == "member"


def test_pms_space_members_require_current_app_admission(client: TestClient) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy

    admin_token = _bootstrap_admin(client)
    user_id, token = _create_direct_user(email="pms-member@example.test", full_name="PMS Member")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    space = client.post("/api/v1/pms/spaces", headers=admin_headers, json={"name": "Delivery"})
    assert space.status_code == 201, space.text
    response = client.post(
        f"/api/v1/pms/spaces/{space.json()['id']}/members",
        headers=admin_headers,
        json={"user_id": user_id, "role": "viewer"},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {token}"}
    allowed = client.get("/api/v1/pms/spaces", headers=headers)
    assert allowed.status_code == 200, allowed.text
    assert space.json()["id"] in {item["id"] for item in allowed.json()}
    with get_session_factory()() as db:
        db.get(AppAccessPolicy, "pms").audience = "selected"
        db.commit()
    denied = client.get("/api/v1/pms/spaces", headers=headers)
    assert denied.status_code == 403, denied.text


def test_pms_space_creator_becomes_owner_and_last_manager_is_protected(client: TestClient) -> None:
    _bootstrap_admin(client)
    creator_id, creator_token = _create_direct_user(
        email="space-creator@open-work-hub.local",
        full_name="Space Creator",
    )

    create_space_response = client.post(
        "/api/v1/pms/spaces",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"name": "Operations", "description": "Owner bootstrap"},
    )
    assert create_space_response.status_code == 201
    space = create_space_response.json()

    members_response = client.get(
        f"/api/v1/pms/spaces/{space['id']}/members",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert members_response.status_code == 200
    assert members_response.json()["items"][0]["user_id"] == creator_id
    assert members_response.json()["items"][0]["role"] == "owner"

    demote_response = client.patch(
        f"/api/v1/pms/spaces/{space['id']}/members/{creator_id}",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"role": "member"},
    )
    assert demote_response.status_code == 409

    remove_response = client.delete(
        f"/api/v1/pms/spaces/{space['id']}/members/{creator_id}",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert remove_response.status_code == 409


def test_platform_admin_reads_business_space_without_implicit_write_role(
    client: TestClient,
) -> None:
    owner_token = _bootstrap_admin(client)
    task_list = _create_pms_task_list(
        client, owner_token, key="READADMIN", name="Read administrator test"
    )
    _, admin_token = _create_direct_user(
        email="reader-admin@example.test", full_name="Read Admin", system_roles=("platform_admin",)
    )
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.get(f"/api/v1/pms/lists/{task_list['id']}", headers=headers)
    assert response.status_code == 200, response.text
    response = client.patch(
        f"/api/v1/pms/lists/{task_list['id']}", headers=headers, json={"name": "Unauthorized edit"}
    )
    assert response.status_code == 403, response.text


def test_app_grant_removal_revokes_existing_session_without_deleting_account(
    client: TestClient,
) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy, AppUserGrant

    _bootstrap_admin(client)
    user_id, token = _create_direct_user(email="revoked-app@example.test", full_name="Revoked App")
    with get_session_factory()() as db:
        db.get(AppAccessPolicy, "docs").audience = "selected"
        db.add(AppUserGrant(app_id="docs", user_id=user_id))
        db.commit()
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/docs/hub", headers=headers)
    assert response.status_code == 200, response.text
    with get_session_factory()() as db:
        db.delete(db.get(AppUserGrant, ("docs", user_id)))
        db.commit()
    denied = client.get("/api/v1/docs/hub", headers=headers)
    assert denied.status_code == 403, denied.text
    current = client.get("/api/v1/auth/me", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["id"] == user_id


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
        f"/api/v1/pms/tasks/{parent_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_response.status_code == 200
    assert len(detail_response.json()["subtasks"]) == 1

    self_parent_response = client.patch(
        f"/api/v1/pms/tasks/{child_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"parent_id": child_issue["id"]},
    )
    assert self_parent_response.status_code == 409

    cycle_response = client.patch(
        f"/api/v1/pms/tasks/{parent_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"parent_id": child_issue["id"]},
    )
    assert cycle_response.status_code == 409

    cross_list_response = client.post(
        f"/api/v1/pms/lists/{secondary_list['id']}/tasks",
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
        f"/api/v1/pms/lists/{primary_list['id']}/labels",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert labels_response.status_code == 200
    labels = labels_response.json()["items"]
    rename_conflict_response = client.patch(
        f"/api/v1/pms/labels/{labels[0]['id']}",
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
