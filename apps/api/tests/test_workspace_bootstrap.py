from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import dev_login
from sqlalchemy import select

from open_alm_api.core.db import get_session_factory
from open_alm_api.core.llm import get_supported_llm_tasks
from open_alm_api.core.settings import Settings, get_settings
from open_alm_api.domains.ai.chat_context_policy import filter_business_chat_context_app_ids
from open_alm_api.domains.ai.registry import (
    get_ai_capability_registry,
    get_chatbot_capable_app_ids,
)
from open_alm_api.domains.auth import access as auth_access
from open_alm_api.domains.auth.models import (
    PlatformAppVisibility,
    Workspace,
    WorkspaceAppEntitlement,
)
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.auth.workspace_apps import (
    WorkspaceAppCatalogItem,
    WorkspaceNavCatalogItem,
    iter_workspace_app_catalog,
)
from open_alm_api.domains.auth.workspace_bootstrap_projection import project_workspace_bootstrap_apps


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def test_workspace_app_catalog_is_a_unique_leaf_app_registry() -> None:
    app_ids = [item.app_id for item in iter_workspace_app_catalog()]

    assert app_ids[0] == "home"
    assert len(app_ids) == len(set(app_ids))
    assert {"ai", "collaboration", "business"}.isdisjoint(app_ids)


def test_workspace_entitlement_seed_policy_uses_launcher_metadata() -> None:
    fixed_app = WorkspaceAppCatalogItem(
        app_id="fixed-app",
        title="Fixed",
        route_base="/fixed-app",
        icon_key="home",
        launcher_fixed=True,
    )
    non_fixed_home = WorkspaceAppCatalogItem(
        app_id="home",
        title="Home-like app",
        route_base="/home-like-app",
        icon_key="home",
        launcher_fixed=False,
    )
    platform_app = WorkspaceAppCatalogItem(
        app_id="platform-app",
        title="Platform app",
        route_base="/platform-app",
        icon_key="home",
        availability_scope="platform",
    )

    assert auth_access._workspace_app_should_have_entitlement(fixed_app) is False
    assert auth_access._workspace_app_should_have_entitlement(non_fixed_home) is True
    assert auth_access._workspace_app_should_have_entitlement(platform_app) is False


