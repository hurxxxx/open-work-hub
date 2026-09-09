from types import SimpleNamespace

from fastapi.testclient import TestClient

from dev_accounts import create_company_user_session, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.principal import system_principal, user_principal
from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy, AppUserGrant
from open_work_hub_api.domains.auth.app_availability import (
    is_company_app_enabled,
    load_app_availability_snapshot,
)
from open_work_hub_api.domains.auth.app_catalog import get_app_catalog_item
from open_work_hub_api.domains.auth.app_gate import is_app_enabled_for_principal
from open_work_hub_api.domains.auth.models import CompanyAppControl, User


def test_app_admission_requires_company_master_and_selected_user(client: TestClient) -> None:
    member = create_company_user_session(
        client,
        login_id="admission-member",
        email="admission@example.test",
        full_name="Admission Member",
    )
    with get_session_factory()() as db:
        policy = db.get(AppAccessPolicy, "docs")
        policy.audience = "selected"
        db.flush()
        assert not can_use_app(db, user_id=member["user"]["id"], app_id="docs")
        db.add(AppUserGrant(app_id="docs", user_id=member["user"]["id"]))
        db.flush()
        assert can_use_app(db, user_id=member["user"]["id"], app_id="docs")
        db.get(CompanyAppControl, "docs").enabled = False
        db.flush()
        assert not can_use_app(db, user_id=member["user"]["id"], app_id="docs")


def test_missing_policy_or_master_and_unknown_apps_fail_closed(client: TestClient) -> None:
    session = dev_login(client, "administrator")
    with get_session_factory()() as db:
        assert can_use_app(db, user_id=session["user"]["id"], app_id="docs")
        db.delete(db.get(AppAccessPolicy, "docs"))
        db.flush()
        assert not can_use_app(db, user_id=session["user"]["id"], app_id="docs")
        db.delete(db.get(CompanyAppControl, "docs"))
        db.flush()
        assert not is_company_app_enabled(db, "docs")
        assert not is_company_app_enabled(db, "unknown-app")
        assert not can_use_app(db, user_id=session["user"]["id"], app_id="unknown-app")


def test_feature_flag_is_required_even_with_company_master_enabled(client: TestClient) -> None:
    dev_login(client, "administrator")
    with get_session_factory()() as db:
        app = get_app_catalog_item("agent-terminal")
        assert app is not None
        db.get(CompanyAppControl, app.app_id).enabled = True
        db.flush()
        disabled = load_app_availability_snapshot(
            db, settings=SimpleNamespace(agent_terminal_enabled=False)
        )
        enabled = load_app_availability_snapshot(
            db, settings=SimpleNamespace(agent_terminal_enabled=True)
        )
        assert not disabled.company_enabled(app)
        assert enabled.company_enabled(app)


def test_principal_gate_requires_current_active_user(client: TestClient) -> None:
    session = dev_login(client, "administrator")
    with get_session_factory()() as db:
        principal = user_principal(user_id=session["user"]["id"], source="test.admission")
        assert is_app_enabled_for_principal(db, principal, "docs")
        assert not is_app_enabled_for_principal(db, system_principal(source="test.system"), "docs")
        db.get(User, session["user"]["id"]).login_blocked = True
        db.flush()
        assert not is_app_enabled_for_principal(db, principal, "docs")
