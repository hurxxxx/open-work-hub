from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from celery import Celery
from sqlalchemy import func, select
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.core.telemetry import serialize_current_trace_context
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.rag.contracts import RagJobStatus, RagSyncLane, RagSyncOperation, RagTraceContext
from aidoo_api.domains.rag.metrics import record_sync_queue_depth
from aidoo_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob


logger = logging.getLogger(__name__)
_PENDING_RAG_PUBLISHES_KEY = "rag_publish_after_commit"


@lru_cache(maxsize=1)
def _get_celery_client() -> Celery:
    settings = get_settings()
    celery_client = Celery(
        "aidoo_api_rag",
        broker=settings.worker_broker_url,
    )
    celery_client.conf.update(
        result_backend=None,
        task_ignore_result=True,
        task_store_eager_result=False,
        broker_connection_retry=False,
        broker_connection_retry_on_startup=False,
        broker_connection_max_retries=0,
        task_publish_retry=False,
        broker_transport_options={
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "retry_on_timeout": False,
        },
    )
    return celery_client


def enqueue_rag_sync_job(
    db: Session,
    *,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
    operation: RagSyncOperation = RagSyncOperation.UPSERT,
    lane: RagSyncLane = RagSyncLane.REALTIME,
    content_checksum: str | None = None,
    visibility_checksum: str | None = None,
    trace_context: RagTraceContext | dict[str, Any] | None = None,
) -> RagSyncJob:
    resolved_trace_context = (
        serialize_current_trace_context()
        if trace_context is None
        else _normalize_trace_context(trace_context)
    )
    existing = _select_pending_sync_job(
        db,
        workspace_id=workspace_id,
        lane=lane.value,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    if existing is not None:
        existing.operation = _merge_sync_operation(existing.operation, operation.value)
        existing.content_checksum = content_checksum or existing.content_checksum
        existing.visibility_checksum = visibility_checksum or existing.visibility_checksum
        existing.trace_context = resolved_trace_context
        db.add(existing)
        db.flush()
        _schedule_publish_after_commit(db, kind="sync", job_id=existing.id, lane=existing.lane)
        _record_sync_queue_depth(db, workspace_id=workspace_id, lane=lane.value)
        return existing

    job = RagSyncJob(
        id=new_id(),
        workspace_id=workspace_id,
        lane=lane.value,
        resource_type=resource_type,
        resource_id=resource_id,
        operation=operation.value,
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
        _schedule_publish_after_commit(db, kind="sync", job_id=job.id, lane=job.lane)
        _record_sync_queue_depth(db, workspace_id=workspace_id, lane=lane.value)
        return job
    except IntegrityError:
        db.expire_all()
        existing = _select_pending_sync_job(
            db,
            workspace_id=workspace_id,
            lane=lane.value,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if existing is None:
            raise
        existing.operation = _merge_sync_operation(existing.operation, operation.value)
        existing.content_checksum = content_checksum or existing.content_checksum
        existing.visibility_checksum = visibility_checksum or existing.visibility_checksum
        existing.trace_context = resolved_trace_context
        db.add(existing)
        db.flush()
        _schedule_publish_after_commit(db, kind="sync", job_id=existing.id, lane=existing.lane)
        _record_sync_queue_depth(db, workspace_id=workspace_id, lane=lane.value)
        return existing


def enqueue_rag_visibility_recompute_job(
    db: Session,
    *,
    workspace_id: str,
    scope_type: str,
    scope_id: str,
    cursor: dict[str, Any] | None = None,
    trace_context: RagTraceContext | dict[str, Any] | None = None,
) -> RagVisibilityRecomputeJob:
    resolved_trace_context = (
        serialize_current_trace_context()
        if trace_context is None
        else _normalize_trace_context(trace_context)
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
        existing.cursor = _merge_recompute_cursor(existing.cursor, normalized_cursor)
        db.add(existing)
        db.flush()
        _schedule_publish_after_commit(db, kind="visibility", job_id=existing.id, lane=None)
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
        _schedule_publish_after_commit(db, kind="visibility", job_id=job.id, lane=None)
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
        existing.cursor = _merge_recompute_cursor(existing.cursor, normalized_cursor)
        db.add(existing)
        db.flush()
        _schedule_publish_after_commit(db, kind="visibility", job_id=existing.id, lane=None)
        _record_visibility_queue_depth(db, workspace_id=workspace_id)
        return existing


def _select_pending_sync_job(
    db: Session,
    *,
    workspace_id: str,
    lane: str,
    resource_type: str,
    resource_id: str,
) -> RagSyncJob | None:
    return db.scalar(
        select(RagSyncJob)
        .where(
            RagSyncJob.workspace_id == workspace_id,
            RagSyncJob.lane == lane,
            RagSyncJob.resource_type == resource_type,
            RagSyncJob.resource_id == resource_id,
            RagSyncJob.status == RagJobStatus.PENDING.value,
        )
        .order_by(RagSyncJob.created_at.desc())
        .limit(1)
    )


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


def _normalize_trace_context(
    value: RagTraceContext | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, RagTraceContext):
        return value.model_dump(mode="json")
    return dict(value)


def _merge_sync_operation(existing: str, incoming: str) -> str:
    if existing == RagSyncOperation.DELETE.value:
        return existing
    if incoming == RagSyncOperation.DELETE.value:
        return incoming
    if incoming == RagSyncOperation.UPSERT.value:
        return incoming
    if existing == RagSyncOperation.UPSERT.value:
        return existing
    return RagSyncOperation.VISIBILITY_UPDATE.value


def _merge_recompute_cursor(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if existing is None:
        return incoming
    if incoming is None:
        return existing

    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"doc_ids", "issue_ids"}:
            merged[key] = sorted({*(merged.get(key) or []), *(value or [])})
            continue
        merged[key] = value
    return merged


def _record_sync_queue_depth(
    db: Session,
    *,
    workspace_id: str,
    lane: str,
) -> None:
    pending_count = db.scalar(
        select(func.count())
        .select_from(RagSyncJob)
        .where(
            RagSyncJob.workspace_id == workspace_id,
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


def _schedule_publish_after_commit(
    db: Session,
    *,
    kind: str,
    job_id: str,
    lane: str | None,
) -> None:
    pending = db.info.setdefault(_PENDING_RAG_PUBLISHES_KEY, set())
    if not isinstance(pending, set):
        pending = set()
        db.info[_PENDING_RAG_PUBLISHES_KEY] = pending
    pending.add((kind, job_id, lane))


@event.listens_for(Session, "after_commit")
def _publish_pending_rag_jobs(session: Session) -> None:
    pending = session.info.pop(_PENDING_RAG_PUBLISHES_KEY, None)
    if not pending:
        return
    for kind, job_id, lane in sorted(pending):
        try:
            _publish_job(kind=kind, job_id=job_id, lane=lane)
        except Exception:
            logger.warning("Failed to publish RAG job after commit", exc_info=True)


@event.listens_for(Session, "after_rollback")
def _clear_pending_rag_job_publications(session: Session) -> None:
    session.info.pop(_PENDING_RAG_PUBLISHES_KEY, None)


def _publish_job(*, kind: str, job_id: str, lane: str | None) -> None:
    celery_client = _get_celery_client()
    if kind == "sync":
        task_name = (
            "rag.sync_backfill_resource"
            if lane == RagSyncLane.BACKFILL.value
            else "rag.sync_resource"
        )
        queue = (
            "rag_sync_backfill"
            if lane == RagSyncLane.BACKFILL.value
            else "rag_sync_realtime"
        )
    else:
        task_name = "rag.recompute_visibility"
        queue = "rag_visibility_recompute"
    celery_client.signature(task_name, args=[job_id], immutable=True).apply_async(
        queue=queue,
        retry=False,
    )