def test_workspace_bootstrap_returns_entitled_apps_and_nav(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_LEGACY_ISSUE_COMPRESSOR_ENABLED", "0")
    get_settings.cache_clear()
    session = _dev_login(client, "administrator")
    token = session["token"]

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["workspace"]["slug"] == "ai-tft"
    app_ids = {item["app_id"] for item in payload["apps"]}
    stale_category_app_ids = {
        "ai",
        "collaboration",
        "business",
    }
    assert stale_category_app_ids.isdisjoint(app_ids)
    assert {
        "home",
        "pms",
        "docs",
        "legacy-issues",
        "data-viz",
        "learning",
        "spec-compare",
        "ppt-assistant",
        "retrieval-search",
    } <= app_ids
    assert "extensions" not in app_ids
    assert "image-wizard" not in app_ids
    apps_by_id = {item["app_id"]: item for item in payload["apps"]}
    assert apps_by_id["chatbot"]["coming_soon"] is True
    assert payload["app_bar_categories"] == []
    assert all(item["id"] != "meeting-minutes" for item in payload["nav"])
    assert all("feature_app_id" not in item for item in payload["nav"])
    spec_compare = next(item for item in payload["nav"] if item["id"] == "spec-compare")
    assert spec_compare["coming_soon"] is False
    assert spec_compare["app_id"] == "spec-compare"
    ppt_assistant = next(item for item in payload["nav"] if item["id"] == "ppt-assistant")
    assert ppt_assistant["coming_soon"] is False
    assert ppt_assistant["app_id"] == "ppt-assistant"
    retrieval_search = next(item for item in payload["nav"] if item["id"] == "retrieval-search")
    assert retrieval_search["coming_soon"] is False
    assert retrieval_search["app_id"] == "retrieval-search"
    assert retrieval_search["category"] == "Business AI"
    data_viz = next(item for item in payload["nav"] if item["id"] == "data-viz")
    assert data_viz["app_id"] == "data-viz"
    learning_home = next(item for item in payload["nav"] if item["id"] == "learning-home")
    assert learning_home["app_id"] == "learning"
    assert any(item["id"] == "pms-tasks-assigned" for item in payload["nav"])
    assert payload["chatbot_app_ids"] == filter_business_chat_context_app_ids(
        app_id for app_id in get_chatbot_capable_app_ids() if app_id in app_ids
    )
    keyword_entities = {item["value"]: item for item in payload["keyword_search"]["entity_types"]}
    keyword_entity_types = set(keyword_entities)
    assert {"doc", "pms_task"} <= keyword_entity_types
    assert keyword_entities["doc"]["label_key"] == "ai.search.entityDoc"
    assert keyword_entities["pms_task"]["label_key"] == "ai.search.entityPms"
    assert "planner_event" not in keyword_entity_types
    assert {"mail", "planner", "community", "news", "qa-assistant"}.isdisjoint(app_ids)
    assert all(
        item["app_id"] not in {"mail", "planner", "community", "news", "qa-assistant"}
        for item in payload["nav"]
    )
    assert stale_category_app_ids.isdisjoint({item["app_id"] for item in payload["nav"]})
    assert all(item["id"] != "image-wizard" for item in payload["nav"])
    assert all(item["app_id"] != "extensions" for item in payload["nav"])
    patent_automation = next(
        item
        for item in payload["nav"]
        if item["app_id"] == "patent-automation" and item["id"] == "patent-automation"
    )
    assert patent_automation["path_suffix"] is None
    get_settings.cache_clear()


def test_apps_bootstrap_projects_platform_apps_and_personal_tools(
    client: TestClient,
) -> None:
    session = _dev_login(client, "administrator")

    response = client.get(
        "/api/v1/apps/bootstrap",
        headers={"Authorization": f"Bearer {session['token']}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    app_ids = {item["app_id"] for item in payload["apps"]}
    personal_tool_ids = {item["app_id"] for item in payload["personal_tools"]}
    categorized_app_ids = {
        item["app_id"] for category in payload["app_bar_categories"] for item in category["items"]
    }
    assert {"mail", "planner", "news", "qa-assistant"} <= app_ids
    assert "docs" not in app_ids
    apps_by_id = {item["app_id"]: item for item in payload["apps"]}
    assert apps_by_id["qa-assistant"]["icon_key"] == "message-circle-question"
    assert apps_by_id["qa-assistant"]["availability_scope"] == "platform"
    assert personal_tool_ids == {"mail", "planner"}
    assert {"mail", "planner"}.isdisjoint(categorized_app_ids)
    assert payload["principal"]["scope"] == "personal"
    assert payload["principal"]["workspace_id"] is None
    assert set(payload["platform_enabled_app_ids"]) == app_ids


def test_apps_bootstrap_hard_hides_platform_disabled_app(
    client: TestClient,
) -> None:
    session = _dev_login(client, "administrator")
    with get_session_factory()() as db:
        row = db.scalar(select(PlatformAppVisibility).where(PlatformAppVisibility.app_id == "mail"))
        assert row is not None
        row.visible = False
        db.add(row)
        db.commit()

    response = client.get(
        "/api/v1/apps/bootstrap",
        headers={"Authorization": f"Bearer {session['token']}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "mail" not in {item["app_id"] for item in payload["apps"]}
    assert "mail" not in {item["app_id"] for item in payload["personal_tools"]}
    assert "mail" not in payload["platform_enabled_app_ids"]


def test_workspace_bootstrap_exposes_legacy_issues_without_implicit_category(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_LEGACY_ISSUE_COMPRESSOR_ENABLED", "0")
    get_settings.cache_clear()
    session = _dev_login(client, "administrator")
    token = session["token"]

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "extensions" not in {item["app_id"] for item in payload["apps"]}
    assert "legacy-issues" in {item["app_id"] for item in payload["apps"]}
    assert payload["app_bar_categories"] == []
    legacy_issue_items = {
        item["id"]: item for item in payload["nav"] if item["app_id"] == "legacy-issues"
    }
    assert {
        "legacy-issues-assistant",
        "legacy-issues-assistant-history",
        "legacy-issues-field-settings",
        "legacy-issues-common-code",
        "legacy-issues-common-master",
        "legacy-issues-vehicle-checklists",
        "legacy-issues-vehicle-management",
        "legacy-issues-aircon",
        "legacy-issues-electrical-mechanical",
        "legacy-issues-electrical-control-hw",
        "legacy-issues-electrical-control-sw",
        "legacy-issues-interior",
        "legacy-issues-cooling-module",
    } <= legacy_issue_items.keys()
    assert {
        "legacy-issues-compressor-mechanical",
        "legacy-issues-compressor-electric",
    }.isdisjoint(legacy_issue_items)
    assert legacy_issue_items["legacy-issues-common-master"]["path_suffix"] == "/common-master"
    assert (
        legacy_issue_items["legacy-issues-vehicle-checklists"]["path_suffix"]
        == "/vehicle-checklists"
    )
    assert (
        legacy_issue_items["legacy-issues-electrical-control-hw"]["path_suffix"]
        == "/electrical/control/hw"
    )
    assert legacy_issue_items["legacy-issues-field-settings"]["path_suffix"] == "/settings/fields"
    assert (
        legacy_issue_items["legacy-issues-common-code"]["path_suffix"] == "/settings/common-codes"
    )
    assert (
        legacy_issue_items["legacy-issues-vehicle-management"]["path_suffix"]
        == "/settings/vehicle-models"
    )
    get_settings.cache_clear()


def test_legacy_issue_compressor_setting_defaults_off_and_accepts_env_alias(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPEN_ALM_LEGACY_ISSUE_COMPRESSOR_ENABLED", raising=False)
    postgres_dsn = "postgresql+psycopg://open_alm_test:open_alm_test@127.0.0.1:5432/open_alm_test"

    disabled_settings = Settings(_env_file=None, postgres_dsn=postgres_dsn)
    enabled_settings = Settings(
        _env_file=None,
        postgres_dsn=postgres_dsn,
        OPEN_ALM_LEGACY_ISSUE_COMPRESSOR_ENABLED="1",
    )

    assert disabled_settings.legacy_issue_compressor_enabled is False
    assert enabled_settings.legacy_issue_compressor_enabled is True


def test_workspace_bootstrap_includes_compressor_nav_when_feature_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_LEGACY_ISSUE_COMPRESSOR_ENABLED", "1")
    get_settings.cache_clear()
    session = _dev_login(client, "administrator")
    token = session["token"]

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    compressor_items = {
        item["id"]: item
        for item in payload["nav"]
        if item["category"] == "legacy-issues-compressor"
    }

    assert set(compressor_items) == {
        "legacy-issues-compressor-mechanical",
        "legacy-issues-compressor-electric",
    }
    assert compressor_items["legacy-issues-compressor-mechanical"]["path_suffix"] == (
        "/compressor/mechanical"
    )
    assert compressor_items["legacy-issues-compressor-electric"]["path_suffix"] == (
        "/compressor/electric"
    )
    get_settings.cache_clear()


def test_workspace_bootstrap_projection_builds_apps_and_flat_nav() -> None:
    catalog = (
        WorkspaceAppCatalogItem(
            app_id="toolbox",
            title="Toolbox",
            route_base="/toolbox",
            icon_key="brain",
            nav_items=(
                WorkspaceNavCatalogItem(
                    id="search",
                    app_id="toolbox",
                    title="Search",
                    category="Core",
                    icon_key="search",
                    path_suffix="?q=1",
                ),
                WorkspaceNavCatalogItem(
                    id="image-wizard",
                    app_id="toolbox",
                    title="Image Wizard",
                    category="Core",
                    icon_key="image",
                    feature_flag="image_enabled",
                ),
                WorkspaceNavCatalogItem(
                    id="linked-tool",
                    app_id="toolbox",
                    title="Linked Tool",
                    category="Assistants",
                    icon_key="mic",
                    link_app_id="meeting",
                    path_suffix="?tab=recordings",
                    coming_soon=True,
                ),
            ),
        ),
        WorkspaceAppCatalogItem(
            app_id="docs",
            title="DOCS",
            route_base="/docs",
            icon_key="file-text",
            nav_items=(
                WorkspaceNavCatalogItem(
                    id="docs-library",
                    app_id="docs",
                    title="Docs",
                    category="Documents",
                    icon_key="file-text",
                ),
            ),
        ),
        WorkspaceAppCatalogItem(
            app_id="mail",
            title="MAIL",
            route_base="/mail",
            icon_key="mail",
        ),
    )

    projection = project_workspace_bootstrap_apps(
        catalog,
        enabled_app_ids={"toolbox", "docs"},
        settings={"image_enabled": False},
    )

    assert [item["app_id"] for item in projection.apps] == ["toolbox", "docs"]
    assert [item["id"] for item in projection.nav] == [
        "search",
        "linked-tool",
        "docs-library",
    ]
    assert projection.apps[0]["nav_items"] == projection.nav[:2]
    assert projection.apps[1]["nav_items"] == projection.nav[2:]
    assert all(item["id"] != "image-wizard" for item in projection.nav)
    assert all(item["app_id"] != "mail" for item in projection.apps)

    search = projection.nav[0]
    assert search["path_suffix"] == "?q=1"
    assert search["absolute_path"] is None

    linked_tool = projection.nav[1]
    assert linked_tool["link_app_id"] == "meeting"
    assert linked_tool["path_suffix"] == "?tab=recordings"
    assert linked_tool["coming_soon"] is True

    docs_library = projection.nav[2]
    assert docs_library["absolute_path"] is None
    assert docs_library["path_suffix"] is None


def test_workspace_bootstrap_projection_includes_feature_flagged_nav() -> None:
    catalog = (
        WorkspaceAppCatalogItem(
            app_id="toolbox",
            title="Toolbox",
            route_base="/toolbox",
            icon_key="brain",
            nav_items=(
                WorkspaceNavCatalogItem(
                    id="image-wizard",
                    app_id="toolbox",
                    title="Image Wizard",
                    category="Core",
                    icon_key="image",
                    feature_flag="image_enabled",
                ),
            ),
        ),
    )

    projection = project_workspace_bootstrap_apps(
        catalog,
        enabled_app_ids={"toolbox"},
        settings={"image_enabled": True},
    )

    assert [item["id"] for item in projection.nav] == ["image-wizard"]


def test_workspace_bootstrap_projection_keeps_app_when_child_flag_is_disabled() -> None:
    catalog = (
        WorkspaceAppCatalogItem(
            app_id="toolbox",
            title="Toolbox",
            route_base="/toolbox",
            icon_key="brain",
            nav_items=(
                WorkspaceNavCatalogItem(
                    id="search",
                    app_id="toolbox",
                    title="Search",
                    category="Core",
                    icon_key="search",
                ),
                WorkspaceNavCatalogItem(
                    id="flagged-child",
                    app_id="toolbox",
                    title="Flagged child",
                    category="Core",
                    icon_key="image",
                    feature_flag="child_enabled",
                ),
            ),
        ),
    )

    projection = project_workspace_bootstrap_apps(
        catalog,
        enabled_app_ids={"toolbox"},
        settings={"child_enabled": False},
    )

    assert [item["app_id"] for item in projection.apps] == ["toolbox"]
    assert [item["id"] for item in projection.nav] == ["search"]


def test_workspace_bootstrap_includes_image_wizard_when_image_feature_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_IMAGE_ENABLED", "1")
    get_settings.cache_clear()

    session = _dev_login(client, "administrator")
    token = session["token"]

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert any(item["id"] == "image-wizard" for item in payload["nav"])
    assert "image-wizard" in {item["app_id"] for item in payload["apps"]}
    get_settings.cache_clear()


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


def test_workspace_bootstrap_ignores_stale_category_app_entitlement(
    client: TestClient,
) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "ai-tft"))
        assert workspace is not None
        db.add(
            WorkspaceAppEntitlement(
                id=new_id(),
                workspace_id=workspace.id,
                app_id="ai",
                visibility_override=False,
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "ai" not in {item["app_id"] for item in payload["apps"]}
    assert all(item["app_id"] != "ai" for item in payload["nav"])
    assert "docs" in {item["app_id"] for item in payload["apps"]}


def test_workspace_bootstrap_hides_app_with_workspace_visibility_override(
    client: TestClient,
) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "ai-tft"))
        assert workspace is not None
        entitlement = db.scalar(
            select(WorkspaceAppEntitlement).where(
                WorkspaceAppEntitlement.workspace_id == workspace.id,
                WorkspaceAppEntitlement.app_id == "docs",
            )
        )
        assert entitlement is not None
        entitlement.visibility_override = False
        db.add(entitlement)
        db.commit()

    response = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "docs" not in {item["app_id"] for item in payload["apps"]}
    assert all(item["app_id"] != "docs" for item in payload["nav"])
    assert "doc" not in {item["value"] for item in payload["keyword_search"]["entity_types"]}


def test_workspace_app_gate_checks_leaf_visibility_override(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]
    headers = {"Authorization": f"Bearer {token}"}
    path = "/api/v1/workspaces/ai-tft/legacy-issues/org-units"

    enabled_response = client.get(path, headers=headers)
    assert enabled_response.status_code == 200, enabled_response.text

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "ai-tft"))
        assert workspace is not None
        entitlement = db.scalar(
            select(WorkspaceAppEntitlement).where(
                WorkspaceAppEntitlement.workspace_id == workspace.id,
                WorkspaceAppEntitlement.app_id == "legacy-issues",
            )
        )
        assert entitlement is not None
        entitlement.visibility_override = False
        db.add(entitlement)
        db.commit()

    disabled_response = client.get(path, headers=headers)
    assert disabled_response.status_code == 403
    assert disabled_response.json()["code"] == "legacy_issues.app_disabled"


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
        "pms",
        "docs",
    }
    assert "qa-assistant" not in {item["app_id"] for item in payload["apps"]}
    assert {"ai", "collaboration", "business"}.isdisjoint(
        {item["app_id"] for item in payload["apps"]}
    )
    enabled_app_ids = {item["app_id"] for item in payload["apps"]}
    assert payload["chatbot_app_ids"] == filter_business_chat_context_app_ids(
        app_id for app_id in get_chatbot_capable_app_ids() if app_id in enabled_app_ids
    )


def test_registry_drives_llm_task_seed_and_tool_metadata(client: TestClient) -> None:
    registry = get_ai_capability_registry()
    task_kinds = {item.task_kind for item in get_supported_llm_tasks()}

    assert {
        "chatbot",
        "meeting_summary",
        "meeting_insight_actions",
        "meeting_insight_decisions",
        "meeting_insight_followup",
        "patent_invoice_extract",
        "ppt_generate",
        "spec_compare_compare",
        "spec_compare_extract",
        "spec_compare_report",
    } <= task_kinds
    assert {
        "pms.search_tasks",
        "docs.list_hub",
        "meeting.find_availability",
        "meeting.extract_actions",
        "meeting.extract_decisions",
        "meeting.draft_followup_schedule",
        "planner.list_events",
    } <= set(registry.tools.keys())
    assert all(tool.handler is not None for tool in registry.tools.values())
