from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import (
    AiCapabilityRegistry,
    ApprovalPreview,
    PreviewField,
    WorkspaceContext,
)
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.planner.event_time import parse_iso_or_date


class _ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ListMeetingsArgs(_ToolArgsModel):
    scope: Literal["mine", "upcoming", "all"] = Field(
        default="mine",
        description=(
            "Meeting range. Use 'upcoming' only for future meetings. "
            "Use 'all' when the user asks for the latest, last, previous, or past meeting."
        ),
    )
    from_at: str | None = Field(
        default=None,
        alias="from",
        description="Optional inclusive lower bound as ISO date/datetime.",
    )
    to_at: str | None = Field(
        default=None,
        alias="to",
        description="Optional inclusive upper bound as ISO date/datetime.",
    )


class GetMeetingArgs(_ToolArgsModel):
    meeting_id: str = Field(..., min_length=1)


class FindAvailabilityArgs(_ToolArgsModel):
    user_ids: list[str] = Field(..., min_length=1)
    from_at: str = Field(..., alias="from", min_length=1)
    to_at: str = Field(..., alias="to", min_length=1)


class RefreshMeetingInsightsArgs(_ToolArgsModel):
    meeting_id: str = Field(..., min_length=1)
    refresh: bool = False


class DraftFollowupScheduleArgs(_ToolArgsModel):
    meeting_id: str = Field(..., min_length=1)
    attendee_user_ids: list[str] | None = Field(default=None, max_length=50)
    refresh: bool = False


class CreateMeetingArgs(_ToolArgsModel):
    title: str = Field(..., min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime
    attendee_user_ids: list[str] | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=240)


def _parse_range_arg(arguments: Mapping[str, Any], key: str):
    value = str(arguments[key])
    try:
        return parse_iso_or_date(value)
    except ValueError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.invalid_iso_datetime_for_field",
            field=key,
            error=str(exc),
        ) from exc


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


def _insights_module():
    from open_work_hub_api.domains.meeting import insights as meeting_insights

    return meeting_insights


def _meeting_service():
    from open_work_hub_api.domains.meeting import service as meeting_service

    return meeting_service


