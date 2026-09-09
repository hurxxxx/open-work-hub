from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.planner import service as planner_service
from open_work_hub_api.domains.planner.approval_preview import (
    build_create_event_preview,
    build_delete_event_preview,
    build_update_event_preview,
)
from open_work_hub_api.domains.planner.event_time import parse_iso_or_date


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
            {"title", "start_at", "end_at", "description", "location"}
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
        return parse_iso_or_date(str(value))
    except ValueError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.invalid_iso_datetime_for_field",
            field=key,
            error=str(exc),
        ) from exc


def _list_events(
    db: Session,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    result = planner_service.list_events(
        db,
        principal=principal,
        user=user,
        from_at=_parse_optional_range_arg(arguments, "from"),
        to_at=_parse_optional_range_arg(arguments, "to"),
    )
    return result.model_dump(mode="json", by_alias=True)


def _create_event(
    db: Session,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return planner_service.create_event_for_ai(
        db,
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
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return planner_service.update_event_for_ai(
        db,
        principal=principal,
        user=user,
        event_id=str(arguments["event_id"]),
        title=arguments.get("title"),
        start_at=arguments.get("start_at"),
        end_at=arguments.get("end_at"),
        description=arguments.get("description"),
        location=arguments.get("location"),
        approved_call_id=approved_call_id,
    )


def _delete_event(
    db: Session,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return planner_service.delete_event_for_ai(
        db,
        principal=principal,
        user=user,
        event_id=str(arguments["event_id"]),
        approved_call_id=approved_call_id,
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_preview_builder(
        preview_builder_id="planner.create_event_preview",
        builder=build_create_event_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="planner.update_event_preview",
        builder=build_update_event_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="planner.delete_event_preview",
        builder=build_delete_event_preview,
    )
    registry.register_tool(
        name="planner.list_events",
        description="List the caller's personal planner events.",
        owner_domain="planner",
        handler=_list_events,
        args_model=ListEventsArgs,
    )
    if not get_settings().ai_write_tools_enabled:
        return
    registry.register_tool(
        name="planner.create_event",
        description="Create an event in the caller's personal planner.",
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
        description="Update one event in the caller's personal planner.",
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
        description="Delete one event in the caller's personal planner.",
        owner_domain="planner",
        handler=_delete_event,
        args_model=DeleteEventArgs,
        mode="write",
        approval_required=True,
        preview_builder_id="planner.delete_event_preview",
        output_projection="resource_ids",
    )
