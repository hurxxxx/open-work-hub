from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import dev_login
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.llm import get_supported_llm_tasks
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import (
    get_ai_capability_registry,
)
from open_work_hub_api.domains.auth import access as auth_access
from open_work_hub_api.domains.auth.workspace_app_features import (
    is_workspace_catalog_feature_enabled,
)
from open_work_hub_api.domains.auth.models import (
    CompanyAppControl,
    PlatformAppBarCategory,
    PlatformAppBarCategoryApp,
    Workspace,
    WorkspaceAppDefault,
    WorkspaceAppOverride,
)
from open_work_hub_api.domains.auth.workspace_apps import (
    WorkspaceAppCatalogItem,
    WorkspaceNavCatalogItem,
    iter_workspace_app_catalog,
)
from open_work_hub_api.domains.auth.workspace_bootstrap_projection import (
    project_workspace_bootstrap_apps,
)


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def test_workspace_app_catalog_is_a_unique_leaf_app_registry() -> None:
    app_ids = [item.app_id for item in iter_workspace_app_catalog()]

    assert app_ids[0] == "home"
    assert len(app_ids) == len(set(app_ids))
    assert {"ai", "collaboration", "business"}.isdisjoint(app_ids)


def test_app_control_seed_is_complete_for_the_leaf_catalog(client: TestClient) -> None:
    del client
    catalog = tuple(iter_workspace_app_catalog())
    with get_session_factory()() as db:
        company_ids = set(db.scalars(select(CompanyAppControl.app_id)).all())
        default_ids = set(db.scalars(select(WorkspaceAppDefault.app_id)).all())

    assert company_ids == {app.app_id for app in catalog}
    assert default_ids == {
        app.app_id for app in catalog if app.availability_scope == "workspace"
    }


def test_apps_bootstrap_hard_hides_platform_disabled_app(
    client: TestClient,
) -> None:
    session = _dev_login(client, "administrator")
    with get_session_factory()() as db:
        row = db.scalar(select(CompanyAppControl).where(CompanyAppControl.app_id == "mail"))
        assert row is not None
        row.enabled = False
        db.add(row)
        db.commit()

    response = client.get(
        "/api/v1/apps/bootstrap",
        headers={"Authorization": f"Bearer {session['token']}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "mail" not in {item["app_id"] for item in payload["apps"]}
    assert "mail" not in payload["personal_tool_app_ids"]


def test_workspace_bootstrap_projection_builds_apps_and_flat_nav() -> None:
    catalog = (
        WorkspaceAppCatalogItem(
            app_id="toolbox",
            title="Toolbox",
            route_base="/apps/toolbox",
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
                    id="optional-tool",
                    app_id="toolbox",
                    title="Optional Tool",
                    category="Core",
                    icon_key="box",
                    feature_flag="optional_enabled",
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
            route_base="/apps/docs",
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
            route_base="/apps/mail",
            icon_key="mail",
        ),
    )

    projection = project_workspace_bootstrap_apps(
        catalog,
        enabled_app_ids={"toolbox", "docs"},
        settings={"optional_enabled": False},
    )

    assert [item["app_id"] for item in projection.apps] == ["toolbox", "docs"]
    assert [item["id"] for item in projection.nav] == [
        "search",
        "linked-tool",
        "docs-library",
    ]
    assert projection.apps[0]["nav_items"] == projection.nav[:2]
    assert projection.apps[1]["nav_items"] == projection.nav[2:]
    assert all(item["id"] != "optional-tool" for item in projection.nav)
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
            route_base="/apps/toolbox",
            icon_key="brain",
            nav_items=(
                WorkspaceNavCatalogItem(
                    id="optional-tool",
                    app_id="toolbox",
                    title="Optional Tool",
                    category="Core",
                    icon_key="box",
                    feature_flag="optional_enabled",
                ),
            ),
        ),
    )

    projection = project_workspace_bootstrap_apps(
        catalog,
        enabled_app_ids={"toolbox"},
        settings={"optional_enabled": True},
    )

    assert [item["id"] for item in projection.nav] == ["optional-tool"]


