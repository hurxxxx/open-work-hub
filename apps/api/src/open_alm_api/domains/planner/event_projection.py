from __future__ import annotations

from open_alm_api.domains.planner.event_time import serialize_event_bounds

from .models import PlannerEvent
from .schemas import PlannerEventOut


def project_planner_event(event: PlannerEvent) -> PlannerEventOut:
    start, end = serialize_event_bounds(
        all_day=event.all_day,
        start_at=event.start_at,
        end_at=event.end_at,
        start_has_time=event.start_has_time,
        end_has_time=event.end_has_time,
        time_zone=event.time_zone,
    )
    return PlannerEventOut(
        id=event.id,
        owner_id=event.owner_id,
        owner_name=event.owner.full_name if event.owner else event.owner_id,
        title=event.title,
        description=event.description,
        location=event.location,
        time_zone=event.time_zone,
        all_day=event.all_day,
        start_has_time=event.start_has_time,
        end_has_time=event.end_has_time,
        start=start,
        end=end,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def project_planner_event_for_ai(event_out: PlannerEventOut) -> dict[str, object]:
    return event_out.model_dump(mode="json", by_alias=True)


def project_deleted_planner_event(event_id: str) -> dict[str, object]:
    return {"id": event_id, "deleted": True}
