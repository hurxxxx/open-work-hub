from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.registry import AiCapabilityRegistry
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.docs import service as docs_service


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


def _list_hub(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return docs_service.list_hub(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        category=_optional_str(arguments, "category") or "all",
        q=_optional_str(arguments, "q") or "",
        sort_by=_optional_str(arguments, "sort_by") or "updated_at",
        sort_dir=_optional_str(arguments, "sort_dir") or "desc",
        page=_optional_int(arguments, "page", 1),
        page_size=_optional_int(arguments, "page_size", 50),
    )


def _get_item(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return docs_service.get_item(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        item_id=_required_str(arguments, "item_id"),
        share_token=_optional_str(arguments, "share_token"),
    )


def _list_pages(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return docs_service.list_pages(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        item_id=_required_str(arguments, "item_id"),
        share_token=_optional_str(arguments, "share_token"),
    )


def _read_page(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return docs_service.read_page(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        page_id=_required_str(arguments, "page_id"),
        share_token=_optional_str(arguments, "share_token"),
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_tool(
        name="docs.list_hub",
        description="List visible docs for the current workspace.",
        owner_domain="docs",
        handler=_list_hub,
    )
    registry.register_tool(
        name="docs.get_item",
        description="Load one docs item in the current workspace.",
        owner_domain="docs",
        handler=_get_item,
    )
    registry.register_tool(
        name="docs.list_pages",
        description="List pages for a docs item in the current workspace.",
        owner_domain="docs",
        handler=_list_pages,
    )
    registry.register_tool(
        name="docs.read_page",
        description="Read one docs page in the current workspace.",
        owner_domain="docs",
        handler=_read_page,
    )
