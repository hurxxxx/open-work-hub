from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


_WORKSPACE_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_WORKSPACE_ROUTE_BASE_PATTERN = re.compile(
    r"/(?:[a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?:/[a-z][a-z0-9]*(?:-[a-z0-9]+)*)*"
)
_BACKEND_DOMAIN_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_SYSTEM_ROLE_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


AppAvailabilityScope = Literal["platform", "workspace"]
_APP_AVAILABILITY_SCOPES: frozenset[str] = frozenset({"platform", "workspace"})


@dataclass(frozen=True)
class WorkspaceNavCatalogItem:
    id: str
    app_id: str
    title: str
    category: str
    icon_key: str
    link_app_id: str | None = None
    path_suffix: str | None = None
    absolute_path: str | None = None
    coming_soon: bool = False
    feature_flag: str | None = None


@dataclass(frozen=True)
class WorkspaceAppCatalogItem:
    app_id: str
    title: str
    route_base: str
    icon_key: str
    availability_scope: AppAvailabilityScope = "workspace"
    enabled_by_default: bool = False
    visible_by_default: bool = False
    launcher_category: bool = False
    launcher_fixed: bool = False
    launcher_personal_tools: bool = False
    launcher_pinned_by_default: bool = False
    nav_items: tuple[WorkspaceNavCatalogItem, ...] = ()
    coming_soon: bool = False
    feature_flag: str | None = None
    platform_admin_activation_required: bool = False
    required_system_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceNavRegistration:
    id: str
    title: str
    category: str
    icon_key: str
    link_app_id: str | None = None
    path_suffix: str | None = None
    absolute_path: str | None = None
    coming_soon: bool = False
    feature_flag: str | None = None


@dataclass(frozen=True)
class WorkspaceAppRegistration:
    app_id: str
    title: str
    route_base: str
    icon_key: str
    availability_scope: AppAvailabilityScope = "workspace"
    enabled_by_default: bool = False
    visible_by_default: bool = False
    launcher_category: bool = False
    launcher_fixed: bool = False
    launcher_personal_tools: bool = False
    launcher_pinned_by_default: bool = False
    nav_items: tuple[WorkspaceNavRegistration, ...] = ()
    coming_soon: bool = False
    feature_flag: str | None = None
    platform_admin_activation_required: bool = False
    required_system_roles: tuple[str, ...] = ()
    backend_domain: str | None = None


@dataclass(frozen=True)
class WorkspaceAppRegistry:
    catalog: tuple[WorkspaceAppCatalogItem, ...]
    by_app_id: Mapping[str, WorkspaceAppCatalogItem]

    @property
    def app_ids(self) -> tuple[str, ...]:
        return tuple(item.app_id for item in self.catalog)

    @property
    def launcher_fixed_app_ids(self) -> frozenset[str]:
        return frozenset(item.app_id for item in self.catalog if item.launcher_fixed)

    @property
    def launcher_pinned_by_default_app_ids(self) -> tuple[str, ...]:
        return tuple(item.app_id for item in self.catalog if item.launcher_pinned_by_default)

    @property
    def launcher_personal_tools_app_ids(self) -> frozenset[str]:
        return frozenset(item.app_id for item in self.catalog if item.launcher_personal_tools)

    @property
    def platform_app_ids(self) -> frozenset[str]:
        return frozenset(
            item.app_id for item in self.catalog if item.availability_scope == "platform"
        )


