from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.app_bar_categories import (
    app_bar_category_app_ids_from_catalog,
)
from open_work_hub_api.domains.auth.app_bar_preferences import serialize_app_bar_layout
from open_work_hub_api.domains.auth.app_catalog import (
    iter_app_catalog,
)
from open_work_hub_api.domains.auth.app_features import (
    is_catalog_feature_enabled,
)
from open_work_hub_api.domains.auth.models import (
    AuditLog,
    CompanyAppControl,
    PlatformAppBarCategory,
    PlatformAppBarCategoryApp,
    User,
    UserSystemRole,
)
from open_work_hub_api.domains.auth.roles import (
    SYSTEM_PLATFORM_ADMIN,
    _sorted_system_roles,
    normalize_system_role,
)
from open_work_hub_api.domains.auth.roles import (
    SYSTEM_ROLE_ALIASES as SYSTEM_ROLE_ALIASES,
)
from open_work_hub_api.domains.auth.roles import (
    SYSTEM_ROLE_ORDER as SYSTEM_ROLE_ORDER,
)
from open_work_hub_api.domains.auth.roles import (
    SYSTEM_ROLE_PERMISSION_MAP as SYSTEM_ROLE_PERMISSION_MAP,
)
from open_work_hub_api.domains.auth.roles import (
    VALID_SYSTEM_ROLES as VALID_SYSTEM_ROLES,
)
from open_work_hub_api.domains.auth.roles import (
    is_valid_system_role as is_valid_system_role,
)
from open_work_hub_api.domains.auth.security import (
    hash_password,
    new_id,
)
from open_work_hub_api.domains.auth.session_lifecycle import revoke_active_impersonation_sessions
from open_work_hub_api.domains.groups.service import current_group_ids, managed_organization_ids
from open_work_hub_api.domains.organization.models import OrganizationUnit  # noqa: F401
from open_work_hub_api.domains.pms.roles import (
    TEAM_ROLE_ALIASES as TEAM_ROLE_ALIASES,
)
from open_work_hub_api.domains.pms.roles import (
    TEAM_ROLE_RANK as TEAM_ROLE_RANK,
)
from open_work_hub_api.domains.pms.roles import (
    VALID_TEAM_ROLES as VALID_TEAM_ROLES,
)
from open_work_hub_api.domains.pms.roles import (
    is_valid_team_role as is_valid_team_role,
)
from open_work_hub_api.domains.pms.roles import (
    team_role_allows as team_role_allows,
)

logger = logging.getLogger(__name__)


DEFAULT_TIME_ZONE = "Asia/Seoul"
DEFAULT_LOCALE = "ko-KR"
DEFAULT_DATE_FORMAT = "korean"
SUPPORTED_LOCALES = frozenset({"ko-KR", "en-US"})
SUPPORTED_DATE_FORMATS = frozenset({"korean", "iso", "us", "european", "locale"})


def normalize_time_zone(value: str | None) -> str:
    if value is None or not value.strip():
        return DEFAULT_TIME_ZONE
    normalized = value.strip()
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Invalid time zone.") from exc
    return normalized


def normalize_locale(value: str | None) -> str:
    if value is None or not value.strip():
        return DEFAULT_LOCALE
    normalized = value.strip()
    if normalized not in SUPPORTED_LOCALES:
        raise ValueError("Invalid locale.")
    return normalized


def normalize_date_format(value: str | None) -> str:
    if value is None or not value.strip():
        return DEFAULT_DATE_FORMAT
    normalized = value.strip()
    if normalized not in SUPPORTED_DATE_FORMATS:
        raise ValueError("Invalid date format.")
    return normalized


DEV_APP_BAR_CATEGORY_KEY = "dev-all-apps"
DEV_APP_BAR_CATEGORY_TITLE = "All Apps"
DEV_APP_BAR_CATEGORY_ICON_KEY = "layout-grid"

DEV_LOGIN_ACCOUNTS = [
    {
        "key": "administrator",
        "label": "Administrator",
        "email": "admin@open-work-hub.local",
        "description": "개발 환경 플랫폼 관리자",
        "category": "Administrators",
        "system_roles": [SYSTEM_PLATFORM_ADMIN],
    }
]

