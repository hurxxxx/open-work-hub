from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.domains.auth.models import (
    AccessGroup,
    AuditLog,
    FeaturePolicy,
    GroupSystemRole,
    OrgUnit,
    Team,
    TeamMember,
    User,
    UserAccessGroup,
    UserSystemRole,
    Workspace,
    WorkspaceGroupBinding,
    WorkspaceUserBinding,
)
from aidoo_api.domains.auth.security import hash_password, new_id


SYSTEM_PLATFORM_ADMIN = "platform_admin"
SYSTEM_ORG_ADMIN = "org_admin"

SYSTEM_ROLE_ORDER = (
    SYSTEM_PLATFORM_ADMIN,
    SYSTEM_ORG_ADMIN,
)
VALID_SYSTEM_ROLES = frozenset(SYSTEM_ROLE_ORDER)

LEGACY_GROUP_ROLE_MAP = {
    "platform-admin": SYSTEM_PLATFORM_ADMIN,
    "org-admin": SYSTEM_ORG_ADMIN,
    "people-admin": SYSTEM_ORG_ADMIN,
    "workspace-admin": SYSTEM_ORG_ADMIN,
    "audit-viewer": SYSTEM_ORG_ADMIN,
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
            "feature_policy.read",
            "feature_policy.write",
            "audit.read",
            "session.revoke",
        }
    ),
    SYSTEM_ORG_ADMIN: frozenset(
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
            "feature_policy.read",
            "feature_policy.write",
            "audit.read",
            "session.revoke",
        }
    ),
}

WORKSPACE_ROLE_RANK = {
    "viewer": 10,
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
    "viewer": "viewer",
    "member": "member",
    "admin": "admin",
}
TEAM_ROLE_ALIASES = {
    "viewer": "viewer",
    "member": "member",
    "admin": "admin",
    "owner": "owner",
}

APP_FEATURE_CODES = {
    "ai": "nav.ai",
    "docs": "nav.docs",
    "pms": "nav.pms",
    "planner": "nav.planner",
    "meeting": "nav.meeting",
    "admin": "nav.admin",
}
FEATURE_APP_CODES = {value: key for key, value in APP_FEATURE_CODES.items()}

DEFAULT_WORKSPACES = [
    {"key": "ai", "name": "AI Workspace", "description": "AI workflows and search experiences."},
    {"key": "docs", "name": "Docs Workspace", "description": "Documents and knowledge work."},
    {"key": "pms", "name": "PMS Workspace", "description": "Project and issue management."},
    {"key": "planner", "name": "Planner Workspace", "description": "Calendar and planning tools."},
    {"key": "meeting", "name": "Meeting Workspace", "description": "Meeting minutes and linked work."},
    {"key": "admin", "name": "Admin Console", "description": "Identity and operations control."},
]

DEFAULT_PMS_SPACE_KEY = "team-space"
DEFAULT_PMS_SPACE_NAME = "Team Space"
DEFAULT_PMS_SPACE_DESCRIPTION = "Default PMS space for shared lists and docs."

DEFAULT_FEATURE_POLICIES = [
    {
        "code": "nav.ai",
        "name": "AI navigation",
        "description": "Expose the AI workspace entrypoint.",
        "allowed_workspace_keys": ["ai"],
    },
    {
        "code": "nav.docs",
        "name": "Docs navigation",
        "description": "Expose the Docs workspace entrypoint.",
        "allowed_workspace_keys": ["docs"],
    },
    {
        "code": "nav.pms",
        "name": "PMS navigation",
        "description": "Expose the PMS workspace entrypoint.",
        "allowed_workspace_keys": ["pms"],
    },
    {
        "code": "nav.planner",
        "name": "Planner navigation",
        "description": "Expose the Planner workspace entrypoint.",
        "allowed_workspace_keys": ["planner"],
    },
    {
        "code": "nav.meeting",
        "name": "Meeting navigation",
        "description": "Expose the Meeting workspace entrypoint.",
        "allowed_workspace_keys": ["meeting"],
    },
    {
        "code": "nav.admin",
        "name": "Admin console navigation",
        "description": "Expose the admin console entrypoint.",
        "allowed_workspace_keys": ["admin"],
    },
]

