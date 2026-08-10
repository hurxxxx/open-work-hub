from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
from typing import Any

from celery import Celery
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_do_api.core.settings import get_settings
from ai_do_api.core.telemetry import serialize_current_trace_context
from ai_do_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from ai_do_api.core.worker_queue_contract import (
    SEARCH_INDEX_REALTIME_QUEUE,
    SEARCH_INDEX_RESOURCE_TASK_NAME,
)
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.retrieval.models import RetrievalProjectionEvent
from ai_do_api.domains.retrieval.projection_fencing import ProjectionEventRef
from ai_do_api.domains.search.default_projection_adapters import (
    ensure_search_projection_adapters_registered,
)
from ai_do_api.domains.search.entity_adapter_registry import get_search_entity_adapter
from ai_do_api.domains.search.models import SearchIndexJob
from ai_do_api.domains.search.projection_registry import get_search_projection_adapter


logger = logging.getLogger(__name__)
PENDING_STATUS = "pending"
_PENDING_SEARCH_PUBLISHES_KEY = "search_index_publish_after_commit"


@dataclass(frozen=True, slots=True)
class _ProjectionJobSnapshot:
    workspace_id: str
    entity_type: str
    entity_id: str
    resource_type: str
    event_sequence: int
    projection_version: int
    retrieval_partition_id: str
    desired_state: str
    operation: str


@lru_cache(maxsize=1)
def get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "ai_do_api_search_index",
        broker=settings.worker_broker_url,
        ignore_result=True,
    )


def enqueue_search_index_job(
    db: Session,
    *,
    workspace_id: str,
    entity_type: object,
    entity_id: str,
    operation: str = "upsert",
    trace_context: dict[str, Any] | None = None,
    projection_event: ProjectionEventRef | None = None,
) -> SearchIndexJob:
    resolved_entity_type, resolved_trace_context = _normalize_job_request(
        entity_type=entity_type,
        operation=operation,
        trace_context=trace_context,
    )
    projection_snapshot = _projection_job_snapshot(
        db,
        workspace_id=workspace_id,
        entity_type=resolved_entity_type,
        entity_id=entity_id,
        operation=operation,
        projection_event=projection_event,
    )
    job = _upsert_pending_job(
        db,
        workspace_id=workspace_id,
        entity_type=resolved_entity_type,
        entity_id=entity_id,
        operation=operation,
        trace_context=resolved_trace_context,
        projection_snapshot=projection_snapshot,
    )
    _schedule_publish_after_commit(db, job_id=job.id)
    return job


