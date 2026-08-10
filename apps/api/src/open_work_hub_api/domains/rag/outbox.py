from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from celery import Celery
from sqlalchemy import func, select
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from open_work_hub_api.core.telemetry import serialize_current_trace_context
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.rag.contracts import (
    RagJobStatus,
    RagScopeKind,
    RagSyncLane,
    RagSyncOperation,
    RagTraceContext,
)
from open_work_hub_api.domains.rag.job_publication import (
    RagJobPublication,
    clear_pending_rag_job_publications_after_rollback,
    publish_pending_rag_job_publications_after_commit,
    publish_rag_job_publication,
    schedule_rag_job_publication_after_commit,
)
from open_work_hub_api.domains.rag.job_state import (
    merge_recompute_cursor,
    merge_sync_operation,
    normalize_trace_context,
)
from open_work_hub_api.domains.rag.default_source_adapters import ensure_rag_source_adapters_registered
from open_work_hub_api.domains.rag.metrics import record_sync_queue_depth
from open_work_hub_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
from open_work_hub_api.domains.rag.source_adapter_registry import (
    RagResourceAdapter,
    get_rag_resource_adapter,
    get_rag_visibility_scope_adapter,
)
from open_work_hub_api.domains.retrieval.models import RetrievalProjectionEvent
from open_work_hub_api.domains.retrieval.projection_fencing import ProjectionEventRef


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "open_work_hub_api_rag",
        broker=settings.worker_broker_url,
        ignore_result=True,
    )


