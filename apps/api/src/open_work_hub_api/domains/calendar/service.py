"""Calendar events service.

Aggregates calendar-shaped data from Meeting and PMS task domains for the
current authenticated user, returning a unified ``CalendarEventOut`` list
consumed by the frontend ``<UnifiedCalendar/>`` component.

Design notes (per autoplan Round 2 Eng review):

ENG-CRIT-1: This service NEVER accepts a caller-supplied ``user_id`` or
``assignee_id`` filter. The user is always derived from the authenticated
request context. If "view someone else's calendar" is needed later, that
becomes a separate sharing feature with explicit ACL.

ENG-CRIT-3: Meeting query uses ``selectinload(Meeting.attendees)`` so we
do not hit N+1 when computing ``attendee_count``. PMS multi-assignee query
uses ``selectinload(Task.assignee_links)`` for the same reason.

ENG-HIGH-4: Caller is responsible for enforcing ordered bounds and the 366-day
range cap before calling this service. ``query_policy`` owns that HTTP query
contract for the calendar endpoint.

ENG-MED-4: The calendar source catalog owns calendar-specific source queries
instead of reusing list APIs with different range semantics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User

from .schemas import (
    CalendarEventsResponse,
    CalendarSourceType,
)
from .source_catalog import (
    DEFAULT_CALENDAR_SOURCES,
    collect_calendar_source_events,
)


def list_calendar_events(
    db: Session,
    *,
    user: User,
    from_at: datetime,
    to_at: datetime,
    sources: Iterable[CalendarSourceType] = DEFAULT_CALENDAR_SOURCES,
) -> CalendarEventsResponse:
    """Return unified calendar events for ``user`` in ``[from_at, to_at)``.

    The range bounds use UTC-naive datetimes for SQL comparison. The frontend
    converts timed events using the user's configured calendar timezone.
    ``sources`` is expected to be normalized by ``query_policy``.
    """
    items = collect_calendar_source_events(
        db=db,
        user=user,
        from_at=from_at,
        to_at=to_at,
        sources=sources,
    )
    items.sort(key=lambda ev: ev.start)
    return CalendarEventsResponse(items=items)
