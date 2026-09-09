from __future__ import annotations

SYSTEM_PLATFORM_ADMIN = "platform_admin"

SYSTEM_ROLE_ORDER = (SYSTEM_PLATFORM_ADMIN,)
VALID_SYSTEM_ROLES = frozenset(SYSTEM_ROLE_ORDER)

SYSTEM_ROLE_ALIASES = {
    "platform_admin": SYSTEM_PLATFORM_ADMIN,
}

SYSTEM_ROLE_PERMISSION_MAP = {
    SYSTEM_PLATFORM_ADMIN: frozenset(
        {
            "admin.access",
            "user.read",
            "user.write",
            "organization.read",
            "organization.write",
            "platform_api_key.read",
            "platform_api_key.write",
            "platform_api_key.reveal",
            "audit.read",
            "session.revoke",
        }
    ),
}


def normalize_system_role(role: str | None) -> str | None:
    if role is None:
        return None
    return SYSTEM_ROLE_ALIASES.get(role.strip().lower())


def is_valid_system_role(role: str) -> bool:
    return normalize_system_role(role) in VALID_SYSTEM_ROLES


def _sorted_system_roles(roles: set[str]) -> list[str]:
    ordered = [role for role in SYSTEM_ROLE_ORDER if role in roles]
    extras = sorted(role for role in roles if role not in SYSTEM_ROLE_ORDER)
    return ordered + extras
