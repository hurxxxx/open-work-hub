from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai_do_api.domains.auth.models import (
    AccessGroup,
    AuditLog,
    GroupSystemRole,
    OrgUnit,
    Team,
    TeamMember,
    User,
    UserAccessGroup,
    UserSystemRole,
    Workspace,
    WorkspaceAppEntitlement,
    WorkspaceGroupBinding,
    WorkspaceUserBinding,
)
from ai_do_api.domains.auth.workspace_apps import (
    WORKSPACE_APP_IDS,
    iter_workspace_app_catalog,
)
from ai_do_api.domains.auth.security import hash_password, new_id

logger = logging.getLogger(__name__)


SYSTEM_PLATFORM_ADMIN = "platform_admin"
DEFAULT_TIME_ZONE = "Asia/Seoul"
DEFAULT_LOCALE = "ko-KR"
SUPPORTED_LOCALES = frozenset({"ko-KR", "en-US"})

SYSTEM_ROLE_ORDER = (SYSTEM_PLATFORM_ADMIN,)
VALID_SYSTEM_ROLES = frozenset(SYSTEM_ROLE_ORDER)


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


LEGACY_GROUP_ROLE_MAP = {
    "platform-admin": SYSTEM_PLATFORM_ADMIN,
    "org-admin": SYSTEM_PLATFORM_ADMIN,
    "people-admin": SYSTEM_PLATFORM_ADMIN,
    "workspace-admin": SYSTEM_PLATFORM_ADMIN,
    "audit-viewer": SYSTEM_PLATFORM_ADMIN,
}

SYSTEM_ROLE_ALIASES = {
    "platform_admin": SYSTEM_PLATFORM_ADMIN,
    "platform-admin": SYSTEM_PLATFORM_ADMIN,
    "org_admin": SYSTEM_PLATFORM_ADMIN,
    "org-admin": SYSTEM_PLATFORM_ADMIN,
    "people_admin": SYSTEM_PLATFORM_ADMIN,
    "people-admin": SYSTEM_PLATFORM_ADMIN,
    "workspace_admin": SYSTEM_PLATFORM_ADMIN,
    "workspace-admin": SYSTEM_PLATFORM_ADMIN,
    "audit_viewer": SYSTEM_PLATFORM_ADMIN,
    "audit-viewer": SYSTEM_PLATFORM_ADMIN,
}

SYSTEM_ROLE_PERMISSION_MAP = {
    SYSTEM_PLATFORM_ADMIN: frozenset(
        {
            "admin.access",
            "user.read",
            "user.write",
            "group.read",
            "group.write",
            "org_unit.read",
            "org_unit.write",
            "workspace.read",
            "workspace.write",
            "team.read",
            "team.write",
            "audit.read",
            "session.revoke",
        }
    ),
}

WORKSPACE_ROLE_RANK = {
    "member": 20,
    "admin": 40,
}
TEAM_ROLE_RANK = {
    "viewer": 10,
    "member": 20,
    "admin": 30,
    "owner": 40,
}
VALID_WORKSPACE_ROLES = frozenset(WORKSPACE_ROLE_RANK)
VALID_TEAM_ROLES = frozenset(TEAM_ROLE_RANK)

WORKSPACE_ROLE_ALIASES = {
    "viewer": "member",
    "member": "member",
    "admin": "admin",
    "owner": "admin",
}
TEAM_ROLE_ALIASES = {
    "viewer": "viewer",
    "member": "member",
    "admin": "admin",
    "owner": "owner",
}
DEFAULT_WORKSPACE_SEEDS = [
    {
        "key": "administrator",
        "name": "Administrator",
        "description": "Administrator workspace.",
    },
    {
        "key": "ai-tft",
        "name": "AI TFT",
        "description": "Workspace for the AI TFT team.",
    },
]
DEV_WORKSPACE_SEEDS = []
DEV_WORKSPACE_SEED_KEYS = frozenset(
    definition["key"] for definition in [*DEFAULT_WORKSPACE_SEEDS, *DEV_WORKSPACE_SEEDS]
)

DEFAULT_PMS_SPACE_KEY = "team-space"
DEFAULT_PMS_SPACE_NAME = "Team Space"
DEFAULT_PMS_SPACE_DESCRIPTION = "Default PMS space for shared lists and docs."

