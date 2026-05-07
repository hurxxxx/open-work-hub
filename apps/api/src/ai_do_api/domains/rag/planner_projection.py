from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ai_do_api.domains.planner.models import PlannerEvent
from ai_do_api.domains.rag.contracts import RagProjection
from ai_do_api.domains.rag.projection import build_projection


PLANNER_EVENT_RESOURCE_TYPE = "planner_event"
PLANNER_EVENT_SOURCE_KIND = "planner_event"


def load_planner_event_projection(
    db: Session,
    *,
    event_id: str,
) -> RagProjection | None:
    event = db.scalar(
        select(PlannerEvent)
        .options(selectinload(PlannerEvent.owner))
        .where(PlannerEvent.id == event_id)
    )
    if event is None:
        return None
    return build_planner_event_projection(event)


def build_planner_event_projection(event: PlannerEvent) -> RagProjection:
    schedule_text = _schedule_text(event)
    text_sections = [
        event.title.strip(),
        event.description.strip(),
        event.location.strip(),
        schedule_text,
    ]
    visibility_refs = [
        f"workspace:{event.workspace_id}",
        f"owner:{event.owner_id}",
    ]
    if event.visibility == "public":
        visibility_refs.append(f"workspace_public:{event.workspace_id}")

    return build_projection(
        workspace_id=event.workspace_id,
        resource_type=PLANNER_EVENT_RESOURCE_TYPE,
        resource_id=event.id,
        source_kind=PLANNER_EVENT_SOURCE_KIND,
        title=event.title,
        summary=_build_summary(event),
        text_content="\n\n".join(section for section in text_sections if section),
        owner_label=getattr(event.owner, "full_name", None),
        visibility_refs=sorted(visibility_refs),
        metadata={
            "visibility": event.visibility,
            "all_day": event.all_day,
            "location": event.location,
            "start_at": event.start_at.isoformat(),
            "end_at": event.end_at.isoformat(),
        },
    )


def _build_summary(event: PlannerEvent) -> str | None:
    parts = [event.description.strip(), event.location.strip(), _schedule_text(event)]
    summary = " | ".join(part for part in parts if part)
    return summary or event.title.strip() or None


def _schedule_text(event: PlannerEvent) -> str:
    if event.all_day:
        return f"all_day {event.start_at.date().isoformat()} {event.end_at.date().isoformat()}"
    return f"{event.start_at.isoformat()} {event.end_at.isoformat()}"