DEV_LOGIN_PASSWORD = "Aidoo!dev1234"

DEV_LOGIN_ACCOUNTS = [
    {
        "key": "platform-admin",
        "label": "Platform Admin",
        "email": "platform-admin@aidoo.local",
        "description": "전역 관리자 권한으로 모든 앱과 설정을 관리합니다.",
        "category": "Administrators",
        "group": {
            "name": "Platform Admins",
            "slug": "platform-admins",
            "description": "Seeded platform administrators.",
            "system_roles": [SYSTEM_PLATFORM_ADMIN],
        },
        "workspace_bindings": [],
        "team_role": None,
    },
    {
        "key": "org-admin",
        "label": "Org Admin",
        "email": "org-admin@aidoo.local",
        "description": "사용자, 그룹, 워크스페이스, 기능 정책을 관리합니다.",
        "category": "Administrators",
        "group": {
            "name": "Org Admins",
            "slug": "org-admins",
            "description": "Seeded organization administrators.",
            "system_roles": [SYSTEM_ORG_ADMIN],
        },
        "workspace_bindings": [],
        "team_role": None,
    },
    {
        "key": "ai-member",
        "label": "AI Member",
        "email": "ai-member@aidoo.local",
        "description": "AI 앱 접근 권한만 가진 일반 사용자입니다.",
        "category": "Applications",
        "workspace_bindings": [
            ("ai", "member"),
            ("planner", "member"),
            ("meeting", "member"),
        ],
        "team_role": None,
    },
    {
        "key": "docs-member",
        "label": "Docs Member",
        "email": "docs-member@aidoo.local",
        "description": "Docs 앱 접근 권한만 가진 일반 사용자입니다.",
        "category": "Applications",
        "workspace_bindings": [("docs", "member")],
        "team_role": None,
    },
    {
        "key": "planner-member",
        "label": "Planner Member",
        "email": "planner-member@aidoo.local",
        "description": "Planner 앱 접근 권한만 가진 일반 사용자입니다.",
        "category": "Applications",
        "workspace_bindings": [("planner", "member")],
        "team_role": None,
    },
    {
        "key": "pms-viewer",
        "label": "PMS Viewer",
        "email": "pms-viewer@aidoo.local",
        "description": "PMS 공간을 읽기 전용으로 확인합니다.",
        "category": "Applications",
        "workspace_bindings": [("pms", "member")],
        "team_role": "viewer",
    },
    {
        "key": "pms-member",
        "label": "PMS Member",
        "email": "pms-member@aidoo.local",
        "description": "PMS 공간에서 일반 작업을 수행합니다.",
        "category": "Applications",
        "workspace_bindings": [
            ("pms", "member"),
            ("planner", "member"),
            ("meeting", "member"),
        ],
        "team_role": "member",
    },
    {
        "key": "outsider",
        "label": "No Access User",
        "email": "outsider@aidoo.local",
        "description": "어떤 앱 접근 권한도 가지지 않는 기본 사용자입니다.",
        "category": "Applications",
        "workspace_bindings": [],
        "team_role": None,
    },
]

DEV_LOGIN_ACCOUNT_MAP = {item["key"]: item for item in DEV_LOGIN_ACCOUNTS}

DEFAULT_DEV_PMS_PROJECT = {
    "key": "DEMO",
    "name": "Demo Workspace List",
    "description": "Seeded PMS list for role-based smoke checks.",
}

DEFAULT_DEV_PROJECT_STATUSES = [
    ("backlog", "Backlog", "#6b7280", "backlog", 0),
    ("todo", "Todo", "#3b82f6", "active", 1),
    ("in_progress", "In Progress", "#f59e0b", "active", 2),
    ("done", "Done", "#22c55e", "done", 3),
    ("canceled", "Canceled", "#ef4444", "canceled", 4),
]

