"""Calendar events HTTP router."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from aidoo_api.domains.auth.models import User, Workspace

from .schemas import CalendarEventsResponse, CalendarSourceType
from .service import list_calendar_events, parse_iso_or_date


router = APIRouter(prefix="/calendar", tags=["calendar"])


_VALID_SOURCES: set[CalendarSourceType] = {"meeting", "pms_due", "pms_block", "planner_event"}
_MAX_RANGE_DAYS = 366


@router.get("/events", response_model=CalendarEventsResponse)
def list_events(
    from_param: str = Query(..., alias="from", description="ISO date or datetime"),
    to_param: str = Query(..., alias="to", description="Exclusive end (ISO)"),
    sources: str = Query(
        default="meeting,pms_due,pms_block,planner_event",
        description="Comma-separated source types to include.",
    ),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> CalendarEventsResponse:
    """Return unified calendar events for the **current authenticated user**.

    The endpoint never accepts a caller-supplied user/assignee id — calendar
    sharing across users is not supported in this round (ENG-CRIT-1).
    """
    try:
        from_at = parse_iso_or_date(from_param)
        to_at = parse_iso_or_date(to_param)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ISO date/datetime: {exc}",
        ) from exc

    if to_at <= from_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Range 'to' must be strictly after 'from'.",
        )

    # ENG-HIGH-4: bound the range to prevent unbounded queries (e.g. 1970→2099).
    if (to_at - from_at) > timedelta(days=_MAX_RANGE_DAYS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Range exceeds maximum {_MAX_RANGE_DAYS} days.",
        )

    requested_sources = {s.strip() for s in sources.split(",") if s.strip()}
    invalid = requested_sources - _VALID_SOURCES
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown source types: {sorted(invalid)}",
        )
    if not requested_sources:
        # Empty filter → return empty result (per Phase 2 design D1: explicit empty).
        return CalendarEventsResponse(items=[])

    return list_calendar_events(
        db,
        workspace=workspace,
        user=current_user,
        from_at=from_at,
        to_at=to_at,
        sources=tuple(requested_sources),  # type: ignore[arg-type]
    )