def _list_meetings(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    scope = str(arguments.get("scope", "mine"))
    result = _meeting_service().list_meetings(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        scope=scope,
        from_at=_parse_optional_range_arg(arguments, "from"),
        to_at=_parse_optional_range_arg(arguments, "to"),
    )
    payload = result.model_dump(mode="json", by_alias=True)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    if items:
        payload = {
            "total": payload.get("total", len(items)),
            "sort": "start_at_asc",
            "scope": scope,
            "items": items,
        }
        if scope == "upcoming":
            payload["nextMeeting"] = items[0]
        if scope == "all":
            payload["latestMeeting"] = items[-1]
    return payload


def _get_meeting(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return _meeting_service().get_meeting_for_ai(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=str(arguments["meeting_id"]),
    )


def _find_availability(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    from_at = _parse_range_arg(arguments, "from")
    to_at = _parse_range_arg(arguments, "to")
    if to_at <= from_at:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.range_to_after_from",
        )
    if (to_at - from_at) > timedelta(days=31):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.availability_range_too_large",
            days=31,
        )
    result = _meeting_service().list_meeting_availability(
        db,
        workspace=workspace,
        principal=principal,
        viewer=user,
        user_ids=list(arguments["user_ids"]),
        from_at=from_at,
        to_at=to_at,
    )
    return result.model_dump(mode="json", by_alias=True)


def _extract_actions(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return _insights_module().list_action_insights(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=str(arguments["meeting_id"]),
        refresh=bool(arguments.get("refresh", False)),
    )


def _extract_decisions(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return _insights_module().list_decision_insights(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=str(arguments["meeting_id"]),
        refresh=bool(arguments.get("refresh", False)),
    )


def _draft_followup_schedule(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return _insights_module().draft_followup_schedule(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=str(arguments["meeting_id"]),
        attendee_user_ids=(
            [str(item) for item in arguments.get("attendee_user_ids") or []] or None
        ),
        refresh=bool(arguments.get("refresh", False)),
    )


def _create_meeting(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return _meeting_service().create_meeting_for_ai(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        title=str(arguments["title"]),
        start_at=arguments["start_at"],
        end_at=arguments["end_at"],
        attendee_user_ids=[str(item) for item in arguments.get("attendee_user_ids") or []],
        description=str(arguments.get("description") or ""),
        location=arguments.get("location"),
        approved_call_id=approved_call_id,
    )


def _build_create_meeting_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = (
        parsed_args.model_dump(mode="python", by_alias=True, exclude_none=True)
        if isinstance(parsed_args, BaseModel)
        else dict(parsed_args)
    )
    attendee_count = len(values.get("attendee_user_ids") or [])
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Create meeting",
        summary=str(values.get("description") or "Create a meeting from AI.").strip()
        or "Create a meeting from AI.",
        fields=(
            PreviewField(label="Title", value=str(values.get("title", "-"))),
            PreviewField(label="Start", value=str(values.get("start_at", "-"))),
            PreviewField(label="Attendees", value=str(attendee_count)),
        ),
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_task(
        task_kind="meeting_summary",
        default_policy="local_only",
        description="Meeting transcript summarization (worker)",
        # recording.py(녹취 분석)도 같은 task_kind 로 요약을 호출하므로 recording 앱을 함께 선언한다.
        app_ids=("meeting", "recording"),
    )
    registry.register_llm_task(
        task_kind="meeting_insight_actions",
        default_policy="local_only",
        description="Meeting action-item extraction (worker/read refresh)",
        app_ids=("meeting",),
    )
    registry.register_llm_task(
        task_kind="meeting_insight_decisions",
        default_policy="local_only",
        description="Meeting decision extraction (worker/read refresh)",
        app_ids=("meeting",),
    )
    registry.register_llm_task(
        task_kind="meeting_insight_followup",
        default_policy="local_only",
        description="Meeting follow-up schedule extraction (worker/read refresh)",
        app_ids=("meeting",),
    )
    registry.register_preview_builder(
        preview_builder_id="meeting.create_meeting_preview",
        builder=_build_create_meeting_preview,
    )
    registry.register_tool(
        name="meeting.list_meetings",
        description=(
            "List meetings in the current workspace. For questions about the latest, "
            "last, previous, or past meeting, call this with scope='all'. "
            "For future schedule questions, call this with scope='upcoming'."
        ),
        owner_domain="meeting",
        handler=_list_meetings,
        args_model=ListMeetingsArgs,
    )
    registry.register_tool(
        name="meeting.get_meeting",
        description="Load one meeting in the current workspace.",
        owner_domain="meeting",
        handler=_get_meeting,
        args_model=GetMeetingArgs,
    )
    registry.register_tool(
        name="meeting.find_availability",
        description="Find attendee availability in the current workspace.",
        owner_domain="meeting",
        handler=_find_availability,
        args_model=FindAvailabilityArgs,
    )
    registry.register_tool(
        name="meeting.extract_actions",
        description="Return stored AI action-item suggestions for a meeting.",
        owner_domain="meeting",
        handler=_extract_actions,
        args_model=RefreshMeetingInsightsArgs,
    )
    registry.register_tool(
        name="meeting.extract_decisions",
        description="Return stored AI decision suggestions for a meeting.",
        owner_domain="meeting",
        handler=_extract_decisions,
        args_model=RefreshMeetingInsightsArgs,
    )
    registry.register_tool(
        name="meeting.draft_followup_schedule",
        description="Return stored follow-up meeting suggestions and availability for a meeting.",
        owner_domain="meeting",
        handler=_draft_followup_schedule,
        args_model=DraftFollowupScheduleArgs,
    )
    if not get_settings().ai_write_tools_enabled:
        return
    registry.register_tool(
        name="meeting.create_meeting",
        description="Create a meeting in the current workspace.",
        owner_domain="meeting",
        handler=_create_meeting,
        args_model=CreateMeetingArgs,
        mode="write",
        approval_required=True,
        preview_builder_id="meeting.create_meeting_preview",
        output_projection="resource_ids",
    )
