from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, cast

from open_work_hub_api.core.app_contracts_generated import APP_CONTRACT_BY_ID

_APP_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_APP_ROUTE_BASE_PATTERN = re.compile(
    r"/(?:[a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?:/[a-z][a-z0-9]*(?:-[a-z0-9]+)*)*"
)
_BACKEND_DOMAIN_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_SYSTEM_ROLE_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


AppExecutionContextKind = Literal["personal", "company"]
AppResourceScope = Literal["personal", "company", "hybrid"]


@dataclass(frozen=True)
class AppNavCatalogItem:
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
class AppCatalogItem:
    app_id: str
    title: str
    route_base: str
    icon_key: str
    execution_context_kind: AppExecutionContextKind = "company"
    resource_scope: AppResourceScope = "company"
    entry_route_id: str = ""
    launcher_category: bool = False
    launcher_fixed: bool = False
    launcher_personal_tools: bool = False
    launcher_pinned_by_default: bool = False
    nav_items: tuple[AppNavCatalogItem, ...] = ()
    coming_soon: bool = False
    feature_flag: str | None = None
    required_system_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppNavRegistration:
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
class AppRegistration:
    app_id: str
    title: str
    route_base: str
    icon_key: str
    launcher_category: bool = False
    launcher_fixed: bool = False
    launcher_personal_tools: bool = False
    launcher_pinned_by_default: bool = False
    nav_items: tuple[AppNavRegistration, ...] = ()
    coming_soon: bool = False
    feature_flag: str | None = None
    required_system_roles: tuple[str, ...] = ()
    backend_domain: str | None = None


def app_registration(
    app_id: str,
    *,
    nav_items: tuple[AppNavRegistration, ...] = (),
    coming_soon: bool = False,
    backend_domain: str | None = None,
) -> AppRegistration:
    """Create an app registration from the generated leaf-app contract.

    Domain modules own implementation metadata such as nav items and backend
    composition. Identity, route, scope, feature, role, and launcher policy are
    generated from packages/contracts/app-contracts.json.
    """

    contract = APP_CONTRACT_BY_ID.get(app_id)
    if contract is None:
        raise RuntimeError(f"Unknown generated app contract: {app_id}")
    launcher = cast(dict[str, Any], contract["launcher"])
    placement = str(launcher["placement"])
    return AppRegistration(
        app_id=app_id,
        title=str(contract["title"]),
        route_base=str(contract["route_base"]),
        icon_key=str(contract["icon_key"]),
        launcher_category=placement == "category",
        launcher_fixed=placement == "fixed",
        launcher_personal_tools=placement == "personal_tools",
        launcher_pinned_by_default=bool(launcher["pinned_by_default"]),
        nav_items=nav_items,
        coming_soon=coming_soon,
        feature_flag=cast(str | None, contract.get("feature_flag")),
        required_system_roles=tuple(cast(list[str], contract.get("required_system_roles", []))),
        backend_domain=backend_domain,
    )


@dataclass(frozen=True)
class AppRegistry:
    catalog: tuple[AppCatalogItem, ...]
    by_app_id: Mapping[str, AppCatalogItem]

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


