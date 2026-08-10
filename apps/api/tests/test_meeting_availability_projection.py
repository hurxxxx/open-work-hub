from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from open_alm_api.domains.meeting.availability_projection import (
    build_availability_response,
    build_meeting_busy_blocks,
    project_planner_event_busy_block,
)
from open_alm_api.domains.meeting.schemas import MeetingAvailabilityBlock


def _dt(day: int, hour: int) -> datetime:
    return datetime(2026, 5, day, hour, tzinfo=UTC).replace(tzinfo=None)


def test_build_availability_response_dedupes_users_keeps_order_and_sorts_blocks() -> None:
    early_block = MeetingAvailabilityBlock(
        id="planner-event-early",
        start="2026-05-18T01:00:00+00:00",
        end="2026-05-18T02:00:00+00:00",
        all_day=False,
        source_type="planner_event",
        masked=False,
    )
    later_block = MeetingAvailabilityBlock(
        id="meeting-later",
        start="2026-05-18T03:00:00+00:00",
        end="2026-05-18T04:00:00+00:00",
        all_day=False,
        source_type="meeting",
        masked=True,
    )

    response = build_availability_response(
        requested_user_ids=["user-2", "user-1", "user-2"],
        users_by_id={
            "user-1": SimpleNamespace(full_name="Ada Lovelace"),
            "user-2": SimpleNamespace(full_name="Grace Hopper"),
        },
        blocks_by_user_id={"user-2": [later_block, early_block], "user-1": []},
    )

    assert [item.user_id for item in response.items] == ["user-2", "user-1"]
    assert response.items[0].full_name == "Grace Hopper"
    assert [block.id for block in response.items[0].blocks] == [
        "planner-event-early",
        "meeting-later",
    ]


def test_project_planner_event_busy_block_masks_personal_events_for_other_viewers() -> None:
    block = project_planner_event_busy_block(
        SimpleNamespace(
            id="event-1",
            owner_id="owner-1",
            title="Private appointment",
            location="Clinic",
            time_zone="Asia/Seoul",
            all_day=False,
            start_at=_dt(18, 1),
            end_at=_dt(18, 2),
        ),
        viewer_id="viewer-1",
    )

    assert block.masked is True
    assert block.title is None
    assert block.location is None
    assert block.start == "2026-05-18T01:00:00+00:00"
    assert block.end == "2026-05-18T02:00:00+00:00"


def test_build_meeting_busy_blocks_includes_organizer_and_attendees_only() -> None:
    blocks_by_user_id = build_meeting_busy_blocks(
        [
            SimpleNamespace(
                id="meeting-1",
                organizer_id="organizer-1",
                start_at=_dt(19, 3),
                end_at=_dt(19, 4),
                attendees=[
                    SimpleNamespace(user_id="attendee-1"),
                    SimpleNamespace(user_id="other-1"),
                ],
            )
        ],
        requested_user_ids=["attendee-1", "organizer-1", "missing-1"],
    )

    assert [block.id for block in blocks_by_user_id["attendee-1"]] == ["meeting-meeting-1"]
    assert [block.id for block in blocks_by_user_id["organizer-1"]] == ["meeting-meeting-1"]
    assert blocks_by_user_id["missing-1"] == []
    assert blocks_by_user_id["attendee-1"][0].masked is True
