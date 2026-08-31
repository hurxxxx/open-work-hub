from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.workspace_app_registry import WorkspaceAppCatalogItem
from open_work_hub_api.domains.auth.models import (
    CompanyAppControl,
    WorkspaceAppDefault,
    WorkspaceAppOverride,
)
from open_work_hub_api.domains.auth.workspace_app_features import (
    is_workspace_catalog_feature_enabled,
)
from open_work_hub_api.domains.auth.workspace_apps import (
    get_workspace_app_catalog_item,
    iter_workspace_app_catalog,
)


@dataclass(frozen=True)
class AppAvailabilitySnapshot:
    """Immutable bulk view of the runtime app-control truth.

    Static identity and feature metadata come from the compiled leaf-app
    catalog. Runtime enablement comes only from the control tables. Missing
    rows are disabled; catalog defaults are never an authorization fallback.
    """

    company_enabled_by_app_id: Mapping[str, bool]
    workspace_default_by_app_id: Mapping[str, bool]
    workspace_override_by_key: Mapping[tuple[str, str], bool]
    settings: object

    def company_enabled(self, app: WorkspaceAppCatalogItem) -> bool:
        return _catalog_feature_enabled(app, self.settings) and bool(
            self.company_enabled_by_app_id.get(app.app_id, False)
        )

    def platform_enabled(self, app: WorkspaceAppCatalogItem) -> bool:
        return app.availability_scope == "platform" and self.company_enabled(app)

    def workspace_enabled(
        self,
        app: WorkspaceAppCatalogItem,
        workspace_id: str,
    ) -> bool:
        if app.availability_scope != "workspace" or not self.company_enabled(app):
            return False
        override_key = (workspace_id, app.app_id)
        if override_key in self.workspace_override_by_key:
            return bool(self.workspace_override_by_key[override_key])
        return bool(self.workspace_default_by_app_id.get(app.app_id, False))

    def enabled(self, app: WorkspaceAppCatalogItem, *, workspace_id: str | None) -> bool:
        if app.availability_scope == "platform":
            return self.platform_enabled(app)
        return workspace_id is not None and self.workspace_enabled(app, workspace_id)


def _catalog_feature_enabled(app: WorkspaceAppCatalogItem, settings: object) -> bool:
    return app.feature_flag is None or is_workspace_catalog_feature_enabled(
        settings,
        app.feature_flag,
    )


def load_app_availability_snapshot(
    db: Session,
    *,
    workspace_ids: Iterable[str] = (),
    settings: object | None = None,
) -> AppAvailabilitySnapshot:
    normalized_workspace_ids = tuple(dict.fromkeys(workspace_ids))
    company_controls = MappingProxyType(
        dict(db.execute(select(CompanyAppControl.app_id, CompanyAppControl.enabled)).all())
    )
    workspace_defaults = MappingProxyType(
        dict(db.execute(select(WorkspaceAppDefault.app_id, WorkspaceAppDefault.enabled)).all())
    )
    workspace_overrides: dict[tuple[str, str], bool] = {}
    if normalized_workspace_ids:
        workspace_overrides = {
            (workspace_id, app_id): bool(enabled)
            for workspace_id, app_id, enabled in db.execute(
                select(
                    WorkspaceAppOverride.workspace_id,
                    WorkspaceAppOverride.app_id,
                    WorkspaceAppOverride.enabled,
                ).where(WorkspaceAppOverride.workspace_id.in_(normalized_workspace_ids))
            ).all()
        }
    return AppAvailabilitySnapshot(
        company_enabled_by_app_id=company_controls,
        workspace_default_by_app_id=workspace_defaults,
        workspace_override_by_key=MappingProxyType(workspace_overrides),
        settings=settings if settings is not None else get_settings(),
    )


def is_company_app_enabled(db: Session, app_id: str) -> bool:
    app = get_workspace_app_catalog_item(app_id)
    if app is None:
        return False
    return load_app_availability_snapshot(db).company_enabled(app)


def is_app_enabled(
    db: Session,
    app_id: str,
    *,
    workspace_id: str | None = None,
) -> bool:
    app = get_workspace_app_catalog_item(app_id)
    if app is None:
        return False
    return load_app_availability_snapshot(
        db,
        workspace_ids=(workspace_id,) if workspace_id is not None else (),
    ).enabled(app, workspace_id=workspace_id)


def is_platform_app_enabled(db: Session, app_id: str) -> bool:
    app = get_workspace_app_catalog_item(app_id)
    if app is None:
        return False
    return load_app_availability_snapshot(db).platform_enabled(app)


def is_workspace_app_enabled(db: Session, workspace_id: str, app_id: str) -> bool:
    app = get_workspace_app_catalog_item(app_id)
    if app is None:
        return False
    return load_app_availability_snapshot(
        db,
        workspace_ids=(workspace_id,),
    ).enabled(app, workspace_id=workspace_id)


def resolve_company_enabled_app_ids(db: Session) -> list[str]:
    snapshot = load_app_availability_snapshot(db)
    return sorted(
        app.app_id for app in iter_workspace_app_catalog() if snapshot.company_enabled(app)
    )


def resolve_platform_enabled_app_ids(db: Session) -> list[str]:
    snapshot = load_app_availability_snapshot(db)
    return sorted(
        app.app_id for app in iter_workspace_app_catalog() if snapshot.platform_enabled(app)
    )


def resolve_workspace_enabled_app_ids(db: Session, workspace_id: str) -> list[str]:
    snapshot = load_app_availability_snapshot(db, workspace_ids=(workspace_id,))
    return sorted(
        app.app_id
        for app in iter_workspace_app_catalog()
        if snapshot.workspace_enabled(app, workspace_id)
    )


def resolve_workspace_runtime_enabled_app_ids(db: Session, workspace_id: str) -> list[str]:
    snapshot = load_app_availability_snapshot(db, workspace_ids=(workspace_id,))
    return sorted(
        app.app_id
        for app in iter_workspace_app_catalog()
        if snapshot.enabled(app, workspace_id=workspace_id)
    )


__all__ = [
    "AppAvailabilitySnapshot",
    "is_app_enabled",
    "is_company_app_enabled",
    "is_platform_app_enabled",
    "is_workspace_app_enabled",
    "load_app_availability_snapshot",
    "resolve_company_enabled_app_ids",
    "resolve_platform_enabled_app_ids",
    "resolve_workspace_enabled_app_ids",
    "resolve_workspace_runtime_enabled_app_ids",
]
