from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.app_bar_preferences import serialize_app_bar_layout
from open_work_hub_api.domains.auth.app_bar_categories import (
    app_bar_category_app_ids_from_catalog,
)
from open_work_hub_api.domains.auth.app_availability import (
    resolve_workspace_enabled_app_ids,
)
from open_work_hub_api.domains.auth.roles import (
    SYSTEM_PLATFORM_ADMIN,
    SYSTEM_ROLE_ALIASES as SYSTEM_ROLE_ALIASES,
    SYSTEM_ROLE_ORDER as SYSTEM_ROLE_ORDER,
    SYSTEM_ROLE_PERMISSION_MAP as SYSTEM_ROLE_PERMISSION_MAP,
    TEAM_ROLE_ALIASES as TEAM_ROLE_ALIASES,
    TEAM_ROLE_RANK as TEAM_ROLE_RANK,
    VALID_SYSTEM_ROLES as VALID_SYSTEM_ROLES,
    VALID_TEAM_ROLES as VALID_TEAM_ROLES,
    VALID_WORKSPACE_ROLES as VALID_WORKSPACE_ROLES,
    WORKSPACE_ROLE_ALIASES as WORKSPACE_ROLE_ALIASES,
    WORKSPACE_ROLE_RANK as WORKSPACE_ROLE_RANK,
    _higher_team_role,
    _higher_workspace_role,
    _sorted_system_roles,
    is_valid_system_role as is_valid_system_role,
    is_valid_team_role as is_valid_team_role,
    is_valid_workspace_role as is_valid_workspace_role,
    normalize_system_role,
    normalize_team_role,
    normalize_workspace_role,
    team_role_allows as team_role_allows,
    workspace_role_allows as workspace_role_allows,
)
from open_work_hub_api.domains.auth.models import (
    AuditLog,
    PlatformAppBarCategory,
    PlatformAppBarCategoryApp,
    Team,
    TeamMember,
    User,
    UserSystemRole,
    Workspace,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.auth.workspace_apps import (
    iter_workspace_app_catalog,
)
from open_work_hub_api.domains.organization.models import OrganizationUnit  # noqa: F401
from open_work_hub_api.domains.auth.workspace_app_features import (
    is_workspace_catalog_feature_enabled,
)
from open_work_hub_api.domains.auth.workspace_bootstrap_projection import (
    project_workspace_bootstrap_apps,
)
from open_work_hub_api.domains.auth.security import (
    derive_login_id_from_email,
    hash_password,
    new_id,
)
from open_work_hub_api.domains.auth.session_lifecycle import revoke_active_impersonation_sessions

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


DEFAULT_WORKSPACE_SEEDS = [
    {
        "key": "administrator",
        "name": "Administrator",
        "description": "Administrator workspace.",
    },
    {
        "key": "general",
        "name": "General",
        "description": "General collaboration workspace.",
    },
]
DEV_WORKSPACE_SEEDS = []
DEV_WORKSPACE_SEED_KEYS = frozenset(
    definition["key"] for definition in [*DEFAULT_WORKSPACE_SEEDS, *DEV_WORKSPACE_SEEDS]
)

DEFAULT_PMS_SPACE_KEY = "team-space"
DEFAULT_PMS_SPACE_NAME = "Team Space"
DEFAULT_PMS_SPACE_DESCRIPTION = "Default PMS space for shared lists and docs."

DEV_APP_BAR_CATEGORY_KEY = "dev-all-apps"
DEV_APP_BAR_CATEGORY_TITLE = "All Apps"
DEV_APP_BAR_CATEGORY_ICON_KEY = "layout-grid"

DEV_LOGIN_ACCOUNTS = [
    {
        "key": "administrator",
        "label": "Administrator",
        "email": "admin@open-work-hub.local",
        "description": "관리자 권한으로 기본 워크스페이스를 관리합니다.",
        "category": "Administrators",
        "system_roles": [SYSTEM_PLATFORM_ADMIN],
        "workspace_memberships": [("administrator", "admin"), ("general", "admin")],
        "team_memberships": [("administrator", "owner"), ("general", "owner")],
    },
]

DEV_LOGIN_ACCOUNT_MAP = {item["key"]: item for item in DEV_LOGIN_ACCOUNTS}

USER_GRAPH_OPTIONS = (
    selectinload(User.primary_organization_unit),
    selectinload(User.system_role_links),
    selectinload(User.workspace_bindings).joinedload(WorkspaceUserBinding.workspace),
    selectinload(User.team_memberships).joinedload(TeamMember.team).joinedload(Team.workspace),
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
    if user is not None:
        # An explicit replacement supersedes the legacy independent admin grant.
        user.is_admin = False
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


CURRENT_WORKSPACE_DB_INFO_KEY = "current_workspace"


def bind_current_workspace(db: Session, workspace: Workspace | None) -> None:
    if workspace is None:
        db.info.pop(CURRENT_WORKSPACE_DB_INFO_KEY, None)
        return
    db.info[CURRENT_WORKSPACE_DB_INFO_KEY] = workspace


def reset_current_workspace(db: Session) -> None:
    db.info.pop(CURRENT_WORKSPACE_DB_INFO_KEY, None)


def get_current_workspace(db: Session) -> Workspace | None:
    workspace = db.info.get(CURRENT_WORKSPACE_DB_INFO_KEY)
    return workspace if isinstance(workspace, Workspace) else None


def is_infrastructure_seeded(db: Session) -> bool:
    workspace_id = db.scalar(select(Workspace.id).limit(1))
    return workspace_id is not None


def _ensure_user_system_role_migration(db: Session) -> None:
    for user in db.scalars(select(User)).all():
        current_roles = {
            normalize_system_role(role)
            for role in db.scalars(
                select(UserSystemRole.role).where(UserSystemRole.user_id == user.id)
            ).all()
            if normalize_system_role(role) is not None
        }
        migrated_roles: set[str] = set()
        if user.is_admin or SYSTEM_PLATFORM_ADMIN in current_roles:
            migrated_roles.add(SYSTEM_PLATFORM_ADMIN)
        if current_roles - migrated_roles:
            _replace_user_system_roles(db, user.id, list(migrated_roles))


def _ensure_workspace_rows(
    db: Session,
    definitions: Sequence[dict[str, Any]],
) -> dict[str, Workspace]:
    workspaces = {workspace.key: workspace for workspace in db.scalars(select(Workspace)).all()}
    ensured: dict[str, Workspace] = {}
    for definition in definitions:
        workspace = workspaces.get(definition["key"])
        if workspace is None:
            workspace = Workspace(
                id=new_id(),
                key=definition["key"],
                name=definition["name"],
                description=definition["description"],
                active=True,
            )
            db.add(workspace)
            db.flush()
        else:
            workspace.name = definition["name"]
            workspace.description = definition["description"]
            workspace.active = True
            db.add(workspace)
            db.flush()

        ensure_workspace_default_pms_space(db, workspace)
        ensured[workspace.key] = workspace

    return ensured


def ensure_seed_data(db: Session) -> None:
    _ensure_user_system_role_migration(db)

    existing_workspaces = list(db.scalars(select(Workspace)).all())
    if not existing_workspaces:
        _ensure_workspace_rows(db, DEFAULT_WORKSPACE_SEEDS)
    else:
        for workspace in existing_workspaces:
            ensure_workspace_default_pms_space(db, workspace)

    if not _platform_app_bar_category_tables_exist(db):
        logger.warning(
            "platform app bar category tables are missing; app bar categories remain "
            "empty until alembic migrations are applied."
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
    workspace_by_key: dict[str, Workspace],
) -> None:
    """Make every registered launcher app available in development seed workspaces."""

    del workspace_by_key

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
    category_apps = [app for app in iter_workspace_app_catalog() if app.launcher_category]
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


def are_dev_workspace_seeds_present(db: Session) -> bool:
    existing_keys = set(
        db.scalars(
            select(Workspace.key).where(Workspace.key.in_(tuple(DEV_WORKSPACE_SEED_KEYS)))
        ).all()
    )
    return DEV_WORKSPACE_SEED_KEYS.issubset(existing_keys)


def _sync_user_workspace_memberships(
    db: Session,
    user: User,
    membership_defs: Sequence[tuple[str, str]],
    workspace_by_key: dict[str, Workspace],
) -> None:
    requested = {
        workspace_by_key[workspace_key].id: normalized_role
        for workspace_key, role in membership_defs
        if workspace_key in workspace_by_key
        and (normalized_role := normalize_workspace_role(role)) is not None
    }
    current_bindings = {
        binding.workspace_id: binding
        for binding in db.scalars(
            select(WorkspaceUserBinding).where(WorkspaceUserBinding.user_id == user.id)
        ).all()
    }
    for workspace_id, binding in list(current_bindings.items()):
        next_role = requested.get(workspace_id)
        if next_role is None:
            db.delete(binding)
            continue
        binding.role = next_role
        db.add(binding)
    for workspace_id, role in requested.items():
        if workspace_id in current_bindings:
            continue
        db.add(
            WorkspaceUserBinding(
                id=new_id(),
                workspace_id=workspace_id,
                user_id=user.id,
                role=role,
            )
        )


def _sync_seed_default_space_memberships(
    db: Session,
    user: User,
    team_memberships: Sequence[tuple[str, str]],
    default_spaces_by_workspace_key: dict[str, Team],
) -> None:
    requested_roles = {
        default_spaces_by_workspace_key[workspace_key].id: normalized_role
        for workspace_key, role in team_memberships
        if workspace_key in default_spaces_by_workspace_key
        and (normalized_role := normalize_team_role(role)) is not None
    }
    current_memberships = {
        membership.team_id: membership
        for membership in db.scalars(
            select(TeamMember).where(
                TeamMember.user_id == user.id,
                TeamMember.team_id.in_(
                    [space.id for space in default_spaces_by_workspace_key.values()]
                ),
            )
        ).all()
    }
    for team_id, membership in list(current_memberships.items()):
        next_role = requested_roles.get(team_id)
        if next_role is None:
            db.delete(membership)
            continue
        membership.role = next_role
        db.add(membership)
    for team_id, role in requested_roles.items():
        if team_id in current_memberships:
            continue
        db.add(
            TeamMember(
                id=new_id(),
                team_id=team_id,
                user_id=user.id,
                role=role,
            )
        )


def ensure_dev_login_seed_data(db: Session) -> None:
    if (
        is_infrastructure_seeded(db)
        and are_dev_login_accounts_seeded(db)
        and are_dev_workspace_seeds_present(db)
    ):
        workspace_by_key = {
            workspace.key: workspace
            for workspace in db.scalars(select(Workspace).where(Workspace.active.is_(True))).all()
        }
        ensure_dev_seed_app_access(db, workspace_by_key)
        db.commit()
        return

    ensure_seed_data(db)
    workspace_by_key = {
        **{
            workspace.key: workspace
            for workspace in db.scalars(select(Workspace).where(Workspace.active.is_(True))).all()
        },
        **_ensure_workspace_rows(db, [*DEFAULT_WORKSPACE_SEEDS, *DEV_WORKSPACE_SEEDS]),
    }
    ensure_dev_seed_app_access(db, workspace_by_key)
    default_spaces_by_workspace_key = {
        workspace_key: ensure_workspace_default_pms_space(db, workspace)
        for workspace_key, workspace in workspace_by_key.items()
    }

    dev_login_password = get_settings().dev_login_password
    for definition in DEV_LOGIN_ACCOUNTS:
        user = db.scalar(select(User).where(User.email == definition["email"]))
        if user is None:
            user = User(
                id=new_id(),
                login_id=definition["key"],
                email=definition["email"],
                full_name=definition["label"],
                display_name=definition["label"],
                password_hash=hash_password(dev_login_password),
                status="active",
                must_change_password=False,
                theme_preference="system",
                locale=DEFAULT_LOCALE,
                time_zone=DEFAULT_TIME_ZONE,
                date_format=DEFAULT_DATE_FORMAT,
                is_admin=False,
            )
        else:
            user.login_id = getattr(user, "login_id", None) or derive_login_id_from_email(
                definition["email"]
            )
            user.full_name = definition["label"]
            user.display_name = definition["label"]
            user.password_hash = hash_password(dev_login_password)
            user.status = "active"
            user.must_change_password = False
            user.theme_preference = "system"
            user.locale = normalize_locale(getattr(user, "locale", None))
            user.time_zone = normalize_time_zone(getattr(user, "time_zone", None))
            user.date_format = normalize_date_format(getattr(user, "date_format", None))
            user.is_admin = False
        db.add(user)
        db.flush()

        _replace_user_system_roles(db, user.id, definition.get("system_roles", []))
        _sync_user_workspace_memberships(
            db,
            user,
            definition.get("workspace_memberships", []),
            workspace_by_key,
        )
        _sync_seed_default_space_memberships(
            db,
            user,
            definition.get("team_memberships", []),
            default_spaces_by_workspace_key,
        )

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


def ensure_workspace_default_pms_space(db: Session, workspace: Workspace) -> Team:
    team = db.scalar(
        select(Team).where(
            Team.workspace_id == workspace.id,
            Team.key == DEFAULT_PMS_SPACE_KEY,
        )
    )
    if team is not None:
        team.active = True
        team.trashed_at = None
        db.add(team)
        db.flush()
        return team

    team = Team(
        id=new_id(),
        workspace_id=workspace.id,
        key=DEFAULT_PMS_SPACE_KEY,
        name=DEFAULT_PMS_SPACE_NAME,
        description=DEFAULT_PMS_SPACE_DESCRIPTION,
        active=True,
    )
    db.add(team)
    db.flush()
    return team


def get_or_create_default_pms_space(db: Session, *, workspace: Workspace) -> Team:
    return ensure_workspace_default_pms_space(db, workspace)


def resolve_system_roles(db: Session, user: User) -> list[str]:
    roles = {
        normalized_role
        for link in getattr(user, "system_role_links", [])
        if (normalized_role := normalize_system_role(link.role)) is not None
    }

    if user.is_admin:
        roles.add(SYSTEM_PLATFORM_ADMIN)

    return _sorted_system_roles(roles)


def has_system_role(db: Session, user: User, *roles: str) -> bool:
    role_set = set(resolve_system_roles(db, user))
    normalized_requested_roles = {
        normalized for role in roles if (normalized := normalize_system_role(role)) is not None
    }
    return any(role in role_set for role in normalized_requested_roles)


def is_platform_admin_user(user: User, db: Session | None = None) -> bool:
    if db is None:
        return user.is_admin
    return has_system_role(db, user, SYSTEM_PLATFORM_ADMIN)


def load_active_workspace_by_id(db: Session, workspace_id: str) -> Workspace | None:
    return db.scalar(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.active.is_(True))
    )


def load_active_workspace_by_key(db: Session, workspace_key: str) -> Workspace | None:
    return db.scalar(
        select(Workspace).where(Workspace.key == workspace_key, Workspace.active.is_(True))
    )


def resolve_workspace_role_map(db: Session, user: User) -> dict[str, str]:
    role_map: dict[str, str] = {}

    for binding in user.workspace_bindings:
        normalized_role = normalize_workspace_role(binding.role)
        if not binding.workspace.active or normalized_role is None:
            continue
        role_map[binding.workspace_id] = (
            _higher_workspace_role(
                role_map.get(binding.workspace_id),
                normalized_role,
            )
            or normalized_role
        )

    return role_map


def resolve_workspace_role(db: Session, user: User, workspace_id: str) -> str | None:
    # Authorization must not reuse a relationship loaded before a revocation.
    role = db.scalar(
        select(WorkspaceUserBinding.role)
        .join(Workspace, Workspace.id == WorkspaceUserBinding.workspace_id)
        .join(User, User.id == WorkspaceUserBinding.user_id)
        .where(
            WorkspaceUserBinding.workspace_id == workspace_id,
            WorkspaceUserBinding.user_id == user.id,
            Workspace.active.is_(True),
            User.status == "active",
            User.login_blocked.is_(False),
        )
    )
    return normalize_workspace_role(role)


def resolve_team_role(db: Session, user: User, team: Team) -> str | None:
    effective_role = None
    workspace_role = resolve_workspace_role(db, user, team.workspace_id)
    if workspace_role is None or not team.active or team.trashed_at is not None:
        return None
    if workspace_role == "admin":
        effective_role = _higher_team_role(effective_role, "admin")

    membership_role = db.scalar(
        select(TeamMember.role).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user.id,
        )
    )
    effective_role = _higher_team_role(effective_role, membership_role)
    return normalize_team_role(effective_role)