def compile_workspace_app_registry(
    registrations: Iterable[WorkspaceAppRegistration],
) -> WorkspaceAppRegistry:
    catalog: list[WorkspaceAppCatalogItem] = []
    by_app_id: dict[str, WorkspaceAppCatalogItem] = {}
    app_id_by_route_base: dict[str, str] = {}
    app_id_by_nav_id: dict[str, str] = {}

    for registration in registrations:
        _validate_identifier(registration.app_id, kind="app id")
        if registration.app_id in by_app_id:
            raise RuntimeError(f"Duplicate workspace app registration: {registration.app_id}")
        if registration.availability_scope not in _APP_AVAILABILITY_SCOPES:
            raise RuntimeError(
                "Invalid app availability scope for "
                f"{registration.app_id}: {registration.availability_scope!r}"
            )
        if registration.backend_domain is not None and not _BACKEND_DOMAIN_PATTERN.fullmatch(
            registration.backend_domain
        ):
            raise RuntimeError(
                "Invalid workspace app backend domain for "
                f"{registration.app_id}: {registration.backend_domain!r}"
            )
        if len(set(registration.required_system_roles)) != len(
            registration.required_system_roles
        ):
            raise RuntimeError(
                "Duplicate required system role for "
                f"{registration.app_id}: {registration.required_system_roles!r}"
            )
        for role in registration.required_system_roles:
            if not _SYSTEM_ROLE_PATTERN.fullmatch(role):
                raise RuntimeError(
                    "Invalid required system role for "
                    f"{registration.app_id}: {role!r}"
                )
        if not _WORKSPACE_ROUTE_BASE_PATTERN.fullmatch(registration.route_base):
            raise RuntimeError(
                "Invalid workspace app route base for "
                f"{registration.app_id}: {registration.route_base!r}"
            )
        route_owner = app_id_by_route_base.get(registration.route_base)
        if route_owner is not None:
            raise RuntimeError(
                "Duplicate workspace app route base: "
                f"{registration.route_base} ({route_owner}, {registration.app_id})"
            )
        if registration.launcher_fixed and registration.launcher_category:
            raise RuntimeError(
                f"Fixed launcher app cannot belong to a category: {registration.app_id}"
            )
        if registration.launcher_fixed and registration.launcher_pinned_by_default:
            raise RuntimeError(
                f"Fixed launcher app cannot be pinned by default: {registration.app_id}"
            )
        if registration.launcher_pinned_by_default and not registration.launcher_category:
            raise RuntimeError(
                f"Default-pinned launcher app must belong to a category: {registration.app_id}"
            )
        if registration.launcher_personal_tools and (
            registration.launcher_category
            or registration.launcher_fixed
            or registration.launcher_pinned_by_default
        ):
            raise RuntimeError(
                "Personal-tools launcher app cannot use another launcher placement: "
                f"{registration.app_id}"
            )
        if registration.launcher_personal_tools and registration.availability_scope != "platform":
            raise RuntimeError(
                f"Personal-tools launcher app must be platform-available: {registration.app_id}"
            )

        for nav_item in registration.nav_items:
            _validate_identifier(nav_item.id, kind="nav id")
            nav_owner = app_id_by_nav_id.get(nav_item.id)
            if nav_owner is not None:
                raise RuntimeError(
                    "Duplicate workspace nav registration: "
                    f"{nav_item.id} ({nav_owner}, {registration.app_id})"
                )
            if nav_item.link_app_id is not None:
                _validate_identifier(nav_item.link_app_id, kind="nav link app id")
            app_id_by_nav_id[nav_item.id] = registration.app_id

        catalog_item = WorkspaceAppCatalogItem(
            app_id=registration.app_id,
            title=registration.title,
            route_base=registration.route_base,
            icon_key=registration.icon_key,
            availability_scope=registration.availability_scope,
            enabled_by_default=registration.enabled_by_default,
            visible_by_default=registration.visible_by_default,
            launcher_category=registration.launcher_category,
            launcher_fixed=registration.launcher_fixed,
            launcher_personal_tools=registration.launcher_personal_tools,
            launcher_pinned_by_default=registration.launcher_pinned_by_default,
            nav_items=tuple(
                WorkspaceNavCatalogItem(
                    id=item.id,
                    app_id=registration.app_id,
                    title=item.title,
                    category=item.category,
                    icon_key=item.icon_key,
                    link_app_id=item.link_app_id,
                    path_suffix=item.path_suffix,
                    absolute_path=item.absolute_path,
                    coming_soon=item.coming_soon,
                    feature_flag=item.feature_flag,
                )
                for item in registration.nav_items
            ),
            coming_soon=registration.coming_soon,
            feature_flag=registration.feature_flag,
            platform_admin_activation_required=(
                registration.platform_admin_activation_required
            ),
            required_system_roles=registration.required_system_roles,
        )
        catalog.append(catalog_item)
        by_app_id[registration.app_id] = catalog_item
        app_id_by_route_base[registration.route_base] = registration.app_id

    for app in catalog:
        for nav_item in app.nav_items:
            if nav_item.link_app_id is not None and nav_item.link_app_id not in by_app_id:
                raise RuntimeError(
                    "Workspace nav registration "
                    f"{nav_item.id} references unknown app id: {nav_item.link_app_id}"
                )

    return WorkspaceAppRegistry(
        catalog=tuple(catalog),
        by_app_id=MappingProxyType(by_app_id),
    )


def app_is_available_to_system_roles(
    app: WorkspaceAppCatalogItem,
    system_roles: Iterable[str],
) -> bool:
    if not app.required_system_roles:
        return True
    return bool(set(system_roles).intersection(app.required_system_roles))


def _validate_identifier(value: str, *, kind: str) -> None:
    if not _WORKSPACE_IDENTIFIER_PATTERN.fullmatch(value):
        raise RuntimeError(f"Invalid workspace {kind}: {value!r}")