DEFAULT_DEV_PROJECT_LABELS = [
    ("blocked", "#b45309"),
    ("customer", "#1d4ed8"),
    ("qa", "#0f766e"),
]

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
    selectinload(User.team_memberships)
    .joinedload(TeamMember.team)
    .joinedload(Team.workspace),
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


def is_valid_workspace_role(role: str) -> bool:
    return normalize_workspace_role(role) in VALID_WORKSPACE_ROLES


def is_valid_team_role(role: str) -> bool:
    return normalize_team_role(role) in VALID_TEAM_ROLES


def is_valid_system_role(role: str) -> bool:
    return role in VALID_SYSTEM_ROLES


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


def _replace_user_system_roles(db: Session, user_id: str, roles: Sequence[str]) -> None:
    requested_roles = {role for role in roles if is_valid_system_role(role)}
    current_links = {
        link.role: link
        for link in db.scalars(select(UserSystemRole).where(UserSystemRole.user_id == user_id)).all()
    }
    for role, link in list(current_links.items()):
        if role not in requested_roles:
            db.delete(link)
    for role in requested_roles - set(current_links):
        db.add(UserSystemRole(id=new_id(), user_id=user_id, role=role))


def replace_user_system_roles(db: Session, user_id: str, roles: Sequence[str]) -> None:
    _replace_user_system_roles(db, user_id, roles)


def _replace_group_system_roles(db: Session, group_id: str, roles: Sequence[str]) -> None:
    requested_roles = {role for role in roles if is_valid_system_role(role)}
    current_links = {
        link.role: link
        for link in db.scalars(select(GroupSystemRole).where(GroupSystemRole.group_id == group_id)).all()
    }
    for role, link in list(current_links.items()):
        if role not in requested_roles:
            db.delete(link)
    for role in requested_roles - set(current_links):
        db.add(GroupSystemRole(id=new_id(), group_id=group_id, role=role))


def replace_group_system_roles(db: Session, group_id: str, roles: Sequence[str]) -> None:
    _replace_group_system_roles(db, group_id, roles)


def load_user_graph(db: Session, user_id: str) -> User | None:
    return db.scalar(select(User).options(*USER_GRAPH_OPTIONS).where(User.id == user_id))