def resolve_workspaces(db: Session, user: User) -> list[dict[str, Any]]:
    active_workspaces = db.scalars(
        select(Workspace)
        .where(Workspace.active.is_(True))
        .order_by(Workspace.name.asc(), Workspace.key.asc())
    ).all()
    role_map = resolve_workspace_role_map(db, user)

    items: list[dict[str, Any]] = []
    for workspace in active_workspaces:
        role = role_map.get(workspace.id)
        if role is None:
            continue
        items.append(
            {
                "id": workspace.id,
                "slug": workspace.key,
                "name": workspace.name,
                "role": role,
            }
        )
    return items


def project_platform_app_bar_categories(
    db: Session,
    *,
    enabled_app_ids: set[str],
    settings: object,
) -> list[dict[str, Any]]:
    catalog_items = tuple(iter_workspace_app_catalog())
    catalog_by_app_id = {app.app_id: app for app in catalog_items}
    target_app_ids = app_bar_category_app_ids_from_catalog(catalog_items)

    def app_is_available(app_id: str) -> bool:
        app = catalog_by_app_id.get(app_id)
        if app is None or app_id not in target_app_ids or app_id not in enabled_app_ids:
            return False
        if app.feature_flag is not None and not is_workspace_catalog_feature_enabled(
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
            "availability_scope": app.availability_scope,
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


def build_workspace_bootstrap(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    source: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    role = resolve_workspace_role(db, user, workspace.id)
    enabled_app_ids = set(resolve_workspace_enabled_app_ids(db, workspace.id))
    settings = get_settings()
    catalog = iter_workspace_app_catalog()
    app_nav_projection = project_workspace_bootstrap_apps(
        catalog,
        enabled_app_ids=enabled_app_ids,
        settings=settings,
    )
    app_bar_categories = project_platform_app_bar_categories(
        db,
        enabled_app_ids=enabled_app_ids,
        settings=settings,
    )

    # Business-chat context picker entries are intentionally narrower than the
    # full tool registry. They must be registered, runtime-enabled, and allowed
    # by the business-chat context policy.
    from open_work_hub_api.domains.ai.chat_context_policy import (
        filter_business_chat_context_app_ids,
    )
    from open_work_hub_api.domains.ai.registry import get_chatbot_capable_app_ids

    chatbot_app_ids = filter_business_chat_context_app_ids(
        app_id for app_id in get_chatbot_capable_app_ids() if app_id in enabled_app_ids
    )

    from open_work_hub_api.domains.search.entity_adapter_registry import (
        resolve_workspace_keyword_search_scope,
    )

    keyword_search_scope = resolve_workspace_keyword_search_scope(enabled_app_ids)

    return {
        "workspace": {
            "id": workspace.id,
            "slug": workspace.key,
            "name": workspace.name,
            "role": role or "member",
        },
        "apps": app_nav_projection.apps,
        "app_bar_categories": app_bar_categories,
        "nav": app_nav_projection.nav,
        "chatbot_app_ids": chatbot_app_ids,
        "keyword_search": {
            "entity_types": [
                {
                    "value": descriptor.entity_type,
                    "label": descriptor.label,
                    "label_key": descriptor.label_key,
                }
                for descriptor in keyword_search_scope.descriptors
            ]
        },
        "principal": {
            "kind": "user",
            "workspace_id": workspace.id,
            "source": source,
            "user_id": user.id,
            "session_id": session_id,
        },
    }


def resolve_workspace_roles(db: Session, user: User) -> list[dict[str, str]]:
    return [
        {
            "workspace_id": item["id"],
            "key": item["slug"],
            "name": item["name"],
            "role": item["role"],
        }
        for item in resolve_workspaces(db, user)
    ]


def serialize_auth_user(db: Session, user: User) -> dict[str, Any]:
    workspaces = resolve_workspaces(db, user)
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
        "workspaces": workspaces,
        "workspace_roles": [
            {
                "workspace_id": item["id"],
                "key": item["slug"],
                "name": item["name"],
                "role": item["role"],
            }
            for item in workspaces
        ],
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
