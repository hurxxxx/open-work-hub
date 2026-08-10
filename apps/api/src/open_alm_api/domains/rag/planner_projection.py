from __future__ import annotations

from sqlalchemy.orm import Session

from open_alm_api.domains.planner.models import PlannerEvent
from open_alm_api.domains.rag.contracts import RagProjection


PLANNER_EVENT_SOURCE_KIND = "planner_event"


def load_planner_event_projection(
    db: Session,
    *,
    event_id: str,
) -> RagProjection | None:
    del db, event_id
    return None


def build_planner_event_projection(event: PlannerEvent) -> RagProjection:
    del event
    raise ValueError("Personal planner events are not workspace RAG resources")
