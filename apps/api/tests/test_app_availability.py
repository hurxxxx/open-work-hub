from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from dev_accounts import dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.principal import system_principal
from open_work_hub_api.domains.auth.app_availability import (
    is_platform_app_enabled,
    is_workspace_app_enabled,
    load_app_availability_snapshot,
)
from open_work_hub_api.domains.auth.models import (
    CompanyAppControl,
    Workspace,
    WorkspaceAppDefault,
    WorkspaceAppOverride,
)
from open_work_hub_api.domains.auth.workspace_apps import get_workspace_app_catalog_item
from open_work_hub_api.domains.auth.workspace_app_gate import is_app_enabled_for_principal


def _general_workspace_id(client: TestClient) -> str:
    dev_login(client, "administrator")
    with get_session_factory()() as db:
        workspace_id = db.scalar(select(Workspace.id).where(Workspace.key == "general"))
    assert workspace_id is not None
    return workspace_id


def test_app_availability_truth_table_and_company_master_precedence(
    client: TestClient,
) -> None:
    workspace_id = _general_workspace_id(client)
    with get_session_factory()() as db:
        assert is_workspace_app_enabled(db, workspace_id, "docs") is True

        default = db.get(WorkspaceAppDefault, "docs")
        assert default is not None
        default.enabled = False
        db.add(default)
        db.flush()
        assert is_workspace_app_enabled(db, workspace_id, "docs") is False

        override = WorkspaceAppOverride(
            workspace_id=workspace_id,
            app_id="docs",
            enabled=True,
        )
        db.add(override)
        db.flush()
        assert is_workspace_app_enabled(db, workspace_id, "docs") is True

        company_control = db.get(CompanyAppControl, "docs")
        assert company_control is not None
        company_control.enabled = False
        db.add(company_control)
        db.flush()
        assert is_workspace_app_enabled(db, workspace_id, "docs") is False


def test_app_availability_missing_rows_and_unknown_apps_fail_closed(
    client: TestClient,
) -> None:
    workspace_id = _general_workspace_id(client)
    with get_session_factory()() as db:
        company_control = db.get(CompanyAppControl, "docs")
        assert company_control is not None
        db.delete(company_control)
        db.flush()

        assert is_workspace_app_enabled(db, workspace_id, "docs") is False
        assert is_workspace_app_enabled(db, workspace_id, "unknown-app") is False
        assert is_platform_app_enabled(db, "unknown-app") is False


def test_feature_flag_and_scope_are_part_of_the_same_snapshot(
    client: TestClient,
) -> None:
    workspace_id = _general_workspace_id(client)
    with get_session_factory()() as db:
        agent_terminal = get_workspace_app_catalog_item("agent-terminal")
        mail = get_workspace_app_catalog_item("mail")
        docs = get_workspace_app_catalog_item("docs")
        assert agent_terminal is not None
        assert mail is not None
        assert docs is not None

        disabled_snapshot = load_app_availability_snapshot(
            db,
            workspace_ids=(workspace_id,),
            settings={"agent_terminal_enabled": False},
        )
        enabled_snapshot = load_app_availability_snapshot(
            db,
            workspace_ids=(workspace_id,),
            settings={"agent_terminal_enabled": True},
        )

        assert disabled_snapshot.platform_enabled(agent_terminal) is False
        assert enabled_snapshot.platform_enabled(agent_terminal) is True
        assert enabled_snapshot.workspace_enabled(mail, workspace_id) is False
        assert enabled_snapshot.platform_enabled(docs) is False


def test_generic_non_user_principals_do_not_bypass_user_or_role_policy(
    client: TestClient,
) -> None:
    workspace_id = _general_workspace_id(client)
    with get_session_factory()() as db:
        assert is_workspace_app_enabled(db, workspace_id, "docs") is True
        assert (
            is_app_enabled_for_principal(
                db,
                system_principal(
                    workspace_id=workspace_id,
                    source="test.system",
                ),
                "docs",
            )
            is False
        )
