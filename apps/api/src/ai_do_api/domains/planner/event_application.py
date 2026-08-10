from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import status

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.planner.event_time import parse_event_bounds, serialize_event_bounds
from ai_do_api.domains.planner.models import PlannerEvent
from ai_do_api.domains.rag.contracts import RagSyncOperation


@dataclass(frozen=True)
class PlannerEventCreateCommand:
    title: str
    description: str
    location: str
    all_day: bool
    start: str
    end: str
    time_zone: str
    event_id: str | None = None


@dataclass(frozen=True)
class PlannerEventUpdateCommand:
    title: str | None = None
    description: str | None = None
    location: str | None = None
    all_day: bool | None = None
    start: str | None = None
    end: str | None = None


def new_planner_event(
    *,
    owner_id: str,
    command: PlannerEventCreateCommand,
    id_factory: Callable[[], str],
) -> PlannerEvent:
    bounds = parse_event_bounds(
        all_day=command.all_day,
        start=command.start,
        end=command.end,
        time_zone=command.time_zone,
    )
    return PlannerEvent(
        id=command.event_id or id_factory(),
        owner_id=owner_id,
        title=command.title.strip(),
        description=command.description.strip(),
        location=command.location.strip(),
        time_zone=command.time_zone,
        all_day=command.all_day,
        start_has_time=bounds.start_has_time,
        end_has_time=bounds.end_has_time,
        start_at=bounds.start_at,
        end_at=bounds.end_at,
    )


def apply_planner_event_update(
    event: PlannerEvent,
    command: PlannerEventUpdateCommand,
) -> RagSyncOperation | None:
    operation: RagSyncOperation | None = None

    next_all_day = command.all_day if command.all_day is not None else event.all_day
    next_start = command.start
    next_end = command.end
    if (next_start is None) != (next_end is None):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="planner.update_start_end_required",
        )
    if command.all_day is not None and next_start is None:
        next_start, next_end = serialize_event_bounds(
            all_day=next_all_day,
            start_at=event.start_at,
            end_at=event.end_at,
            start_has_time=event.start_has_time,
            end_has_time=event.end_has_time,
            time_zone=event.time_zone,
        )
    if next_start is not None and next_end is not None:
        bounds = parse_event_bounds(
            all_day=next_all_day,
            start=next_start,
            end=next_end,
            time_zone=event.time_zone,
        )
        event.start_at = bounds.start_at
        event.end_at = bounds.end_at
        event.start_has_time = bounds.start_has_time
        event.end_has_time = bounds.end_has_time
        operation = RagSyncOperation.UPSERT
    event.all_day = next_all_day
    if command.all_day is not None:
        operation = RagSyncOperation.UPSERT

    if command.title is not None:
        event.title = command.title.strip()
        operation = RagSyncOperation.UPSERT
    if command.description is not None:
        event.description = command.description.strip()
        operation = RagSyncOperation.UPSERT
    if command.location is not None:
        event.location = command.location.strip()
        operation = RagSyncOperation.UPSERT
    return operation
