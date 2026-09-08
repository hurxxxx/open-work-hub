from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.app_registry import AppCatalogItem
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.app_catalog import get_app_catalog_item, iter_app_catalog
from open_work_hub_api.domains.auth.app_features import is_catalog_feature_enabled
from open_work_hub_api.domains.auth.models import CompanyAppControl


@dataclass(frozen=True)
class AppAvailabilitySnapshot:
    """Company master switches. User work additionally requires app admission."""

    company_enabled_by_app_id: Mapping[str, bool]
    settings: object

    def company_enabled(self, app: AppCatalogItem) -> bool:
        return bool(self.company_enabled_by_app_id.get(app.app_id, False)) and (
            app.feature_flag is None or is_catalog_feature_enabled(self.settings, app.feature_flag)
        )


def load_app_availability_snapshot(
    db: Session, *, settings: object | None = None
) -> AppAvailabilitySnapshot:
    return AppAvailabilitySnapshot(
        company_enabled_by_app_id=MappingProxyType(
            dict(db.execute(select(CompanyAppControl.app_id, CompanyAppControl.enabled)).all())
        ),
        settings=settings if settings is not None else get_settings(),
    )


def is_company_app_enabled(db: Session, app_id: str) -> bool:
    app = get_app_catalog_item(app_id)
    return app is not None and load_app_availability_snapshot(db).company_enabled(app)


def resolve_company_enabled_app_ids(db: Session) -> list[str]:
    snapshot = load_app_availability_snapshot(db)
    return sorted(app.app_id for app in iter_app_catalog() if snapshot.company_enabled(app))
