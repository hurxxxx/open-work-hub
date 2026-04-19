from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.registry import AiCapabilityRegistry
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.pms import service as pms_service


def _optional_str(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool argument '{key}' must be a string.",
        )
    return value


def _required_str(arguments: Mapping[str, Any], key: str) -> str:
    value = _optional_str(arguments, key)
    if value is None or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool argument '{key}' is required.",
        )
    return value


def _optional_int(arguments: Mapping[str, Any], key: str, default: int) -> int:
    value = arguments.get(key, default)
    if not isinstance(value, int):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool argument '{key}' must be an integer.",
        )
    return value


def _optional_bool(arguments: Mapping[str, Any], key: str) -> bool | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool argument '{key}' must be a boolean.",
        )
    return value


def _optional_str_list(arguments: Mapping[str, Any], key: str) -> list[str] | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool argument '{key}' must be a list of strings.",
        )
    return list(value)


def _search_issues(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return pms_service.search_issues(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        q=_optional_str(arguments, "q") or "",
        list_id=_optional_str(arguments, "list_id"),
        assignee_id=_optional_str(arguments, "assignee_id"),
        status_filter=_optional_str_list(arguments, "status_filter"),
        archived=_optional_bool(arguments, "archived"),
        limit=_optional_int(arguments, "limit", 20),
    )


def _get_issue(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return pms_service.get_issue_detail(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        issue_id=_required_str(arguments, "issue_id"),
    )


def _list_spaces(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "items": pms_service.list_spaces(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
        )
    }


def _list_task_lists(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    sort_dir = _optional_str(arguments, "sort_dir") or "desc"
    if sort_dir not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tool argument 'sort_dir' must be 'asc' or 'desc'.",
        )
    return pms_service.list_task_lists(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        page=_optional_int(arguments, "page", 1),
        page_size=_optional_int(arguments, "page_size", 20),
        sort_by=_optional_str(arguments, "sort_by") or "updated_at",
        sort_dir=sort_dir,
        q=_optional_str(arguments, "q") or "",
        archived=_optional_bool(arguments, "archived"),
        team_id=_optional_str(arguments, "team_id"),
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_tool(
        name="pms.search_issues",
        description="Search issues in the current workspace.",
        owner_domain="pms",
        handler=_search_issues,
    )
    registry.register_tool(
        name="pms.get_issue",
        description="Load one issue in the current workspace.",
        owner_domain="pms",
        handler=_get_issue,
    )
    registry.register_tool(
        name="pms.list_spaces",
        description="List PMS spaces in the current workspace.",
        owner_domain="pms",
        handler=_list_spaces,
    )
    registry.register_tool(
        name="pms.list_task_lists",
        description="List PMS task lists in the current workspace.",
        owner_domain="pms",
        handler=_list_task_lists,
    )
