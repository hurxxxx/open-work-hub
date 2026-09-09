from __future__ import annotations

from open_work_hub_api.core.app_registry import AppCatalogItem


def is_app_bar_category_app(item: AppCatalogItem) -> bool:
    return item.launcher_category


def app_bar_category_app_ids_from_catalog(
    catalog: tuple[AppCatalogItem, ...],
) -> frozenset[str]:
    return frozenset(item.app_id for item in catalog if is_app_bar_category_app(item))