def enqueue_rag_sync_job(
    db: Session,
    *,
    workspace_id: str | None,
    scope_kind: RagScopeKind | str = RagScopeKind.WORKSPACE,
    resource_type: str,
    resource_id: str,
    operation: RagSyncOperation = RagSyncOperation.UPSERT,
    lane: RagSyncLane = RagSyncLane.REALTIME,
    content_checksum: str | None = None,
    visibility_checksum: str | None = None,
    trace_context: RagTraceContext | dict[str, Any] | None = None,
    supersede_delete: bool = False,
    projection_event: ProjectionEventRef | None = None,
) -> RagSyncJob:
    scope_kind = _normalize_rag_scope_kind(scope_kind)
    workspace_id = _normalize_rag_workspace_id(scope_kind=scope_kind, workspace_id=workspace_id)
    operation = _normalize_rag_sync_operation(operation)
    resource_adapter = _require_registered_rag_resource_adapter(resource_type)
    resource_type = resource_adapter.resource_type
    _require_sync_operation_supported(resource_adapter, operation)
    resource_id = _require_non_empty_rag_resource_id(resource_id)
    projection_event = _validate_projection_event(
        db,
        projection_event=projection_event,
        resource_type=resource_type,
        resource_id=resource_id,
        operation=operation,
        content_checksum=content_checksum,
        visibility_checksum=visibility_checksum,
    )
    if projection_event is not None:
        content_checksum = projection_event.content_checksum
        visibility_checksum = projection_event.visibility_checksum
    resolved_trace_context = (
        serialize_current_trace_context()
        if trace_context is None
        else normalize_trace_context(trace_context)
    )
    existing = _select_pending_sync_job(
        db,
        scope_kind=scope_kind.value,
        workspace_id=workspace_id,
        lane=lane.value,
        resource_type=resource_type,
        resource_id=resource_id,
        projection_event=projection_event,
    )
    if existing is not None:
        _merge_pending_sync_job(
            existing,
            operation=operation,
            projection_event=projection_event,
            content_checksum=content_checksum,
            visibility_checksum=visibility_checksum,
            trace_context=resolved_trace_context,
            supersede_delete=supersede_delete,
            scope_kind=scope_kind.value,
            workspace_id=workspace_id,
        )
        db.add(existing)
        db.flush()
        schedule_rag_job_publication_after_commit(
            db,
            RagJobPublication.sync(job_id=existing.id, lane=existing.lane),
        )
        _record_sync_queue_depth(
            db,
            scope_kind=scope_kind.value,
            workspace_id=workspace_id,
            lane=lane.value,
        )
        return existing

    job = RagSyncJob(
        id=new_id(),
        scope_kind=scope_kind.value,
        workspace_id=workspace_id,
        lane=lane.value,
        resource_type=resource_type,
        resource_id=resource_id,
        operation=operation.value,
        retrieval_partition_id=(
            projection_event.retrieval_partition_id if projection_event is not None else None
        ),
        projection_event_sequence=(
            projection_event.event_sequence if projection_event is not None else None
        ),
        projection_version=(
            projection_event.projection_version if projection_event is not None else None
        ),
        desired_state=(projection_event.desired_state if projection_event is not None else None),
        content_checksum=content_checksum,
        visibility_checksum=visibility_checksum,
        trace_context=resolved_trace_context,
        status=RagJobStatus.PENDING.value,
        attempts=0,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
        schedule_rag_job_publication_after_commit(
            db,
            RagJobPublication.sync(job_id=job.id, lane=job.lane),
        )
        _record_sync_queue_depth(
            db,
            scope_kind=scope_kind.value,
            workspace_id=workspace_id,
            lane=lane.value,
        )
        return job
    except IntegrityError:
        db.expire_all()
        existing = _select_pending_sync_job(
            db,
            scope_kind=scope_kind.value,
            workspace_id=workspace_id,
            lane=lane.value,
            resource_type=resource_type,
            resource_id=resource_id,
            projection_event=projection_event,
        )
        if existing is None:
            raise
        _merge_pending_sync_job(
            existing,
            operation=operation,
            projection_event=projection_event,
            content_checksum=content_checksum,
            visibility_checksum=visibility_checksum,
            trace_context=resolved_trace_context,
            supersede_delete=supersede_delete,
            scope_kind=scope_kind.value,
            workspace_id=workspace_id,
        )
        db.add(existing)
        db.flush()
        schedule_rag_job_publication_after_commit(
            db,
            RagJobPublication.sync(job_id=existing.id, lane=existing.lane),
        )
        _record_sync_queue_depth(
            db,
            scope_kind=scope_kind.value,
            workspace_id=workspace_id,
            lane=lane.value,
        )
        return existing


def _validate_projection_event(
    db: Session,
    *,
    projection_event: ProjectionEventRef | None,
    resource_type: str,
    resource_id: str,
    operation: RagSyncOperation,
    content_checksum: str | None,
    visibility_checksum: str | None,
) -> ProjectionEventRef | None:
    if projection_event is None:
        return None
    if not isinstance(projection_event, ProjectionEventRef):
        raise ValueError("RAG projection_event must be a ProjectionEventRef")
    persisted = db.get(RetrievalProjectionEvent, projection_event.event_sequence)
    if persisted is None:
        raise ValueError(
            f"RAG projection_event is not persisted: {projection_event.event_sequence}"
        )
    mismatches = [
        field
        for field in (
            "resource_type",
            "resource_id",
            "projection_version",
            "retrieval_partition_id",
            "change_kind",
            "desired_state",
            "content_checksum",
            "visibility_checksum",
            "diagnostic_workspace_id",
        )
        if getattr(projection_event, field) != getattr(persisted, field)
    ]
    if mismatches:
        raise ValueError(
            "RAG projection_event does not match its persisted event: " + ", ".join(mismatches)
        )
    if projection_event.resource_type != resource_type:
        raise ValueError(
            "RAG projection_event resource_type mismatch: "
            f"{projection_event.resource_type} != {resource_type}"
        )
    if projection_event.resource_id != resource_id:
        raise ValueError(
            "RAG projection_event resource_id mismatch: "
            f"{projection_event.resource_id} != {resource_id}"
        )
    expected_state = "deleted" if operation == RagSyncOperation.DELETE else "active"
    if projection_event.desired_state != expected_state:
        raise ValueError(
            "RAG projection_event desired_state does not match operation: "
            f"{projection_event.desired_state} != {operation.value}"
        )
    if content_checksum is not None and content_checksum != projection_event.content_checksum:
        raise ValueError("RAG content_checksum does not match projection_event")
    if (
        visibility_checksum is not None
        and visibility_checksum != projection_event.visibility_checksum
    ):
        raise ValueError("RAG visibility_checksum does not match projection_event")
    return projection_event


def _merge_pending_sync_job(
    job: RagSyncJob,
    *,
    operation: RagSyncOperation,
    projection_event: ProjectionEventRef | None,
    content_checksum: str | None,
    visibility_checksum: str | None,
    trace_context: dict[str, Any] | None,
    supersede_delete: bool,
    scope_kind: str,
    workspace_id: str | None,
) -> None:
    existing_fence = (
        job.retrieval_partition_id,
        job.projection_event_sequence,
        job.projection_version,
        job.desired_state,
    )
    has_existing_fence = any(value is not None for value in existing_fence)
    has_complete_existing_fence = all(value is not None for value in existing_fence)
    if has_existing_fence and not has_complete_existing_fence:
        raise ValueError(f"RAG pending job has an incomplete projection fence: {job.id}")

    if projection_event is None:
        if has_complete_existing_fence:
            return
        job.operation = merge_sync_operation(
            job.operation,
            operation.value,
            supersede_delete=supersede_delete,
        )
        job.content_checksum = content_checksum or job.content_checksum
        job.visibility_checksum = visibility_checksum or job.visibility_checksum
        job.trace_context = trace_context
        return

    if not has_complete_existing_fence:
        _apply_projection_event_snapshot(
            job,
            operation=operation,
            projection_event=projection_event,
            trace_context=trace_context,
            scope_kind=scope_kind,
            workspace_id=workspace_id,
        )
        return

    existing_version = int(job.projection_version or 0)
    if projection_event.projection_version < existing_version:
        return
    if projection_event.projection_version > existing_version:
        _apply_projection_event_snapshot(
            job,
            operation=operation,
            projection_event=projection_event,
            trace_context=trace_context,
            scope_kind=scope_kind,
            workspace_id=workspace_id,
        )
        return

    mismatches = [
        field
        for field, current, incoming in (
            (
                "projection_event_sequence",
                job.projection_event_sequence,
                projection_event.event_sequence,
            ),
            (
                "retrieval_partition_id",
                job.retrieval_partition_id,
                projection_event.retrieval_partition_id,
            ),
            ("desired_state", job.desired_state, projection_event.desired_state),
            ("operation", job.operation, operation.value),
            ("content_checksum", job.content_checksum, projection_event.content_checksum),
            (
                "visibility_checksum",
                job.visibility_checksum,
                projection_event.visibility_checksum,
            ),
        )
        if current != incoming
    ]
    if mismatches:
        raise ValueError(
            "RAG pending job has a same-version projection mismatch: " + ", ".join(mismatches)
        )
    job.trace_context = trace_context


def _apply_projection_event_snapshot(
    job: RagSyncJob,
    *,
    operation: RagSyncOperation,
    projection_event: ProjectionEventRef,
    trace_context: dict[str, Any] | None,
    scope_kind: str,
    workspace_id: str | None,
) -> None:
    job.scope_kind = scope_kind
    job.workspace_id = workspace_id
    job.operation = operation.value
    job.retrieval_partition_id = projection_event.retrieval_partition_id
    job.projection_event_sequence = projection_event.event_sequence
    job.projection_version = projection_event.projection_version
    job.desired_state = projection_event.desired_state
    job.content_checksum = projection_event.content_checksum
    job.visibility_checksum = projection_event.visibility_checksum
    job.trace_context = trace_context


def enqueue_rag_visibility_recompute_job(
    db: Session,
    *,
    workspace_id: str,
    scope_type: str,
    scope_id: str,
    cursor: dict[str, Any] | None = None,
    trace_context: RagTraceContext | dict[str, Any] | None = None,
) -> RagVisibilityRecomputeJob:
    scope_type = _require_registered_rag_visibility_scope_type(scope_type)
    scope_id = _require_non_empty_rag_scope_id(scope_id)
    resolved_trace_context = (
        serialize_current_trace_context()
        if trace_context is None
        else normalize_trace_context(trace_context)
    )
    normalized_cursor = dict(cursor or {}) or None
    existing = _select_pending_visibility_job(
        db,
        workspace_id=workspace_id,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    if existing is not None:
        existing.trace_context = resolved_trace_context
        existing.cursor = merge_recompute_cursor(existing.cursor, normalized_cursor)
        db.add(existing)
        db.flush()
        schedule_rag_job_publication_after_commit(
            db,
            RagJobPublication.visibility_recompute(job_id=existing.id),
        )
        _record_visibility_queue_depth(db, workspace_id=workspace_id)
        return existing

    job = RagVisibilityRecomputeJob(
        id=new_id(),
        workspace_id=workspace_id,
        scope_type=scope_type,
        scope_id=scope_id,
        trace_context=resolved_trace_context,
        cursor=normalized_cursor,
        status=RagJobStatus.PENDING.value,
        attempts=0,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
        schedule_rag_job_publication_after_commit(
            db,
            RagJobPublication.visibility_recompute(job_id=job.id),
        )
        _record_visibility_queue_depth(db, workspace_id=workspace_id)
        return job
    except IntegrityError:
        db.expire_all()
        existing = _select_pending_visibility_job(
            db,
            workspace_id=workspace_id,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        if existing is None:
            raise
        existing.trace_context = resolved_trace_context
        existing.cursor = merge_recompute_cursor(existing.cursor, normalized_cursor)
        db.add(existing)
        db.flush()
        schedule_rag_job_publication_after_commit(
            db,
            RagJobPublication.visibility_recompute(job_id=existing.id),
        )
        _record_visibility_queue_depth(db, workspace_id=workspace_id)
        return existing


def _select_pending_sync_job(
    db: Session,
    *,
    scope_kind: str,
    workspace_id: str | None,
    lane: str,
    resource_type: str,
    resource_id: str,
    projection_event: ProjectionEventRef | None,
) -> RagSyncJob | None:
    query = select(RagSyncJob).where(
        RagSyncJob.lane == lane,
        RagSyncJob.resource_type == resource_type,
        RagSyncJob.resource_id == resource_id,
        RagSyncJob.status == RagJobStatus.PENDING.value,
    )
    if projection_event is None:
        query = query.where(
            RagSyncJob.workspace_id == workspace_id,
            RagSyncJob.scope_kind == scope_kind,
            RagSyncJob.projection_version.is_(None),
        )
    else:
        query = query.where(RagSyncJob.projection_version.is_not(None))
    return db.scalar(query.order_by(RagSyncJob.created_at.desc()).limit(1))


def _require_registered_rag_resource_type(resource_type: str) -> str:
    return _require_registered_rag_resource_adapter(resource_type).resource_type


def _normalize_rag_sync_operation(operation: RagSyncOperation | str) -> RagSyncOperation:
    try:
        return RagSyncOperation(str(operation))
    except ValueError as exc:
        raise ValueError(f"RAG sync operation is not supported: {operation}") from exc


def _normalize_rag_scope_kind(scope_kind: RagScopeKind | str) -> RagScopeKind:
    try:
        return RagScopeKind(str(scope_kind))
    except ValueError as exc:
        raise ValueError(f"RAG scope_kind is not supported: {scope_kind}") from exc


def _normalize_rag_workspace_id(
    *,
    scope_kind: RagScopeKind,
    workspace_id: str | None,
) -> str | None:
    if scope_kind == RagScopeKind.COMPANY:
        return None
    normalized = str(workspace_id or "").strip()
    if not normalized:
        raise ValueError("RAG workspace scope requires workspace_id")
    return normalized


def _require_registered_rag_resource_adapter(resource_type: str) -> RagResourceAdapter:
    normalized = str(resource_type or "").strip()
    if not normalized:
        raise ValueError("RAG resource_type must not be empty")
    ensure_rag_source_adapters_registered()
    adapter = get_rag_resource_adapter(normalized)
    if adapter is None:
        raise ValueError(f"RAG resource_type is not registered: {normalized}")
    return adapter


def _require_sync_operation_supported(
    adapter: RagResourceAdapter,
    operation: RagSyncOperation,
) -> None:
    if operation == RagSyncOperation.DELETE:
        return
    if adapter.load_projection is None:
        raise ValueError(
            f"RAG resource_type does not support projection sync: {adapter.resource_type}"
        )


def _require_registered_rag_visibility_scope_type(scope_type: str) -> str:
    normalized = str(scope_type or "").strip()
    if not normalized:
        raise ValueError("RAG visibility scope_type must not be empty")
    ensure_rag_source_adapters_registered()
    if get_rag_visibility_scope_adapter(normalized) is None:
        raise ValueError(f"RAG visibility scope_type is not registered: {normalized}")
    return normalized


def _require_non_empty_rag_resource_id(resource_id: str) -> str:
    normalized = str(resource_id or "").strip()
    if not normalized:
        raise ValueError("RAG resource_id must not be empty")
    return normalized


def _require_non_empty_rag_scope_id(scope_id: str) -> str:
    normalized = str(scope_id or "").strip()
    if not normalized:
        raise ValueError("RAG visibility scope_id must not be empty")
    return normalized


def _select_pending_visibility_job(
    db: Session,
    *,
    workspace_id: str,
    scope_type: str,
    scope_id: str,
) -> RagVisibilityRecomputeJob | None:
    return db.scalar(
        select(RagVisibilityRecomputeJob)
        .where(
            RagVisibilityRecomputeJob.workspace_id == workspace_id,
            RagVisibilityRecomputeJob.scope_type == scope_type,
            RagVisibilityRecomputeJob.scope_id == scope_id,
            RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value,
        )
        .order_by(RagVisibilityRecomputeJob.created_at.desc())
        .limit(1)
    )


def _record_sync_queue_depth(
    db: Session,
    *,
    scope_kind: str,
    workspace_id: str | None,
    lane: str,
) -> None:
    pending_count = db.scalar(
        select(func.count())
        .select_from(RagSyncJob)
        .where(
            RagSyncJob.workspace_id == workspace_id,
            RagSyncJob.scope_kind == scope_kind,
            RagSyncJob.lane == lane,
            RagSyncJob.status == RagJobStatus.PENDING.value,
        )
    )
    record_sync_queue_depth(
        depth=int(pending_count or 0),
        workspace_id=workspace_id,
        job_lane=lane,
        job_kind="resource_sync",
    )


def _record_visibility_queue_depth(
    db: Session,
    *,
    workspace_id: str,
) -> None:
    pending_count = db.scalar(
        select(func.count())
        .select_from(RagVisibilityRecomputeJob)
        .where(
            RagVisibilityRecomputeJob.workspace_id == workspace_id,
            RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value,
        )
    )
    record_sync_queue_depth(
        depth=int(pending_count or 0),
        workspace_id=workspace_id,
        job_lane="visibility_recompute",
        job_kind="visibility_recompute",
    )


@event.listens_for(Session, "after_commit")
def _publish_pending_rag_jobs(session: Session) -> None:
    publish_pending_rag_job_publications_after_commit(
        session,
        publisher=_publish_job,
        logger=logger,
    )


@event.listens_for(Session, "after_rollback")
def _clear_pending_rag_job_publications(session: Session) -> None:
    clear_pending_rag_job_publications_after_rollback(session)


def _publish_job(publication: RagJobPublication) -> None:
    publish_rag_job_publication(get_celery_client(), publication)