def ensure_seed_data(db: Session) -> None:
    root_org = db.scalar(select(OrgUnit).where(OrgUnit.slug == "hq"))
    if root_org is None:
        db.add(
            OrgUnit(
                id=new_id(),
                name="Headquarters",
                slug="hq",
            )
        )

    existing_groups = {group.id: group for group in db.scalars(select(AccessGroup)).all()}
    for group in existing_groups.values():
        inferred_roles = _infer_system_roles_from_permissions(group.permissions or [])
        legacy_role = LEGACY_GROUP_ROLE_MAP.get(group.slug)
        needs_legacy_role_sync = (
            group.group_kind == "access"
            or bool(group.permissions)
            or legacy_role is not None
        )
        if legacy_role is not None:
            inferred_roles.add(legacy_role)
        if needs_legacy_role_sync:
            _replace_group_system_roles(db, group.id, inferred_roles)
        group.permissions = []
        if group.group_kind == "access":
            group.group_kind = "principal"
        db.add(group)

    for user in db.scalars(select(User)).all():
        current_roles = {
            role
            for role in db.scalars(select(UserSystemRole.role).where(UserSystemRole.user_id == user.id)).all()
        }
        migrated_roles: set[str] = set()
        if user.is_admin or SYSTEM_PLATFORM_ADMIN in current_roles:
            migrated_roles.add(SYSTEM_PLATFORM_ADMIN)
        if current_roles.intersection({"people_admin", "workspace_admin", "audit_viewer", SYSTEM_ORG_ADMIN}):
            migrated_roles.add(SYSTEM_ORG_ADMIN)
        if user.is_admin and not db.scalar(
            select(UserSystemRole.id).where(
                UserSystemRole.user_id == user.id,
                UserSystemRole.role == SYSTEM_PLATFORM_ADMIN,
            )
        ):
            db.add(
                UserSystemRole(
                    id=new_id(),
                    user_id=user.id,
                    role=SYSTEM_PLATFORM_ADMIN,
                )
            )
        if current_roles - migrated_roles:
            _replace_user_system_roles(db, user.id, list(migrated_roles))

    existing_workspaces = {
        workspace.key: workspace for workspace in db.scalars(select(Workspace)).all()
    }
    for definition in DEFAULT_WORKSPACES:
        workspace = existing_workspaces.get(definition["key"])
        if workspace is None:
            db.add(
                Workspace(
                    id=new_id(),
                    key=definition["key"],
                    name=definition["name"],
                    description=definition["description"],
                )
            )
            continue

        workspace.name = definition["name"]
        workspace.description = definition["description"]
        db.add(workspace)

    db.flush()

    default_pms_space = get_or_create_default_pms_space(db)

    from aidoo_api.domains.pms.models import Project

    for project in db.scalars(select(Project).where(Project.team_id.is_(None))).all():
        project.team_id = default_pms_space.id

    existing_policies = {
        policy.code: policy for policy in db.scalars(select(FeaturePolicy)).all()
    }
    for definition in DEFAULT_FEATURE_POLICIES:
        policy = existing_policies.get(definition["code"])
        if policy is None:
            db.add(
                FeaturePolicy(
                    id=new_id(),
                    code=definition["code"],
                    name=definition["name"],
                    description=definition["description"],
                    required_permissions=[],
                    allowed_workspace_keys=list(definition["allowed_workspace_keys"]),
                    allowed_group_slugs=[],
                )
            )
            continue

        policy.name = definition["name"]
        policy.description = definition["description"]
        policy.required_permissions = []
        policy.allowed_workspace_keys = list(definition["allowed_workspace_keys"])
        policy.allowed_group_slugs = []
        db.add(policy)

    db.commit()


