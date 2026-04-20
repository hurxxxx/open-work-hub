from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.registry import AiCapabilityRegistry
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.docs import service as docs_service


class _ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListHubArgs(_ToolArgsModel):
    view: str = "all"
    q: str = ""
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1)


class GetItemArgs(_ToolArgsModel):
    item_id: str = Field(..., min_length=1)
    share_token: str | None = None


class ListPagesArgs(_ToolArgsModel):
    item_id: str = Field(..., min_length=1)
    share_token: str | None = None


class ReadPageArgs(_ToolArgsModel):
    page_id: str = Field(..., min_length=1)
    share_token: str | None = None


def _list_hub(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return docs_service.list_hub(
        db,
        user=user,
        view=str(arguments.get("view", "all")),
        q=str(arguments.get("q", "")),
        sort_by=str(arguments.get("sort_by", "updated_at")),
        sort_dir=str(arguments.get("sort_dir", "desc")),
        page=int(arguments.get("page", 1)),
        page_size=int(arguments.get("page_size", 50)),
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
        user=user,
        item_id=str(arguments["item_id"]),
        share_token=arguments.get("share_token"),
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
        user=user,
        item_id=str(arguments["item_id"]),
        share_token=arguments.get("share_token"),
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
        user=user,
        page_id=str(arguments["page_id"]),
        share_token=arguments.get("share_token"),
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_tool(
        name="docs.list_hub",
        description="List visible docs for the current workspace.",
        owner_domain="docs",
        handler=_list_hub,
        args_model=ListHubArgs,
    )
    registry.register_tool(
        name="docs.get_item",
        description="Load one docs item in the current workspace.",
        owner_domain="docs",
        handler=_get_item,
        args_model=GetItemArgs,
    )
    registry.register_tool(
        name="docs.list_pages",
        description="List pages for a docs item in the current workspace.",
        owner_domain="docs",
        handler=_list_pages,
        args_model=ListPagesArgs,
    )
    registry.register_tool(
        name="docs.read_page",
        description="Read one docs page in the current workspace.",
        owner_domain="docs",
        handler=_read_page,
        args_model=ReadPageArgs,
    )
