from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypedDict

from open_work_hub_api.domains.auth.app_catalog import (
    AppCatalogItem,
    AppNavCatalogItem,
)
from open_work_hub_api.domains.auth.app_features import (
    is_catalog_feature_enabled,
)


class BootstrapNavItemProjection(TypedDict):
    id: str
    app_id: str
    title: str
    category: str
    icon_key: str
    link_app_id: str | None
    path_suffix: str | None
    absolute_path: str | None
    coming_soon: bool


class BootstrapAppProjection(TypedDict):
    app_id: str
    title: str
    route_base: str
    icon_key: str
    enabled: bool
    coming_soon: bool
    nav_items: list[BootstrapNavItemProjection]


@dataclass(frozen=True)
class BootstrapProjection:
    apps: list[BootstrapAppProjection]
    nav: list[BootstrapNavItemProjection]


def project_bootstrap_apps(
    catalog: Iterable[AppCatalogItem],
    *,
    enabled_app_ids: Iterable[str],
    settings: object,
) -> BootstrapProjection:
    enabled_app_id_set = set(enabled_app_ids)
    apps: list[BootstrapAppProjection] = []
    nav: list[BootstrapNavItemProjection] = []

    for app in catalog:
        if app.app_id not in enabled_app_id_set or not _app_feature_enabled(
            app,
            settings,
        ):
            continue
        nav_items = _project_bootstrap_nav_items(
            app,
            settings=settings,
        )
        apps.append(
            {
                "app_id": app.app_id,
                "title": app.title,
                "route_base": app.route_base,
                "icon_key": app.icon_key,
                "enabled": True,
                "coming_soon": app.coming_soon,
                "nav_items": nav_items,
            }
        )
        nav.extend(nav_items)

    return BootstrapProjection(
        apps=apps,
        nav=nav,
    )


def _app_feature_enabled(
    item: AppCatalogItem,
    settings: object,
) -> bool:
    return item.feature_flag is None or _setting_is_enabled(settings, item.feature_flag)


def _nav_item_feature_enabled(
    item: AppNavCatalogItem,
    settings: object,
) -> bool:
    return item.feature_flag is None or _setting_is_enabled(settings, item.feature_flag)


def _setting_is_enabled(settings: object, key: str) -> bool:
    return is_catalog_feature_enabled(settings, key)


def _project_bootstrap_nav_item(
    item: AppNavCatalogItem,
) -> BootstrapNavItemProjection:
    return {
        "id": item.id,
        "app_id": item.app_id,
        "title": item.title,
        "category": item.category,
        "icon_key": item.icon_key,
        "link_app_id": item.link_app_id,
        "path_suffix": item.path_suffix,
        "absolute_path": item.absolute_path,
        "coming_soon": item.coming_soon,
    }


def _project_bootstrap_nav_items(
    app: AppCatalogItem,
    *,
    settings: object,
) -> list[BootstrapNavItemProjection]:
    return [
        _project_bootstrap_nav_item(item)
        for item in app.nav_items
        if _nav_item_feature_enabled(item, settings)
    ]
