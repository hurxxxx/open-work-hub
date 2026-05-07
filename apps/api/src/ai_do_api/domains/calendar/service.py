"""Calendar events service.

Aggregates calendar-shaped data from Meeting and PMS issue domains for the
current authenticated user, returning a unified ``CalendarEventOut`` list
consumed by the frontend ``<UnifiedCalendar/>`` component.

Design notes (per autoplan Round 2 Eng review):

ENG-CRIT-1: This service NEVER accepts a caller-supplied ``user_id`` or
``assignee_id`` filter. The user is always derived from the authenticated
request context. If "view someone else's calendar" is needed later, that
becomes a separate sharing feature with explicit ACL.

ENG-CRIT-3: Meeting query uses ``selectinload(Meeting.attendees)`` so we
do not hit N+1 when computing ``attendee_count``. PMS multi-assignee query
uses ``selectinload(Issue.assignee_links)`` for the same reason.

ENG-HIGH-4: Caller is responsible for enforcing the 366-day range cap before
calling this service. Router enforces it.

ENG-MED-4: This service owns its calendar-specific meeting overlap query
instead of reusing ``meeting_service.list_meetings``. The meeting list API has
different range semantics, so sharing the helper would leak inclusive-end
behavior into the calendar endpoint.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ai_do_api.domains.auth.models import Team, User, Workspace
from ai_do_api.domains.meeting.models import Meeting, MeetingAttendee
from ai_do_api.domains.pms.models import Issue, IssueAssignee, TaskList
from ai_do_api.domains.planner.models import PlannerEvent

from .schemas import (
    CalendarEventMetadata,
    CalendarEventOut,
    CalendarEventsResponse,
    CalendarSourceType,
)


# Hex color tokens duplicated from the frontend ``CALENDAR_SOURCE_COLORS`` map.
# Backend is the single source of truth for the wire format; the frontend uses
# whatever value comes back. Pms_block ideally inherits from status color, but
# for now we ship the same green default and let the polish phase improve it.
_SOURCE_COLORS: dict[CalendarSourceType, str] = {
    "meeting": "#3b82f6",   # blue-500
    "pms_due": "#f59e0b",   # amber-500
    "pms_block": "#22c55e", # green-500
    "planner_event": "#14b8a6", # teal-500
}


def _utc_iso(value: datetime) -> str:
    """Emit a naive-UTC ``datetime`` as an unambiguous ``+00:00`` ISO string.

    Meeting.start_at is stored as a naive UTC ``DateTime`` column. Returning
    ``isoformat()`` directly produces ``"2026-04-15T01:00:00"`` which the
    FullCalendar luxon plugin would interpret as the calendar's local zone,
    causing a 9-hour drift in KST. Append the explicit offset so the wire
    format is unambiguous.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()


def list_calendar_events(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    from_at: datetime,
    to_at: datetime,
    sources: Iterable[CalendarSourceType] = ("meeting", "pms_due", "pms_block"),
) -> CalendarEventsResponse:
    """Return unified calendar events for ``user`` in ``[from_at, to_at)``.

    The range bounds use UTC-naive datetimes for SQL comparison. The frontend
    converts timed events using the user's configured calendar timezone.
    """
    source_set: set[CalendarSourceType] = set(sources)
    items: list[CalendarEventOut] = []

    if "meeting" in source_set:
        items.extend(_meeting_events(db, workspace=workspace, user=user, from_at=from_at, to_at=to_at))

    wants_due = "pms_due" in source_set
    wants_block = "pms_block" in source_set
    if wants_due or wants_block:
        items.extend(
            _pms_events(
                db,
                workspace=workspace,
                user=user,
                from_at=from_at,
                to_at=to_at,
                include_due=wants_due,
                include_block=wants_block,
            )
        )
    if "planner_event" in source_set:
        items.extend(
            _planner_events(
                db,
                workspace=workspace,
                user=user,
                from_at=from_at,
                to_at=to_at,
            )
        )

    items.sort(key=lambda ev: ev.start)
    return CalendarEventsResponse(items=items)


def _meeting_events(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    from_at: datetime,
    to_at: datetime,
) -> list[CalendarEventOut]:
    attendee_meeting_ids = select(MeetingAttendee.meeting_id).where(
        MeetingAttendee.user_id == user.id
    )
    meetings = db.scalars(
        select(Meeting)
        .where(Meeting.workspace_id == workspace.id)
        .where(
            or_(
                Meeting.organizer_id == user.id,
                Meeting.id.in_(attendee_meeting_ids),
            )
        )
        # Calendar contract is [from, to): exclude events starting exactly at
        # the exclusive end, include events that overlap the range.
        .where(Meeting.end_at > from_at)
        .where(Meeting.start_at < to_at)
        .options(selectinload(Meeting.attendees))
        .order_by(Meeting.start_at.asc())
    ).all()
    return [
        CalendarEventOut(
            id=f"meeting-{meeting.id}",
            title=meeting.title,
            start=_utc_iso(meeting.start_at),
            end=_utc_iso(meeting.end_at),
            all_day=False,
            source_type="meeting",
            source_id=meeting.id,
            color=_SOURCE_COLORS["meeting"],
            metadata=CalendarEventMetadata(
                meeting_id=meeting.id,
                attendee_count=len(meeting.attendees),
            ),
        )
        for meeting in meetings
    ]


