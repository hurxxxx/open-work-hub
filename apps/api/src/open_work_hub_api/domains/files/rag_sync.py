from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.files.models import FileManagerCorpus, FileManagerFile
from open_work_hub_api.domains.files.rag_projection import (
    mark_file_extraction_failed,
    purge_deleted_file_retrieval_artifact,
)
from open_work_hub_api.domains.files.retrieval_contract import FILES_RETRIEVAL_ACTIVE
from open_work_hub_api.domains.files.search_hooks import (
    enqueue_file_search_index_by_id,
    stage_file_search_reconciliation_job,
)
from open_work_hub_api.domains.rag.contracts import RagScopeKind, RagSyncOperation
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.rag.outbox import enqueue_rag_sync_job
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalPartitionState,
    RetrievalProjectionChangeKind,
    RetrievalProjectionDesiredState,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.retrieval.partitioning import assign_default_partition
from open_work_hub_api.domains.retrieval.projection_fencing import (
    ProjectionEventRef,
    record_projection_event,
)
from open_work_hub_api.domains.search.models import SearchIndexJob
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


@dataclass(frozen=True, slots=True)
class _FileProjectionEnvelope:
    retrieval_partition_id: str
    scope_kind: RagScopeKind


@dataclass(frozen=True, slots=True)
class FileRetrievalReconciliationBatch:
    target_event_sequence: int
    next_event_sequence: int
    scanned_events: int
    staged_resources: int
    complete: bool


@dataclass(frozen=True, slots=True)
class FileRetrievalReconciliationStatus:
    target_event_sequence: int
    current_event_sequence: int
    keyword_remaining: int
    vector_remaining: int
    caught_up: bool


@dataclass(frozen=True, slots=True)
class LegacyFileRetrievalAdoptionBatch:
    next_file_id: str | None
    scanned_files: int
    recorded_events: int
    complete: bool
    event_watermark: int


def enqueue_file_retrieval_sync(
    db: Session,
    *,
    file: FileManagerFile,
    operation: RagSyncOperation,
) -> None:
    envelope = _resolve_file_projection_envelope(db, file=file)
    projection_event = record_projection_event(
        db,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id=file.id,
        retrieval_partition_id=envelope.retrieval_partition_id,
        change_kind=(
            RetrievalProjectionChangeKind.DELETE
            if operation == RagSyncOperation.DELETE
            else (
                RetrievalProjectionChangeKind.VISIBILITY
                if operation == RagSyncOperation.VISIBILITY_UPDATE
                else RetrievalProjectionChangeKind.CONTENT
            )
        ),
        desired_state=(
            RetrievalProjectionDesiredState.DELETED
            if operation == RagSyncOperation.DELETE
            else RetrievalProjectionDesiredState.ACTIVE
        ),
        content_checksum=file.extraction_content_checksum,
    )
    if not FILES_RETRIEVAL_ACTIVE:
        return
    if operation == RagSyncOperation.DELETE:
        enqueue_file_search_index_by_id(
            db,
            file_id=file.id,
            operation="delete",
            projection_event=projection_event,
        )
    if not get_settings().rag_enabled:
        return
    enqueue_rag_sync_job(
        db,
        scope_kind=envelope.scope_kind,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id=file.id,
        operation=operation,
        projection_event=projection_event,
    )


def capture_file_retrieval_event_watermark(db: Session) -> int:
    """Capture the durable Files source watermark used by staged reconciliation."""
    return int(
        db.scalar(
            select(func.max(RetrievalProjectionEvent.event_sequence)).where(
                RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE
            )
        )
        or 0
    )


