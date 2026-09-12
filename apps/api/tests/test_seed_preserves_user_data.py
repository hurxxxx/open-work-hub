"""Company bootstrap is idempotent and preserves app policies and business data."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_dev_accounts() -> None:
    from dev_accounts import configure_company_app_access
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.access import ensure_dev_login_seed_data

    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
        configure_company_app_access(db)


def test_seeded_dev_account_supports_configured_password_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from open_work_hub_api.core.settings import get_settings

    password = "test-seeded-account-password"
    monkeypatch.setenv("OPEN_WORK_HUB_API_DEV_LOGIN_PASSWORD", password)
    get_settings.cache_clear()
    _seed_dev_accounts()

    response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "administrator",
            "password": password,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["user"]["login_id"] == "administrator"
    assert payload["user"]["email"] == "admin@open-work-hub.local"
    assert "platform_admin" in payload["user"]["system_roles"]
    assert payload["token"]
    me = client.get("/api/v1/auth/me", headers=_auth_headers(payload["token"]))
    assert me.status_code == 200, me.text
    assert me.json()["id"] == payload["user"]["id"]
    rejected = client.post(
        "/api/v1/auth/login", json={"login_id": "administrator", "password": "wrong-password"}
    )
    assert rejected.status_code == 401, rejected.text
    assert rejected.json()["code"] == "auth.invalid_credentials"


def test_seed_preserves_user_created_space_membership(client: TestClient) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.access import ensure_seed_data
    from open_work_hub_api.domains.pms.space_models import TeamMember

    _seed_dev_accounts()

    # Log in as the company member account and create a new PMS space.
    login_response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": "administrator"},
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
        "/api/v1/pms/spaces",
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
    from open_work_hub_api.domains.pms.space_models import TeamMember
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
        "/api/v1/pms/spaces",
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
        "/api/v1/pms/spaces",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200
    assert any(item["id"] == space_id for item in list_response.json())


def test_seed_recreates_missing_app_as_disabled_without_granting_access(client: TestClient) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.access import ensure_dev_login_seed_data
    from open_work_hub_api.domains.auth.models import CompanyAppControl
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy

    _seed_dev_accounts()
    with get_session_factory()() as db:
        db.delete(db.get(CompanyAppControl, "web-search"))
        db.commit()
        ensure_dev_login_seed_data(db)
        assert db.get(CompanyAppControl, "web-search").enabled is False
        assert db.get(AppAccessPolicy, "web-search").audience == "selected"


def test_seed_preserves_existing_master_and_audience_policy(client: TestClient) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.access import ensure_dev_login_seed_data, ensure_seed_data
    from open_work_hub_api.domains.auth.models import CompanyAppControl
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy

    _seed_dev_accounts()
    with get_session_factory()() as db:
        db.get(CompanyAppControl, "docs").enabled = False
        db.get(AppAccessPolicy, "pms").audience = "selected"
        db.commit()
        ensure_seed_data(db)
        ensure_dev_login_seed_data(db)
        assert db.get(CompanyAppControl, "docs").enabled is False
        assert db.get(AppAccessPolicy, "pms").audience == "selected"


def test_core_seed_does_not_create_implicit_business_spaces(client: TestClient) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.pms.space_models import Team, TeamMember

    _seed_dev_accounts()
    with get_session_factory()() as db:
        assert db.scalar(select(Team.id)) is None
        assert db.scalar(select(TeamMember.id)) is None


def test_initial_dev_seed_enables_apps_but_repeated_seed_keeps_admin_choices(
    client: TestClient,
) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.access import ensure_dev_login_seed_data
    from open_work_hub_api.domains.auth.models import CompanyAppControl
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
    from open_work_hub_api.domains.auth.app_catalog import iter_app_catalog

    with get_session_factory()() as db:
        db.execute(delete(CompanyAppControl))
        db.commit()
        ensure_dev_login_seed_data(db)
        for app in iter_app_catalog():
            assert db.get(CompanyAppControl, app.app_id).enabled is True
            assert db.get(AppAccessPolicy, app.app_id).audience == "all"
        db.get(CompanyAppControl, "docs").enabled = False
        db.get(AppAccessPolicy, "pms").audience = "selected"
        db.commit()
        ensure_dev_login_seed_data(db)
        assert db.get(CompanyAppControl, "docs").enabled is False
        assert db.get(AppAccessPolicy, "pms").audience == "selected"
