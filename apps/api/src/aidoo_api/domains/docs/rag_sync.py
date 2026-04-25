from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.docs.models import DocMeetingAccess, NativeDoc
from aidoo_api.domains.meeting.models import Meeting, MeetingDocLink
from aidoo_api.domains.rag.contracts import RagSyncOperation
from aidoo_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE
from aidoo_api.domains.rag.outbox import (
    enqueue_rag_sync_job,
    enqueue_rag_visibility_recompute_job,
)
from aidoo_api.domains.search.hooks import enqueue_doc_search_index, enqueue_doc_search_index_by_id


MEETING_VISIBILITY_SCOPE = "meeting"


def enqueue_native_doc_rag_sync(
    db: Session,
    *,
    doc: NativeDoc,
    operation: RagSyncOperation,
) -> None:
    enqueue_doc_search_index(
        db,
        doc=doc,
        operation=_search_operation(operation),
    )
    if not get_settings().rag_enabled:
        return

    enqueue_rag_sync_job(
        db,
        workspace_id=doc.workspace_id,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id=doc.id,
        operation=operation,
    )


def enqueue_native_doc_rag_sync_by_id(
    db: Session,
    *,
    doc_id: str,
    operation: RagSyncOperation,
) -> None:
    doc = db.scalar(
        select(NativeDoc).where(NativeDoc.id == doc_id)
    )
    if doc is None:
        return
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=operation,
    )


def collect_meeting_visibility_doc_ids(
    db: Session,
    *,
    meeting_id: str,
) -> list[str]:
    doc_ids = set(
        db.scalars(select(MeetingDocLink.doc_id).where(MeetingDocLink.meeting_id == meeting_id))
    )
    doc_ids.update(
        db.scalars(
            select(DocMeetingAccess.doc_id).where(
                DocMeetingAccess.granted_by_meeting_id == meeting_id
            )
        )
    )
    meeting = db.get(Meeting, meeting_id)
    if meeting is not None and meeting.notes_doc_id:
        doc_ids.add(meeting.notes_doc_id)
    return sorted(doc_id for doc_id in doc_ids if doc_id)


def enqueue_meeting_visibility_recompute(
    db: Session,
    *,
    workspace_id: str,
    meeting_id: str,
    doc_ids: list[str] | None = None,
) -> None:
    affected_doc_ids = collect_meeting_visibility_doc_ids(db, meeting_id=meeting_id) if doc_ids is None else doc_ids
    for doc_id in affected_doc_ids:
        enqueue_doc_search_index_by_id(
            db,
            doc_id=doc_id,
            operation="upsert",
        )
    if not get_settings().rag_enabled:
        return

    normalized_doc_ids = sorted({doc_id for doc_id in doc_ids or [] if doc_id})
    cursor = {"doc_ids": normalized_doc_ids} if normalized_doc_ids else None
    enqueue_rag_visibility_recompute_job(
        db,
        workspace_id=workspace_id,
        scope_type=MEETING_VISIBILITY_SCOPE,
        scope_id=meeting_id,
        cursor=cursor,
    )


def _search_operation(operation: RagSyncOperation) -> str:
    return "delete" if operation == RagSyncOperation.DELETE else "upsert"