def adopt_legacy_file_retrieval_heads(
    db: Session,
    *,
    after_file_id: str | None,
    limit: int = 500,
) -> LegacyFileRetrievalAdoptionBatch:
    """Adopt pre-fencing Files rows as repair heads without scheduling backend work."""
    batch_limit = int(limit)
    if batch_limit < 1 or batch_limit > 1_000:
        raise ValueError("limit must be between 1 and 1000")
    cursor = str(after_file_id or "").strip() or None
    missing_head = ~exists(
        select(RetrievalProjectionHead.resource_id).where(
            RetrievalProjectionHead.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
            RetrievalProjectionHead.resource_id == FileManagerFile.id,
        )
    )
    statement = select(FileManagerFile).where(missing_head)
    if cursor is not None:
        statement = statement.where(FileManagerFile.id > cursor)
    candidates = list(
        db.scalars(
            statement.order_by(FileManagerFile.id.asc())
            .limit(batch_limit + 1)
            .with_for_update(skip_locked=True)
        )
    )
    has_more = len(candidates) > batch_limit
    files = candidates[:batch_limit]
    for file in files:
        envelope = _resolve_file_projection_envelope(db, file=file)
        desired_state, content_checksum = _legacy_file_adoption_projection(file)
        record_projection_event(
            db,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id=file.id,
            retrieval_partition_id=envelope.retrieval_partition_id,
            change_kind=RetrievalProjectionChangeKind.REPAIR,
            desired_state=desired_state,
            content_checksum=content_checksum,
            trace_context={"reconciliation": "legacy_files_adoption"},
        )

    return LegacyFileRetrievalAdoptionBatch(
        next_file_id=files[-1].id if files else cursor,
        scanned_files=len(files),
        recorded_events=len(files),
        complete=not has_more,
        event_watermark=capture_file_retrieval_event_watermark(db),
    )


def stage_file_retrieval_reconciliation(
    db: Session,
    *,
    after_event_sequence: int,
    through_event_sequence: int,
    limit: int = 500,
) -> FileRetrievalReconciliationBatch:
    """Stage current Files heads through an explicit, stable event watermark.

    This is the operator-only bridge between a disabled producer gate and
    reactivation. Normal source mutations never bypass the gate; reconciliation
    may stage fenced jobs while workers remain paused so no event is lost.
    """
    after = int(after_event_sequence)
    target = int(through_event_sequence)
    batch_limit = int(limit)
    if after < 0:
        raise ValueError("after_event_sequence must be non-negative")
    if target < after:
        raise ValueError("through_event_sequence must not precede after_event_sequence")
    if batch_limit < 1 or batch_limit > 1_000:
        raise ValueError("limit must be between 1 and 1000")
    current_watermark = capture_file_retrieval_event_watermark(db)
    if target > current_watermark:
        raise ValueError("through_event_sequence exceeds the persisted Files watermark")

    candidates = list(
        db.scalars(
            select(RetrievalProjectionEvent)
            .where(
                RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                RetrievalProjectionEvent.event_sequence > after,
                RetrievalProjectionEvent.event_sequence <= target,
            )
            .order_by(RetrievalProjectionEvent.event_sequence.asc())
            .limit(batch_limit + 1)
        )
    )
    has_more = len(candidates) > batch_limit
    events = candidates[:batch_limit]
    if not events:
        return FileRetrievalReconciliationBatch(
            target_event_sequence=target,
            next_event_sequence=target,
            scanned_events=0,
            staged_resources=0,
            complete=True,
        )

    resource_ids = tuple(dict.fromkeys(event.resource_id for event in events))
    heads = {
        head.resource_id: head
        for head in db.scalars(
            select(RetrievalProjectionHead).where(
                RetrievalProjectionHead.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                RetrievalProjectionHead.resource_id.in_(resource_ids),
            )
        )
    }
    staged = 0
    for event in events:
        head = heads.get(event.resource_id)
        if not _projection_event_is_current_head(event=event, head=head):
            continue
        projection_event = _projection_event_ref(event)
        envelope = _resolve_reconciliation_envelope(
            db,
            projection_event=projection_event,
        )
        stage_file_search_reconciliation_job(
            db,
            projection_event=projection_event,
        )
        enqueue_rag_sync_job(
            db,
            scope_kind=envelope.scope_kind,
            resource_type=projection_event.resource_type,
            resource_id=projection_event.resource_id,
            operation=_reconciliation_rag_operation(projection_event),
            projection_event=projection_event,
        )
        staged += 1

    return FileRetrievalReconciliationBatch(
        target_event_sequence=target,
        next_event_sequence=int(events[-1].event_sequence),
        scanned_events=len(events),
        staged_resources=staged,
        complete=not has_more,
    )


