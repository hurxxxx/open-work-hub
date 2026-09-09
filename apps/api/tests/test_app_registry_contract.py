from __future__ import annotations

import pytest

from open_work_hub_api.core.app_registry import (
    AppRegistration,
    AppNavRegistration,
    app_is_available_to_system_roles,
    compile_app_registry,
)
from open_work_hub_api.domains.auth.app_catalog import get_app_catalog_item, iter_app_catalog
from open_work_hub_api.domains.auth.app_bar_preferences import normalize_app_bar_pinned_app_ids
from open_work_hub_api.domains.files.app_catalog import FILES_APP


def _registration(
    app_id: str,
    *,
    nav_items: tuple[AppNavRegistration, ...] = (),
) -> AppRegistration:
    return AppRegistration(
        app_id=app_id,
        title=app_id,
        route_base=f"/apps/{app_id}",
        icon_key="box",
        launcher_category=True,
        nav_items=nav_items,
    )


def test_registry_injects_app_identity_into_owned_nav_items() -> None:
    registry = compile_app_registry(
        (
            _registration(
                "custom-app",
                nav_items=(
                    AppNavRegistration(
                        id="custom-nav",
                        title="Custom nav",
                        category="Custom",
                        icon_key="box",
                    ),
                ),
            ),
        )
    )

    assert registry.catalog[0].nav_items[0].app_id == "custom-app"


def test_registry_rejects_duplicate_app_ids() -> None:
    with pytest.raises(
        RuntimeError,
        match="Duplicate app registration: duplicate-app",
    ):
        compile_app_registry((_registration("duplicate-app"), _registration("duplicate-app")))


def test_registration_defaults_exclude_unspecified_launcher_placement() -> None:
    registry = compile_app_registry(
        (
            AppRegistration(
                app_id="inactive-app",
                title="Inactive",
                route_base="/apps/inactive-app",
                icon_key="box",
            ),
        )
    )

    app = registry.catalog[0]
    assert app.launcher_category is False
    assert app.execution_context_kind == "company"
    assert app.resource_scope == "company"
    assert app.required_system_roles == ()


def test_registry_projects_and_checks_required_system_roles() -> None:
    registry = compile_app_registry(
        (
            AppRegistration(
                app_id="admin-tool",
                title="Admin tool",
                route_base="/apps/admin-tool",
                icon_key="terminal",
                required_system_roles=("platform_admin",),
            ),
        )
    )

    app = registry.catalog[0]
    assert app.required_system_roles == ("platform_admin",)
    assert app_is_available_to_system_roles(app, ["platform_admin"]) is True
    assert app_is_available_to_system_roles(app, []) is False


@pytest.mark.parametrize(
    "roles",
    (("platform_admin", "platform_admin"), ("../admin",)),
)
def test_registry_rejects_invalid_required_system_roles(roles: tuple[str, ...]) -> None:
    with pytest.raises(RuntimeError, match="required system role"):
        compile_app_registry(
            (
                AppRegistration(
                    app_id="admin-tool",
                    title="Admin tool",
                    route_base="/apps/admin-tool",
                    icon_key="terminal",
                    required_system_roles=roles,
                ),
            )
        )


def test_files_catalog_exposes_search_submenu() -> None:
    app = get_app_catalog_item(FILES_APP.app_id)

    assert app is not None
    search = next(item for item in app.nav_items if item.id == "files-search")
    assert search.path_suffix == "?view=search"
    assert search.icon_key == "search"


@pytest.mark.parametrize("app_id", ("", "Bad_App", "-leading", "trailing-", "two--dash"))
def test_registry_rejects_invalid_app_id_format(app_id: str) -> None:
    with pytest.raises(RuntimeError, match="Invalid app app id"):
        compile_app_registry(
            (
                AppRegistration(
                    app_id=app_id,
                    title="Invalid",
                    route_base="/apps/invalid",
                    icon_key="box",
                ),
            )
        )


@pytest.mark.parametrize("backend_domain", ("", "QualityRecords", "quality-records", "../quality"))
def test_registry_rejects_invalid_backend_domain(backend_domain: str) -> None:
    with pytest.raises(RuntimeError, match="Invalid app backend domain"):
        compile_app_registry(
            (
                AppRegistration(
                    app_id="quality-search",
                    title="Quality Search",
                    route_base="/apps/quality-search",
                    icon_key="search",
                    backend_domain=backend_domain,
                ),
            )
        )


@pytest.mark.parametrize(
    "route_base",
    ("docs", "/docs/", "//docs", "/Docs", "/docs?tab=all", "/docs#top"),
)
def test_registry_rejects_invalid_route_base_format(route_base: str) -> None:
    with pytest.raises(RuntimeError, match="Invalid app route base for docs"):
        compile_app_registry(
            (
                AppRegistration(
                    app_id="docs",
                    title="Docs",
                    route_base=route_base,
                    icon_key="box",
                ),
            )
        )


def test_registry_rejects_duplicate_route_bases() -> None:
    with pytest.raises(
        RuntimeError,
        match=r"Duplicate app route base: /apps/shared \(first-app, second-app\)",
    ):
        compile_app_registry(
            (
                AppRegistration(
                    app_id="first-app",
                    title="First",
                    route_base="/apps/shared",
                    icon_key="box",
                ),
                AppRegistration(
                    app_id="second-app",
                    title="Second",
                    route_base="/apps/shared",
                    icon_key="box",
                ),
            )
        )


