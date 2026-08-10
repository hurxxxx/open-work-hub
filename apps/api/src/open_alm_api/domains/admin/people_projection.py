from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.access import (
    SYSTEM_PLATFORM_ADMIN,
    SYSTEM_ROLE_ORDER,
    normalize_date_format,
    normalize_locale,
    normalize_system_role,
    normalize_time_zone,
    normalize_workspace_role,
    serialize_org_unit,
)
from open_alm_api.domains.auth.models import User, Workspace


def sort_admin_user_system_roles(roles: set[str]) -> list[str]:
    ordered = [role for role in SYSTEM_ROLE_ORDER if role in roles]
    extras = sorted(role for role in roles if role not in SYSTEM_ROLE_ORDER)
    return ordered + extras


def resolve_loaded_admin_user_system_roles(user: User) -> list[str]:
    roles = {
        normalized_role
        for link in user.system_role_links
        if (normalized_role := normalize_system_role(link.role)) is not None
    }

    if user.is_admin:
        roles.add(SYSTEM_PLATFORM_ADMIN)

    return sort_admin_user_system_roles(roles)


def resolve_loaded_admin_user_workspace_role_map(
    user: User,
    active_workspace_ids: set[str],
) -> dict[str, str]:
    role_map: dict[str, str] = {}
    for binding in user.workspace_bindings:
        normalized_role = normalize_workspace_role(binding.role)
        if (
            normalized_role is None
            or binding.workspace_id not in active_workspace_ids
            or not binding.workspace.active
        ):
            continue
        role_map[binding.workspace_id] = normalized_role

    return role_map


def admin_user_list_item_projection(
    *,
    user: User,
    active_workspaces: list[Workspace],
) -> dict[str, Any]:
    workspace_role_map = resolve_loaded_admin_user_workspace_role_map(
        user,
        {workspace.id for workspace in active_workspaces},
    )
    sorted_workspaces = sorted(active_workspaces, key=lambda item: item.key)
    workspace_roles = [
        {
            "workspace_id": workspace.id,
            "key": workspace.key,
            "name": workspace.name,
            "role": role,
        }
        for workspace in sorted_workspaces
        if (role := workspace_role_map.get(workspace.id)) is not None
    ]
    workspace_summaries = [
        {
            "id": workspace.id,
            "slug": workspace.key,
            "name": workspace.name,
            "role": role,
        }
        for workspace in sorted_workspaces
        if (role := workspace_role_map.get(workspace.id)) is not None
    ]

    return {
        "id": user.id,
        "login_id": user.login_id,
        "email": user.email,
        "full_name": user.full_name,
        "display_name": user.display_name or user.full_name,
        "employee_code": user.employee_code,
        "auth_provider": user.auth_provider,
        "status": user.status,
        "login_blocked": user.login_blocked,
        "theme_preference": user.theme_preference,
        "locale": normalize_locale(getattr(user, "locale", None)),
        "time_zone": user.time_zone or normalize_time_zone(None),
        "date_format": normalize_date_format(getattr(user, "date_format", None)),
        "primary_org_unit": serialize_org_unit(user.primary_org_unit),
        "system_roles": resolve_loaded_admin_user_system_roles(user),
        "workspaces": workspace_summaries,
        "workspace_roles": workspace_roles,
        "must_change_password": user.must_change_password,
        "hr_source_system": user.hr_source_system,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


def admin_user_list_projection(
    db: Session,
    users: list[User],
) -> list[dict[str, Any]]:
    active_workspaces = list(
        db.scalars(select(Workspace).where(Workspace.active.is_(True))).all()
    )
    return [
        admin_user_list_item_projection(user=user, active_workspaces=active_workspaces)
        for user in users
    ]
