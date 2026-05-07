from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.principal import CallerPrincipal
from ai_do_api.core.settings import get_settings
from ai_do_api.domains.ai.registry import (
    AiCapabilityRegistry,
    ApprovalPreview,
    PreviewField,
    WorkspaceContext,
)
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.planner import service as planner_service


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


class UpdateEventArgs(_ToolArgsModel):
    event_id: str = Field(..., min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start_at: datetime | None = None
    end_at: datetime | None = None
    description: str | None = Field(default=None, max_length=4000)
    visibility: Literal["private", "public"] | None = None
    location: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def _validate_mutation(self) -> "UpdateEventArgs":
        if (self.start_at is None) != (self.end_at is None):
            raise PydanticCustomError(
                "planner.update_start_at_end_at_required",
                "Planner event updates must provide both start_at and end_at together.",
                {},
            )
        if self.model_fields_set.intersection(
            {"title", "start_at", "end_at", "description", "visibility", "location"}
        ):
            return self
        raise PydanticCustomError(
            "planner.update_mutable_field_required",
            "Planner event updates must provide at least one mutable field.",
            {},
        )


class DeleteEventArgs(_ToolArgsModel):
    event_id: str = Field(..., min_length=1)


def _parse_optional_range_arg(arguments: Mapping[str, Any], key: str):
    value = arguments.get(key)
    if value is None:
        return None
    try:
        return planner_service.parse_iso_or_date(str(value))
    except ValueError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.invalid_iso_datetime_for_field",
            field=key,
            error=str(exc),
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


def _update_event(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return planner_service.update_event_for_ai(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        event_id=str(arguments["event_id"]),
        title=arguments.get("title"),
        start_at=arguments.get("start_at"),
        end_at=arguments.get("end_at"),
        description=arguments.get("description"),
        visibility=arguments.get("visibility"),
        location=arguments.get("location"),
        approved_call_id=approved_call_id,
    )


def _delete_event(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return planner_service.delete_event_for_ai(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        event_id=str(arguments["event_id"]),
        approved_call_id=approved_call_id,
    )


def _preview_values(parsed_args: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(parsed_args, BaseModel):
        return parsed_args.model_dump(mode="python", by_alias=True, exclude_none=True)
    return dict(parsed_args)


def _build_create_event_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
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


def _build_update_event_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    fields: list[PreviewField] = [
        PreviewField(label="Event ID", value=str(values.get("event_id", "-"))),
    ]
    if values.get("title") is not None:
        fields.append(PreviewField(label="Title", value=str(values["title"])))
    if values.get("start_at") is not None:
        fields.append(PreviewField(label="Start", value=str(values["start_at"])))
    if values.get("visibility") is not None:
        fields.append(PreviewField(label="Visibility", value=str(values["visibility"])))
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Update planner event",
        summary=str(values.get("description") or "Update a planner event from AI.").strip()
        or "Update a planner event from AI.",
        fields=tuple(fields),
    )


def _build_delete_event_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Delete planner event",
        summary="Delete a planner event from AI.",
        fields=(
            PreviewField(label="Event ID", value=str(values.get("event_id", "-"))),
        ),
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_preview_builder(
        preview_builder_id="planner.create_event_preview",
        builder=_build_create_event_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="planner.update_event_preview",
        builder=_build_update_event_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="planner.delete_event_preview",
        builder=_build_delete_event_preview,
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
    registry.register_tool(
        name="planner.update_event",
        description="Update one planner event in the current workspace.",
        owner_domain="planner",
        handler=_update_event,
        args_model=UpdateEventArgs,
        mode="write",
        approval_required=True,
        preview_builder_id="planner.update_event_preview",
        output_projection="resource_ids",
    )
    registry.register_tool(
        name="planner.delete_event",
        description="Delete one planner event in the current workspace.",
        owner_domain="planner",
        handler=_delete_event,
        args_model=DeleteEventArgs,
        mode="write",
        approval_required=True,
        preview_builder_id="planner.delete_event_preview",
        output_projection="resource_ids",
    )