DEV_LOGIN_ACCOUNT_MAP = {item["key"]: item for item in DEV_LOGIN_ACCOUNTS}

USER_GRAPH_OPTIONS = (
    selectinload(User.primary_organization_unit),
    selectinload(User.system_role_links),
    selectinload(User.sessions),
)


def slugify(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("&", " and ")
        .replace("/", "-")
        .replace("_", "-")
        .replace(" ", "-")
    )


def _replace_user_system_roles(db: Session, user_id: str, roles: Sequence[str]) -> None:
    requested_roles = {
        normalized for role in roles if (normalized := normalize_system_role(role)) is not None
    }
    current_links = db.scalars(
        select(UserSystemRole).where(UserSystemRole.user_id == user_id)
    ).all()
    current_normalized_roles: set[str] = set()
    for link in current_links:
        normalized_role = normalize_system_role(link.role)
        if (
            normalized_role is None
            or normalized_role not in requested_roles
            or link.role != normalized_role
        ):
            db.delete(link)
            continue
        current_normalized_roles.add(normalized_role)
    for role in requested_roles - current_normalized_roles:
        db.add(UserSystemRole(id=new_id(), user_id=user_id, role=role))


def replace_user_system_roles(db: Session, user_id: str, roles: Sequence[str]) -> None:
    user = db.get(User, user_id)
    _replace_user_system_roles(db, user_id, roles)
    db.flush()
    if user is not None:
        db.expire(user, ["system_role_links"])
        if SYSTEM_PLATFORM_ADMIN not in resolve_system_roles(db, user):
            revoke_active_impersonation_sessions(
                db,
                impersonator_user_id=user.id,
                revoked_at=datetime.now(UTC).replace(tzinfo=None),
            )


def load_user_graph(db: Session, user_id: str) -> User | None:
    return db.scalar(
        select(User)
        .options(*USER_GRAPH_OPTIONS)
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )


def is_infrastructure_seeded(db: Session) -> bool:
    return db.scalar(select(CompanyAppControl.app_id).limit(1)) is not None


def ensure_seed_data(db: Session) -> None:
    """Initialize explicit company controls; new business apps start disabled."""
    from sqlalchemy.dialects.postgresql import insert

    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy

    for app in iter_app_catalog():
        db.execute(
            insert(CompanyAppControl)
            .values(app_id=app.app_id, enabled=app.app_id == "home")
            .on_conflict_do_nothing(index_elements=[CompanyAppControl.app_id])
        )
        db.execute(
            insert(AppAccessPolicy)
            .values(app_id=app.app_id, audience="all" if app.app_id == "home" else "selected")
            .on_conflict_do_nothing(index_elements=[AppAccessPolicy.app_id])
        )
    db.commit()


def _platform_app_bar_category_tables_exist(db: Session) -> bool:
    bind = db.get_bind()
    inspector = inspect(bind)
    return inspector.has_table(PlatformAppBarCategory.__tablename__) and inspector.has_table(
        PlatformAppBarCategoryApp.__tablename__
    )


def ensure_dev_seed_app_access(
    db: Session,
) -> None:
    """Make every registered launcher app available in the initial development deployment."""

    if not _platform_app_bar_category_tables_exist(db):
        return

    category = db.scalar(
        select(PlatformAppBarCategory).where(PlatformAppBarCategory.key == DEV_APP_BAR_CATEGORY_KEY)
    )
    if category is None:
        category = PlatformAppBarCategory(
            id=new_id(),
            key=DEV_APP_BAR_CATEGORY_KEY,
            title=DEV_APP_BAR_CATEGORY_TITLE,
            icon_key=DEV_APP_BAR_CATEGORY_ICON_KEY,
            position=0,
        )
        db.add(category)
        db.flush()

    existing_app_ids = set(db.scalars(select(PlatformAppBarCategoryApp.app_id)).all())
    category_apps = [app for app in iter_app_catalog() if app.launcher_category]
    for position, app in enumerate(category_apps):
        if app.app_id in existing_app_ids:
            continue
        db.add(
            PlatformAppBarCategoryApp(
                id=new_id(),
                category_id=category.id,
                app_id=app.app_id,
                position=position,
            )
        )
    db.flush()