def compile_app_registry(
    registrations: Iterable[AppRegistration],
    *,
    require_generated_contract: bool = False,
) -> AppRegistry:
    catalog: list[AppCatalogItem] = []
    by_app_id: dict[str, AppCatalogItem] = {}
    app_id_by_route_base: dict[str, str] = {}
    app_id_by_nav_id: dict[str, str] = {}

    for registration in registrations:
        _validate_identifier(registration.app_id, kind="app id")
        contract = APP_CONTRACT_BY_ID.get(registration.app_id)
        if contract is None and require_generated_contract:
            raise RuntimeError(f"App registration has no generated contract: {registration.app_id}")
        if contract is not None and require_generated_contract:
            contract_projection = (
                str(contract["route_base"]),
                str(contract["icon_key"]),
            )
            registration_projection = (
                registration.route_base,
                registration.icon_key,
            )
            if registration_projection != contract_projection:
                raise RuntimeError(
                    "App registration disagrees with generated contract for "
                    f"{registration.app_id}: "
                    f"{registration_projection!r} != {contract_projection!r}"
                )
        if registration.app_id in by_app_id:
            raise RuntimeError(f"Duplicate app registration: {registration.app_id}")
        if registration.backend_domain is not None and not _BACKEND_DOMAIN_PATTERN.fullmatch(
            registration.backend_domain
        ):
            raise RuntimeError(
                "Invalid app backend domain for "
                f"{registration.app_id}: {registration.backend_domain!r}"
            )
        if len(set(registration.required_system_roles)) != len(registration.required_system_roles):
            raise RuntimeError(
                "Duplicate required system role for "
                f"{registration.app_id}: {registration.required_system_roles!r}"
            )
        for role in registration.required_system_roles:
            if not _SYSTEM_ROLE_PATTERN.fullmatch(role):
                raise RuntimeError(
                    f"Invalid required system role for {registration.app_id}: {role!r}"
                )
        if not _APP_ROUTE_BASE_PATTERN.fullmatch(registration.route_base):
            raise RuntimeError(
                f"Invalid app route base for {registration.app_id}: {registration.route_base!r}"
            )
        route_owner = app_id_by_route_base.get(registration.route_base)
        if route_owner is not None:
            raise RuntimeError(
                "Duplicate app route base: "
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

        for nav_item in registration.nav_items:
            _validate_identifier(nav_item.id, kind="nav id")
            nav_owner = app_id_by_nav_id.get(nav_item.id)
            if nav_owner is not None:
                raise RuntimeError(
                    "Duplicate app nav registration: "
                    f"{nav_item.id} ({nav_owner}, {registration.app_id})"
                )
            if nav_item.link_app_id is not None:
                _validate_identifier(nav_item.link_app_id, kind="nav link app id")
            app_id_by_nav_id[nav_item.id] = registration.app_id

        catalog_item = AppCatalogItem(
            app_id=registration.app_id,
            title=registration.title,
            route_base=registration.route_base,
            icon_key=registration.icon_key,
            execution_context_kind=cast(
                AppExecutionContextKind,
                contract["execution_context_kind"] if contract is not None else "company",
            ),
            resource_scope=cast(
                AppResourceScope,
                contract["resource_scope"] if contract is not None else "company",
            ),
            entry_route_id=(
                str(contract["entry_route_id"])
                if contract is not None
                else f"{registration.app_id}.root"
            ),
            launcher_category=registration.launcher_category,
            launcher_fixed=registration.launcher_fixed,
            launcher_personal_tools=registration.launcher_personal_tools,
            launcher_pinned_by_default=registration.launcher_pinned_by_default,
            nav_items=tuple(
                AppNavCatalogItem(
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
            required_system_roles=registration.required_system_roles,
        )
        catalog.append(catalog_item)
        by_app_id[registration.app_id] = catalog_item
        app_id_by_route_base[registration.route_base] = registration.app_id

    for app in catalog:
        for nav_item in app.nav_items:
            if nav_item.link_app_id is not None and nav_item.link_app_id not in by_app_id:
                raise RuntimeError(
                    "App nav registration "
                    f"{nav_item.id} references unknown app id: {nav_item.link_app_id}"
                )

    return AppRegistry(
        catalog=tuple(catalog),
        by_app_id=MappingProxyType(by_app_id),
    )


def app_is_available_to_system_roles(
    app: AppCatalogItem,
    system_roles: Iterable[str],
) -> bool:
    if not app.required_system_roles:
        return True
    return bool(set(system_roles).intersection(app.required_system_roles))


def _validate_identifier(value: str, *, kind: str) -> None:
    if not _APP_IDENTIFIER_PATTERN.fullmatch(value):
        raise RuntimeError(f"Invalid app {kind}: {value!r}")


__all__ = [
    "AppExecutionContextKind",
    "AppResourceScope",
    "AppCatalogItem",
    "AppRegistration",
    "AppRegistry",
    "AppNavCatalogItem",
    "AppNavRegistration",
    "app_is_available_to_system_roles",
    "compile_app_registry",
    "app_registration",
]