def test_registry_rejects_invalid_and_duplicate_nav_ids() -> None:
    invalid_nav = AppNavRegistration(
        id="Bad_Nav",
        title="Invalid",
        category="Test",
        icon_key="box",
    )
    with pytest.raises(RuntimeError, match="Invalid app nav id"):
        compile_app_registry((_registration("invalid-nav", nav_items=(invalid_nav,)),))

    shared_nav = AppNavRegistration(
        id="shared-nav",
        title="Shared",
        category="Test",
        icon_key="box",
    )
    with pytest.raises(
        RuntimeError,
        match=r"Duplicate app nav registration: shared-nav \(first-app, second-app\)",
    ):
        compile_app_registry(
            (
                _registration("first-app", nav_items=(shared_nav,)),
                _registration("second-app", nav_items=(shared_nav,)),
            )
        )


def test_registry_validates_nav_link_app_references_after_composition() -> None:
    linked_nav = AppNavRegistration(
        id="linked-nav",
        title="Linked",
        category="Test",
        icon_key="box",
        link_app_id="target-app",
    )
    registry = compile_app_registry(
        (
            _registration("source-app", nav_items=(linked_nav,)),
            _registration("target-app"),
        )
    )
    assert registry.catalog[0].nav_items[0].link_app_id == "target-app"

    with pytest.raises(
        RuntimeError,
        match="App nav registration linked-nav references unknown app id: target-app",
    ):
        compile_app_registry((_registration("source-app", nav_items=(linked_nav,)),))


def test_registry_rejects_invalid_nav_link_app_id_format() -> None:
    with pytest.raises(RuntimeError, match="Invalid app nav link app id"):
        compile_app_registry(
            (
                _registration(
                    "source-app",
                    nav_items=(
                        AppNavRegistration(
                            id="linked-nav",
                            title="Linked",
                            category="Test",
                            icon_key="box",
                            link_app_id="../admin",
                        ),
                    ),
                ),
            )
        )


def test_registry_preserves_registration_order_and_indexes_compiled_items() -> None:
    registry = compile_app_registry((_registration("first-app"), _registration("second-app")))

    assert registry.app_ids == ("first-app", "second-app")
    assert len(registry.catalog) == 2
    assert registry.by_app_id["first-app"] is registry.catalog[0]


def test_registry_derives_launcher_policy_from_app_registrations() -> None:
    registry = compile_app_registry(
        (
            AppRegistration(
                app_id="fixed-app",
                title="Fixed",
                route_base="/apps/fixed-app",
                icon_key="box",
                launcher_category=False,
                launcher_fixed=True,
            ),
            AppRegistration(
                app_id="default-pin",
                title="Default pin",
                route_base="/apps/default-pin",
                icon_key="box",
                launcher_category=True,
                launcher_pinned_by_default=True,
            ),
        )
    )

    assert registry.launcher_fixed_app_ids == frozenset({"fixed-app"})
    assert registry.launcher_pinned_by_default_app_ids == ("default-pin",)


def test_registry_derives_platform_personal_tools_launcher_policy() -> None:
    registry = compile_app_registry(
        (
            AppRegistration(
                app_id="mail",
                title="Personal mail",
                route_base="/apps/mail",
                icon_key="mail",
                launcher_personal_tools=True,
            ),
        )
    )

    app = registry.catalog[0]
    assert app.execution_context_kind == "personal"
    assert app.launcher_personal_tools is True
    assert registry.launcher_personal_tools_app_ids == frozenset({"mail"})


def test_registry_rejects_invalid_personal_tools_launcher_placement() -> None:
    with pytest.raises(
        RuntimeError,
        match="Personal-tools launcher app cannot use another launcher placement",
    ):
        compile_app_registry(
            (
                AppRegistration(
                    app_id="mail",
                    title="Personal mail",
                    route_base="/apps/mail",
                    icon_key="mail",
                    launcher_category=True,
                    launcher_personal_tools=True,
                ),
            )
        )


def test_registry_rejects_conflicting_launcher_policy() -> None:
    with pytest.raises(
        RuntimeError,
        match="Fixed launcher app cannot belong to a category: invalid-app",
    ):
        compile_app_registry(
            (
                AppRegistration(
                    app_id="invalid-app",
                    title="Invalid",
                    route_base="/apps/invalid-app",
                    icon_key="box",
                    launcher_category=True,
                    launcher_fixed=True,
                ),
            )
        )


def test_canonical_company_registry_exposes_all_composed_apps_by_identity() -> None:
    catalog = iter_app_catalog()

    assert len(catalog) == len({app.app_id for app in catalog})
    assert catalog[0].app_id == "home"
    assert get_app_catalog_item("home") is catalog[0]
    assert get_app_catalog_item("docs") is not None
    assert get_app_catalog_item("unknown-app") is None


def test_production_registry_requires_a_generated_leaf_app_contract() -> None:
    with pytest.raises(
        RuntimeError,
        match="App registration has no generated contract: custom-app",
    ):
        compile_app_registry(
            (_registration("custom-app"),),
            require_generated_contract=True,
        )


def test_production_registry_rejects_identity_drift_from_generated_contract() -> None:
    with pytest.raises(
        RuntimeError,
        match="App registration disagrees with generated contract for docs",
    ):
        compile_app_registry(
            (
                AppRegistration(
                    app_id="docs",
                    title="Docs",
                    route_base="/apps/wrong-docs",
                    icon_key="files",
                ),
            ),
            require_generated_contract=True,
        )


def test_bento_catalog_exposes_document_hub() -> None:
    app = get_app_catalog_item("bento")

    assert app is not None
    assert app.route_base == "/apps/bento"
    assert app.icon_key == "presentation"
    assert app.launcher_category is True
    assert [item.id for item in app.nav_items] == [
        "bento-all",
        "bento-mine",
        "bento-archived",
    ]


def test_personal_tools_apps_are_removed_from_pinned_preferences() -> None:
    assert normalize_app_bar_pinned_app_ids(["mail", "docs", "planner"]) == ["docs"]