def are_dev_login_accounts_seeded(db: Session) -> bool:
    required_emails = {definition["email"] for definition in DEV_LOGIN_ACCOUNTS}
    existing = set(db.scalars(select(User.email).where(User.email.in_(required_emails))).all())
    return required_emails.issubset(existing)


def ensure_dev_login_seed_data(db: Session) -> None:
    initial_seed = not is_infrastructure_seeded(db)
    ensure_seed_data(db)
    ensure_dev_seed_app_access(db)
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy

    if initial_seed:
        for app in iter_app_catalog():
            db.get(CompanyAppControl, app.app_id).enabled = True
            db.get(AppAccessPolicy, app.app_id).audience = "all"
    for definition in DEV_LOGIN_ACCOUNTS:
        user = db.scalar(select(User).where(User.email == definition["email"]))
        if user is None:
            user = User(
                id=new_id(),
                login_id=definition["key"],
                email=definition["email"],
                full_name=definition["label"],
                display_name=definition["label"],
                password_hash=hash_password(get_settings().dev_login_password),
                status="active",
                must_change_password=False,
                locale=DEFAULT_LOCALE,
                time_zone=DEFAULT_TIME_ZONE,
                date_format=DEFAULT_DATE_FORMAT,
            )
            db.add(user)
            db.flush()
            _replace_user_system_roles(db, user.id, definition["system_roles"])
    db.commit()


def list_dev_login_accounts(db: Session) -> list[dict[str, str]]:
    emails = [item["email"] for item in DEV_LOGIN_ACCOUNTS]
    users = {
        user.email: user
        for user in db.scalars(
            select(User).where(User.email.in_(emails), User.status == "active").order_by(User.email)
        ).all()
    }

    items: list[dict[str, str]] = []
    for definition in DEV_LOGIN_ACCOUNTS:
        if definition["email"] not in users:
            continue
        items.append(
            {
                "account_key": definition["key"],
                "label": definition["label"],
                "email": definition["email"],
                "description": definition["description"],
                "category": definition["category"],
            }
        )

    return items


def list_dev_login_account_catalog() -> list[dict[str, str]]:
    return [
        {
            "account_key": definition["key"],
            "label": definition["label"],
            "email": definition["email"],
            "description": definition["description"],
            "category": definition["category"],
        }
        for definition in DEV_LOGIN_ACCOUNTS
    ]


def get_dev_login_user(db: Session, account_key: str) -> User | None:
    definition = DEV_LOGIN_ACCOUNT_MAP.get(account_key)
    if definition is None:
        return None
    return db.scalar(select(User).where(User.email == definition["email"], User.status == "active"))


def resolve_system_roles(db: Session, user: User) -> list[str]:
    return _sorted_system_roles(
        set(db.scalars(select(UserSystemRole.role).where(UserSystemRole.user_id == user.id)))
    )


def has_system_role(db: Session, user: User, *roles: str) -> bool:
    role_set = set(resolve_system_roles(db, user))
    normalized_requested_roles = {
        normalized for role in roles if (normalized := normalize_system_role(role)) is not None
    }
    return any(role in role_set for role in normalized_requested_roles)


def is_platform_admin_user(user: User, db: Session) -> bool:
    return has_system_role(db, user, SYSTEM_PLATFORM_ADMIN)


