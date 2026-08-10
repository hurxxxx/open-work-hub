from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import status

from ai_do_api.core.i18n import localized_http_exception

DEFAULT_TIME_ZONE = "Asia/Seoul"


def event_time_zone(time_zone: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((time_zone or DEFAULT_TIME_ZONE).strip())
    except (KeyError, ValueError):
        return ZoneInfo(DEFAULT_TIME_ZONE)


@dataclass(frozen=True)
class ParsedEventBounds:
    start_at: datetime
    end_at: datetime
    start_has_time: bool
    end_has_time: bool


def parse_iso_or_date(value: str, time_zone: str | None = None) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        try:
            only_date = date.fromisoformat(value)
            if time_zone is None:
                return datetime.combine(only_date, time.min)
            return (
                datetime.combine(
                    only_date,
                    time.min,
                    tzinfo=event_time_zone(time_zone),
                )
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
        except ValueError:
            raise exc
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()


def local_date_string(value: datetime, time_zone: str | None = None) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.astimezone(event_time_zone(time_zone)).date().isoformat()


def _local_day_start(value: date, time_zone: str | None) -> datetime:
    local = datetime.combine(value, time.min, tzinfo=event_time_zone(time_zone))
    return local.astimezone(UTC).replace(tzinfo=None)


def _local_day_end(value: date, time_zone: str | None) -> datetime:
    local = datetime.combine(value, time.max, tzinfo=event_time_zone(time_zone))
    return local.astimezone(UTC).replace(tzinfo=None)


def _parse_date_only(value: str) -> date:
    return date.fromisoformat(value)


def _has_time_component(value: str) -> bool:
    return "T" in value


def parse_event_bounds(
    *,
    all_day: bool,
    start: str,
    end: str,
    time_zone: str | None = None,
) -> ParsedEventBounds:
    if all_day:
        try:
            start_date = _parse_date_only(start)
            end_date = _parse_date_only(end)
        except ValueError as exc:
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="planner.all_day_date_required",
            ) from exc
        if end_date <= start_date:
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="planner.event_end_after_start",
            )
        zone = event_time_zone(time_zone)
        start_local = datetime.combine(start_date, time.min, tzinfo=zone)
        end_local = datetime.combine(end_date, time.min, tzinfo=zone)
        return ParsedEventBounds(
            start_at=start_local.astimezone(UTC).replace(tzinfo=None),
            end_at=end_local.astimezone(UTC).replace(tzinfo=None),
            start_has_time=False,
            end_has_time=False,
        )

    start_has_time = _has_time_component(start)
    end_has_time = _has_time_component(end)
    try:
        start_at = (
            parse_iso_or_date(start)
            if start_has_time
            else _local_day_start(_parse_date_only(start), time_zone)
        )
        end_at = (
            parse_iso_or_date(end)
            if end_has_time
            else _local_day_end(_parse_date_only(end), time_zone)
        )
    except ValueError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="planner.all_day_date_required",
        ) from exc
    if end_at <= start_at:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="planner.event_end_after_start",
        )
    return ParsedEventBounds(
        start_at=start_at,
        end_at=end_at,
        start_has_time=start_has_time,
        end_has_time=end_has_time,
    )


def serialize_event_bounds(
    *,
    all_day: bool,
    start_at: datetime,
    end_at: datetime,
    start_has_time: bool = True,
    end_has_time: bool = True,
    time_zone: str | None = None,
) -> tuple[str, str]:
    if all_day:
        return (
            local_date_string(start_at, time_zone),
            local_date_string(end_at, time_zone),
        )
    return (
        utc_iso(start_at) if start_has_time else local_date_string(start_at, time_zone),
        utc_iso(end_at) if end_has_time else local_date_string(end_at, time_zone),
    )
