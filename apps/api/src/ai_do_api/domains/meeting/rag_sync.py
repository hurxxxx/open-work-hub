from __future__ import annotations

from sqlalchemy.orm import Session

from ai_do_api.domains.meeting.models import Meeting
from ai_do_api.domains.rag.contracts import RagSyncOperation
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
