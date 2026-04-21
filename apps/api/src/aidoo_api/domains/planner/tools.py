from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.registry import (
    AiCapabilityRegistry,
    ApprovalPreview,
    PreviewField,
    WorkspaceContext,
)
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.planner import service as planner_service


class _ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ListEventsArgs(_ToolArgsModel):
    from_at: str | None = Field(default=None, alias="from")
    to_at: str | None = Field(default=None, alias="to")


class CreateEventArgs(_ToolArgsModel):
    title: str = Field(..., min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime
    scope: Literal["personal", "team"] = "personal"
    team_id: str | None = None
    description: str | None = Field(default=None, max_length=4000)


def _parse_optional_range_arg(arguments: Mapping[str, Any], key: str):
    value = arguments.get(key)
    if value is None:
        return None
    try:
        return planner_service.parse_iso_or_date(str(value))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ISO date/datetime for '{key}': {exc}",
        ) from exc


def _list_events(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    result = planner_service.list_events(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        from_at=_parse_optional_range_arg(arguments, "from"),
        to_at=_parse_optional_range_arg(arguments, "to"),
    )
    return result.model_dump(mode="json", by_alias=True)


def _create_event(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return planner_service.create_event_for_ai(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        title=str(arguments["title"]),
        start_at=arguments["start_at"],
        end_at=arguments["end_at"],
        scope=str(arguments.get("scope") or "personal"),
        team_id=arguments.get("team_id"),
        description=str(arguments.get("description") or ""),
        approved_call_id=approved_call_id,
    )


def _build_create_event_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = (
        parsed_args.model_dump(mode="python", by_alias=True, exclude_none=True)
        if isinstance(parsed_args, BaseModel)
        else dict(parsed_args)
    )
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Create planner event",
        summary=str(values.get("description") or "Create a planner event from AI.").strip()
        or "Create a planner event from AI.",
        fields=(
            PreviewField(label="Title", value=str(values.get("title", "-"))),
            PreviewField(label="Start", value=str(values.get("start_at", "-"))),
            PreviewField(label="Scope", value=str(values.get("scope", "personal"))),
        ),
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_preview_builder(
        preview_builder_id="planner.create_event_preview",
        builder=_build_create_event_preview,
    )
    registry.register_tool(
        name="planner.list_events",
        description="List the caller's planner events in the current workspace.",
        owner_domain="planner",
        handler=_list_events,
        args_model=ListEventsArgs,
    )
    if not get_settings().ai_write_tools_enabled:
        return
    registry.register_tool(
        name="planner.create_event",
        description="Create a planner event in the current workspace.",
        owner_domain="planner",
        handler=_create_event,
        args_model=CreateEventArgs,
        mode="write",
        approval_required=True,
        preview_builder_id="planner.create_event_preview",
        output_projection="resource_ids",
    )
