"""Calendar source catalog and source-specific event adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ai_do_api.domains.auth.access import (
    resolve_workspace_enabled_app_ids,
    resolve_workspaces,
)
from ai_do_api.domains.auth.models import Team, User
from ai_do_api.domains.meeting.models import Meeting, MeetingAttendee
from ai_do_api.domains.pms.models import Task, TaskAssignee, TaskList
from ai_do_api.domains.planner.models import PlannerEvent
from ai_do_api.domains.planner.event_time import local_date_string

from .schemas import CalendarEventOut, CalendarSourceType, CalendarWorkspaceRef
from .source_projection import (
    project_meeting_calendar_event,
    project_planner_calendar_event,
    project_pms_task_calendar_events,
)


DEFAULT_CALENDAR_SOURCES: tuple[CalendarSourceType, ...] = (
    "meeting",
    "pms_due",
    "pms_block",
    "planner_event",
)
DEFAULT_CALENDAR_SOURCES_PARAM = ",".join(DEFAULT_CALENDAR_SOURCES)
VALID_CALENDAR_SOURCES = frozenset(DEFAULT_CALENDAR_SOURCES)


@dataclass(frozen=True, slots=True)
class CalendarSourceContext:
    db: Session
    user: User
    from_at: datetime
    to_at: datetime
    workspaces_by_id: dict[str, CalendarWorkspaceRef]
    enabled_workspace_ids_by_app: dict[str, frozenset[str]]

    def workspace_ids_for(self, app_id: str) -> frozenset[str]:
        return self.enabled_workspace_ids_by_app.get(app_id, frozenset())


class CalendarSourceAdapter(Protocol):
    source_types: tuple[CalendarSourceType, ...]

    def collect(
        self,
        context: CalendarSourceContext,
        *,
        requested_sources: set[CalendarSourceType],
    ) -> list[CalendarEventOut]: ...


class MeetingCalendarSource:
    source_types: tuple[CalendarSourceType, ...] = ("meeting",)

    def collect(
        self,
        context: CalendarSourceContext,
        *,
        requested_sources: set[CalendarSourceType],
    ) -> list[CalendarEventOut]:
        workspace_ids = context.workspace_ids_for("meeting")
        if "meeting" not in requested_sources or not workspace_ids:
            return []
        attendee_meeting_ids = select(MeetingAttendee.meeting_id).where(
            MeetingAttendee.user_id == context.user.id
        )
        meetings = context.db.scalars(
            select(Meeting)
            .where(Meeting.workspace_id.in_(workspace_ids))
            .where(
                or_(
                    Meeting.organizer_id == context.user.id,
                    Meeting.id.in_(attendee_meeting_ids),
                )
            )
            .where(Meeting.end_at > context.from_at)
            .where(Meeting.start_at < context.to_at)
            .options(selectinload(Meeting.attendees))
            .order_by(Meeting.start_at.asc())
        ).all()
        return [
            project_meeting_calendar_event(
                meeting,
                workspace=context.workspaces_by_id[meeting.workspace_id],
            )
            for meeting in meetings
        ]


class PmsTaskCalendarSource:
    source_types: tuple[CalendarSourceType, ...] = ("pms_due", "pms_block")

    def collect(
        self,
        context: CalendarSourceContext,
        *,
        requested_sources: set[CalendarSourceType],
    ) -> list[CalendarEventOut]:
        include_due = "pms_due" in requested_sources
        include_block = "pms_block" in requested_sources
        workspace_ids = context.workspace_ids_for("pms")
        if (not include_due and not include_block) or not workspace_ids:
            return []

        range_start = date.fromisoformat(local_date_string(context.from_at, context.user.time_zone))
        range_end = date.fromisoformat(local_date_string(context.to_at, context.user.time_zone))
        multi_assignee_subq = select(TaskAssignee.task_id).where(
            TaskAssignee.user_id == context.user.id
        )
        stmt = (
            select(Task, Team.workspace_id)
            .join(TaskList, TaskList.id == Task.list_id)
            .join(Team, Team.id == TaskList.team_id)
            .where(Team.workspace_id.in_(workspace_ids))
            .where(Task.archived.is_(False))
            .where(TaskList.archived.is_(False))
            .where(
                or_(
                    Task.assignee_id == context.user.id,
                    Task.id.in_(multi_assignee_subq),
                )
            )
            .options(
                selectinload(Task.assignee_links),
                selectinload(Task.task_list),
            )
        )
        or_clauses = []
        if include_due:
            or_clauses.append((Task.due_date >= range_start) & (Task.due_date < range_end))
        if include_block:
            or_clauses.append(
                (Task.start_date.is_not(None))
                & (Task.due_date.is_not(None))
                & (Task.start_date < range_end)
                & (Task.due_date >= range_start)
            )
        rows = context.db.execute(stmt.where(or_(*or_clauses))).all()
        return [
            event
            for task, workspace_id in rows
            for event in project_pms_task_calendar_events(
                task,
                include_due=include_due,
                include_block=include_block,
                workspace=context.workspaces_by_id[workspace_id],
            )
        ]


class PlannerCalendarSource:
    source_types: tuple[CalendarSourceType, ...] = ("planner_event",)

    def collect(
        self,
        context: CalendarSourceContext,
        *,
        requested_sources: set[CalendarSourceType],
    ) -> list[CalendarEventOut]:
        if "planner_event" not in requested_sources:
            return []
        events = context.db.scalars(
            select(PlannerEvent)
            .where(PlannerEvent.owner_id == context.user.id)
            .where(PlannerEvent.end_at > context.from_at)
            .where(PlannerEvent.start_at < context.to_at)
            .options(selectinload(PlannerEvent.owner))
            .order_by(PlannerEvent.start_at.asc())
        ).all()
        return [project_planner_calendar_event(event) for event in events]


CALENDAR_SOURCE_ADAPTERS: tuple[CalendarSourceAdapter, ...] = (
    MeetingCalendarSource(),
    PmsTaskCalendarSource(),
    PlannerCalendarSource(),
)


def _calendar_workspace_context(
    db: Session,
    *,
    user: User,
) -> tuple[
    dict[str, CalendarWorkspaceRef],
    dict[str, frozenset[str]],
]:
    accessible = resolve_workspaces(db, user)
    workspaces_by_id = {
        item["id"]: CalendarWorkspaceRef(id=item["id"], slug=item["slug"], name=item["name"])
        for item in accessible
    }
    enabled_by_app: dict[str, set[str]] = {"meeting": set(), "pms": set()}
    for workspace_id in workspaces_by_id:
        enabled_app_ids = set(resolve_workspace_enabled_app_ids(db, workspace_id))
        for app_id in enabled_by_app:
            if app_id in enabled_app_ids:
                enabled_by_app[app_id].add(workspace_id)
    return workspaces_by_id, {
        app_id: frozenset(workspace_ids) for app_id, workspace_ids in enabled_by_app.items()
    }


def collect_calendar_source_events(
    *,
    db: Session,
    user: User,
    from_at: datetime,
    to_at: datetime,
    sources: Iterable[CalendarSourceType],
) -> list[CalendarEventOut]:
    requested_sources = set(sources)
    workspaces_by_id, enabled_workspace_ids_by_app = _calendar_workspace_context(db, user=user)
    context = CalendarSourceContext(
        db=db,
        user=user,
        from_at=from_at,
        to_at=to_at,
        workspaces_by_id=workspaces_by_id,
        enabled_workspace_ids_by_app=enabled_workspace_ids_by_app,
    )
    return [
        event
        for adapter in CALENDAR_SOURCE_ADAPTERS
        for event in adapter.collect(context, requested_sources=requested_sources)
    ]