def inspect_file_retrieval_reconciliation(
    db: Session,
    *,
    through_event_sequence: int,
) -> FileRetrievalReconciliationStatus:
    """Check that current Files heads reached both projection backends at one watermark."""
    target = int(through_event_sequence)
    if target < 0:
        raise ValueError("through_event_sequence must be non-negative")
    current = capture_file_retrieval_event_watermark(db)
    if target > current:
        raise ValueError("through_event_sequence exceeds the persisted Files watermark")

    current_events = (
        select(
            RetrievalProjectionEvent.event_sequence.label("event_sequence"),
            RetrievalProjectionEvent.resource_type.label("resource_type"),
            RetrievalProjectionEvent.resource_id.label("resource_id"),
            RetrievalProjectionEvent.projection_version.label("projection_version"),
        )
        .join(
            RetrievalProjectionHead,
            and_(
                RetrievalProjectionHead.resource_type == RetrievalProjectionEvent.resource_type,
                RetrievalProjectionHead.resource_id == RetrievalProjectionEvent.resource_id,
                RetrievalProjectionHead.projection_version
                == RetrievalProjectionEvent.projection_version,
                RetrievalProjectionHead.retrieval_partition_id
                == RetrievalProjectionEvent.retrieval_partition_id,
                RetrievalProjectionHead.desired_state == RetrievalProjectionEvent.desired_state,
            ),
        )
        .where(RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE)
        .subquery()
    )
    keyword_succeeded = exists(
        select(SearchIndexJob.id).where(
            SearchIndexJob.resource_type == current_events.c.resource_type,
            SearchIndexJob.entity_id == current_events.c.resource_id,
            SearchIndexJob.projection_event_sequence == current_events.c.event_sequence,
            SearchIndexJob.projection_version == current_events.c.projection_version,
            SearchIndexJob.status == "succeeded",
        )
    )
    vector_succeeded = exists(
        select(RagSyncJob.id).where(
            RagSyncJob.resource_type == current_events.c.resource_type,
            RagSyncJob.resource_id == current_events.c.resource_id,
            RagSyncJob.projection_event_sequence == current_events.c.event_sequence,
            RagSyncJob.projection_version == current_events.c.projection_version,
            RagSyncJob.status == "succeeded",
        )
    )
    keyword_remaining = int(
        db.scalar(select(func.count()).select_from(current_events).where(~keyword_succeeded)) or 0
    )
    vector_remaining = int(
        db.scalar(select(func.count()).select_from(current_events).where(~vector_succeeded)) or 0
    )
    return FileRetrievalReconciliationStatus(
        target_event_sequence=target,
        current_event_sequence=current,
        keyword_remaining=keyword_remaining,
        vector_remaining=vector_remaining,
        caught_up=(current == target and keyword_remaining == 0 and vector_remaining == 0),
    )


def mark_file_projection_prepared(
    db: Session,
    *,
    file_id: str,
    projection_event: ProjectionEventRef | None = None,
) -> None:
    if projection_event is not None:
        if projection_event.resource_id != file_id:
            raise ValueError("Files prepared projection event does not match file_id")
        file = db.get(FileManagerFile, file_id, populate_existing=True)
        if file is None:
            return
        if projection_event.content_checksum != file.extraction_content_checksum:
            enqueue_file_retrieval_sync(
                db,
                file=file,
                operation=RagSyncOperation.UPSERT,
            )
            return
    event_kwargs = {"projection_event": projection_event} if projection_event is not None else {}
    enqueue_file_search_index_by_id(
        db,
        file_id=file_id,
        operation="upsert",
        **event_kwargs,
    )


def mark_file_projection_deleted(db: Session, *, file_id: str) -> None:
    purge_deleted_file_retrieval_artifact(db, file_id=file_id)


def mark_file_projection_failed(
    db: Session,
    *,
    file_id: str,
    error: str,
    phase: str,
) -> None:
    if phase not in {"extraction", "ocr", "parser"}:
        return
    normalized_error = " ".join(str(error).split())
    error_code = f"{phase}:{normalized_error}" if normalized_error else phase
    mark_file_extraction_failed(db, file_id=file_id, error_code=error_code)


