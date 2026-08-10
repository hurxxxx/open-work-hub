from __future__ import annotations

SYSTEM_PLATFORM_ADMIN = "platform_admin"

SYSTEM_ROLE_ORDER = (SYSTEM_PLATFORM_ADMIN,)
VALID_SYSTEM_ROLES = frozenset(SYSTEM_ROLE_ORDER)

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
