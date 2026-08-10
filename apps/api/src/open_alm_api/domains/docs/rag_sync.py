from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.settings import get_settings
from open_alm_api.domains.docs.models import DocMeetingAccess, NativeDoc
from open_alm_api.domains.docs.partitioning import ensure_native_doc_partition
from open_alm_api.domains.meeting.models import Meeting, MeetingDocLink
from open_alm_api.domains.rag.contracts import RagSyncOperation
from open_alm_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE
from open_alm_api.domains.rag.outbox import (
    enqueue_rag_sync_job,
    enqueue_rag_visibility_recompute_job,
)
from open_alm_api.domains.retrieval.projection_fencing import record_projection_event
from open_alm_api.domains.search.hooks import enqueue_doc_search_index, enqueue_doc_search_index_by_id


MEETING_VISIBILITY_SCOPE = "meeting"


@dataclass(frozen=True, slots=True)
class _MeetingVisibilityTargets:
    search_doc_ids: list[str]
    cursor_doc_ids: list[str]


def enqueue_native_doc_rag_sync(
    db: Session,
    *,
    doc: NativeDoc,
    operation: RagSyncOperation,
) -> None:
    partition_id = ensure_native_doc_partition(db, doc=doc)
    projection_event = record_projection_event(
        db,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id=doc.id,
        retrieval_partition_id=partition_id,
        change_kind=("delete" if operation == RagSyncOperation.DELETE else "content"),
        desired_state=("deleted" if operation == RagSyncOperation.DELETE else "active"),
        diagnostic_workspace_id=doc.workspace_id,
    )
    enqueue_doc_search_index(
        db,
        doc=doc,
        operation=_search_operation(operation),
        projection_event=projection_event,
    )
    if not get_settings().rag_enabled:
        return

    enqueue_rag_sync_job(
        db,
        workspace_id=doc.workspace_id,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id=doc.id,
        operation=operation,
        projection_event=projection_event,
    )


def enqueue_native_doc_rag_sync_by_id(
    db: Session,
    *,
    doc_id: str,
    operation: RagSyncOperation,
) -> None:
    doc = db.scalar(select(NativeDoc).where(NativeDoc.id == doc_id))
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
    cursor: dict | None = None,
) -> list[str]:
    doc_ids = {str(doc_id) for doc_id in (cursor or {}).get("doc_ids", []) if doc_id}
    doc_ids.update(
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
    targets = _meeting_visibility_targets(db, meeting_id=meeting_id, doc_ids=doc_ids)
    for doc_id in targets.search_doc_ids:
        enqueue_doc_search_index_by_id(
            db,
            doc_id=doc_id,
            operation="upsert",
        )
    if not get_settings().rag_enabled:
        return

    cursor = {"doc_ids": targets.cursor_doc_ids} if targets.cursor_doc_ids else None
    enqueue_rag_visibility_recompute_job(
        db,
        workspace_id=workspace_id,
        scope_type=MEETING_VISIBILITY_SCOPE,
        scope_id=meeting_id,
        cursor=cursor,
    )


def _meeting_visibility_targets(
    db: Session,
    *,
    meeting_id: str,
    doc_ids: list[str] | None,
) -> _MeetingVisibilityTargets:
    if doc_ids is None:
        return _MeetingVisibilityTargets(
            search_doc_ids=collect_meeting_visibility_doc_ids(db, meeting_id=meeting_id),
            cursor_doc_ids=[],
        )
    return _MeetingVisibilityTargets(
        search_doc_ids=doc_ids,
        cursor_doc_ids=_normalize_doc_ids(doc_ids),
    )


def _normalize_doc_ids(doc_ids: list[str]) -> list[str]:
    return sorted({doc_id for doc_id in doc_ids if doc_id})


def _search_operation(operation: RagSyncOperation) -> str:
    return "delete" if operation == RagSyncOperation.DELETE else "upsert"
