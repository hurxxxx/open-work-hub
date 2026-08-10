from __future__ import annotations

from datetime import date, timedelta

from open_work_hub_api.domains.planner.event_time import local_date_string, utc_iso

from .schemas import (
    CalendarEventMetadata,
    CalendarEventOut,
    CalendarSourceType,
    CalendarWorkspaceRef,
)


# Hex color tokens duplicated from the frontend ``CALENDAR_SOURCE_COLORS`` map.
# Backend is the single source of truth for the wire format; the frontend uses
# whatever value comes back. Pms_block ideally inherits from status color, but
# for now we ship the same green default and let the polish phase improve it.
SOURCE_COLORS: dict[CalendarSourceType, str] = {
    "meeting": "#3b82f6",  # blue-500
    "pms_due": "#f59e0b",  # amber-500
    "pms_block": "#22c55e",  # green-500
    "planner_event": "#14b8a6",  # teal-500
}


def project_meeting_calendar_event(meeting, *, workspace: CalendarWorkspaceRef) -> CalendarEventOut:
    return CalendarEventOut(
        id=f"meeting-{meeting.id}",
        title=meeting.title,
        start=utc_iso(meeting.start_at),
        end=utc_iso(meeting.end_at),
        all_day=False,
        source_type="meeting",
        source_id=meeting.id,
        color=SOURCE_COLORS["meeting"],
        workspace=workspace,
        metadata=CalendarEventMetadata(
            meeting_id=meeting.id,
            attendee_count=len(meeting.attendees),
        ),
    )


def project_pms_task_calendar_events(
    task,
    *,
    include_due: bool,
    include_block: bool,
    workspace: CalendarWorkspaceRef,
) -> list[CalendarEventOut]:
    has_block = task.start_date is not None and task.due_date is not None
    is_block = include_block and has_block
    is_due = include_due and task.due_date is not None and not is_block
    assignee_ids = [link.user_id for link in task.assignee_links]
    if task.assignee_id and task.assignee_id not in assignee_ids:
        assignee_ids.append(task.assignee_id)
    meta = CalendarEventMetadata(
        task_list_id=task.list_id,
        task_list_key=task.task_list.key if task.task_list else None,
        task_number=task.task_number,
        status=task.status,
        assignee_ids=assignee_ids or None,
    )
    if is_block and task.start_date and task.due_date:
        return [
            CalendarEventOut(
                id=f"pms-block-{task.id}",
                title=_pms_task_title(task),
                start=task.start_date.isoformat(),
                end=(task.due_date + timedelta(days=1)).isoformat(),
                all_day=True,
                source_type="pms_block",
                source_id=task.id,
                color=SOURCE_COLORS["pms_block"],
                workspace=workspace,
                metadata=meta,
            )
        ]
    if is_due and task.due_date is not None:
        return [
            CalendarEventOut(
                id=f"pms-due-{task.id}",
                title=_pms_task_title(task),
                start=task.due_date.isoformat(),
                end=(task.due_date + timedelta(days=1)).isoformat(),
                all_day=True,
                source_type="pms_due",
                source_id=task.id,
                color=SOURCE_COLORS["pms_due"],
                workspace=workspace,
                metadata=meta,
            )
        ]
    return []


def _add_date_string_days(value: str, days: int) -> str:
    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()


def _project_planner_event_render_bounds(event) -> tuple[str, str, bool]:
    if event.all_day:
        return (
            local_date_string(event.start_at, event.time_zone),
            local_date_string(event.end_at, event.time_zone),
            True,
        )
    if event.start_has_time and event.end_has_time:
        return utc_iso(event.start_at), utc_iso(event.end_at), False
    if event.start_has_time:
        marker_end = min(event.end_at, event.start_at + timedelta(minutes=30))
        if marker_end <= event.start_at:
            marker_end = event.start_at + timedelta(minutes=30)
        return utc_iso(event.start_at), utc_iso(marker_end), False
    if event.end_has_time:
        marker_start = max(event.start_at, event.end_at - timedelta(minutes=30))
        if marker_start >= event.end_at:
            marker_start = event.end_at - timedelta(minutes=30)
        return utc_iso(marker_start), utc_iso(event.end_at), False

    start = local_date_string(event.start_at, event.time_zone)
    end = _add_date_string_days(local_date_string(event.end_at, event.time_zone), 1)
    return start, end, True


def project_planner_calendar_event(event) -> CalendarEventOut:
    start, end, calendar_all_day = _project_planner_event_render_bounds(event)
    return CalendarEventOut(
        id=f"planner-event-{event.id}",
        title=event.title,
        start=start,
        end=end,
        all_day=calendar_all_day,
        source_type="planner_event",
        source_id=event.id,
        color=SOURCE_COLORS["planner_event"],
        workspace=None,
        metadata=CalendarEventMetadata(
            planner_event_id=event.id,
            owner_id=event.owner_id,
            owner_name=event.owner.full_name if event.owner else None,
            location=event.location or None,
            planner_all_day=event.all_day,
            planner_start_has_time=event.start_has_time,
            planner_end_has_time=event.end_has_time,
            planner_time_zone=event.time_zone,
        ),
    )


def _pms_task_title(task) -> str:
    task_list_key = task.task_list.key if task.task_list else "PMS"
    return f"{task_list_key}-{task.task_number} {task.title}"