DEV_LOGIN_PASSWORD = "AI-DO!dev1234"

DEV_LOGIN_ACCOUNTS = [
    {
        "key": "administrator",
        "label": "Administrator",
        "email": "admin@ai-do.local",
        "description": "관리자 권한으로 Administrator와 AI TFT 워크스페이스를 관리합니다.",
        "category": "Administrators",
        "group": {
            "name": "Administrators",
            "slug": "administrators",
            "description": "Seeded administrators.",
            "system_roles": [SYSTEM_PLATFORM_ADMIN],
        },
        "workspace_memberships": [("administrator", "admin"), ("ai-tft", "admin")],
        "team_memberships": [("administrator", "owner"), ("ai-tft", "owner")],
    },
]

DEV_LOGIN_ACCOUNT_MAP = {item["key"]: item for item in DEV_LOGIN_ACCOUNTS}

USER_GRAPH_OPTIONS = (
    joinedload(User.primary_org_unit),
    selectinload(User.system_role_links),
    selectinload(User.group_links)
    .joinedload(UserAccessGroup.group)
    .selectinload(AccessGroup.system_role_links),
    selectinload(User.group_links)
    .joinedload(UserAccessGroup.group)
    .selectinload(AccessGroup.workspace_bindings)
    .joinedload(WorkspaceGroupBinding.workspace),
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


def normalize_workspace_role(role: str | None) -> str | None:
    if role is None:
        return None
    return WORKSPACE_ROLE_ALIASES.get(role.strip().lower())


def normalize_team_role(role: str | None) -> str | None:
    if role is None:
        return None
    return TEAM_ROLE_ALIASES.get(role.strip().lower())


def normalize_system_role(role: str | None) -> str | None:
    if role is None:
        return None
    return SYSTEM_ROLE_ALIASES.get(role.strip().lower())


def is_valid_workspace_role(role: str) -> bool:
    return normalize_workspace_role(role) in VALID_WORKSPACE_ROLES


def is_valid_team_role(role: str) -> bool:
    return normalize_team_role(role) in VALID_TEAM_ROLES


def is_valid_system_role(role: str) -> bool:
    return normalize_system_role(role) in VALID_SYSTEM_ROLES


def workspace_role_allows(role: str | None, min_role: str) -> bool:
    normalized_role = normalize_workspace_role(role)
    normalized_min_role = normalize_workspace_role(min_role)
    if normalized_min_role is None:
        raise ValueError(f"Unknown workspace role: {min_role}")
    if normalized_role is None:
        return False
    return WORKSPACE_ROLE_RANK[normalized_role] >= WORKSPACE_ROLE_RANK[normalized_min_role]


def team_role_allows(role: str | None, min_role: str) -> bool:
    normalized_role = normalize_team_role(role)
    normalized_min_role = normalize_team_role(min_role)
    if normalized_min_role is None:
        raise ValueError(f"Unknown team role: {min_role}")
    if normalized_role is None:
        return False
    return TEAM_ROLE_RANK[normalized_role] >= TEAM_ROLE_RANK[normalized_min_role]


def _sorted_system_roles(roles: set[str]) -> list[str]:
    ordered = [role for role in SYSTEM_ROLE_ORDER if role in roles]
    extras = sorted(role for role in roles if role not in SYSTEM_ROLE_ORDER)
    return ordered + extras


def _infer_system_roles_from_permissions(permissions: Sequence[str]) -> set[str]:
    granted = set(permissions or [])
    roles: set[str] = set()
    for role, required in SYSTEM_ROLE_PERMISSION_MAP.items():
        if required & granted:
            roles.add(role)
    return roles


def _higher_workspace_role(left: str | None, right: str | None) -> str | None:
    normalized_left = normalize_workspace_role(left)
    normalized_right = normalize_workspace_role(right)
    if normalized_left is None:
        return normalized_right
    if normalized_right is None:
        return normalized_left
    return (
        normalized_left
        if WORKSPACE_ROLE_RANK[normalized_left] >= WORKSPACE_ROLE_RANK[normalized_right]
        else normalized_right
    )


def _higher_team_role(left: str | None, right: str | None) -> str | None:
    normalized_left = normalize_team_role(left)
    normalized_right = normalize_team_role(right)
    if normalized_left is None:
        return normalized_right
    if normalized_right is None:
        return normalized_left
    return (
        normalized_left
        if TEAM_ROLE_RANK[normalized_left] >= TEAM_ROLE_RANK[normalized_right]
        else normalized_right
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
    _replace_user_system_roles(db, user_id, roles)


def _replace_group_system_roles(db: Session, group_id: str, roles: Sequence[str]) -> None:
    requested_roles = {
        normalized for role in roles if (normalized := normalize_system_role(role)) is not None
    }
    current_links = db.scalars(
        select(GroupSystemRole).where(GroupSystemRole.group_id == group_id)
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
        db.add(GroupSystemRole(id=new_id(), group_id=group_id, role=role))


def replace_group_system_roles(db: Session, group_id: str, roles: Sequence[str]) -> None:
    _replace_group_system_roles(db, group_id, roles)


def load_user_graph(db: Session, user_id: str) -> User | None:
    return db.scalar(select(User).options(*USER_GRAPH_OPTIONS).where(User.id == user_id))


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
    root_org_id = db.scalar(select(OrgUnit.id).where(OrgUnit.slug == "hq"))
    workspace_id = db.scalar(select(Workspace.id).limit(1))
    return root_org_id is not None and workspace_id is not None


def _ensure_root_org(db: Session) -> OrgUnit:
    root_org = db.scalar(select(OrgUnit).where(OrgUnit.slug == "hq"))
    if root_org is not None:
        return root_org

    root_org = OrgUnit(
        id=new_id(),
        name="Headquarters",
        slug="hq",
    )
    db.add(root_org)
    db.flush()
    return root_org


def _ensure_principal_group_migration(db: Session) -> None:
    existing_groups = {group.id: group for group in db.scalars(select(AccessGroup)).all()}
    for group in existing_groups.values():
        inferred_roles = _infer_system_roles_from_permissions(group.permissions or [])
        legacy_role = LEGACY_GROUP_ROLE_MAP.get(group.slug)
        stored_roles = {
            normalized
            for role in db.scalars(
                select(GroupSystemRole.role).where(GroupSystemRole.group_id == group.id)
            ).all()
            if (normalized := normalize_system_role(role)) is not None
        }
        inferred_roles.update(stored_roles)
        if legacy_role is not None:
            inferred_roles.add(legacy_role)
        if group.group_kind == "access" or bool(group.permissions) or legacy_role is not None:
            _replace_group_system_roles(db, group.id, inferred_roles)
        group.permissions = []
        if group.group_kind == "access":
            group.group_kind = "principal"
        db.add(group)


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
    _ensure_root_org(db)
    _ensure_principal_group_migration(db)
    _ensure_user_system_role_migration(db)

    existing_workspaces = list(db.scalars(select(Workspace)).all())
    if not existing_workspaces:
        _ensure_workspace_rows(db, DEFAULT_WORKSPACE_SEEDS)
    else:
        for workspace in existing_workspaces:
            ensure_workspace_default_pms_space(db, workspace)

    if _workspace_app_entitlements_table_exists(db):
        ensure_workspace_app_entitlements(db)
    else:
        logger.warning(
            "workspace_app_entitlements table is missing; skipping entitlement seed "
            "and falling back to the default app catalog until alembic migrations are applied."
        )
    ensure_llm_policy_seed_data(db)

    db.commit()


def ensure_llm_policy_seed_data(db: Session) -> None:
    """Idempotent insert-if-missing of baseline LlmPolicy rows.

    Never overwrites existing rows — admins can mutate policies without worry
    of seed drift. New task_kinds shipped in later phases are added here so
    that booting against an existing DB fills in the missing rows.
    """
    from ai_do_api.domains.ai.models import LlmPolicy
    from ai_do_api.domains.auth.security import new_id
    from ai_do_api.core.llm import get_llm_policy_seed_data

    existing_kinds = set(db.scalars(select(LlmPolicy.task_kind)).all())
    to_insert = [
        (task_kind, policy_mode, description)
        for task_kind, policy_mode, description in get_llm_policy_seed_data()
        if task_kind not in existing_kinds
    ]
    for task_kind, policy_mode, description in to_insert:
        db.add(
            LlmPolicy(
                id=new_id(),
                task_kind=task_kind,
                policy_mode=policy_mode,
                description=description,
            )
        )
    if to_insert:
        db.flush()


def _workspace_app_entitlements_table_exists(db: Session) -> bool:
    return inspect(db.get_bind()).has_table(WorkspaceAppEntitlement.__tablename__)


def ensure_workspace_app_entitlements(db: Session) -> None:
    if not _workspace_app_entitlements_table_exists(db):
        return
    existing_pairs = {
        (workspace_id, app_id)
        for workspace_id, app_id in db.execute(
            select(WorkspaceAppEntitlement.workspace_id, WorkspaceAppEntitlement.app_id)
        ).all()
    }
    workspace_ids = list(db.scalars(select(Workspace.id)).all())
    for workspace_id in workspace_ids:
        for app in iter_workspace_app_catalog():
            pair = (workspace_id, app.app_id)
            if pair in existing_pairs:
                continue
            db.add(
                WorkspaceAppEntitlement(
                    id=new_id(),
                    workspace_id=workspace_id,
                    app_id=app.app_id,
                    enabled=app.enabled_by_default,
                )
            )
    if workspace_ids:
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
        return

    ensure_seed_data(db)
    root_org = db.scalar(select(OrgUnit).where(OrgUnit.slug == "hq"))
    if root_org is None:
        raise RuntimeError("Root org unit must exist before seeding dev login accounts.")

    workspace_by_key = {
        **{
            workspace.key: workspace
            for workspace in db.scalars(select(Workspace).where(Workspace.active.is_(True))).all()
        },
        **_ensure_workspace_rows(db, [*DEFAULT_WORKSPACE_SEEDS, *DEV_WORKSPACE_SEEDS]),
    }
    ensure_workspace_app_entitlements(db)
    default_spaces_by_workspace_key = {
        workspace_key: ensure_workspace_default_pms_space(db, workspace)
        for workspace_key, workspace in workspace_by_key.items()
    }

    group_ids_by_slug: dict[str, str] = {}
    for definition in DEV_LOGIN_ACCOUNTS:
        group_definition = definition.get("group")
        if not group_definition:
            continue

        group = db.scalar(select(AccessGroup).where(AccessGroup.slug == group_definition["slug"]))
        if group is None:
            group = AccessGroup(
                id=new_id(),
                name=group_definition["name"],
                slug=group_definition["slug"],
                description=group_definition["description"],
                group_kind="principal",
                active=True,
                permissions=[],
            )
        else:
            group.name = group_definition["name"]
            group.description = group_definition["description"]
            group.group_kind = "principal"
            group.active = True
            group.permissions = []
        db.add(group)
        db.flush()
        _replace_group_system_roles(db, group.id, group_definition["system_roles"])
        group_ids_by_slug[group_definition["slug"]] = group.id

    for definition in DEV_LOGIN_ACCOUNTS:
        user = db.scalar(select(User).where(User.email == definition["email"]))
        if user is None:
            user = User(
                id=new_id(),
                email=definition["email"],
                full_name=definition["label"],
                display_name=definition["label"],
                password_hash=hash_password(DEV_LOGIN_PASSWORD),
                status="active",
                must_change_password=False,
                theme_preference="system",
                locale=DEFAULT_LOCALE,
                time_zone=DEFAULT_TIME_ZONE,
                primary_org_unit_id=root_org.id,
                is_admin=False,
            )
        else:
            user.full_name = definition["label"]
            user.display_name = definition["label"]
            user.password_hash = hash_password(DEV_LOGIN_PASSWORD)
            user.status = "active"
            user.must_change_password = False
            user.theme_preference = "system"
            user.locale = normalize_locale(getattr(user, "locale", None))
            user.time_zone = normalize_time_zone(getattr(user, "time_zone", None))
            user.primary_org_unit_id = root_org.id
            user.is_admin = False
        db.add(user)
        db.flush()

        group_definition = definition.get("group")
        group_ids = (
            [group_ids_by_slug[group_definition["slug"]]] if group_definition is not None else []
        )
        assign_user_groups(db, user, group_ids)
        _replace_user_system_roles(db, user.id, [])
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

    for link in getattr(user, "group_links", []):
        if not link.group.active:
            continue
        roles.update(
            normalized_role
            for system_link in getattr(link.group, "system_role_links", [])
            if (normalized_role := normalize_system_role(system_link.role)) is not None
        )

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

    for link in user.group_links:
        if not link.group.active:
            continue
        for binding in link.group.workspace_bindings:
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
    return resolve_workspace_role_map(db, user).get(workspace_id)


def resolve_team_role(db: Session, user: User, team: Team) -> str | None:
    effective_role = None
    workspace_role = resolve_workspace_role(db, user, team.workspace_id)
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


def resolve_group_slugs(user: User) -> list[str]:
    return sorted({link.group.slug for link in user.group_links if link.group.active})


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


def resolve_workspace_enabled_app_ids(db: Session, workspace_id: str) -> list[str]:
    if not _workspace_app_entitlements_table_exists(db):
        return [app.app_id for app in iter_workspace_app_catalog() if app.enabled_by_default]
    enabled_ids = {
        app_id
        for app_id, enabled in db.execute(
            select(WorkspaceAppEntitlement.app_id, WorkspaceAppEntitlement.enabled).where(
                WorkspaceAppEntitlement.workspace_id == workspace_id
            )
        ).all()
        if enabled
    }
    if not enabled_ids:
        enabled_ids = {app.app_id for app in iter_workspace_app_catalog() if app.enabled_by_default}
    return [app_id for app_id in WORKSPACE_APP_IDS if app_id in enabled_ids]


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
    apps: list[dict[str, Any]] = []
    nav: list[dict[str, Any]] = []

    for app in iter_workspace_app_catalog():
        if app.app_id not in enabled_app_ids:
            continue
        nav_items = [
            {
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
            for item in app.nav_items
        ]
        apps.append(
            {
                "app_id": app.app_id,
                "title": app.title,
                "route_base": app.route_base,
                "icon_key": app.icon_key,
                "enabled": True,
                "nav_items": nav_items,
            }
        )
        nav.extend(nav_items)

    # Apps the chatbot has registered tools for *and* that this workspace has
    # entitled. The frontend scope picker renders the intersection, so adding
    # a new domain via ``register_ai_capabilities`` makes it available here
    # without any frontend change.
    from ai_do_api.domains.ai.registry import get_chatbot_capable_app_ids

    chatbot_app_ids = [
        app_id for app_id in get_chatbot_capable_app_ids() if app_id in enabled_app_ids
    ]

    return {
        "workspace": {
            "id": workspace.id,
            "slug": workspace.key,
            "name": workspace.name,
            "role": role or "member",
        },
        "apps": apps,
        "nav": nav,
        "chatbot_app_ids": chatbot_app_ids,
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


def serialize_org_unit(org_unit: OrgUnit | None) -> dict[str, Any] | None:
    if org_unit is None:
        return None

    return {
        "id": org_unit.id,
        "name": org_unit.name,
        "slug": org_unit.slug,
        "parent_id": org_unit.parent_id,
    }


def serialize_auth_user(db: Session, user: User) -> dict[str, Any]:
    workspaces = resolve_workspaces(db, user)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "display_name": user.display_name or user.full_name,
        "job_title": user.job_title,
        "status": user.status,
        "theme_preference": user.theme_preference,
        "locale": normalize_locale(getattr(user, "locale", None)),
        "time_zone": user.time_zone or DEFAULT_TIME_ZONE,
        "primary_org_unit": serialize_org_unit(user.primary_org_unit),
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
        "group_ids": sorted({link.group_id for link in user.group_links if link.group.active}),
        "group_slugs": resolve_group_slugs(user),
        "must_change_password": user.must_change_password,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
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


def assign_user_groups(db: Session, user: User, group_ids: Sequence[str]) -> None:
    requested_ids = set(group_ids)
    current_map = {link.group_id: link for link in user.group_links}

    for group_id, link in list(current_map.items()):
        if group_id not in requested_ids:
            db.delete(link)

    existing_ids = {group.id for group in db.scalars(select(AccessGroup)).all()}
    for group_id in requested_ids:
        if group_id not in current_map and group_id in existing_ids:
            db.add(UserAccessGroup(id=new_id(), user_id=user.id, group_id=group_id))


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
    audit_log = AuditLog(
        id=new_id(),
        actor_user_id=actor_user_id,
        action=action,
        entity_kind=entity_kind,
        entity_id=entity_id,
        summary=summary,
        payload=payload or {},
    )
    db.add(audit_log)
    return audit_log
