from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.registry import AiCapabilityRegistry
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.meeting import service as meeting_service
from aidoo_api.domains.planner.service import parse_iso_or_date


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


def _required_str_list(arguments: Mapping[str, Any], key: str) -> list[str]:
    value = arguments.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool argument '{key}' must be a list of strings.",
        )
    return list(value)


def _parse_range_arg(arguments: Mapping[str, Any], key: str):
    value = _required_str(arguments, key)
    try:
        return parse_iso_or_date(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ISO date/datetime for '{key}': {exc}",
        ) from exc


def _parse_optional_range_arg(arguments: Mapping[str, Any], key: str):
    value = _optional_str(arguments, key)
    if value is None:
        return None
    try:
        return parse_iso_or_date(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ISO date/datetime for '{key}': {exc}",
        ) from exc


def _list_meetings(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    scope = _optional_str(arguments, "scope") or "mine"
    result = meeting_service.list_meetings(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        scope=scope,
        from_at=_parse_optional_range_arg(arguments, "from"),
        to_at=_parse_optional_range_arg(arguments, "to"),
    )
    return result.model_dump(mode="json", by_alias=True)


def _get_meeting(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    result = meeting_service.get_meeting(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=_required_str(arguments, "meeting_id"),
    )
    return result.model_dump(mode="json", by_alias=True)


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Range 'to' must be strictly after 'from'.",
        )
    if (to_at - from_at) > timedelta(days=31):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Availability range exceeds maximum 31 days.",
        )
    result = meeting_service.list_meeting_availability(
        db,
        workspace=workspace,
        principal=principal,
        viewer=user,
        user_ids=_required_str_list(arguments, "user_ids"),
        from_at=from_at,
        to_at=to_at,
    )
    return result.model_dump(mode="json", by_alias=True)


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_task(
        task_kind="meeting_summary",
        default_policy="local_only",
        description="Meeting transcript summarization (worker)",
    )
    registry.register_tool(
        name="meeting.list_meetings",
        description="List meetings in the current workspace.",
        owner_domain="meeting",
        handler=_list_meetings,
    )
    registry.register_tool(
        name="meeting.get_meeting",
        description="Load one meeting in the current workspace.",
        owner_domain="meeting",
        handler=_get_meeting,
    )
    registry.register_tool(
        name="meeting.find_availability",
        description="Find attendee availability in the current workspace.",
        owner_domain="meeting",
        handler=_find_availability,
    )
