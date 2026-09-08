"""Calendar events HTTP router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.dependencies import (
    require_current_user,
)
from open_work_hub_api.domains.auth.models import User

from .query_policy import CalendarQueryPolicyError, parse_calendar_events_query
from .schemas import CalendarEventsResponse
from .service import list_calendar_events
from .source_catalog import DEFAULT_CALENDAR_SOURCES_PARAM

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
)


@router.get("/events", response_model=CalendarEventsResponse)
def list_events(
    from_param: str = Query(..., alias="from", description="ISO date or datetime"),
    to_param: str = Query(..., alias="to", description="Exclusive end (ISO)"),
    sources: str = Query(
        default=DEFAULT_CALENDAR_SOURCES_PARAM,
        description="Comma-separated source types to include.",
    ),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CalendarEventsResponse:
    """Return unified calendar events for the **current authenticated user**.

    The endpoint never accepts a caller-supplied user/assignee id — calendar
    sharing across users is not supported in this round (ENG-CRIT-1).
    """
    try:
        query = parse_calendar_events_query(
            from_param=from_param,
            to_param=to_param,
            sources_param=sources,
            time_zone=current_user.time_zone,
        )
    except CalendarQueryPolicyError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=exc.code,
            **exc.params,
        ) from exc

    if query.is_empty_source_filter:
        return CalendarEventsResponse(items=[])

    return list_calendar_events(
        db,
        user=current_user,
        from_at=query.from_at,
        to_at=query.to_at,
        sources=query.sources,
    )
