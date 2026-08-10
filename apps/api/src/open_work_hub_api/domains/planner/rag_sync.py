from __future__ import annotations

from sqlalchemy.orm import Session

from open_work_hub_api.domains.planner.models import PlannerEvent
from open_work_hub_api.domains.rag.contracts import RagSyncOperation


def enqueue_planner_event_rag_sync(
    db: Session,
    *,
    event: PlannerEvent,
    operation: RagSyncOperation,
) -> None:
    """Personal planner events are not projected into workspace search/RAG."""
    del db, event, operation
