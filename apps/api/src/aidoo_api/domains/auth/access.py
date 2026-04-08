from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.domains.auth.models import (
    AccessGroup,
    AuditLog,
    FeaturePolicy,
    OrgUnit,
    Team,
    TeamMember,
    User,
    UserAccessGroup,
    Workspace,
    WorkspaceGroupBinding,
    WorkspaceUserBinding,
)
from aidoo_api.domains.auth.security import new_id


CORE_PERMISSIONS = [
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
]

DEFAULT_GROUP_DEFINITIONS = [
    {
        "slug": "platform-admin",
        "name": "Platform Admin",
        "description": "Full tenant-wide administration access.",
        "permissions": CORE_PERMISSIONS,
    },
    {
        "slug": "people-admin",
        "name": "People Admin",
        "description": "Manage users, groups, and org units.",
        "permissions": [
            "user.read",
            "user.write",
            "group.read",
            "group.write",
            "org_unit.read",
            "org_unit.write",
            "session.revoke",
        ],
    },
    {
        "slug": "workspace-admin",
        "name": "Workspace Admin",
        "description": "Manage workspaces, teams, and feature visibility.",
        "permissions": [
            "workspace.read",
            "workspace.write",
            "team.read",
            "team.write",
            "feature_policy.read",
            "feature_policy.write",
        ],
    },
    {
        "slug": "audit-viewer",
        "name": "Audit Viewer",
        "description": "Read-only access to audit logs.",
        "permissions": ["audit.read"],
    },
]

DEFAULT_WORKSPACES = [
    {"key": "ai", "name": "AI Workspace", "description": "AI workflows and search experiences."},
    {"key": "docs", "name": "Docs Workspace", "description": "Documents and knowledge work."},
    {"key": "pms", "name": "PMS Workspace", "description": "Project and issue management."},
    {"key": "planner", "name": "Planner Workspace", "description": "Calendar and planning tools."},
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
        "required_permissions": [],
        "allowed_workspace_keys": ["ai"],
        "allowed_group_slugs": [],
    },
    {
        "code": "nav.docs",
        "name": "Docs navigation",
        "description": "Expose the Docs workspace entrypoint.",
        "required_permissions": [],
        "allowed_workspace_keys": ["docs"],
        "allowed_group_slugs": [],
    },
    {
        "code": "nav.pms",
        "name": "PMS navigation",
        "description": "Expose the PMS workspace entrypoint.",
        "required_permissions": [],
        "allowed_workspace_keys": ["pms"],
        "allowed_group_slugs": [],
    },
    {
        "code": "nav.planner",
        "name": "Planner navigation",
        "description": "Expose the Planner workspace entrypoint.",
        "required_permissions": [],
        "allowed_workspace_keys": ["planner"],
        "allowed_group_slugs": [],
    },
    {
        "code": "nav.admin",
        "name": "Admin console navigation",
        "description": "Expose the admin console entrypoint.",
        "required_permissions": ["admin.access"],
        "allowed_workspace_keys": ["admin"],
        "allowed_group_slugs": [],
    },
]

ROLE_RANK = {
    "viewer": 10,
    "member": 20,
    "team_admin": 30,
    "workspace_admin": 40,
}

