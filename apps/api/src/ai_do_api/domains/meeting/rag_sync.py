from __future__ import annotations

from sqlalchemy.orm import Session

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.meeting.models import Meeting
from ai_do_api.domains.rag.contracts import RagSyncOperation
from ai_do_api.domains.rag.meeting_projection import MEETING_RESOURCE_TYPE
from ai_do_api.domains.rag.outbox import enqueue_rag_sync_job
from ai_do_api.domains.search.hooks import enqueue_meeting_search_index


def enqueue_meeting_rag_sync(
    db: Session,
    *,
    meeting: Meeting,
    operation: RagSyncOperation,
) -> None:
    enqueue_meeting_search_index(
        db,
        meeting=meeting,
        operation="delete" if operation == RagSyncOperation.DELETE else "upsert",
    )
    if not get_settings().rag_enabled:
        return
    enqueue_rag_sync_job(
        db,
        workspace_id=meeting.workspace_id,
        resource_type=MEETING_RESOURCE_TYPE,
        resource_id=meeting.id,
        operation=operation,
    )


def enqueue_meeting_rag_sync_by_id(
    db: Session,
    *,
    meeting_id: str,
    operation: RagSyncOperation,
) -> None:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        return
    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=operation,
    )