def ensure_dev_login_seed_data(db: Session) -> None:
    ensure_seed_data(db)

    root_org = db.scalar(select(OrgUnit).where(OrgUnit.slug == "hq"))
    if root_org is None:
        raise RuntimeError("Root org unit must exist before seeding dev login accounts.")

    workspace_by_key = {
        workspace.key: workspace
        for workspace in db.scalars(select(Workspace).where(Workspace.active.is_(True))).all()
    }
    default_pms_space = get_or_create_default_pms_space(db)

    group_ids_by_slug: dict[str, str] = {}
    for definition in DEV_LOGIN_ACCOUNTS:
        group_definition = definition.get("group")
        if not group_definition:
            continue

        group = db.scalar(
            select(AccessGroup).where(AccessGroup.slug == group_definition["slug"])
        )
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

    seeded_users: dict[str, User] = {}
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
                primary_org_unit_id=root_org.id,
                is_admin=False,
            )
        else:
            user.full_name = definition["label"]
            user.display_name = definition["label"]
            user.status = "active"
            user.must_change_password = False
            user.theme_preference = "system"
            user.primary_org_unit_id = root_org.id
            user.is_admin = False
        db.add(user)
        db.flush()

        group_definition = definition.get("group")
        group_ids = (
            [group_ids_by_slug[group_definition["slug"]]]
            if group_definition is not None
            else []
        )
        assign_user_groups(db, user, group_ids)
        _replace_user_system_roles(db, user.id, [])

        requested_workspace_roles = {
            workspace_by_key[workspace_key].id: normalize_workspace_role(role)
            for workspace_key, role in definition.get("workspace_bindings", [])
            if workspace_key in workspace_by_key and normalize_workspace_role(role) is not None
        }
        current_workspace_bindings = {
            binding.workspace_id: binding
            for binding in db.scalars(
                select(WorkspaceUserBinding).where(WorkspaceUserBinding.user_id == user.id)
            ).all()
        }
        for workspace_id, binding in list(current_workspace_bindings.items()):
            requested_role = requested_workspace_roles.get(workspace_id)
            if requested_role is None:
                db.delete(binding)
                continue
            binding.role = requested_role
            db.add(binding)
        for workspace_id, requested_role in requested_workspace_roles.items():
            if workspace_id in current_workspace_bindings:
                continue
            db.add(
                WorkspaceUserBinding(
                    id=new_id(),
                    workspace_id=workspace_id,
                    user_id=user.id,
                    role=requested_role,
                )
            )

        # Reconcile the seed user's membership in the default PMS space ONLY.
        # Any other TeamMember rows (e.g. user-created spaces) are the user's
        # own data and must not be touched by the seed loop — deleting them
        # here previously wiped out spaces every time the server restarted.
        requested_team_role = normalize_team_role(definition.get("team_role"))
        default_space_membership = db.scalar(
            select(TeamMember).where(
                TeamMember.user_id == user.id,
                TeamMember.team_id == default_pms_space.id,
            )
        )
        if requested_team_role is None:
            if default_space_membership is not None:
                db.delete(default_space_membership)
        else:
            if default_space_membership is None:
                db.add(
                    TeamMember(
                        id=new_id(),
                        team_id=default_pms_space.id,
                        user_id=user.id,
                        role=requested_team_role,
                    )
                )
            else:
                default_space_membership.role = requested_team_role
                db.add(default_space_membership)

        seeded_users[definition["key"]] = user

    from aidoo_api.domains.pms.models import Label, Project, ProjectStatus

    platform_admin = seeded_users.get("platform-admin")
    if platform_admin is not None:
        project = db.scalar(
            select(Project).where(Project.key == DEFAULT_DEV_PMS_PROJECT["key"])
        )
        if project is None:
            project = Project(
                id=new_id(),
                key=DEFAULT_DEV_PMS_PROJECT["key"],
                name=DEFAULT_DEV_PMS_PROJECT["name"],
                description=DEFAULT_DEV_PMS_PROJECT["description"],
                status="active",
                team_id=default_pms_space.id,
                created_by_id=platform_admin.id,
            )
            db.add(project)
            db.flush()
        else:
            project.name = DEFAULT_DEV_PMS_PROJECT["name"]
            project.description = DEFAULT_DEV_PMS_PROJECT["description"]
            project.status = "active"
            project.archived = False
            project.team_id = default_pms_space.id
            db.add(project)
            db.flush()

        if not db.scalar(select(ProjectStatus.id).where(ProjectStatus.project_id == project.id)):
            for slug, name, color, category, sort_order in DEFAULT_DEV_PROJECT_STATUSES:
                db.add(
                    ProjectStatus(
                        id=new_id(),
                        project_id=project.id,
                        slug=slug,
                        name=name,
                        color=color,
                        category=category,
                        sort_order=sort_order,
                    )
                )

        if not db.scalar(select(Label.id).where(Label.project_id == project.id)):
            for name, color in DEFAULT_DEV_PROJECT_LABELS:
                db.add(
                    Label(
                        id=new_id(),
                        project_id=project.id,
                        name=name,
                        color=color,
                    )
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


def get_dev_login_user(db: Session, account_key: str) -> User | None:
    definition = DEV_LOGIN_ACCOUNT_MAP.get(account_key)
    if definition is None:
        return None
    return db.scalar(
        select(User).where(User.email == definition["email"], User.status == "active")
    )


def get_or_create_default_pms_space(db: Session) -> Team:
    workspace = db.scalar(select(Workspace).where(Workspace.key == "pms"))
    if workspace is None:
        raise RuntimeError("PMS workspace must exist before creating the default PMS space.")

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


def resolve_system_roles(db: Session, user: User) -> list[str]:
    roles = {
        link.role
        for link in getattr(user, "system_role_links", [])
        if is_valid_system_role(link.role)
    }

    for link in getattr(user, "group_links", []):
        if not link.group.active:
            continue
        roles.update(
            system_link.role
            for system_link in getattr(link.group, "system_role_links", [])
            if is_valid_system_role(system_link.role)
        )

    if user.is_admin:
        roles.add(SYSTEM_PLATFORM_ADMIN)

    return _sorted_system_roles(roles)


def has_system_role(db: Session, user: User, *roles: str) -> bool:
    role_set = set(resolve_system_roles(db, user))
    return any(role in role_set for role in roles)


def is_org_admin_user(user: User, db: Session) -> bool:
    return has_system_role(db, user, SYSTEM_ORG_ADMIN)


def is_platform_admin_user(user: User, db: Session | None = None) -> bool:
    if db is None:
        return user.is_admin
    return has_system_role(db, user, SYSTEM_PLATFORM_ADMIN)


def load_active_workspace_by_id(db: Session, workspace_id: str) -> Workspace | None:
    return db.scalar(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.active.is_(True),
        )
    )


