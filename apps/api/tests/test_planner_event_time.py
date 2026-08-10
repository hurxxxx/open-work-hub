from datetime import datetime

import pytest
from fastapi import HTTPException

from ai_do_api.domains.planner.event_time import (
    local_date_string,
    parse_event_bounds,
    parse_iso_or_date,
    serialize_event_bounds,
    utc_iso,
)


def test_parse_iso_or_date_normalizes_offset_datetimes_to_naive_utc() -> None:
    assert parse_iso_or_date("2026-05-04T10:00:00+09:00") == datetime(
        2026, 5, 4, 1, 0
    )
    assert parse_iso_or_date("2026-05-04") == datetime(2026, 5, 4, 0, 0)


def test_all_day_bounds_round_trip_through_kst_dates() -> None:
    bounds = parse_event_bounds(
        all_day=True,
        start="2026-05-06",
        end="2026-05-08",
    )

    assert bounds.start_at == datetime(2026, 5, 5, 15, 0)
    assert bounds.end_at == datetime(2026, 5, 7, 15, 0)
    assert bounds.start_has_time is False
    assert bounds.end_has_time is False
    assert serialize_event_bounds(
        all_day=True,
        start_at=bounds.start_at,
        end_at=bounds.end_at,
    ) == ("2026-05-06", "2026-05-08")


def test_timed_bounds_require_datetimes_and_emit_utc_iso() -> None:
    bounds = parse_event_bounds(
        all_day=False,
        start="2026-05-04T10:00:00+09:00",
        end="2026-05-04T12:00:00+09:00",
    )

    assert bounds.start_at == datetime(2026, 5, 4, 1, 0)
    assert bounds.end_at == datetime(2026, 5, 4, 3, 0)
    assert bounds.start_has_time is True
    assert bounds.end_has_time is True
    assert serialize_event_bounds(
        all_day=False,
        start_at=bounds.start_at,
        end_at=bounds.end_at,
    ) == ("2026-05-04T01:00:00+00:00", "2026-05-04T03:00:00+00:00")
    assert utc_iso(bounds.start_at) == "2026-05-04T01:00:00+00:00"


def test_non_all_day_bounds_allow_optional_start_and_end_times() -> None:
    start_only = parse_event_bounds(
        all_day=False,
        start="2026-05-04T10:00:00+09:00",
        end="2026-05-04",
    )
    assert start_only.start_has_time is True
    assert start_only.end_has_time is False
    assert serialize_event_bounds(
        all_day=False,
        start_at=start_only.start_at,
        end_at=start_only.end_at,
        start_has_time=start_only.start_has_time,
        end_has_time=start_only.end_has_time,
    ) == ("2026-05-04T01:00:00+00:00", "2026-05-04")

    end_only = parse_event_bounds(
        all_day=False,
        start="2026-05-04",
        end="2026-05-04T18:00:00+09:00",
    )
    assert end_only.start_has_time is False
    assert end_only.end_has_time is True
    assert serialize_event_bounds(
        all_day=False,
        start_at=end_only.start_at,
        end_at=end_only.end_at,
        start_has_time=end_only.start_has_time,
        end_has_time=end_only.end_has_time,
    ) == ("2026-05-04", "2026-05-04T09:00:00+00:00")

    no_time = parse_event_bounds(
        all_day=False,
        start="2026-05-04",
        end="2026-05-04",
    )
    assert no_time.start_has_time is False
    assert no_time.end_has_time is False
    assert serialize_event_bounds(
        all_day=False,
        start_at=no_time.start_at,
        end_at=no_time.end_at,
        start_has_time=no_time.start_has_time,
        end_has_time=no_time.end_has_time,
    ) == ("2026-05-04", "2026-05-04")


def test_invalid_event_bounds_raise_localized_http_errors() -> None:
    with pytest.raises(HTTPException) as all_day_error:
        parse_event_bounds(all_day=True, start="2026-05-05", end="2026-05-04")
    assert all_day_error.value.status_code == 400

    with pytest.raises(HTTPException) as ordered_error:
        parse_event_bounds(
            all_day=False,
            start="2026-05-04T12:00:00+09:00",
            end="2026-05-04T10:00:00+09:00",
        )
    assert ordered_error.value.status_code == 400


def test_local_date_string_handles_aware_and_naive_utc_values() -> None:
    assert local_date_string(datetime(2026, 5, 5, 15, 0)) == "2026-05-06"
    assert (
        local_date_string(parse_iso_or_date("2026-05-06T00:30:00+09:00"))
        == "2026-05-06"
    )
