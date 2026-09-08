from __future__ import annotations

from sqlalchemy import func

TEAM_ROLE_RANK = {
    "viewer": 10,
    "member": 20,
    "admin": 30,
    "owner": 40,
}


VALID_TEAM_ROLES = frozenset(TEAM_ROLE_RANK)


TEAM_ROLE_ALIASES = {
    "viewer": "viewer",
    "member": "member",
    "admin": "admin",
    "owner": "owner",
}


def normalize_team_role(role: str | None) -> str | None:
    if role is None:
        return None
    return TEAM_ROLE_ALIASES.get(role.strip().lower())


def is_valid_team_role(role: str) -> bool:
    return normalize_team_role(role) in VALID_TEAM_ROLES


def team_role_allows(role: str | None, min_role: str) -> bool:
    normalized_role = normalize_team_role(role)
    normalized_min_role = normalize_team_role(min_role)
    if normalized_min_role is None:
        raise ValueError(f"Unknown team role: {min_role}")
    if normalized_role is None:
        return False
    return TEAM_ROLE_RANK[normalized_role] >= TEAM_ROLE_RANK[normalized_min_role]


def team_role_allows_predicate(role_column, min_role: str = "viewer"):
    """SQL counterpart for stored team roles, including supported spelling normalization."""
    allowed = [role for role in TEAM_ROLE_ALIASES if team_role_allows(role, min_role)]
    return func.lower(func.trim(role_column)).in_(allowed)


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
