from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.models import User, Workspace, WorkspaceUserBinding
from open_alm_api.domains.auth.workspace_app_gate import is_platform_app_enabled
from open_alm_api.domains.meeting.models import Meeting, MeetingAttendee
from open_alm_api.domains.meeting.schemas import (
    MeetingAvailabilityBlock,
    MeetingAvailabilityItem,
    MeetingAvailabilityResponse,
)
from open_alm_api.domains.planner.event_time import local_date_string, utc_iso
from open_alm_api.domains.planner.app_catalog import PLANNER_WORKSPACE_APP
from open_alm_api.domains.planner.models import PlannerEvent


def dedupe_requested_user_ids(user_ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(user_ids))


def workspace_meeting_user_ids_subquery(workspace_id: str):
    return (
        select(WorkspaceUserBinding.user_id.label("user_id"))
        .where(WorkspaceUserBinding.workspace_id == workspace_id)
        .subquery()
    )


def load_requested_workspace_users(
    db: Session,
    *,
    workspace_id: str,
    requested_user_ids: list[str],
) -> dict[str, User]:
    member_user_ids = workspace_meeting_user_ids_subquery(workspace_id)
    users = db.scalars(
        select(User)
        .join(member_user_ids, member_user_ids.c.user_id == User.id)
        .where(User.status == "active", User.id.in_(requested_user_ids))
        .order_by(User.full_name.asc(), User.email.asc())
    ).all()
    users_by_id = {member.id: member for member in users}
    missing = [user_id for user_id in requested_user_ids if user_id not in users_by_id]
    if missing:
        raise localized_http_exception(
            status_code=422,
            code="meeting.requested_users_workspace_required",
            user_ids=", ".join(missing),
        )
    return users_by_id


def project_meeting_busy_block(meeting: Meeting) -> MeetingAvailabilityBlock:
    return MeetingAvailabilityBlock(
        id=f"meeting-{meeting.id}",
        start=utc_iso(meeting.start_at),
        end=utc_iso(meeting.end_at),
        all_day=False,
        source_type="meeting",
        masked=True,
        title=None,
        location=None,
    )


def build_meeting_busy_blocks(
    meetings: Iterable[Meeting],
    *,
    requested_user_ids: list[str],
) -> dict[str, list[MeetingAvailabilityBlock]]:
    blocks_by_user_id: dict[str, list[MeetingAvailabilityBlock]] = {
        user_id: [] for user_id in requested_user_ids
    }
    for meeting in meetings:
        participant_ids = {meeting.organizer_id}
        participant_ids.update(attendee.user_id for attendee in meeting.attendees)
        for user_id in requested_user_ids:
            if user_id in participant_ids:
                blocks_by_user_id[user_id].append(project_meeting_busy_block(meeting))
    return blocks_by_user_id


def load_meeting_busy_blocks(
    db: Session,
    *,
    workspace_id: str,
    requested_user_ids: list[str],
    from_at: datetime,
    to_at: datetime,
) -> dict[str, list[MeetingAvailabilityBlock]]:
    attendee_meeting_ids = select(MeetingAttendee.meeting_id).where(
        MeetingAttendee.user_id.in_(requested_user_ids)
    )
    meetings = db.scalars(
        select(Meeting)
        .where(Meeting.workspace_id == workspace_id)
        .where(
            or_(
                Meeting.organizer_id.in_(requested_user_ids),
                Meeting.id.in_(attendee_meeting_ids),
            )
        )
        .where(Meeting.end_at > from_at, Meeting.start_at < to_at)
        .options(selectinload(Meeting.attendees))
        .order_by(Meeting.start_at.asc())
    ).all()
    return build_meeting_busy_blocks(meetings, requested_user_ids=requested_user_ids)