def project_platform_app_bar_categories(
    db: Session,
    *,
    enabled_app_ids: set[str],
    settings: object,
) -> list[dict[str, Any]]:
    catalog_items = tuple(iter_app_catalog())
    catalog_by_app_id = {app.app_id: app for app in catalog_items}
    target_app_ids = app_bar_category_app_ids_from_catalog(catalog_items)

    def app_is_available(app_id: str) -> bool:
        app = catalog_by_app_id.get(app_id)
        if app is None or app_id not in target_app_ids or app_id not in enabled_app_ids:
            return False
        if app.feature_flag is not None and not is_catalog_feature_enabled(
            settings,
            app.feature_flag,
        ):
            return False
        return True

    def item_payload(app_id: str, *, position: int) -> dict[str, Any] | None:
        app = catalog_by_app_id.get(app_id)
        if app is None or not app_is_available(app_id):
            return None
        return {
            "app_id": app.app_id,
            "title": app.title,
            "route_base": app.route_base,
            "icon_key": app.icon_key,
            "enabled": True,
            "coming_soon": app.coming_soon,
            "position": position,
        }

    if not _platform_app_bar_category_tables_exist(db):
        return []

    category_rows = db.scalars(
        select(PlatformAppBarCategory)
        .options(selectinload(PlatformAppBarCategory.apps))
        .order_by(PlatformAppBarCategory.position.asc(), PlatformAppBarCategory.key.asc())
    ).all()
    categories = []
    for category in category_rows:
        app_rows = sorted(category.apps, key=lambda item: (item.position, item.app_id))
        items = [
            payload
            for row in app_rows
            if (payload := item_payload(row.app_id, position=row.position)) is not None
        ]
        if not items:
            continue
        categories.append(
            {
                "id": category.id,
                "key": category.key,
                "title": category.title,
                "icon_key": category.icon_key,
                "position": category.position,
                "items": items,
            }
        )
    return categories


def serialize_auth_user(db: Session, user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "login_id": user.login_id,
        "email": user.email,
        "full_name": user.full_name,
        "display_name": user.display_name or user.full_name,
        "employee_code": user.employee_code,
        "job_title": user.job_title,
        "primary_organization_unit": (
            {
                "id": user.primary_organization_unit.id,
                "name": user.primary_organization_unit.name,
                "slug": user.primary_organization_unit.slug,
                "unit_type": user.primary_organization_unit.unit_type,
                "active": user.primary_organization_unit.active,
            }
            if user.primary_organization_unit is not None
            else None
        ),
        "status": user.status,
        "login_blocked": user.login_blocked,
        "theme_preference": user.theme_preference,
        "locale": normalize_locale(getattr(user, "locale", None)),
        "time_zone": user.time_zone or DEFAULT_TIME_ZONE,
        "date_format": normalize_date_format(getattr(user, "date_format", None)),
        "app_bar_layout": serialize_app_bar_layout(getattr(user, "app_bar_layout", None)),
        "system_roles": resolve_system_roles(db, user),
        "group_ids": sorted(current_group_ids(db, user.id)),
        "managed_organization_unit_ids": managed_organization_ids(db, user.id),
        "is_department_head": bool(managed_organization_ids(db, user.id)),
        "must_change_password": user.must_change_password,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def serialize_session_item(
    session_id: str, current_session_id: str | None, session: Any
) -> dict[str, Any]:
    return {
        "id": session.id,
        "is_current": session.id == current_session_id,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "revoked_at": session.revoked_at,
        "last_seen_at": session.last_seen_at,
        "user_agent": session.user_agent,
        "ip_address": session.ip_address,
    }


def record_audit_log(
    db: Session,
    *,
    action: str,
    entity_kind: str,
    summary: str,
    actor_user_id: str | None = None,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    audit_payload = dict(payload or {})
    impersonator_user_id = db.info.get("impersonator_user_id")
    impersonated_user_id = db.info.get("impersonated_user_id")
    impersonation_session_id = db.info.get("impersonation_session_id")
    if (
        isinstance(impersonator_user_id, str)
        and isinstance(impersonated_user_id, str)
        and "impersonation" not in audit_payload
    ):
        audit_payload["impersonation"] = {
            "impersonator_user_id": impersonator_user_id,
            "impersonated_user_id": impersonated_user_id,
            "session_id": impersonation_session_id,
        }
    audit_log = AuditLog(
        id=new_id(),
        actor_user_id=actor_user_id,
        action=action,
        entity_kind=entity_kind,
        entity_id=entity_id,
        summary=summary,
        payload=audit_payload,
    )
    db.add(audit_log)
    return audit_log