def load_active_workspace_by_key(db: Session, workspace_key: str) -> Workspace | None:
    return db.scalar(
        select(Workspace).where(
            Workspace.key == workspace_key,
            Workspace.active.is_(True),
        )
    )


def resolve_workspace_role_map(db: Session, user: User) -> dict[str, str]:
    workspaces = db.scalars(select(Workspace).where(Workspace.active.is_(True))).all()
    role_map: dict[str, str] = {}

    if is_platform_admin_user(user, db):
        for workspace in workspaces:
            role_map[workspace.id] = "admin"
        return role_map

    for binding in user.workspace_bindings:
        normalized_role = normalize_workspace_role(binding.role)
        if not binding.workspace.active or normalized_role is None:
            continue
        role_map[binding.workspace_id] = normalized_role

    for link in user.group_links:
        if not link.group.active:
            continue
        for binding in link.group.workspace_bindings:
            normalized_role = normalize_workspace_role(binding.role)
            if not binding.workspace.active or normalized_role is None:
                continue
            current = role_map.get(binding.workspace_id)
            if current is None or WORKSPACE_ROLE_RANK[normalized_role] > WORKSPACE_ROLE_RANK[current]:
                role_map[binding.workspace_id] = normalized_role

    return role_map


def resolve_workspace_role(db: Session, user: User, workspace_id: str) -> str | None:
    return resolve_workspace_role_map(db, user).get(workspace_id)


def resolve_team_role(db: Session, user: User, team: Team) -> str | None:
    if is_platform_admin_user(user, db):
        return "owner"
    if is_org_admin_user(user, db):
        return "admin"

    membership_role = db.scalar(
        select(TeamMember.role).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user.id,
        )
    )
    normalized_membership_role = normalize_team_role(membership_role)
    if normalized_membership_role is not None:
        return normalized_membership_role

    return None


def resolve_group_slugs(user: User) -> list[str]:
    return sorted(
        {
            link.group.slug
            for link in user.group_links
            if link.group.active
        }
    )


def resolve_workspace_roles(db: Session, user: User) -> list[dict[str, str]]:
    workspaces = db.scalars(select(Workspace).where(Workspace.active.is_(True))).all()
    role_map = resolve_workspace_role_map(db, user)

    items: list[dict[str, str]] = []
    for workspace in sorted(workspaces, key=lambda item: item.key):
        role = role_map.get(workspace.id)
        if role is None:
            continue
        items.append(
            {
                "workspace_id": workspace.id,
                "key": workspace.key,
                "name": workspace.name,
                "role": role,
            }
        )

    return items


