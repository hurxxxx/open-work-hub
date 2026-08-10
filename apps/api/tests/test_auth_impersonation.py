from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_admin_session(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open ALM Admin",
            "email": "admin@open-alm.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_user(
    client: TestClient,
    admin_token: str,
    *,
    login_id: str,
    email: str,
    full_name: str,
) -> dict:
    response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(admin_token),
        json={
            "login_id": login_id,
            "email": email,
            "full_name": full_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_platform_admin_can_impersonate_active_user_and_audit_context(
    client: TestClient,
) -> None:
    from open_alm_api.core.db import get_session_factory
    from open_alm_api.domains.auth.models import AuditLog, AuthSession
    from open_alm_api.domains.auth.security import hash_token

    admin_session = _bootstrap_admin_session(client)
    admin_token = admin_session["token"]
    admin_user_id = admin_session["user"]["id"]
    created = _create_user(
        client,
        admin_token,
        login_id="supporttarget",
        email="support-target@example.test",
        full_name="Support Target",
    )
    target_user_id = created["user"]["id"]

    response = client.post(
        f"/api/v1/auth/impersonations/{target_user_id}",
        headers=_auth_headers(admin_token),
    )
    assert response.status_code == 200, response.text
    impersonated_session = response.json()
    assert impersonated_session["user"]["id"] == target_user_id
    assert "platform_admin" not in impersonated_session["user"]["system_roles"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers=_auth_headers(impersonated_session["token"]),
    )
    assert me_response.status_code == 200, me_response.text
    assert me_response.json()["id"] == target_user_id

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers=_auth_headers(impersonated_session["token"]),
    )
    assert logout_response.status_code == 204, logout_response.text

    with get_session_factory()() as db:
        session_row = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == hash_token(impersonated_session["token"])
            )
        )
        assert session_row is not None
        assert session_row.user_id == target_user_id
        assert session_row.impersonator_user_id == admin_user_id

        impersonate_audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "auth.impersonate")
        )
        assert impersonate_audit is not None
        assert impersonate_audit.actor_user_id == admin_user_id
        assert impersonate_audit.entity_id == target_user_id
        assert impersonate_audit.payload["impersonator_user_id"] == admin_user_id
        assert impersonate_audit.payload["target_user_id"] == target_user_id

        logout_audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "auth.logout",
                AuditLog.actor_user_id == target_user_id,
            )
        )
        assert logout_audit is not None
        assert logout_audit.payload["impersonation"]["impersonator_user_id"] == admin_user_id
        assert logout_audit.payload["impersonation"]["impersonated_user_id"] == target_user_id


def test_non_admin_cannot_impersonate_user(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    created = _create_user(
        client,
        admin_session["token"],
        login_id="regularuser",
        email="regular-user@example.test",
        full_name="Regular User",
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "regularuser",
            "password": created["temporary_password"],
        },
    )
    assert login_response.status_code == 200, login_response.text

    response = client.post(
        f"/api/v1/auth/impersonations/{admin_session['user']['id']}",
        headers=_auth_headers(login_response.json()["token"]),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth.system_role_required"


def test_admin_cannot_impersonate_login_blocked_user(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    admin_token = admin_session["token"]
    created = _create_user(
        client,
        admin_token,
        login_id="blockeduser",
        email="blocked-user@example.test",
        full_name="Blocked User",
    )
    user_id = created["user"]["id"]
    block_response = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=_auth_headers(admin_token),
        json={"login_blocked": True},
    )
    assert block_response.status_code == 200, block_response.text

    response = client.post(
        f"/api/v1/auth/impersonations/{user_id}",
        headers=_auth_headers(admin_token),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth.user_inactive"


def test_blocking_impersonator_revokes_impersonated_session(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    admin_token = admin_session["token"]
    admin_user_id = admin_session["user"]["id"]
    created = _create_user(
        client,
        admin_token,
        login_id="impersonatedtarget",
        email="impersonated-target@example.test",
        full_name="Impersonated Target",
    )

    impersonation_response = client.post(
        f"/api/v1/auth/impersonations/{created['user']['id']}",
        headers=_auth_headers(admin_token),
    )
    assert impersonation_response.status_code == 200, impersonation_response.text
    impersonated_headers = _auth_headers(impersonation_response.json()["token"])
    assert client.get("/api/v1/auth/me", headers=impersonated_headers).status_code == 200

    block_response = client.patch(
        f"/api/v1/admin/users/{admin_user_id}",
        headers=_auth_headers(admin_token),
        json={"login_blocked": True},
    )
    assert block_response.status_code == 200, block_response.text

    assert (
        client.get(
            "/api/v1/auth/me",
            headers=_auth_headers(admin_token),
        ).status_code
        == 401
    )
    assert client.get("/api/v1/auth/me", headers=impersonated_headers).status_code == 401
