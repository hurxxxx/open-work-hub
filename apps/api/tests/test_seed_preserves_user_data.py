"""Regression: ensure_seed_data must not clobber user-created spaces.

The original seed loop scanned each seed user's TeamMember rows and deleted
anything that wasn't the default PMS space. That wiped out user-created
spaces on every app boot because ``init_db()`` calls ``ensure_seed_data()``
at startup — users would create a space, restart the API, and find their
space was still there but the membership row behind it was gone.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import delete, select


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_dev_accounts() -> None:
    """Run the full dev-login seed loop so the /auth/dev-login route can
    find the seeded fixtures (ensure_dev_login_seed_data delegates to
    ensure_seed_data internally)."""
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.access import ensure_dev_login_seed_data

    session_factory = get_session_factory()
    with session_factory() as db:
        ensure_dev_login_seed_data(db)
        db.commit()


def test_seed_preserves_user_created_space_membership(client: TestClient) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.access import ensure_seed_data
    from open_work_hub_api.domains.auth.models import TeamMember

    _seed_dev_accounts()

    # Log in as the seeded workspace member account and create a new PMS space.
    login_response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": "administrator"},
    )
    assert login_response.status_code == 200, login_response.text
    session = login_response.json()
    token = session["token"]
    user_id = session["user"]["id"]

    create_response = client.post(
        "/api/v1/workspaces/general/pms/spaces",
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
        assert membership is not None, "create_space should register the creator as a TeamMember"
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
        "/api/v1/workspaces/general/pms/spaces",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200
    space_ids = {item["id"] for item in list_response.json()}
    assert new_space_id in space_ids


def test_dev_login_is_idempotent_and_preserves_user_spaces(
    client: TestClient,
) -> None:
    """Logging in multiple times (a very common dev loop: bootstrap-status
    on load, then dev-login on button click, then another account switch)
    must NOT rerun the seed reconciler against already-seeded accounts.

    Before the guard landed, each of those requests walked every seed user's
    TeamMember rows and wiped out anything outside the default PMS space,
    destroying user-created spaces on every login."""
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.models import TeamMember
    from sqlalchemy import select

    _seed_dev_accounts()

    # administrator creates a private space.
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": "administrator"},
    )
    assert login.status_code == 200
    token = login.json()["token"]
    user_id = login.json()["user"]["id"]

    create = client.post(
        "/api/v1/workspaces/general/pms/spaces",
        headers=_auth_headers(token),
        json={"name": "Private Space", "description": ""},
    )
    assert create.status_code == 201
    space_id = create.json()["id"]

    session_factory = get_session_factory()

    def owner_row() -> TeamMember | None:
        with session_factory() as db:
            return db.scalar(
                select(TeamMember).where(
                    TeamMember.team_id == space_id,
                    TeamMember.user_id == user_id,
                )
            )

    assert owner_row() is not None

    # Simulate the dev flow: open login screen (bootstrap-status), then log
    # in as administrator, then back to administrator. Each of these calls
    # used to re-run ensure_dev_login_seed_data.
    for _ in range(3):
        assert client.get("/api/v1/auth/bootstrap-status").status_code == 200
        assert (
            client.post("/api/v1/auth/dev-login", json={"account_key": "administrator"}).status_code
            == 200
        )
        assert (
            client.post("/api/v1/auth/dev-login", json={"account_key": "administrator"}).status_code
            == 200
        )

    assert owner_row() is not None, (
        "dev-login / bootstrap-status rerunning the seed loop wiped out the "
        "user's self-created space membership."
    )

    # The user-created space should also still be listed.
    list_response = client.get(
        "/api/v1/workspaces/general/pms/spaces",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200
    assert any(item["id"] == space_id for item in list_response.json())


def test_dev_login_seed_syncs_new_workspace_app_catalog_rows(
    client: TestClient,
) -> None:
    """A completed dev seed must still pick up newly shipped app catalog rows.

    The full seed reconciler stays guarded to preserve user data, but app
    visibility rows are additive product metadata and need to be inserted when
    a new app such as web-search is added after a DB already exists.
    """
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.access import ensure_dev_login_seed_data
    from open_work_hub_api.domains.auth.models import (
        PlatformAppVisibility,
        Workspace,
        WorkspaceAppEntitlement,
    )

    _seed_dev_accounts()
    session_factory = get_session_factory()

    with session_factory() as db:
        workspace_ids = set(db.scalars(select(Workspace.id)).all())
        assert workspace_ids
        db.execute(
            delete(WorkspaceAppEntitlement).where(
                WorkspaceAppEntitlement.app_id == "web-search"
            )
        )
        db.execute(
            delete(PlatformAppVisibility).where(
                PlatformAppVisibility.app_id == "web-search"
            )
        )
        db.commit()

    with session_factory() as db:
        ensure_dev_login_seed_data(db)
        db.commit()

    with session_factory() as db:
        web_search_workspace_ids = set(
            db.scalars(
                select(WorkspaceAppEntitlement.workspace_id).where(
                    WorkspaceAppEntitlement.app_id == "web-search"
                )
            ).all()
        )
        visible = db.scalar(
            select(PlatformAppVisibility.visible).where(
                PlatformAppVisibility.app_id == "web-search"
            )
        )
        assert workspace_ids <= web_search_workspace_ids
        assert visible is True


def test_ensure_seed_data_does_not_overwrite_workspace_renames(
    client: TestClient,
) -> None:
    """``ensure_seed_data`` rewrote workspace name/description back to the
    canonical defaults every time it ran, which made admin-console renames
    silently revert on the next server restart. The guard should skip the
    reconcile entirely once the infrastructure is in place."""
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.access import ensure_seed_data
    from open_work_hub_api.domains.auth.models import Workspace
    from sqlalchemy import select

    _seed_dev_accounts()
    session_factory = get_session_factory()
    workspace_key = "general"

    with session_factory() as db:
        ws = db.scalar(select(Workspace).where(Workspace.key == workspace_key))
        assert ws is not None
        ws.name = "Custom PMS Name"
        ws.description = "Admin-edited description"
        db.add(ws)
        db.commit()

    # Rerun seed. The guard should short-circuit and leave the edits alone.
    with session_factory() as db:
        ensure_seed_data(db)
        db.commit()

    with session_factory() as db:
        ws = db.scalar(select(Workspace).where(Workspace.key == workspace_key))
        assert ws is not None
        assert ws.name == "Custom PMS Name", (
            "ensure_seed_data is still overwriting workspace names on rerun"
        )
        assert ws.description == "Admin-edited description"


def test_seed_still_reconciles_default_space_membership(
    client: TestClient,
) -> None:
    """The seed loop should still enforce the team_role declared in
    DEV_LOGIN_ACCOUNTS against the default PMS spaces for Administrator and
    General Workspace."""
    _seed_dev_accounts()

    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.models import Team, TeamMember, User, Workspace

    session_factory = get_session_factory()
    with session_factory() as db:
        # Seed accounts by email
        def membership_for(email: str, workspace_key: str) -> TeamMember | None:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                return None
            return db.scalar(
                select(TeamMember)
                .join(Team, Team.id == TeamMember.team_id)
                .join(Workspace, Workspace.id == Team.workspace_id)
                .where(
                    TeamMember.user_id == user.id,
                    Team.key == "team-space",
                    Workspace.key == workspace_key,
                )
            )

        administrator_space_ms = membership_for("admin@open-work-hub.local", "administrator")
        general_space_ms = membership_for("admin@open-work-hub.local", "general")

        assert administrator_space_ms is not None, (
            "administrator should own the Administrator default space"
        )
        assert administrator_space_ms.role == "owner"
        assert general_space_ms is not None, "administrator should own the General Workspace default space"
        assert general_space_ms.role == "owner"


def test_dev_login_recreates_missing_dev_workspace_seeds(
    client: TestClient,
) -> None:
    from sqlalchemy.orm import selectinload

    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.models import Team, Workspace

    _seed_dev_accounts()
    session_factory = get_session_factory()

    with session_factory() as db:
        general_workspace = db.scalar(
            select(Workspace)
            .options(
                selectinload(Workspace.user_bindings),
                selectinload(Workspace.teams).selectinload(Team.members),
            )
            .where(Workspace.key == "general")
        )
        assert general_workspace is not None
        db.delete(general_workspace)
        db.commit()

    login_response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": "administrator"},
    )
    assert login_response.status_code == 200, login_response.text
    assert any(
        workspace["slug"] == "general" for workspace in login_response.json()["user"]["workspaces"]
    )

    with session_factory() as db:
        restored_workspace = db.scalar(select(Workspace).where(Workspace.key == "general"))
        assert restored_workspace is not None
