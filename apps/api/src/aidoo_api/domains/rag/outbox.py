from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.rag.contracts import RagJobStatus, RagSyncLane, RagSyncOperation, RagTraceContext
from aidoo_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob


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
    job = RagSyncJob(
        id=new_id(),
        workspace_id=workspace_id,
        lane=lane.value,
        resource_type=resource_type,
        resource_id=resource_id,
        operation=operation.value,
        content_checksum=content_checksum,
        visibility_checksum=visibility_checksum,
        trace_context=_normalize_trace_context(trace_context),
        status=RagJobStatus.PENDING.value,
        attempts=0,
    )
    db.add(job)
    db.flush()
    return job


def enqueue_rag_visibility_recompute_job(
    db: Session,
    *,
    workspace_id: str,
    scope_type: str,
    scope_id: str,
    cursor: dict[str, Any] | None = None,
    trace_context: RagTraceContext | dict[str, Any] | None = None,
) -> RagVisibilityRecomputeJob:
    job = RagVisibilityRecomputeJob(
        id=new_id(),
        workspace_id=workspace_id,
        scope_type=scope_type,
        scope_id=scope_id,
        trace_context=_normalize_trace_context(trace_context),
        cursor=dict(cursor or {}) or None,
        status=RagJobStatus.PENDING.value,
        attempts=0,
    )
    db.add(job)
    db.flush()
    return job


def _normalize_trace_context(
    value: RagTraceContext | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, RagTraceContext):
        return value.model_dump(mode="json")
    return dict(value)
