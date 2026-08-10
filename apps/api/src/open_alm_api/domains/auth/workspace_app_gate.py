from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, status
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.principal import CallerPrincipal
from open_alm_api.core.settings import get_settings
from open_alm_api.domains.auth.dependencies import require_current_workspace
from open_alm_api.domains.auth.models import (
    PlatformAppVisibility,
    Workspace,
    WorkspaceAppEntitlement,
)
from open_alm_api.domains.auth.workspace_app_features import (
    is_workspace_catalog_feature_enabled,
)
from open_alm_api.domains.auth.workspace_apps import get_workspace_app_catalog_item


def _setting_is_enabled(key: str) -> bool:
    settings = get_settings()
    return is_workspace_catalog_feature_enabled(settings, key)


def _catalog_feature_enabled(app_id: str) -> bool:
    catalog_item = get_workspace_app_catalog_item(app_id)
    return catalog_item is not None and (
        catalog_item.feature_flag is None or _setting_is_enabled(catalog_item.feature_flag)
    )


def _table_exists(db: Session, table_name: str) -> bool:
    return inspect(db.get_bind()).has_table(table_name)


def _platform_app_visible(db: Session, app_id: str) -> bool:
    catalog_item = get_workspace_app_catalog_item(app_id)
    default_visible = bool(catalog_item.visible_by_default) if catalog_item else False
    if not _table_exists(db, PlatformAppVisibility.__tablename__):
        return default_visible
    visible = db.scalar(
        select(PlatformAppVisibility.visible).where(PlatformAppVisibility.app_id == app_id)
    )
    return default_visible if visible is None else bool(visible)


def is_platform_app_enabled(db: Session, app_id: str) -> bool:
    catalog_item = get_workspace_app_catalog_item(app_id)
    if catalog_item is None or not _catalog_feature_enabled(app_id):
        return False
    return _platform_app_visible(db, app_id)


def is_workspace_app_enabled(db: Session, workspace_id: str, app_id: str) -> bool:
    catalog_item = get_workspace_app_catalog_item(app_id)
    if catalog_item is None or not _catalog_feature_enabled(app_id):
        return False
    if catalog_item.availability_scope == "platform":
        return _platform_app_visible(db, app_id)
    default_enabled = bool(catalog_item.enabled_by_default)
    if not _table_exists(db, WorkspaceAppEntitlement.__tablename__):
        return default_enabled and _platform_app_visible(db, app_id)

    visibility_override = db.scalar(
        select(WorkspaceAppEntitlement.visibility_override).where(
            WorkspaceAppEntitlement.workspace_id == workspace_id,
            WorkspaceAppEntitlement.app_id == app_id,
        )
    )
    if visibility_override is not None:
        return bool(visibility_override)
    return default_enabled and _platform_app_visible(db, app_id)


def is_app_enabled_for_principal(
    db: Session,
    principal: CallerPrincipal,
    app_id: str,
) -> bool:
    catalog_item = get_workspace_app_catalog_item(app_id)
    if catalog_item is None:
        return False
    if catalog_item.availability_scope == "platform":
        return is_platform_app_enabled(db, app_id)
    if principal.workspace_id is None:
        return False
    return is_workspace_app_enabled(db, principal.workspace_id, app_id)


def require_workspace_app_enabled(
    app_id: str,
    *,
    error_code: str,
) -> Callable[..., None]:
    def dependency(
        db: Session = Depends(get_db_session),
        current_workspace: Workspace = Depends(require_current_workspace),
    ) -> None:
        if not is_workspace_app_enabled(db, current_workspace.id, app_id):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code=error_code,
            )

    return dependency


def require_platform_app_enabled(
    app_id: str,
    *,
    error_code: str = "platform.app_disabled",
) -> Callable[..., None]:
    def dependency(
        db: Session = Depends(get_db_session),
    ) -> None:
        if not is_platform_app_enabled(db, app_id):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code=error_code,
            )

    return dependency


__all__ = [
    "is_app_enabled_for_principal",
    "is_platform_app_enabled",
    "is_workspace_app_enabled",
    "require_platform_app_enabled",
    "require_workspace_app_enabled",
]
