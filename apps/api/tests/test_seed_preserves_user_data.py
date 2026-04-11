"""Regression: ensure_seed_data must not clobber user-created spaces.

The original seed loop scanned each seed user's TeamMember rows and deleted
anything that wasn't the default PMS space. That wiped out user-created
spaces on every app boot because ``init_db()`` calls ``ensure_seed_data()``
at startup — users would create a space, restart the API, and find their
space was still there but the membership row behind it was gone.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_dev_accounts() -> None:
    """Run the full dev-login seed loop so the /auth/dev-login route can
    find the seeded fixtures (ensure_dev_login_seed_data delegates to
    ensure_seed_data internally)."""
    from aidoo_api.core.db import get_session_factory
    from aidoo_api.domains.auth.access import ensure_dev_login_seed_data

    session_factory = get_session_factory()
    with session_factory() as db:
        ensure_dev_login_seed_data(db)
        db.commit()


def test_seed_preserves_user_created_space_membership(client: TestClient) -> None:
    from aidoo_api.core.db import get_session_factory
    from aidoo_api.domains.auth.access import ensure_seed_data
    from aidoo_api.domains.auth.models import TeamMember, User

    _seed_dev_accounts()

    # Log in as the seeded pms-member account and create a new PMS space.
    login_response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": "pms-member"},
    )
    assert login_response.status_code == 200, login_response.text
    session = login_response.json()
    token = session["token"]
    user_id = session["user"]["id"]

    create_response = client.post(
        "/api/v1/pms/spaces",
        headers=_auth_headers(token),
        json={"name": "My Private Space", "description": ""},
    )
    assert create_response.status_code == 201, create_response.text
    new_space_id = create_response.json()["id"]

    # Sanity: membership row exists right after creation.
    session_factory = get_session_factory()
    with session_factory() as db:
        membership = db.scalar(
            select(TeamMember).where(
                TeamMember.team_id == new_space_id,
                TeamMember.user_id == user_id,
            )
        )
        assert membership is not None, (
            "create_space should register the creator as a TeamMember"
        )
        assert membership.role == "owner"

    # Re-run the seed loop (equivalent to restarting the API).
    with session_factory() as db:
        ensure_seed_data(db)
        db.commit()

    # The user-created membership must still be there.
    with session_factory() as db:
        membership = db.scalar(
            select(TeamMember).where(
                TeamMember.team_id == new_space_id,
                TeamMember.user_id == user_id,
            )
        )
        assert membership is not None, (
            "ensure_seed_data deleted a user-created TeamMember row — the seed "
            "loop is clobbering data it should have left alone."
        )
        assert membership.role == "owner"

    # And the user should still be able to list the space.
    list_response = client.get(
        "/api/v1/pms/spaces",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200
    space_ids = {item["id"] for item in list_response.json()}
    assert new_space_id in space_ids


def test_seed_still_reconciles_default_space_membership(
    client: TestClient,
) -> None:
    """The seed loop should still enforce the team_role declared in
    DEV_LOGIN_ACCOUNTS against the default PMS space — e.g. pms-member
    should have a membership there, pms-viewer should be a viewer, and
    platform-admin (team_role=None) should not have a membership there at all."""
    _seed_dev_accounts()

    from aidoo_api.core.db import get_session_factory
    from aidoo_api.domains.auth.models import TeamMember, User

    session_factory = get_session_factory()
    with session_factory() as db:
        # Seed accounts by email
        def membership_for(email: str) -> TeamMember | None:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                return None
            return db.scalar(
                select(TeamMember).where(TeamMember.user_id == user.id)
            )

        pms_member_ms = membership_for("pms-member@aidoo.local")
        pms_viewer_ms = membership_for("pms-viewer@aidoo.local")
        admin_ms = membership_for("platform-admin@aidoo.local")

        assert pms_member_ms is not None, "pms-member should be seeded into default space"
        assert pms_member_ms.role == "member"
        assert pms_viewer_ms is not None
        assert pms_viewer_ms.role == "viewer"
        # platform-admin has team_role=None → no membership
        assert admin_ms is None
