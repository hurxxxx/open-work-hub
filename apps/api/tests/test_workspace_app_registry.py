from __future__ import annotations

import pytest

from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
    compile_workspace_app_registry,
)
from open_work_hub_api.domains.auth.workspace_apps import (
    get_workspace_app_catalog_item,
    iter_workspace_app_catalog,
)
from open_work_hub_api.domains.auth.app_bar_preferences import normalize_app_bar_pinned_app_ids
from open_work_hub_api.domains.files.app_catalog import FILES_WORKSPACE_APP


def _registration(
    app_id: str,
    *,
    nav_items: tuple[WorkspaceNavRegistration, ...] = (),
) -> WorkspaceAppRegistration:
    return WorkspaceAppRegistration(
        app_id=app_id,
        title=app_id,
        route_base=f"/{app_id}",
        icon_key="box",
        enabled_by_default=True,
        visible_by_default=True,
        launcher_category=True,
        nav_items=nav_items,
    )


def test_registry_injects_app_identity_into_owned_nav_items() -> None:
    registry = compile_workspace_app_registry(
        (
            _registration(
                "custom-app",
                nav_items=(
                    WorkspaceNavRegistration(
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
        match="Duplicate workspace app registration: duplicate-app",
    ):
        compile_workspace_app_registry(
            (_registration("duplicate-app"), _registration("duplicate-app"))
        )


def test_registration_defaults_are_safe_until_explicitly_activated() -> None:
    registry = compile_workspace_app_registry(
        (
            WorkspaceAppRegistration(
                app_id="inactive-app",
                title="Inactive",
                route_base="/inactive-app",
                icon_key="box",
            ),
        )
    )

    app = registry.catalog[0]
    assert app.enabled_by_default is False
    assert app.visible_by_default is False
    assert app.launcher_category is False
    assert app.availability_scope == "workspace"


def test_files_catalog_exposes_search_as_a_workspace_submenu() -> None:
    app = get_workspace_app_catalog_item(FILES_WORKSPACE_APP.app_id)

    assert app is not None
    search = next(item for item in app.nav_items if item.id == "files-search")
    assert search.path_suffix == "?view=search"
    assert search.icon_key == "search"


@pytest.mark.parametrize("app_id", ("", "Bad_App", "-leading", "trailing-", "two--dash"))
def test_registry_rejects_invalid_app_id_format(app_id: str) -> None:
    with pytest.raises(RuntimeError, match="Invalid workspace app id"):
        compile_workspace_app_registry(
            (
                WorkspaceAppRegistration(
                    app_id=app_id,
                    title="Invalid",
                    route_base="/invalid",
                    icon_key="box",
                ),
            )
        )


@pytest.mark.parametrize("backend_domain", ("", "QualityRecords", "quality-records", "../quality"))
def test_registry_rejects_invalid_backend_domain(backend_domain: str) -> None:
    with pytest.raises(RuntimeError, match="Invalid workspace app backend domain"):
        compile_workspace_app_registry(
            (
                WorkspaceAppRegistration(
                    app_id="quality-search",
                    title="Quality Search",
                    route_base="/quality-search",
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
    with pytest.raises(RuntimeError, match="Invalid workspace app route base for docs"):
        compile_workspace_app_registry(
            (
                WorkspaceAppRegistration(
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
        match=r"Duplicate workspace app route base: /shared \(first-app, second-app\)",
    ):
        compile_workspace_app_registry(
            (
                WorkspaceAppRegistration(
                    app_id="first-app",
                    title="First",
                    route_base="/shared",
                    icon_key="box",
                ),
                WorkspaceAppRegistration(
                    app_id="second-app",
                    title="Second",
                    route_base="/shared",
                    icon_key="box",
                ),
            )
        )


def test_registry_rejects_invalid_and_duplicate_nav_ids() -> None:
    invalid_nav = WorkspaceNavRegistration(
        id="Bad_Nav",
        title="Invalid",
        category="Test",
        icon_key="box",
    )
    with pytest.raises(RuntimeError, match="Invalid workspace nav id"):
        compile_workspace_app_registry((_registration("invalid-nav", nav_items=(invalid_nav,)),))

    shared_nav = WorkspaceNavRegistration(
        id="shared-nav",
        title="Shared",
        category="Test",
        icon_key="box",
    )
    with pytest.raises(
        RuntimeError,
        match=r"Duplicate workspace nav registration: shared-nav \(first-app, second-app\)",
    ):
        compile_workspace_app_registry(
            (
                _registration("first-app", nav_items=(shared_nav,)),
                _registration("second-app", nav_items=(shared_nav,)),
            )
        )


def test_registry_validates_nav_link_app_references_after_composition() -> None:
    linked_nav = WorkspaceNavRegistration(
        id="linked-nav",
        title="Linked",
        category="Test",
        icon_key="box",
        link_app_id="target-app",
    )
    registry = compile_workspace_app_registry(
        (
            _registration("source-app", nav_items=(linked_nav,)),
            _registration("target-app"),
        )
    )
    assert registry.catalog[0].nav_items[0].link_app_id == "target-app"

    with pytest.raises(
        RuntimeError,
        match="Workspace nav registration linked-nav references unknown app id: target-app",
    ):
        compile_workspace_app_registry((_registration("source-app", nav_items=(linked_nav,)),))


def test_registry_rejects_invalid_nav_link_app_id_format() -> None:
    with pytest.raises(RuntimeError, match="Invalid workspace nav link app id"):
        compile_workspace_app_registry(
            (
                _registration(
                    "source-app",
                    nav_items=(
                        WorkspaceNavRegistration(
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
    registry = compile_workspace_app_registry(
        (_registration("first-app"), _registration("second-app"))
    )

    assert registry.app_ids == ("first-app", "second-app")
    assert len(registry.catalog) == 2
    assert registry.by_app_id["first-app"] is registry.catalog[0]


def test_registry_derives_launcher_policy_from_app_registrations() -> None:
    registry = compile_workspace_app_registry(
        (
            WorkspaceAppRegistration(
                app_id="fixed-app",
                title="Fixed",
                route_base="/fixed-app",
                icon_key="box",
                enabled_by_default=True,
                visible_by_default=True,
                launcher_category=False,
                launcher_fixed=True,
            ),
            WorkspaceAppRegistration(
                app_id="default-pin",
                title="Default pin",
                route_base="/default-pin",
                icon_key="box",
                enabled_by_default=True,
                visible_by_default=True,
                launcher_category=True,
                launcher_pinned_by_default=True,
            ),
        )
    )

    assert registry.launcher_fixed_app_ids == frozenset({"fixed-app"})
    assert registry.launcher_pinned_by_default_app_ids == ("default-pin",)


def test_registry_derives_platform_personal_tools_launcher_policy() -> None:
    registry = compile_workspace_app_registry(
        (
            WorkspaceAppRegistration(
                app_id="personal-mail",
                title="Personal mail",
                route_base="/personal-mail",
                icon_key="mail",
                availability_scope="platform",
                launcher_personal_tools=True,
            ),
        )
    )

    app = registry.catalog[0]
    assert app.availability_scope == "platform"
    assert app.launcher_personal_tools is True
    assert registry.platform_app_ids == frozenset({"personal-mail"})
    assert registry.launcher_personal_tools_app_ids == frozenset({"personal-mail"})


def test_registry_rejects_invalid_personal_tools_launcher_placement() -> None:
    with pytest.raises(
        RuntimeError,
        match="Personal-tools launcher app cannot use another launcher placement",
    ):
        compile_workspace_app_registry(
            (
                WorkspaceAppRegistration(
                    app_id="personal-mail",
                    title="Personal mail",
                    route_base="/personal-mail",
                    icon_key="mail",
                    availability_scope="platform",
                    launcher_category=True,
                    launcher_personal_tools=True,
                ),
            )
        )

    with pytest.raises(
        RuntimeError,
        match="Personal-tools launcher app must be platform-available",
    ):
        compile_workspace_app_registry(
            (
                WorkspaceAppRegistration(
                    app_id="workspace-mail",
                    title="Workspace mail",
                    route_base="/workspace-mail",
                    icon_key="mail",
                    launcher_personal_tools=True,
                ),
            )
        )


def test_registry_rejects_conflicting_launcher_policy() -> None:
    with pytest.raises(
        RuntimeError,
        match="Fixed launcher app cannot belong to a category: invalid-app",
    ):
        compile_workspace_app_registry(
            (
                WorkspaceAppRegistration(
                    app_id="invalid-app",
                    title="Invalid",
                    route_base="/invalid-app",
                    icon_key="box",
                    enabled_by_default=True,
                    visible_by_default=True,
                    launcher_category=True,
                    launcher_fixed=True,
                ),
            )
        )


def test_canonical_workspace_registry_exposes_all_composed_apps_by_identity() -> None:
    catalog = iter_workspace_app_catalog()

    assert len(catalog) == len({app.app_id for app in catalog})
    assert catalog[0].app_id == "home"
    assert get_workspace_app_catalog_item("home") is catalog[0]
    assert get_workspace_app_catalog_item("docs") is not None
    assert get_workspace_app_catalog_item("unknown-app") is None


def test_personal_tools_apps_are_removed_from_pinned_preferences() -> None:
    assert normalize_app_bar_pinned_app_ids(["mail", "docs", "planner"]) == ["docs"]
