from __future__ import annotations

from open_work_hub_api.core.workspace_app_registry import WorkspaceAppCatalogItem


def is_app_bar_category_app(item: WorkspaceAppCatalogItem) -> bool:
    return item.launcher_category


def is_platform_visibility_app(item: WorkspaceAppCatalogItem) -> bool:
    return item.launcher_category or item.launcher_personal_tools


def app_bar_category_app_ids_from_catalog(
    catalog: tuple[WorkspaceAppCatalogItem, ...],
) -> frozenset[str]:
    return frozenset(item.app_id for item in catalog if is_app_bar_category_app(item))
