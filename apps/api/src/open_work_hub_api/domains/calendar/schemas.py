"""Pydantic schemas for the unified calendar events endpoint."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

CalendarSourceType = Literal["meeting", "pms_due", "pms_block", "planner_event"]


def _camel_config() -> ConfigDict:
    """Pydantic config: emit camelCase keys for the wire, accept either."""
    return ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class CalendarEventMetadata(BaseModel):
    """Source-specific extras the UI renders in the popover without a second fetch."""

    model_config = _camel_config()

    # Meeting-only
    meeting_id: str | None = None
    attendee_count: int | None = None
    # PMS-only
    task_list_id: str | None = None
    task_list_key: str | None = None
    task_number: int | None = None
    status: str | None = None
    assignee_ids: list[str] | None = None
    # Planner-only
    planner_event_id: str | None = None
    owner_id: str | None = None
    owner_name: str | None = None
    location: str | None = None
    planner_all_day: bool | None = None
    planner_start_has_time: bool | None = None
    planner_end_has_time: bool | None = None
    planner_time_zone: str | None = None


class CalendarEventOut(BaseModel):
    """Unified event row returned by GET /calendar/events.

    ``start`` / ``end`` are ISO 8601 strings. For all-day events they are dates
    (YYYY-MM-DD). For time-ranged events they include a UTC offset and are
    expected to be interpreted in the calendar component's configured zone.
    """

    model_config = _camel_config()

    id: str
    title: str
    start: str
    end: str
    all_day: bool
    source_type: CalendarSourceType
    source_id: str
    color: str
    metadata: CalendarEventMetadata


class CalendarEventsResponse(BaseModel):
    items: list[CalendarEventOut]


__all__ = [
    "CalendarSourceType",
    "CalendarEventMetadata",
    "CalendarEventOut",
    "CalendarEventsResponse",
]


# Convenience type aliases for the service layer.
CalendarRangeStart = date | datetime
CalendarRangeEnd = date | datetime
