"""Calendar event query parsing and validation policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ai_do_api.domains.planner.event_time import parse_iso_or_date

from .schemas import CalendarSourceType
from .source_catalog import DEFAULT_CALENDAR_SOURCES, VALID_CALENDAR_SOURCES


MAX_CALENDAR_RANGE_DAYS = 366


class CalendarQueryPolicyError(ValueError):
    """Raised when calendar event query parameters violate policy."""

    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass(frozen=True)
class CalendarEventsQuery:
    from_at: datetime
    to_at: datetime
    sources: tuple[CalendarSourceType, ...] = field(default_factory=tuple)

    @property
    def is_empty_source_filter(self) -> bool:
        return not self.sources


def parse_calendar_events_query(
    *,
    from_param: str,
    to_param: str,
    sources_param: str,
    time_zone: str | None = None,
) -> CalendarEventsQuery:
    """Parse and validate GET /calendar/events query params."""
    try:
        from_at = parse_iso_or_date(from_param, time_zone)
        to_at = parse_iso_or_date(to_param, time_zone)
    except ValueError as exc:
        raise CalendarQueryPolicyError(
            "calendar.invalid_iso_datetime",
            error=str(exc),
        ) from exc

    if to_at <= from_at:
        raise CalendarQueryPolicyError("calendar.range_to_after_from")

    if (to_at - from_at) > timedelta(days=MAX_CALENDAR_RANGE_DAYS):
        raise CalendarQueryPolicyError(
            "calendar.range_too_large",
            days=MAX_CALENDAR_RANGE_DAYS,
        )

    return CalendarEventsQuery(
        from_at=from_at,
        to_at=to_at,
        sources=normalize_calendar_sources(sources_param),
    )


def normalize_calendar_sources(sources_param: str) -> tuple[CalendarSourceType, ...]:
    requested_sources = {source.strip() for source in sources_param.split(",") if source.strip()}
    invalid = requested_sources - VALID_CALENDAR_SOURCES
    if invalid:
        raise CalendarQueryPolicyError(
            "calendar.unknown_source_types",
            source_types=", ".join(sorted(invalid)),
        )
    return tuple(source for source in DEFAULT_CALENDAR_SOURCES if source in requested_sources)
