from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import dev_login
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.llm import get_supported_llm_tasks
from open_work_hub_api.domains.ai.registry import get_ai_capability_registry
from open_work_hub_api.domains.auth import access as auth_access
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
from open_work_hub_api.domains.auth.models import CompanyAppControl, PlatformAppBarCategoryApp
from open_work_hub_api.domains.auth.app_catalog import (
    AppCatalogItem,
    AppNavCatalogItem,
    iter_app_catalog,
)
from open_work_hub_api.domains.auth.bootstrap_projection import project_bootstrap_apps


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def test_app_catalog_is_a_unique_leaf_app_registry() -> None:
    app_ids = [item.app_id for item in iter_app_catalog()]

    assert app_ids[0] == "home"
    assert len(app_ids) == len(set(app_ids))
    assert {"ai", "collaboration", "business"}.isdisjoint(app_ids)


def test_app_control_seed_is_complete_for_the_leaf_catalog(client: TestClient) -> None:
    del client
    catalog = tuple(iter_app_catalog())
    with get_session_factory()() as db:
        company_ids = set(db.scalars(select(CompanyAppControl.app_id)).all())
        default_ids = set(db.scalars(select(AppAccessPolicy.app_id)).all())

    assert company_ids == {app.app_id for app in catalog}
    assert default_ids == {app.app_id for app in catalog}


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


def test_bootstrap_projection_builds_apps_and_flat_nav() -> None:
    catalog = (
        AppCatalogItem(
            app_id="toolbox",
            title="Toolbox",
            route_base="/apps/toolbox",
            icon_key="brain",
            nav_items=(
                AppNavCatalogItem(
                    id="search",
                    app_id="toolbox",
                    title="Search",
                    category="Core",
                    icon_key="search",
                    path_suffix="?q=1",
                ),
                AppNavCatalogItem(
                    id="optional-tool",
                    app_id="toolbox",
                    title="Optional Tool",
                    category="Core",
                    icon_key="box",
                    feature_flag="optional_enabled",
                ),
                AppNavCatalogItem(
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
        AppCatalogItem(
            app_id="docs",
            title="DOCS",
            route_base="/apps/docs",
            icon_key="file-text",
            nav_items=(
                AppNavCatalogItem(
                    id="docs-library",
                    app_id="docs",
                    title="Docs",
                    category="Documents",
                    icon_key="file-text",
                ),
            ),
        ),
        AppCatalogItem(
            app_id="mail",
            title="MAIL",
            route_base="/apps/mail",
            icon_key="mail",
        ),
    )

    projection = project_bootstrap_apps(
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


def test_bootstrap_projection_includes_feature_flagged_nav() -> None:
    catalog = (
        AppCatalogItem(
            app_id="toolbox",
            title="Toolbox",
            route_base="/apps/toolbox",
            icon_key="brain",
            nav_items=(
                AppNavCatalogItem(
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

    projection = project_bootstrap_apps(
        catalog,
        enabled_app_ids={"toolbox"},
        settings={"optional_enabled": True},
    )

    assert [item["id"] for item in projection.nav] == ["optional-tool"]


def test_bootstrap_projection_keeps_app_when_child_flag_is_disabled() -> None:
    catalog = (
        AppCatalogItem(
            app_id="toolbox",
            title="Toolbox",
            route_base="/apps/toolbox",
            icon_key="brain",
            nav_items=(
                AppNavCatalogItem(
                    id="search",
                    app_id="toolbox",
                    title="Search",
                    category="Core",
                    icon_key="search",
                ),
                AppNavCatalogItem(
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

    projection = project_bootstrap_apps(
        catalog,
        enabled_app_ids={"toolbox"},
        settings={"child_enabled": False},
    )

    assert [item["app_id"] for item in projection.apps] == ["toolbox"]
    assert [item["id"] for item in projection.nav] == ["search"]


def test_bootstrap_does_not_invent_nav_for_an_app_without_submenu() -> None:
    projection = project_bootstrap_apps(
        (
            AppCatalogItem(
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


def test_bootstrap_contains_current_company_principal(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    response = client.get(
        "/api/v1/apps/bootstrap", headers={"Authorization": f"Bearer {session['token']}"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["principal"]["user_id"] == session["user"]["id"]
    assert "workspace" not in response.json()
    assert session["user"]["system_roles"] == ["platform_admin"]


def test_app_bar_assignments_are_stable_when_seed_repeats(client: TestClient) -> None:
    _dev_login(client, "administrator")
    with get_session_factory()() as db:
        before = db.execute(
            select(PlatformAppBarCategoryApp.app_id, PlatformAppBarCategoryApp.category_id)
        ).all()
        auth_access.ensure_dev_seed_app_access(db)
        after = db.execute(
            select(PlatformAppBarCategoryApp.app_id, PlatformAppBarCategoryApp.category_id)
        ).all()
        assert sorted(after) == sorted(before)
        assert len(after) == len({app_id for app_id, _ in after})
        assert {app_id for app_id, _ in after} == {
            app.app_id for app in iter_app_catalog() if app.launcher_category
        }


def test_bootstrap_ignores_unknown_app_policy(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    with get_session_factory()() as db:
        db.add(CompanyAppControl(app_id="unknown-app", enabled=True))
        db.flush()
        db.add(AppAccessPolicy(app_id="unknown-app", audience="all"))
        db.commit()
    response = client.get(
        "/api/v1/apps/bootstrap", headers={"Authorization": f"Bearer {session['token']}"}
    )
    assert response.status_code == 200, response.text
    assert "unknown-app" not in {item["app_id"] for item in response.json()["apps"]}
    assert "unknown-app" not in {item["app_id"] for item in response.json()["nav"]}


def test_disabled_app_is_removed_from_apps_nav_and_search_types(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    with get_session_factory()() as db:
        db.get(CompanyAppControl, "docs").enabled = False
        db.commit()
    response = client.get(
        "/api/v1/apps/bootstrap", headers={"Authorization": f"Bearer {session['token']}"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "docs" not in {item["app_id"] for item in payload["apps"]}
    assert "docs" not in {item["app_id"] for item in payload["nav"]}
    assert "doc" not in {item["value"] for item in payload["keyword_search"]["entity_types"]}


def test_app_gate_rechecks_company_master_for_existing_session(client: TestClient) -> None:
    session = _dev_login(client, "administrator")
    headers = {"Authorization": f"Bearer {session['token']}"}
    enabled = client.get("/api/v1/docs/hub", headers=headers)
    assert enabled.status_code == 200, enabled.text
    with get_session_factory()() as db:
        db.get(CompanyAppControl, "docs").enabled = False
        db.commit()
    disabled = client.get("/api/v1/docs/hub", headers=headers)
    assert disabled.status_code == 403, disabled.text


def test_bootstrap_fails_closed_when_app_default_is_missing(
    client: TestClient,
) -> None:
    session = _dev_login(client, "administrator")
    token = session["token"]
    with get_session_factory()() as db:
        row = db.get(AppAccessPolicy, "docs")
        assert row is not None
        db.delete(row)
        db.commit()

    response = client.get(
        "/api/v1/apps/bootstrap",
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