def project_planner_event_busy_block(
    event: PlannerEvent,
    *,
    viewer_id: str,
) -> MeetingAvailabilityBlock:
    masked = event.owner_id != viewer_id
    return MeetingAvailabilityBlock(
        id=f"planner-event-{event.id}",
        start=(
            local_date_string(event.start_at, event.time_zone)
            if event.all_day
            else utc_iso(event.start_at)
        ),
        end=(
            local_date_string(event.end_at, event.time_zone)
            if event.all_day
            else utc_iso(event.end_at)
        ),
        all_day=event.all_day,
        source_type="planner_event",
        masked=masked,
        title=None if masked else event.title,
        location=None if masked or not event.location else event.location,
    )


def load_planner_event_busy_blocks(
    db: Session,
    *,
    workspace_id: str,
    requested_user_ids: list[str],
    viewer_id: str,
    from_at: datetime,
    to_at: datetime,
) -> dict[str, list[MeetingAvailabilityBlock]]:
    blocks_by_user_id: dict[str, list[MeetingAvailabilityBlock]] = {
        user_id: [] for user_id in requested_user_ids
    }
    planner_events = db.scalars(
        select(PlannerEvent)
        .where(
            PlannerEvent.owner_id.in_(requested_user_ids),
        )
        .where(
            (PlannerEvent.all_day.is_(True))
            | ((PlannerEvent.start_has_time.is_(True)) & (PlannerEvent.end_has_time.is_(True)))
        )
        .where(PlannerEvent.end_at > from_at, PlannerEvent.start_at < to_at)
        .order_by(PlannerEvent.start_at.asc())
    ).all()
    for event in planner_events:
        blocks_by_user_id[event.owner_id].append(
            project_planner_event_busy_block(event, viewer_id=viewer_id)
        )
    return blocks_by_user_id


def merge_busy_blocks(
    *sources: dict[str, list[MeetingAvailabilityBlock]],
) -> dict[str, list[MeetingAvailabilityBlock]]:
    merged: dict[str, list[MeetingAvailabilityBlock]] = {}
    for source in sources:
        for user_id, blocks in source.items():
            merged.setdefault(user_id, []).extend(blocks)
    return merged


def build_availability_response(
    *,
    requested_user_ids: list[str],
    users_by_id: dict[str, User],
    blocks_by_user_id: dict[str, list[MeetingAvailabilityBlock]],
) -> MeetingAvailabilityResponse:
    unique_user_ids = dedupe_requested_user_ids(requested_user_ids)

    def sort_key(block: MeetingAvailabilityBlock) -> str:
        return f"{block.start}|{block.end}|{block.id}"

    items = [
        MeetingAvailabilityItem(
            user_id=user_id,
            full_name=users_by_id[user_id].full_name,
            blocks=sorted(blocks_by_user_id.get(user_id, []), key=sort_key),
        )
        for user_id in unique_user_ids
    ]
    return MeetingAvailabilityResponse(items=items)


def build_meeting_availability(
    db: Session,
    *,
    workspace: Workspace,
    viewer: User,
    user_ids: list[str],
    from_at: datetime,
    to_at: datetime,
) -> MeetingAvailabilityResponse:
    unique_user_ids = dedupe_requested_user_ids(user_ids)
    if not unique_user_ids:
        return MeetingAvailabilityResponse(items=[])

    users_by_id = load_requested_workspace_users(
        db,
        workspace_id=workspace.id,
        requested_user_ids=unique_user_ids,
    )
    meeting_blocks = load_meeting_busy_blocks(
        db,
        workspace_id=workspace.id,
        requested_user_ids=unique_user_ids,
        from_at=from_at,
        to_at=to_at,
    )
    planner_blocks: dict[str, list[MeetingAvailabilityBlock]] = {}
    if is_platform_app_enabled(db, PLANNER_WORKSPACE_APP.app_id):
        planner_blocks = load_planner_event_busy_blocks(
            db,
            workspace_id=workspace.id,
            requested_user_ids=unique_user_ids,
            viewer_id=viewer.id,
            from_at=from_at,
            to_at=to_at,
        )
    blocks_by_user_id = merge_busy_blocks(meeting_blocks, planner_blocks)
    return build_availability_response(
        requested_user_ids=unique_user_ids,
        users_by_id=users_by_id,
        blocks_by_user_id=blocks_by_user_id,
    )