def _normalize_job_request(
    *,
    entity_type: object,
    operation: str,
    trace_context: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    if operation not in {"upsert", "delete"}:
        raise ValueError(f"Unsupported search index operation: {operation}")
    resolved_entity_type = str(entity_type).strip()
    if not resolved_entity_type:
        raise ValueError("Search index entity_type is required")
    if operation == "upsert":
        _ensure_upsert_projection_contract(resolved_entity_type)
    resolved_trace_context = (
        serialize_current_trace_context() if trace_context is None else dict(trace_context)
    )
    return resolved_entity_type, resolved_trace_context


def _ensure_upsert_projection_contract(entity_type: str) -> None:
    ensure_search_projection_adapters_registered()
    if get_search_projection_adapter(entity_type) is None:
        raise ValueError(f"Search index upsert entity_type lacks projection adapter: {entity_type}")


def _projection_job_snapshot(
    db: Session,
    *,
    workspace_id: str,
    entity_type: str,
    entity_id: str,
    operation: str,
    projection_event: ProjectionEventRef | None,
) -> _ProjectionJobSnapshot | None:
    if projection_event is None:
        return None

    persisted = db.get(RetrievalProjectionEvent, projection_event.event_sequence)
    if persisted is None:
        raise ValueError(
            f"Search projection event is not persisted: {projection_event.event_sequence}"
        )
    persisted_snapshot = (
        persisted.resource_type,
        persisted.resource_id,
        persisted.projection_version,
        persisted.retrieval_partition_id,
        persisted.change_kind,
        persisted.desired_state,
        persisted.content_checksum,
        persisted.visibility_checksum,
        persisted.diagnostic_workspace_id,
    )
    incoming_snapshot = (
        projection_event.resource_type,
        projection_event.resource_id,
        projection_event.projection_version,
        projection_event.retrieval_partition_id,
        projection_event.change_kind,
        projection_event.desired_state,
        projection_event.content_checksum,
        projection_event.visibility_checksum,
        projection_event.diagnostic_workspace_id,
    )
    if incoming_snapshot != persisted_snapshot:
        raise ValueError(
            f"Search projection event snapshot mismatch: {projection_event.event_sequence}"
        )
    if projection_event.resource_id != entity_id:
        raise ValueError(
            "Search projection event resource_id does not match entity_id: "
            f"{projection_event.resource_id} != {entity_id}"
        )

    ensure_search_projection_adapters_registered()
    adapter = get_search_entity_adapter(entity_type)
    if adapter is None:
        raise ValueError(f"Search entity_type lacks entity adapter: {entity_type}")
    if adapter.resource_type != projection_event.resource_type:
        raise ValueError(
            "Search entity adapter resource_type mismatch: "
            f"{adapter.resource_type} != {projection_event.resource_type}"
        )

    expected_operation = "delete" if projection_event.desired_state == "deleted" else "upsert"
    if operation != expected_operation:
        raise ValueError(
            "Search projection event desired_state does not match operation: "
            f"{projection_event.desired_state} != {operation}"
        )
    return _ProjectionJobSnapshot(
        workspace_id=workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
        resource_type=projection_event.resource_type,
        event_sequence=projection_event.event_sequence,
        projection_version=projection_event.projection_version,
        retrieval_partition_id=projection_event.retrieval_partition_id,
        desired_state=projection_event.desired_state,
        operation=operation,
    )


def _upsert_pending_job(
    db: Session,
    *,
    workspace_id: str,
    entity_type: str,
    entity_id: str,
    operation: str,
    trace_context: dict[str, Any],
    projection_snapshot: _ProjectionJobSnapshot | None,
) -> SearchIndexJob:
    existing = _select_pending_job(
        db,
        workspace_id=workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
        projection_snapshot=projection_snapshot,
    )
    if existing is None and projection_snapshot is not None:
        existing = _select_legacy_pending_job(
            db,
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    if existing is not None:
        return _apply_pending_job_update(
            db,
            existing,
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            trace_context=trace_context,
            projection_snapshot=projection_snapshot,
        )

    job = SearchIndexJob(
        id=new_id(),
        workspace_id=workspace_id,
        retrieval_partition_id=(
            projection_snapshot.retrieval_partition_id if projection_snapshot else None
        ),
        resource_type=projection_snapshot.resource_type if projection_snapshot else None,
        projection_event_sequence=(
            projection_snapshot.event_sequence if projection_snapshot else None
        ),
        projection_version=(
            projection_snapshot.projection_version if projection_snapshot else None
        ),
        desired_state=projection_snapshot.desired_state if projection_snapshot else None,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        trace_context=trace_context,
        status=PENDING_STATUS,
        attempts=0,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
        return job
    except IntegrityError:
        db.expire_all()
        existing = _select_pending_job(
            db,
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            projection_snapshot=projection_snapshot,
        )
        if existing is None and projection_snapshot is not None:
            existing = _select_legacy_pending_job(
                db,
                workspace_id=workspace_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        if existing is None:
            raise
        return _apply_pending_job_update(
            db,
            existing,
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            trace_context=trace_context,
            projection_snapshot=projection_snapshot,
        )


def _apply_pending_job_update(
    db: Session,
    job: SearchIndexJob,
    *,
    workspace_id: str,
    entity_type: str,
    entity_id: str,
    operation: str,
    trace_context: dict[str, Any],
    projection_snapshot: _ProjectionJobSnapshot | None,
) -> SearchIndexJob:
    if projection_snapshot is None:
        if _job_has_projection_fence(job):
            return job
        job.operation = operation
        job.trace_context = trace_context
        db.add(job)
        db.flush()
        return job

    if _job_has_projection_fence(job):
        existing_snapshot = _projection_snapshot_from_job(job)
        if projection_snapshot.projection_version < existing_snapshot.projection_version:
            return job
        if projection_snapshot.projection_version == existing_snapshot.projection_version:
            if projection_snapshot != existing_snapshot:
                raise ValueError(
                    "Search pending job same-version projection snapshot mismatch: "
                    f"{projection_snapshot.projection_version}"
                )
            return job

    _cancel_conflicting_legacy_pending_job(
        db,
        job=job,
        workspace_id=workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    job.retrieval_partition_id = projection_snapshot.retrieval_partition_id
    job.workspace_id = workspace_id
    job.entity_type = entity_type
    job.entity_id = entity_id
    job.resource_type = projection_snapshot.resource_type
    job.projection_event_sequence = projection_snapshot.event_sequence
    job.projection_version = projection_snapshot.projection_version
    job.desired_state = projection_snapshot.desired_state
    job.operation = operation
    job.trace_context = trace_context
    db.add(job)
    db.flush()
    return job


def _job_has_projection_fence(job: SearchIndexJob) -> bool:
    return any(
        value is not None
        for value in (
            job.resource_type,
            job.projection_event_sequence,
            job.projection_version,
            job.desired_state,
        )
    )


def _projection_snapshot_from_job(job: SearchIndexJob) -> _ProjectionJobSnapshot:
    if (
        job.resource_type is None
        or job.projection_event_sequence is None
        or job.projection_version is None
        or job.retrieval_partition_id is None
        or job.desired_state is None
    ):
        raise ValueError(f"Search pending job has incomplete projection fence: {job.id}")
    return _ProjectionJobSnapshot(
        workspace_id=job.workspace_id,
        entity_type=job.entity_type,
        entity_id=job.entity_id,
        resource_type=job.resource_type,
        event_sequence=job.projection_event_sequence,
        projection_version=job.projection_version,
        retrieval_partition_id=job.retrieval_partition_id,
        desired_state=job.desired_state,
        operation=job.operation,
    )


def _select_pending_job(
    db: Session,
    *,
    workspace_id: str,
    entity_type: str,
    entity_id: str,
    projection_snapshot: _ProjectionJobSnapshot | None,
) -> SearchIndexJob | None:
    statement = select(SearchIndexJob)
    if projection_snapshot is None:
        statement = statement.where(
            SearchIndexJob.workspace_id == workspace_id,
            SearchIndexJob.entity_type == entity_type,
            SearchIndexJob.entity_id == entity_id,
            SearchIndexJob.status == PENDING_STATUS,
        )
    else:
        statement = statement.where(
            SearchIndexJob.resource_type == projection_snapshot.resource_type,
            SearchIndexJob.entity_id == projection_snapshot.entity_id,
            SearchIndexJob.projection_version.is_not(None),
            SearchIndexJob.status == PENDING_STATUS,
        )
    return db.scalar(
        statement.order_by(SearchIndexJob.created_at.desc()).limit(1).with_for_update()
    )


def _select_legacy_pending_job(
    db: Session,
    *,
    workspace_id: str,
    entity_type: str,
    entity_id: str,
) -> SearchIndexJob | None:
    return db.scalar(
        select(SearchIndexJob)
        .where(
            SearchIndexJob.workspace_id == workspace_id,
            SearchIndexJob.entity_type == entity_type,
            SearchIndexJob.entity_id == entity_id,
            SearchIndexJob.resource_type.is_(None),
            SearchIndexJob.projection_version.is_(None),
            SearchIndexJob.status == PENDING_STATUS,
        )
        .limit(1)
        .with_for_update()
    )


def _cancel_conflicting_legacy_pending_job(
    db: Session,
    *,
    job: SearchIndexJob,
    workspace_id: str,
    entity_type: str,
    entity_id: str,
) -> None:
    conflict = db.scalar(
        select(SearchIndexJob)
        .where(
            SearchIndexJob.id != job.id,
            SearchIndexJob.workspace_id == workspace_id,
            SearchIndexJob.entity_type == entity_type,
            SearchIndexJob.entity_id == entity_id,
            SearchIndexJob.status == PENDING_STATUS,
        )
        .limit(1)
        .with_for_update()
    )
    if conflict is None:
        return
    if _job_has_projection_fence(conflict):
        raise ValueError(
            "Search pending job canonical and compatibility identities conflict: "
            f"{job.id} != {conflict.id}"
        )
    conflict.status = "cancelled"
    conflict.last_error = f"superseded_by_projection_job:{job.id}"
    db.add(conflict)
    db.flush()


def _schedule_publish_after_commit(db: Session, *, job_id: str) -> None:
    pending = db.info.setdefault(_PENDING_SEARCH_PUBLISHES_KEY, set())
    if not isinstance(pending, set):
        pending = set()
        db.info[_PENDING_SEARCH_PUBLISHES_KEY] = pending
    pending.add(job_id)


@event.listens_for(Session, "after_commit")
def _publish_pending_search_index_jobs(session: Session) -> None:
    # SQLAlchemy emits after_commit for savepoint releases too. Publishing there
    # can let a worker observe the job before the outer transaction is committed.
    if session.in_nested_transaction():
        return
    pending = session.info.pop(_PENDING_SEARCH_PUBLISHES_KEY, None)
    if not pending:
        return
    for job_id in sorted(pending):
        try:
            _publish_job(job_id=job_id)
        except Exception:
            logger.warning("Failed to publish search index job after commit", exc_info=True)


@event.listens_for(Session, "after_rollback")
def _clear_pending_search_index_job_publications(session: Session) -> None:
    if session.in_nested_transaction():
        return
    session.info.pop(_PENDING_SEARCH_PUBLISHES_KEY, None)


def _publish_job(*, job_id: str) -> None:
    get_celery_client().signature(
        SEARCH_INDEX_RESOURCE_TASK_NAME,
        args=[job_id],
        immutable=True,
    ).apply_async(
        queue=SEARCH_INDEX_REALTIME_QUEUE,
        retry=False,
    )
