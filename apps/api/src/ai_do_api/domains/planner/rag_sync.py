from __future__ import annotations

from sqlalchemy.orm import Session

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.planner.models import PlannerEvent
from ai_do_api.domains.rag.contracts import RagSyncOperation
from ai_do_api.domains.rag.outbox import enqueue_rag_sync_job
from ai_do_api.domains.rag.planner_projection import PLANNER_EVENT_RESOURCE_TYPE
from ai_do_api.domains.search.hooks import enqueue_planner_event_search_index


def enqueue_planner_event_rag_sync(
    db: Session,
    *,
    event: PlannerEvent,
    operation: RagSyncOperation,
) -> None:
    enqueue_planner_event_search_index(
        db,
        event=event,
        operation="delete" if operation == RagSyncOperation.DELETE else "upsert",
    )
    if not get_settings().rag_enabled:
        return

    enqueue_rag_sync_job(
        db,
        workspace_id=event.workspace_id,
        resource_type=PLANNER_EVENT_RESOURCE_TYPE,
        resource_id=event.id,
        operation=operation,
    )