def test_workspace_bootstrap_projection_keeps_app_when_child_flag_is_disabled() -> None:
    catalog = (
        WorkspaceAppCatalogItem(
            app_id="toolbox",
            title="Toolbox",
            route_base="/apps/toolbox",
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


def test_workspace_bootstrap_does_not_invent_nav_for_an_app_without_submenu() -> None:
    projection = project_workspace_bootstrap_apps(
        (
            WorkspaceAppCatalogItem(
                app_id="single-surface",
                title="Single Surface",
                route_base="/apps/single-surface",
                icon_key="square",
            ),
        ),
        enabled_app_ids={"single-surface"},
        settings={},
    )

    assert [item["app_id"] for item in projection.apps] == ["single-surface"]
    assert projection.apps[0]["nav_items"] == []
    assert projection.nav == []


def test_general_workspace_seed_and_admin_membership(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]

    workspaces = {item["slug"]: item for item in session["user"]["workspaces"]}
    assert workspaces["administrator"]["name"] == "Administrator"
    assert workspaces["administrator"]["role"] == "admin"
    assert workspaces["general"]["name"] == "General"
    assert workspaces["general"]["role"] == "admin"

    response = client.get(
        "/api/v1/workspaces/general/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace"]["slug"] == "general"
    assert payload["workspace"]["name"] == "General"

    spaces_response = client.get(
        "/api/v1/workspaces/general/pms/spaces",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert spaces_response.status_code == 200
    assert any(item["current_user_role"] == "owner" for item in spaces_response.json())


def test_dev_seed_workspaces_register_every_app_and_expose_enabled_apps(
    client: TestClient,
) -> None:
    get_settings.cache_clear()
    try:
        with get_session_factory()() as db:
            initial_category_by_app = dict(
                db.execute(
                    select(PlatformAppBarCategoryApp.app_id, PlatformAppBarCategoryApp.category_id)
                ).all()
            )
        session = _dev_login(client, "administrator")
        token = session["token"]
        headers = {"Authorization": f"Bearer {token}"}
        catalog = tuple(iter_workspace_app_catalog())
        settings = get_settings()
        enabled_catalog = tuple(
            app
            for app in catalog
            if app.feature_flag is None
            or is_workspace_catalog_feature_enabled(settings, app.feature_flag)
        )

        workspace_response = client.get(
            "/api/v1/workspaces/general/bootstrap",
            headers=headers,
        )
        assert workspace_response.status_code == 200, workspace_response.text
        workspace_payload = workspace_response.json()
        expected_workspace_app_ids = {
            app.app_id
            for app in enabled_catalog
            if app.availability_scope == "workspace"
        }
        assert {item["app_id"] for item in workspace_payload["apps"]} == (
            expected_workspace_app_ids
        )

        global_response = client.get("/api/v1/apps/bootstrap", headers=headers)
        assert global_response.status_code == 200, global_response.text
        global_payload = global_response.json()
        assert {item["app_id"] for item in global_payload["apps"]} == {
            app.app_id for app in enabled_catalog
        }

        categorized_app_ids = {
            item["app_id"]
            for payload in (workspace_payload, global_payload)
            for category in payload["app_bar_categories"]
            for item in category["items"]
        }
        personal_tool_ids = set(global_payload["personal_tool_app_ids"])
        fixed_app_ids = {app.app_id for app in enabled_catalog if app.launcher_fixed}
        assert categorized_app_ids | personal_tool_ids | fixed_app_ids == {
            app.app_id for app in enabled_catalog
        }

        with get_session_factory()() as db:
            workspace = db.scalar(select(Workspace).where(Workspace.key == "general"))
            assert workspace is not None
            defaults = dict(
                db.execute(
                    select(WorkspaceAppDefault.app_id, WorkspaceAppDefault.enabled)
                ).all()
            )
            expected_workspace_app_ids = {
                app.app_id for app in catalog if app.availability_scope == "workspace"
            }
            assert defaults.keys() == expected_workspace_app_ids
            assert all(defaults[app_id] is True for app_id in expected_workspace_app_ids)

            category = db.scalar(
                select(PlatformAppBarCategory).where(
                    PlatformAppBarCategory.key == auth_access.DEV_APP_BAR_CATEGORY_KEY
                )
            )
            assert category is not None
            category_app_ids = set(
                db.scalars(
                    select(PlatformAppBarCategoryApp.app_id).where(
                        PlatformAppBarCategoryApp.category_id == category.id
                    )
                ).all()
            )
            expected_category_app_ids = {app.app_id for app in catalog if app.launcher_category}
            # Development seeding fills gaps without moving migration/admin
            # assignments into its own category.
            previously_assigned_elsewhere = {
                app_id
                for app_id, category_id in initial_category_by_app.items()
                if category_id != category.id
            }
            assert category_app_ids == expected_category_app_ids - previously_assigned_elsewhere
            assignments = db.execute(
                select(PlatformAppBarCategoryApp.app_id, PlatformAppBarCategoryApp.category_id)
            ).all()
            category_by_app = dict(assignments)
            assert len(assignments) == len(category_by_app)
            assert category_by_app.keys() == expected_category_app_ids
            assert all(
                category_by_app[app_id] == category_id
                for app_id, category_id in initial_category_by_app.items()
            )
            auth_access.ensure_dev_seed_app_access(db, {workspace.key: workspace})
            repeated_assignments = db.execute(
                select(PlatformAppBarCategoryApp.app_id, PlatformAppBarCategoryApp.category_id)
            ).all()
            assert sorted(repeated_assignments) == sorted(assignments)
    finally:
        get_settings.cache_clear()


def test_workspace_bootstrap_ignores_unknown_app_override(
    client: TestClient,
) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "general"))
        assert workspace is not None
        db.add(
            WorkspaceAppOverride(
                workspace_id=workspace.id,
                app_id="unknown-app",
                enabled=False,
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/workspaces/general/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "unknown-app" not in {item["app_id"] for item in payload["apps"]}
    assert all(item["app_id"] != "unknown-app" for item in payload["nav"])
    assert "docs" in {item["app_id"] for item in payload["apps"]}


def test_workspace_bootstrap_hides_app_with_workspace_override(
    client: TestClient,
) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "general"))
        assert workspace is not None
        db.add(
            WorkspaceAppOverride(
                workspace_id=workspace.id,
                app_id="docs",
                enabled=False,
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/workspaces/general/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "docs" not in {item["app_id"] for item in payload["apps"]}
    assert all(item["app_id"] != "docs" for item in payload["nav"])
    assert "doc" not in {item["value"] for item in payload["keyword_search"]["entity_types"]}


def test_workspace_app_gate_checks_leaf_override(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]
    headers = {"Authorization": f"Bearer {token}"}
    path = "/api/v1/workspaces/general/docs/hub"

    enabled_response = client.get(path, headers=headers)
    assert enabled_response.status_code == 200, enabled_response.text

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "general"))
        assert workspace is not None
        db.add(
            WorkspaceAppOverride(
                workspace_id=workspace.id,
                app_id="docs",
                enabled=False,
            )
        )
        db.commit()

    disabled_response = client.get(path, headers=headers)
    assert disabled_response.status_code == 403
    assert disabled_response.json()["code"] == "workspace.app_disabled"


def test_workspace_bootstrap_fails_closed_when_app_default_is_missing(
    client: TestClient,
) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]
    with get_session_factory()() as db:
        row = db.get(WorkspaceAppDefault, "docs")
        assert row is not None
        db.delete(row)
        db.commit()

    response = client.get(
        "/api/v1/workspaces/general/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "docs" not in {item["app_id"] for item in payload["apps"]}


def test_registry_drives_llm_task_seed_and_tool_metadata(client: TestClient) -> None:
    registry = get_ai_capability_registry()
    task_kinds = {item.task_kind for item in get_supported_llm_tasks()}

    assert {
        "chatbot",
        "meeting_summary",
        "meeting_insight_actions",
        "meeting_insight_decisions",
        "meeting_insight_followup",
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