def _has_docs_native_workspace_access(db: Session, user: User) -> bool:
    from aidoo_api.domains.docs.models import NativeDoc, NativeDocUserShare

    owned_doc_id = db.scalar(
        select(NativeDoc.id).where(
            NativeDoc.owner_id == user.id,
            NativeDoc.trashed_at.is_(None),
        )
    )
    if owned_doc_id is not None:
        return True

    shared_doc_id = db.scalar(
        select(NativeDocUserShare.id)
        .join(NativeDoc, NativeDoc.id == NativeDocUserShare.doc_id)
        .where(
            NativeDocUserShare.user_id == user.id,
            NativeDoc.trashed_at.is_(None),
        )
    )
    return shared_doc_id is not None


def resolve_app_access(db: Session, user: User) -> list[dict[str, str | None]]:
    workspace_roles = {item["key"]: item for item in resolve_workspace_roles(db, user)}
    workspace_lookup = {
        workspace.key: workspace
        for workspace in db.scalars(select(Workspace).where(Workspace.active.is_(True))).all()
    }
    enabled_policies = {
        policy.code: policy
        for policy in db.scalars(
            select(FeaturePolicy).where(FeaturePolicy.enabled.is_(True)).order_by(FeaturePolicy.code)
        ).all()
    }
    system_roles = set(resolve_system_roles(db, user))
    items: list[dict[str, str | None]] = []

    for app_code, feature_code in APP_FEATURE_CODES.items():
        policy = enabled_policies.get(feature_code)
        if policy is None:
            continue

        if app_code == "admin":
            if not system_roles:
                continue
            workspace = workspace_roles.get("admin")
            items.append(
                {
                    "app": "admin",
                    "workspace_id": workspace["workspace_id"] if workspace else None,
                    "workspace_key": "admin",
                    "workspace_name": workspace["name"] if workspace else "Admin Console",
                    "role": "admin",
                }
            )
            continue

        workspace = workspace_roles.get(app_code)
        if app_code == "docs" and workspace is None and _has_docs_native_workspace_access(db, user):
            docs_workspace = workspace_lookup.get("docs")
            if docs_workspace is not None:
                items.append(
                    {
                        "app": "docs",
                        "workspace_id": docs_workspace.id,
                        "workspace_key": docs_workspace.key,
                        "workspace_name": docs_workspace.name,
                        "role": "member",
                    }
                )
            continue
        if app_code == "pms" and workspace is None and SYSTEM_ORG_ADMIN in system_roles:
            pms_workspace = workspace_lookup.get("pms")
            if pms_workspace is not None:
                items.append(
                    {
                        "app": "pms",
                        "workspace_id": pms_workspace.id,
                        "workspace_key": pms_workspace.key,
                        "workspace_name": pms_workspace.name,
                        "role": "admin",
                    }
                )
            continue
        if workspace is None:
            continue
        items.append(
            {
                "app": app_code,
                "workspace_id": workspace["workspace_id"],
                "workspace_key": workspace["key"],
                "workspace_name": workspace["name"],
                "role": workspace["role"],
            }
        )

    return items


def resolve_visible_features(db: Session, user: User) -> list[str]:
    return [
        APP_FEATURE_CODES[item["app"]]
        for item in resolve_app_access(db, user)
        if item["app"] in APP_FEATURE_CODES
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
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "display_name": user.display_name or user.full_name,
        "job_title": user.job_title,
        "status": user.status,
        "theme_preference": user.theme_preference,
        "primary_org_unit": serialize_org_unit(user.primary_org_unit),
        "system_roles": resolve_system_roles(db, user),
        "workspace_roles": resolve_workspace_roles(db, user),
        "app_access": resolve_app_access(db, user),
        "group_ids": sorted({link.group_id for link in user.group_links if link.group.active}),
        "group_slugs": resolve_group_slugs(user),
        "must_change_password": user.must_change_password,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


def serialize_session_item(session_id: str, current_session_id: str | None, session: Any) -> dict[str, Any]:
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
