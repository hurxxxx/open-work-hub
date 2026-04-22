from __future__ import annotations

from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.planner.models import PlannerEvent
from aidoo_api.domains.rag.contracts import RagSyncOperation
from aidoo_api.domains.rag.outbox import enqueue_rag_sync_job
from aidoo_api.domains.rag.planner_projection import PLANNER_EVENT_RESOURCE_TYPE


def enqueue_planner_event_rag_sync(
    db: Session,
    *,
    event: PlannerEvent,
    operation: RagSyncOperation,
) -> None:
    if not get_settings().rag_enabled:
        return

    enqueue_rag_sync_job(
        db,
        workspace_id=event.workspace_id,
        resource_type=PLANNER_EVENT_RESOURCE_TYPE,
        resource_id=event.id,
        operation=operation,
    )