def _pms_events(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    from_at: datetime,
    to_at: datetime,
    include_due: bool,
    include_block: bool,
) -> list[CalendarEventOut]:
    """Cross-list PMS issue query scoped to the workspace.

    Returns issues where:
      - the user is the single assignee (Issue.assignee_id), OR
      - the user is in the multi-assignee junction (IssueAssignee.user_id)
    AND the issue is anchored inside the range by either due_date or
    (start_date, due_date) span depending on which sources are requested.

    Workspace scoping path: Issue → TaskList → Team → workspace_id.
    """
    range_start: date = from_at.date() if isinstance(from_at, datetime) else from_at
    range_end: date = to_at.date() if isinstance(to_at, datetime) else to_at

    multi_assignee_subq = select(IssueAssignee.issue_id).where(
        IssueAssignee.user_id == user.id
    )

    stmt = (
        select(Issue)
        .join(TaskList, TaskList.id == Issue.list_id)
        .join(Team, Team.id == TaskList.team_id)
        .where(Team.workspace_id == workspace.id)
        .where(Issue.archived.is_(False))
        .where(
            or_(
                Issue.assignee_id == user.id,
                Issue.id.in_(multi_assignee_subq),
            )
        )
        .options(
            selectinload(Issue.assignee_links),
            selectinload(Issue.task_list),
        )
    )

    # Build the "anchored in range" predicate based on which sources are wanted.
    # pms_due: due_date IN [start, end), no start_date constraint.
    # pms_block: both start_date and due_date set, range overlaps.
    or_clauses = []
    if include_due:
        or_clauses.append(
            (Issue.due_date >= range_start) & (Issue.due_date < range_end)
        )
    if include_block:
        or_clauses.append(
            (Issue.start_date.is_not(None))
            & (Issue.due_date.is_not(None))
            & (Issue.start_date < range_end)
            & (Issue.due_date >= range_start)
        )
    if not or_clauses:
        return []
    stmt = stmt.where(or_(*or_clauses))

    issues = db.scalars(stmt).all()
    out: list[CalendarEventOut] = []
    for issue in issues:
        has_block = (
            issue.start_date is not None and issue.due_date is not None
        )
        is_block = include_block and has_block
        is_due = include_due and issue.due_date is not None and not is_block
        # Prefer block representation if the issue qualifies — gives the user a
        # time-range chip on the calendar instead of just a single-day marker.
        assignee_ids = [link.user_id for link in issue.assignee_links]
        if issue.assignee_id and issue.assignee_id not in assignee_ids:
            assignee_ids.append(issue.assignee_id)
        meta = CalendarEventMetadata(
            task_list_id=issue.list_id,
            task_list_key=issue.task_list.key if issue.task_list else None,
            issue_number=issue.issue_number,
            status=issue.status,
            assignee_ids=assignee_ids or None,
        )
        if is_block and issue.start_date and issue.due_date:
            # FullCalendar all-day end is exclusive — bump by one day so an
            # issue ending on 2026-04-20 visually fills 2026-04-20.
            from datetime import timedelta
            out.append(
                CalendarEventOut(
                    id=f"pms-block-{issue.id}",
                    title=f"{issue.task_list.key if issue.task_list else 'PMS'}-{issue.issue_number} {issue.title}",
                    start=issue.start_date.isoformat(),
                    end=(issue.due_date + timedelta(days=1)).isoformat(),
                    all_day=True,
                    source_type="pms_block",
                    source_id=issue.id,
                    color=_SOURCE_COLORS["pms_block"],
                    metadata=meta,
                )
            )
        elif is_due and issue.due_date is not None:
            from datetime import timedelta
            out.append(
                CalendarEventOut(
                    id=f"pms-due-{issue.id}",
                    title=f"{issue.task_list.key if issue.task_list else 'PMS'}-{issue.issue_number} {issue.title}",
                    start=issue.due_date.isoformat(),
                    end=(issue.due_date + timedelta(days=1)).isoformat(),
                    all_day=True,
                    source_type="pms_due",
                    source_id=issue.id,
                    color=_SOURCE_COLORS["pms_due"],
                    metadata=meta,
                )
            )
    return out


def _planner_events(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    from_at: datetime,
    to_at: datetime,
) -> list[CalendarEventOut]:
    events = db.scalars(
        select(PlannerEvent)
        .where(
            PlannerEvent.workspace_id == workspace.id,
            PlannerEvent.owner_id == user.id,
        )
        .where(PlannerEvent.end_at > from_at)
        .where(PlannerEvent.start_at < to_at)
        .options(selectinload(PlannerEvent.owner))
        .order_by(PlannerEvent.start_at.asc())
    ).all()
    out: list[CalendarEventOut] = []
    for event in events:
        if event.all_day:
            start = (
                event.start_at.replace(tzinfo=UTC)
                .astimezone(ZoneInfo("Asia/Seoul"))
                .date()
                .isoformat()
            )
            end = (
                event.end_at.replace(tzinfo=UTC)
                .astimezone(ZoneInfo("Asia/Seoul"))
                .date()
                .isoformat()
            )
        else:
            start = _utc_iso(event.start_at)
            end = _utc_iso(event.end_at)
        out.append(
            CalendarEventOut(
                id=f"planner-event-{event.id}",
                title=event.title,
                start=start,
                end=end,
                all_day=event.all_day,
                source_type="planner_event",
                source_id=event.id,
                color=_SOURCE_COLORS["planner_event"],
                metadata=CalendarEventMetadata(
                    planner_event_id=event.id,
                    owner_id=event.owner_id,
                    owner_name=event.owner.full_name if event.owner else None,
                    visibility=event.visibility,  # type: ignore[arg-type]
                    location=event.location or None,
                ),
            )
        )
    return out


def parse_iso_or_date(value: str) -> datetime:
    """Parse the from/to query parameter as either ISO date or datetime.

    Date-only inputs are treated as midnight UTC-naive (the SQL columns are
    naive). Offset-aware datetimes are normalized to naive UTC so SQL range
    comparisons stay consistent regardless of the driver's timezone handling.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        try:
            d = date.fromisoformat(value)
            return datetime.combine(d, time.min)
        except ValueError:
            raise exc
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed
