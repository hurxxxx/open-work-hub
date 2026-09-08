from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from dev_accounts import auth_headers, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import AuditLog, AuthSession, User


@pytest.mark.parametrize("actor_account", ["administrator", "delivery-hub-member"])
@pytest.mark.parametrize("target_blocked", [False, True])
def test_impersonation_is_removed_for_every_role_and_target_state(
    client: TestClient, actor_account: str, target_blocked: bool
) -> None:
    actor = dev_login(client, actor_account)
    target = dev_login(client, "knowledge-base-admin")
    target_id = target["user"]["id"]
    with get_session_factory()() as db:
        if target_blocked:
            db.get(User, target_id).login_blocked = True
            db.commit()
        sessions_before = db.scalar(select(func.count()).select_from(AuthSession))
        impersonation_audits_before = db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "auth.impersonate")
        )
    result = client.post(
        f"/api/v1/auth/impersonations/{target_id}",
        headers=auth_headers(actor["token"]),
    )
    assert result.status_code == 404
    with get_session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == sessions_before
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "auth.impersonate")
            )
            == impersonation_audits_before
        )
    me = client.get("/api/v1/auth/me", headers=auth_headers(actor["token"]))
    assert me.status_code == 200
    assert me.json()["id"] == actor["user"]["id"]
    assert "impersonator_user_id" not in me.json()


def test_administrator_status_does_not_change_an_independently_authenticated_user(
    client: TestClient,
) -> None:
    administrator = dev_login(client, "administrator")
    member = dev_login(client, "delivery-hub-member")
    with get_session_factory()() as db:
        db.get(User, administrator["user"]["id"]).login_blocked = True
        db.commit()
    assert (
        client.get("/api/v1/auth/me", headers=auth_headers(administrator["token"])).status_code
        == 403
    )
    member_me = client.get("/api/v1/auth/me", headers=auth_headers(member["token"]))
    assert member_me.status_code == 200
    assert member_me.json()["id"] == member["user"]["id"]
    assert "platform_admin" not in member_me.json()["system_roles"]
