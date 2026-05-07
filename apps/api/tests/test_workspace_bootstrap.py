from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.llm import get_supported_llm_tasks
from ai_do_api.domains.ai.models import LlmPolicy
from ai_do_api.domains.ai.registry import get_ai_capability_registry
from ai_do_api.domains.auth import access as auth_access
from ai_do_api.domains.auth.access import ensure_dev_login_seed_data
from ai_do_api.domains.auth.models import Workspace, WorkspaceAppEntitlement


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200
    return response.json()


def test_workspace_bootstrap_returns_entitled_apps_and_nav(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["workspace"]["slug"] == "ai-tft"
    assert {item["app_id"] for item in payload["apps"]} >= {
        "home",
        "ai",
        "pms",
        "docs",
        "whiteboard",
        "planner",
        "meeting",
    }
    assert any(item["id"] == "meeting-minutes" for item in payload["nav"])
    assert any(item["id"] == "pms-tasks-assigned" for item in payload["nav"])


def test_ai_tft_workspace_seed_and_admin_membership(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]

    workspaces = {item["slug"]: item for item in session["user"]["workspaces"]}
    assert workspaces["administrator"]["name"] == "Administrator"
    assert workspaces["administrator"]["role"] == "admin"
    assert workspaces["ai-tft"]["name"] == "AI TFT"
    assert workspaces["ai-tft"]["role"] == "admin"

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace"]["slug"] == "ai-tft"
    assert payload["workspace"]["name"] == "AI TFT"

    spaces_response = client.get(
        "/api/v1/workspaces/ai-tft/pms/spaces",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert spaces_response.status_code == 200
    assert any(item["current_user_role"] == "owner" for item in spaces_response.json())


def test_workspace_bootstrap_hides_disabled_app(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "ai-tft"))
        assert workspace is not None
        entitlement = db.scalar(
            select(WorkspaceAppEntitlement).where(
                WorkspaceAppEntitlement.workspace_id == workspace.id,
                WorkspaceAppEntitlement.app_id == "ai",
            )
        )
        assert entitlement is not None
        entitlement.enabled = False
        db.add(entitlement)
        db.commit()

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "ai" not in {item["app_id"] for item in payload["apps"]}
    assert all(item["app_id"] != "ai" for item in payload["nav"])


def test_ensure_seed_data_skips_entitlements_until_migration_exists(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        auth_access,
        "_workspace_app_entitlements_table_exists",
        lambda db: False,
    )

    with get_session_factory()() as db:
        auth_access.ensure_seed_data(db)
        workspace_count = len(db.scalars(select(Workspace)).all())

    assert workspace_count > 0


def test_workspace_bootstrap_falls_back_to_default_catalog_without_entitlement_table(
    client: TestClient,
    monkeypatch,
) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]
    monkeypatch.setattr(
        auth_access,
        "_workspace_app_entitlements_table_exists",
        lambda db: False,
    )

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert {item["app_id"] for item in payload["apps"]} >= {
        "home",
        "ai",
        "pms",
        "docs",
        "whiteboard",
        "planner",
        "meeting",
    }


def test_registry_drives_llm_task_seed_and_tool_metadata(client: TestClient) -> None:
    registry = get_ai_capability_registry()
    task_kinds = {item.task_kind for item in get_supported_llm_tasks()}

    assert {
        "chatbot",
        "meeting_summary",
        "meeting_insight_actions",
        "meeting_insight_decisions",
        "meeting_insight_followup",
        "batch_generation",
    } <= task_kinds
    assert {
        "pms.search_issues",
        "docs.list_hub",
        "meeting.find_availability",
        "meeting.extract_actions",
        "meeting.extract_decisions",
        "meeting.draft_followup_schedule",
        "planner.list_events",
    } <= set(registry.tools.keys())
    assert all(tool.handler is not None for tool in registry.tools.values())

    with get_session_factory()() as db:
        seeded_task_kinds = set(db.scalars(select(LlmPolicy.task_kind)).all())

    assert task_kinds <= seeded_task_kinds
