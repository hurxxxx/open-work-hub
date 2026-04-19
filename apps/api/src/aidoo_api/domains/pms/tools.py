from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.registry import AiCapabilityRegistry
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.pms import service as pms_service


class _ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchIssuesArgs(_ToolArgsModel):
    q: str = ""
    list_id: str | None = None
    assignee_id: str | None = None
    status_filter: list[str] | None = None
    archived: bool | None = None
    limit: int = Field(default=20, ge=1)


class GetIssueArgs(_ToolArgsModel):
    issue_id: str = Field(..., min_length=1)


class ListSpacesArgs(_ToolArgsModel):
    pass


class ListTaskListsArgs(_ToolArgsModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    q: str = ""
    archived: bool | None = None
    team_id: str | None = None


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
        q=str(arguments.get("q", "")),
        list_id=arguments.get("list_id"),
        assignee_id=arguments.get("assignee_id"),
        status_filter=arguments.get("status_filter"),
        archived=arguments.get("archived"),
        limit=int(arguments.get("limit", 20)),
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
        issue_id=str(arguments["issue_id"]),
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
    sort_dir = str(arguments.get("sort_dir", "desc"))
    return pms_service.list_task_lists(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        page=int(arguments.get("page", 1)),
        page_size=int(arguments.get("page_size", 20)),
        sort_by=str(arguments.get("sort_by", "updated_at")),
        sort_dir=sort_dir,
        q=str(arguments.get("q", "")),
        archived=arguments.get("archived"),
        team_id=arguments.get("team_id"),
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_tool(
        name="pms.search_issues",
        description="Search issues in the current workspace.",
        owner_domain="pms",
        handler=_search_issues,
        args_model=SearchIssuesArgs,
    )
    registry.register_tool(
        name="pms.get_issue",
        description="Load one issue in the current workspace.",
        owner_domain="pms",
        handler=_get_issue,
        args_model=GetIssueArgs,
    )
    registry.register_tool(
        name="pms.list_spaces",
        description="List PMS spaces in the current workspace.",
        owner_domain="pms",
        handler=_list_spaces,
        args_model=ListSpacesArgs,
    )
    registry.register_tool(
        name="pms.list_task_lists",
        description="List PMS task lists in the current workspace.",
        owner_domain="pms",
        handler=_list_task_lists,
        args_model=ListTaskListsArgs,
    )
