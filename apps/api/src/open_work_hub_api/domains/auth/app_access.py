from __future__ import annotations

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.app_access_models import (
    AppAccessPolicy,
    AppGroupGrant,
    AppUserGrant,
)
from open_work_hub_api.domains.auth.app_catalog import iter_app_catalog
from open_work_hub_api.domains.auth.app_features import is_catalog_feature_enabled
from open_work_hub_api.domains.auth.models import CompanyAppControl, User, UserSystemRole
from open_work_hub_api.domains.groups.service import user_group_ids_query


def can_use_app(db: Session, *, user_id: str, app_id: str) -> bool:
    """App admission only. The app must independently authorize its resource/action."""
    return app_id in allowed_app_ids(db, user_id=user_id)


def allowed_app_ids(db: Session, *, user_id: str) -> frozenset[str]:
    """Read current authority in bulk. Never cache this result across operations."""
    if (
        db.scalar(
            select(User.id).where(
                User.id == user_id,
                User.status == "active",
                User.login_blocked.is_(False),
                User.must_change_password.is_(False),
            )
        )
        is None
    ):
        return frozenset()
    roles = set(db.scalars(select(UserSystemRole.role).where(UserSystemRole.user_id == user_id)))
    statement = (
        select(AppAccessPolicy.app_id)
        .join(CompanyAppControl, CompanyAppControl.app_id == AppAccessPolicy.app_id)
        .where(
            CompanyAppControl.enabled.is_(True), AppAccessPolicy.audience.in_(("all", "selected"))
        )
    )
    if "platform_admin" not in roles:
        statement = statement.where(
            or_(
                AppAccessPolicy.audience == "all",
                exists().where(
                    AppUserGrant.app_id == AppAccessPolicy.app_id,
                    AppUserGrant.user_id == user_id,
                ),
                exists().where(
                    AppGroupGrant.app_id == AppAccessPolicy.app_id,
                    AppGroupGrant.group_id.in_(user_group_ids_query(user_id)),
                ),
            )
        )
    admitted = set(db.scalars(statement))
    settings = get_settings()
    return frozenset(
        app.app_id
        for app in iter_app_catalog()
        if app.app_id in admitted
        and (not app.required_system_roles or roles.intersection(app.required_system_roles))
        and (app.feature_flag is None or is_catalog_feature_enabled(settings, app.feature_flag))
    )