def _resolve_file_projection_envelope(
    db: Session, *, file: FileManagerFile
) -> _FileProjectionEnvelope:
    if file.corpus_id is None:
        assign_default_partition(
            db, target=file, source_namespace="files", candidate_scope_kind="company"
        )
        return _FileProjectionEnvelope(
            retrieval_partition_id=str(file.retrieval_partition_id), scope_kind=RagScopeKind.COMPANY
        )
    corpus = db.get(FileManagerCorpus, file.corpus_id)
    if corpus is None or file.retrieval_partition_id != corpus.retrieval_partition_id:
        raise ValueError("File partition does not match its corpus")
    partition = db.get(RetrievalPartition, corpus.retrieval_partition_id)
    if (
        partition is None
        or partition.source_namespace != "files"
        or partition.is_default_ingest
        or partition.state != RetrievalPartitionState.ACTIVE.value
        or partition.candidate_scope_kind != "company"
        or partition.candidate_user_id is not None
        or partition.metadata_version != corpus.metadata_version
    ):
        raise ValueError("File corpus partition metadata does not match its source")
    return _FileProjectionEnvelope(
        retrieval_partition_id=partition.id, scope_kind=RagScopeKind.COMPANY
    )


def _projection_event_is_current_head(
    *,
    event: RetrievalProjectionEvent,
    head: RetrievalProjectionHead | None,
) -> bool:
    return bool(
        head is not None
        and head.projection_version == event.projection_version
        and head.retrieval_partition_id == event.retrieval_partition_id
        and head.desired_state == event.desired_state
    )


def _legacy_file_adoption_projection(
    file: FileManagerFile,
) -> tuple[RetrievalProjectionDesiredState, str | None]:
    if file.deleted_at is not None or file.extraction_status == "unsupported":
        return RetrievalProjectionDesiredState.DELETED, None
    if file.extraction_status != "ready" or not file.extraction_content_checksum:
        raise ValueError("Legacy Files source is not ready for retrieval adoption")
    return RetrievalProjectionDesiredState.ACTIVE, file.extraction_content_checksum


def _projection_event_ref(event: RetrievalProjectionEvent) -> ProjectionEventRef:
    return ProjectionEventRef(
        event_sequence=int(event.event_sequence),
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        projection_version=int(event.projection_version),
        retrieval_partition_id=str(event.retrieval_partition_id),
        change_kind=event.change_kind,
        desired_state=event.desired_state,
        content_checksum=event.content_checksum,
        visibility_checksum=event.visibility_checksum,
    )


def _resolve_reconciliation_envelope(
    db: Session, *, projection_event: ProjectionEventRef
) -> _FileProjectionEnvelope:
    file = db.get(FileManagerFile, projection_event.resource_id, populate_existing=True)
    if file is not None:
        envelope = _resolve_file_projection_envelope(db, file=file)
        if envelope.retrieval_partition_id != projection_event.retrieval_partition_id:
            raise ValueError("Files reconciliation source partition does not match its event")
        return envelope
    partition = db.get(RetrievalPartition, projection_event.retrieval_partition_id)
    if (
        partition is None
        or partition.source_namespace != "files"
        or partition.state != RetrievalPartitionState.ACTIVE.value
        or partition.candidate_user_id is not None
        or partition.candidate_scope_kind != "company"
    ):
        raise ValueError("Files reconciliation partition metadata is invalid")
    return _FileProjectionEnvelope(
        retrieval_partition_id=partition.id, scope_kind=RagScopeKind.COMPANY
    )


def _reconciliation_rag_operation(projection_event: ProjectionEventRef) -> RagSyncOperation:
    if projection_event.desired_state == RetrievalProjectionDesiredState.DELETED.value:
        return RagSyncOperation.DELETE
    if projection_event.change_kind == RetrievalProjectionChangeKind.VISIBILITY.value:
        return RagSyncOperation.VISIBILITY_UPDATE
    return RagSyncOperation.UPSERT


__all__ = [
    "FileRetrievalReconciliationBatch",
    "FileRetrievalReconciliationStatus",
    "LegacyFileRetrievalAdoptionBatch",
    "adopt_legacy_file_retrieval_heads",
    "capture_file_retrieval_event_watermark",
    "enqueue_file_retrieval_sync",
    "inspect_file_retrieval_reconciliation",
    "mark_file_projection_deleted",
    "mark_file_projection_failed",
    "mark_file_projection_prepared",
    "stage_file_retrieval_reconciliation",
]