USER_GRAPH_OPTIONS = (
    joinedload(User.primary_org_unit),
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

    existing_groups = {
        group.slug: group for group in db.scalars(select(AccessGroup)).all()
    }
    for definition in DEFAULT_GROUP_DEFINITIONS:
        group = existing_groups.get(definition["slug"])
        if group is None:
            db.add(
                AccessGroup(
                    id=new_id(),
                    slug=definition["slug"],
                    name=definition["name"],
                    description=definition["description"],
                    permissions=list(definition["permissions"]),
                )
            )
            continue

        group.name = definition["name"]
        group.description = definition["description"]
        group.permissions = list(definition["permissions"])
        group.active = True
        db.add(group)

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
        workspace.active = True
        db.add(workspace)

    db.flush()

    default_pms_space = get_or_create_default_pms_space(db)

    # Migrate legacy PMS records without a space into the default PMS space.
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
                    required_permissions=list(definition["required_permissions"]),
                    allowed_workspace_keys=list(definition["allowed_workspace_keys"]),
                    allowed_group_slugs=list(definition["allowed_group_slugs"]),
                )
            )
            continue

        policy.name = definition["name"]
        policy.description = definition["description"]
        policy.required_permissions = list(definition["required_permissions"])
        policy.allowed_workspace_keys = list(definition["allowed_workspace_keys"])
        policy.allowed_group_slugs = list(definition["allowed_group_slugs"])
        policy.enabled = True
        db.add(policy)

    db.commit()


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


def resolve_user_permissions(user: User) -> list[str]:
    permissions = set()
    group_slugs = set()

    for link in user.group_links:
        if not link.group.active:
            continue
        group_slugs.add(link.group.slug)
        permissions.update(link.group.permissions or [])

    if user.is_admin or "platform-admin" in group_slugs:
        permissions.update(CORE_PERMISSIONS)

    return sorted(permissions)


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
    user_permissions = set(resolve_user_permissions(user))
    role_map: dict[str, str] = {}

    if "admin.access" in user_permissions:
        for workspace in workspaces:
            role_map[workspace.id] = "workspace_admin"
    else:
        for binding in user.workspace_bindings:
            if binding.workspace.active:
                role_map[binding.workspace_id] = binding.role

        for link in user.group_links:
            if not link.group.active:
                continue
            for binding in link.group.workspace_bindings:
                if not binding.workspace.active:
                    continue
                current = role_map.get(binding.workspace_id)
                if current is None or ROLE_RANK.get(binding.role, 0) > ROLE_RANK.get(current, 0):
                    role_map[binding.workspace_id] = binding.role

        for membership in user.team_memberships:
            if not membership.team.active or not membership.team.workspace.active:
                continue
            workspace_id = membership.team.workspace_id
            current = role_map.get(workspace_id)
            if current is None or ROLE_RANK.get("member", 0) > ROLE_RANK.get(current, 0):
                role_map[workspace_id] = "member"

    items = []
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


def resolve_visible_features(db: Session, user: User) -> list[str]:
    permissions = set(resolve_user_permissions(user))
    group_slugs = set(resolve_group_slugs(user))
    workspace_keys = {item["key"] for item in resolve_workspace_roles(db, user)}
    visible: list[str] = []

    policies = db.scalars(
        select(FeaturePolicy).where(FeaturePolicy.enabled.is_(True)).order_by(FeaturePolicy.code)
    ).all()
    for policy in policies:
        if policy.required_permissions and not set(policy.required_permissions).issubset(permissions):
            continue
        if policy.allowed_workspace_keys and not set(policy.allowed_workspace_keys).intersection(
            workspace_keys
        ):
            continue
        if policy.allowed_group_slugs and not set(policy.allowed_group_slugs).intersection(group_slugs):
            continue
        visible.append(policy.code)

    return visible


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
    workspace_roles = resolve_workspace_roles(db, user)
    permissions = resolve_user_permissions(user)
    group_slugs = resolve_group_slugs(user)
    is_admin_compat = user.is_admin or "admin.access" in permissions or "platform-admin" in group_slugs

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "display_name": user.display_name or user.full_name,
        "job_title": user.job_title,
        "status": user.status,
        "theme_preference": user.theme_preference,
        "primary_org_unit": serialize_org_unit(user.primary_org_unit),
        "workspace_roles": workspace_roles,
        "group_ids": sorted({link.group_id for link in user.group_links if link.group.active}),
        "group_slugs": group_slugs,
        "permissions": permissions,
        "visible_features": resolve_visible_features(db, user),
        "must_change_password": user.must_change_password,
        "is_admin": is_admin_compat,
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
