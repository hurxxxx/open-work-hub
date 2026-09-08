from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from celery.signals import worker_process_init
from open_work_hub_api.core.telemetry import start_as_current_span
from open_work_hub_api.domains.auth.app_availability import (
    is_company_app_enabled,
)
from open_work_hub_api.domains.rag.contracts import (
    RagJobStatus,
    RagScopeKind,
    RagSyncLane,
    RagSyncOperation,
)
from open_work_hub_api.domains.rag.default_source_adapters import (
    ensure_rag_source_adapters_registered,
)
from open_work_hub_api.domains.rag.job_publication import (
    RagJobPublication,
    resolve_publication_target,
)
from open_work_hub_api.domains.rag.job_state import merge_recompute_cursor
from open_work_hub_api.domains.rag.metrics import (
    record_sync_job_lag,
    record_sync_job_result,
    record_sync_queue_depth,
)
from open_work_hub_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
from open_work_hub_api.domains.rag.outbox import enqueue_rag_sync_job
from open_work_hub_api.domains.rag.providers import (
    RagProviderConfigurationError,
    RagProviderError,
    RagProviderTimeoutError,
    RagProviderTransientError,
)
from open_work_hub_api.domains.rag.providers.base import RagProviderBundle
from open_work_hub_api.domains.rag.runtime import (
    build_partitioned_rag_projection_service,
    build_provider_bundle,
    preload_rag_runtime,
    resolve_default_collection_name,
)
from open_work_hub_api.domains.rag.service import RagService
from open_work_hub_api.domains.rag.source_adapter_registry import (
    get_rag_resource_adapter,
    get_rag_visibility_scope_adapter,
    rag_resource_adapters,
)
from open_work_hub_api.domains.rag.telemetry import rag_span_attributes
from open_work_hub_api.domains.retrieval.models import (
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.retrieval.projection_fencing import ProjectionEventRef
from open_work_hub_api.domains.retrieval.runtime_binding import (
    PartitionedRetrievalRuntimeUnavailable,
    resolve_active_partitioned_generation_pair,
)
from open_work_hub_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)
from opentelemetry.trace import SpanKind
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_work_hub_worker.celery_app import celery_app
from open_work_hub_worker.runtime import db_session as _db_session
from open_work_hub_worker.settings import get_settings

logger = logging.getLogger(__name__)
OUTBOX_REPUBLISH_BATCH_SIZE = 100
FILES_OPERATOR_GATE_PAUSE_SECONDS = 60


class RagProjectionIdentityError(RuntimeError):
    pass


class RagProjectionSuperseded(RuntimeError):
    pass


class RagAppDisabled(RuntimeError):
    def __init__(self, app_id: str) -> None:
        super().__init__(app_id)
        self.app_id = app_id


@dataclass(frozen=True, slots=True)
class _RagProjectionRuntime:
    service: RagService
    collection: str


@lru_cache(maxsize=1)
def provider_bundle() -> RagProviderBundle:
    return build_provider_bundle(get_settings())


@lru_cache(maxsize=1)
def _rag_service() -> RagService:
    settings = get_settings()
    providers = provider_bundle()
    return RagService(
        vector_index=providers.vector_index,
        embedding_client=providers.embedding,
        ocr_client=providers.ocr,
        rerank_client=providers.rerank,
        default_collection=resolve_default_collection_name(settings),
    )


@worker_process_init.connect
def _preload_rag_models_on_worker_startup(**_: object) -> None:
    settings = get_settings()
    if not settings.rag_enabled or not settings.rag_preload_on_startup:
        return
    preload_rag_runtime(settings, providers=provider_bundle())


def _job_lag_ms(created_at: datetime) -> int:
    now = datetime.now(UTC).replace(tzinfo=None)
    return max(int((now - created_at).total_seconds() * 1000), 0)


@celery_app.task(
    name="rag.sync_resource",
    bind=True,
    acks_late=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def sync_resource(self, job_id: str) -> str:
    return _run_sync_job(
        task=self,
        job_id=job_id,
        span_name="rag.sync_resource",
        job_kind="resource_sync",
    )


@celery_app.task(
    name="rag.sync_backfill_resource",
    bind=True,
    acks_late=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def sync_backfill_resource(self, job_id: str) -> str:
    settings = get_settings()
    return _run_sync_job(
        task=self,
        job_id=job_id,
        span_name="rag.sync_backfill_resource",
        job_kind="backfill_sync",
        batch_size=settings.rag_backfill_batch_size,
        throttle_ms=settings.rag_backfill_throttle_ms,
        drain_lane=RagSyncLane.BACKFILL.value,
    )


@celery_app.task(
    name="rag.republish_pending_jobs",
    task_time_limit=60,
    task_soft_time_limit=45,
)
def republish_pending_rag_jobs(limit: int = OUTBOX_REPUBLISH_BATCH_SIZE) -> int:
    session = _db_session()
    try:
        publications = _due_pending_rag_publications(session, limit=limit)
    finally:
        session.close()

    for publication in publications:
        _publish_rag_job_publication(publication)
    if publications:
        logger.info("Republished %s due or stale RAG job(s)", len(publications))
    return len(publications)


def _run_sync_job(
    *,
    task,
    job_id: str,
    span_name: str,
    job_kind: str,
    batch_size: int = 1,
    throttle_ms: int = 0,
    drain_lane: str | None = None,
) -> str:
    settings = get_settings()
    session = _db_session()
    try:
        job, claim_outcome = _claim_sync_job(session, job_id)
        if claim_outcome == "missing":
            logger.warning("RAG sync job not found: %s", job_id)
            record_sync_job_result(status="missing", job_kind=job_kind)
            return "missing"
        if claim_outcome == "app-disabled":
            logger.info("Pausing RAG sync while its owning app is disabled: %s", job_id)
            record_sync_job_result(status="app_disabled", job_kind=job_kind)
            return "app-disabled"
        if claim_outcome != "claimed" or job is None:
            logger.info("Ignoring RAG sync job already claimed or closed: %s", job_id)
            record_sync_job_result(status="ignored", job_kind=job_kind)
            return "ignored"
        result = _execute_sync_job(
            session,
            task=task,
            job=job,
            span_name=span_name,
            job_kind=job_kind,
            rag_enabled=settings.rag_enabled,
        )
        if drain_lane is None or batch_size <= 1:
            return result

        drained = 1
        while drained < batch_size:
            next_job = _claim_next_sync_job(session, lane=drain_lane)
            if next_job is None:
                break
            if throttle_ms > 0:
                time.sleep(throttle_ms / 1000)
            _execute_sync_job(
                session,
                task=task,
                job=next_job,
                span_name=span_name,
                job_kind=job_kind,
                rag_enabled=settings.rag_enabled,
            )
            drained += 1
        return result
    finally:
        session.close()


def _execute_sync_job(
    session: Session,
    *,
    task,
    job: RagSyncJob,
    span_name: str,
    job_kind: str,
    rag_enabled: bool,
) -> str:
    record_sync_job_lag(
        lag_ms=_job_lag_ms(job.created_at),
        resource_type=job.resource_type,
        resource_id=job.resource_id,
        operation=job.operation,
        job_lane=job.lane,
        job_kind=job_kind,
    )
    with start_as_current_span(
        tracer_name="open_work_hub_worker.rag",
        span_name=span_name,
        kind=SpanKind.CONSUMER,
        parent_trace_context=job.trace_context,
        attributes=rag_span_attributes(
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=job.operation,
            job_id=job.id,
            job_lane=job.lane,
        ),
    ):
        if not rag_enabled:
            logger.info("Skipping RAG sync because RAG is disabled: %s", job.id)
            record_sync_job_result(
                resource_type=job.resource_type,
                resource_id=job.resource_id,
                operation=job.operation,
                job_lane=job.lane,
                status="disabled",
                job_kind=job_kind,
            )
            _mark_sync_job(session, job, status=RagJobStatus.CANCELLED.value)
            return "disabled"
        disabled_app_id = _disabled_app_id_for_job(session, job)
        if disabled_app_id is not None:
            job.attempts = max(job.attempts - 1, 0)
            _mark_sync_job(
                session,
                job,
                status=RagJobStatus.PENDING.value,
                last_error=f"app_disabled:{disabled_app_id}",
            )
            return "app-disabled"
        try:
            stale_reason = _initial_projection_fence_stale_reason(session, job)
            if stale_reason is not None:
                record_sync_job_result(
                    status="superseded",
                    resource_type=job.resource_type,
                    resource_id=job.resource_id,
                    operation=job.operation,
                    job_lane=job.lane,
                    job_kind=job_kind,
                )
                _mark_sync_job(
                    session,
                    job,
                    status=RagJobStatus.CANCELLED.value,
                    last_error=f"superseded_by_projection_head:initial:{stale_reason}",
                )
                return "superseded"
            superseding = _latest_superseding_sync_job(session, job)
            if superseding is not None:
                record_sync_job_result(
                    status="superseded",
                    resource_type=job.resource_type,
                    resource_id=job.resource_id,
                    operation=job.operation,
                    job_lane=job.lane,
                    job_kind=job_kind,
                )
                _cancel_superseded_sync_job(
                    session,
                    job,
                    superseding_job=superseding,
                    phase="before_mutation",
                )
                return "superseded"
            try:
                result = _process_sync_job(session, job)
            except RagAppDisabled as error:
                job.attempts = max(job.attempts - 1, 0)
                _mark_sync_job(
                    session,
                    job,
                    status=RagJobStatus.PENDING.value,
                    last_error=f"app_disabled:{error.app_id}",
                )
                record_sync_job_result(
                    status="app_disabled",
                    resource_type=job.resource_type,
                    resource_id=job.resource_id,
                    operation=job.operation,
                    job_lane=job.lane,
                    job_kind=job_kind,
                )
                return "app-disabled"
            except RagProjectionSuperseded as error:
                record_sync_job_result(
                    status="superseded",
                    resource_type=job.resource_type,
                    resource_id=job.resource_id,
                    operation=job.operation,
                    job_lane=job.lane,
                    job_kind=job_kind,
                )
                _mark_sync_job(
                    session,
                    job,
                    status=RagJobStatus.CANCELLED.value,
                    last_error=f"superseded_by_projection_head:final:{error}",
                )
                return "superseded"
            superseding = _latest_superseding_sync_job(session, job)
            if superseding is not None:
                if superseding.status == RagJobStatus.SUCCEEDED.value:
                    enqueue_rag_sync_job(
                        session,
                        scope_kind=superseding.scope_kind,
                        resource_type=superseding.resource_type,
                        resource_id=superseding.resource_id,
                        operation=RagSyncOperation(superseding.operation),
                        lane=RagSyncLane(superseding.lane),
                        content_checksum=superseding.content_checksum,
                        visibility_checksum=superseding.visibility_checksum,
                        trace_context=superseding.trace_context,
                        projection_event=_projection_event_ref_for_job(
                            session,
                            superseding,
                        ),
                    )
                record_sync_job_result(
                    status="superseded",
                    resource_type=job.resource_type,
                    resource_id=job.resource_id,
                    operation=job.operation,
                    job_lane=job.lane,
                    job_kind=job_kind,
                )
                _cancel_superseded_sync_job(
                    session,
                    job,
                    superseding_job=superseding,
                    phase="after_mutation",
                )
                return "superseded"
            record_sync_job_result(
                status=result,
                resource_type=job.resource_type,
                resource_id=job.resource_id,
                operation=job.operation,
                job_lane=job.lane,
                job_kind=job_kind,
            )
            unsupported = result == "unsupported_resource_type"
            final_status = (
                RagJobStatus.FAILED.value if unsupported else RagJobStatus.SUCCEEDED.value
            )
            _mark_sync_job(
                session,
                job,
                status=final_status,
                last_error=(
                    f"unsupported resource_type: {job.resource_type}" if unsupported else None
                ),
            )
            return result
        except Exception as error:
            return _handle_sync_job_failure(
                session,
                task=task,
                job=job,
                error=error,
                job_kind=job_kind,
            )


@celery_app.task(
    name="rag.recompute_visibility",
    bind=True,
    acks_late=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def recompute_visibility(self, job_id: str) -> str:
    settings = get_settings()
    session = _db_session()
    try:
        job, claim_outcome = _claim_visibility_job(session, job_id)
        if claim_outcome == "missing":
            logger.warning("RAG visibility recompute job not found: %s", job_id)
            record_sync_job_result(status="missing", job_kind="visibility_recompute")
            return "missing"
        if claim_outcome == "app-disabled":
            logger.info(
                "Pausing RAG visibility recompute while its owning app is disabled: %s",
                job_id,
            )
            record_sync_job_result(status="app_disabled", job_kind="visibility_recompute")
            return "app-disabled"
        if claim_outcome != "claimed" or job is None:
            logger.info("Ignoring RAG visibility job already claimed or closed: %s", job_id)
            record_sync_job_result(status="ignored", job_kind="visibility_recompute")
            return "ignored"
        return _execute_visibility_job(
            session,
            task=self,
            job=job,
            rag_enabled=settings.rag_enabled,
        )
    finally:
        session.close()


def _execute_visibility_job(
    session: Session,
    *,
    task,
    job: RagVisibilityRecomputeJob,
    rag_enabled: bool,
) -> str:
    record_sync_job_lag(
        lag_ms=_job_lag_ms(job.created_at),
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        job_kind="visibility_recompute",
    )
    with start_as_current_span(
        tracer_name="open_work_hub_worker.rag",
        span_name="rag.recompute_visibility",
        kind=SpanKind.CONSUMER,
        parent_trace_context=job.trace_context,
        attributes=rag_span_attributes(
            scope_type=job.scope_type,
            scope_id=job.scope_id,
            job_id=job.id,
        ),
    ):
        if not rag_enabled:
            logger.info("Skipping RAG visibility recompute because RAG is disabled: %s", job.id)
            record_sync_job_result(
                status="disabled",
                scope_type=job.scope_type,
                scope_id=job.scope_id,
                job_kind="visibility_recompute",
            )
            _mark_visibility_job(session, job, status=RagJobStatus.CANCELLED.value)
            return "disabled"
        disabled_app_id = _disabled_app_id_for_visibility_job(session, job)
        if disabled_app_id is not None:
            job.attempts = max(job.attempts - 1, 0)
            _mark_visibility_job(
                session,
                job,
                status=RagJobStatus.PENDING.value,
                last_error=f"app_disabled:{disabled_app_id}",
            )
            return "app-disabled"
        try:
            result, last_error = _process_visibility_job(session, job)
            record_sync_job_result(
                status=result,
                scope_type=job.scope_type,
                scope_id=job.scope_id,
                job_kind="visibility_recompute",
            )
            final_status = (
                RagJobStatus.FAILED.value
                if result == "unsupported_scope_type"
                else RagJobStatus.SUCCEEDED.value
            )
            _mark_visibility_job(session, job, status=final_status, last_error=last_error)
            return result
        except Exception as error:
            return _handle_visibility_job_failure(
                session,
                task=task,
                job=job,
                error=error,
            )


def _process_sync_job(session: Session, job: RagSyncJob) -> str:
    disabled_app_id = _disabled_app_id_for_job(session, job)
    if disabled_app_id is not None:
        raise RagAppDisabled(disabled_app_id)
    runtime = _rag_runtime_for_job(session, job)
    collection = runtime.collection
    service = runtime.service
    adapter = _resource_adapter_for_job(job)
    if adapter is None:
        logger.warning("Unsupported RAG resource type: %s", job.resource_type)
        return "unsupported_resource_type"

    if job.operation == RagSyncOperation.DELETE.value:
        _lock_projection_head_for_vector_mutation(session, job)
        service.delete_projection(
            scope_kind=RagScopeKind(job.scope_kind),
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            collection=collection,
            retrieval_partition_id=getattr(job, "retrieval_partition_id", None),
        )
        if adapter.on_projection_deleted is not None:
            adapter.on_projection_deleted(session, job.resource_id)
        logger.info("Deleted RAG projection for %s:%s", job.resource_type, job.resource_id)
        return "deleted"

    projection = _load_projection_for_job(session, job, rag_service=service)
    if projection == "unsupported":
        logger.warning("Unsupported RAG resource type: %s", job.resource_type)
        return "unsupported_resource_type"
    if projection is None:
        _lock_projection_head_for_vector_mutation(session, job)
        service.delete_projection(
            scope_kind=RagScopeKind(job.scope_kind),
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            collection=collection,
            retrieval_partition_id=getattr(job, "retrieval_partition_id", None),
        )
        logger.info(
            "Projection missing during RAG sync; deleted stale vectors for %s:%s",
            job.resource_type,
            job.resource_id,
        )
        if adapter.on_projection_deleted is not None:
            adapter.on_projection_deleted(session, job.resource_id)
        return "deleted_missing_projection"

    _ensure_projection_matches_job(projection, job)
    projection = _projection_with_job_fence(projection, job)
    if adapter.on_projection_prepared_event is not None:
        adapter.on_projection_prepared_event(
            session,
            job.resource_id,
            _projection_event_ref_for_job(session, job),
        )
        session.commit()
        stale_reason = _initial_projection_fence_stale_reason(session, job)
        if stale_reason is not None:
            raise RagProjectionSuperseded(stale_reason)
    elif adapter.on_projection_prepared is not None:
        adapter.on_projection_prepared(session, job.resource_id)
        session.commit()
    disabled_app_id = _disabled_app_id_for_job(session, job)
    if disabled_app_id is not None:
        raise RagAppDisabled(disabled_app_id)
    sync_with_fence = getattr(service, "sync_projection_with_fence", None)
    if callable(sync_with_fence):
        sync_result = sync_with_fence(
            projection,
            collection=collection,
            before_vector_write=lambda: _lock_projection_head_for_vector_mutation(
                session,
                job,
            ),
        )
    else:
        # Test doubles and legacy service wrappers do not expose the split
        # embed/write seam. Lock before their atomic mutation instead.
        _lock_projection_head_for_vector_mutation(session, job)
        sync_result = service.sync_projection(projection, collection=collection)
    if adapter.on_projection_synced is not None:
        adapter.on_projection_synced(session, job.resource_id, sync_result.chunk_count)
    logger.info("Synced RAG projection for %s:%s", job.resource_type, job.resource_id)
    return "succeeded"


def _rag_runtime_for_job(
    session: Session,
    job: RagSyncJob,
) -> _RagProjectionRuntime:
    if job.resource_type != FILE_MANAGER_FILE_RESOURCE_TYPE:
        return _RagProjectionRuntime(
            service=_rag_service(),
            collection=collection_name(),
        )
    settings = get_settings()
    if not settings.files_retrieval_enabled:
        raise PartitionedRetrievalRuntimeUnavailable(reason="operator_gate_disabled")
    if not _file_job_has_complete_projection_fence(job):
        raise PartitionedRetrievalRuntimeUnavailable(reason="unfenced_file_job")
    pair = resolve_active_partitioned_generation_pair(session, settings=settings)
    collection = pair.qdrant_physical_name
    return _RagProjectionRuntime(
        service=build_partitioned_rag_projection_service(
            settings,
            collection=collection,
            providers=provider_bundle(),
        ),
        collection=collection,
    )


def _file_job_has_complete_projection_fence(job: RagSyncJob) -> bool:
    return bool(
        getattr(job, "retrieval_partition_id", None) is not None
        and getattr(job, "projection_event_sequence", None) is not None
        and getattr(job, "projection_version", None) is not None
        and getattr(job, "desired_state", None) in {"active", "deleted"}
    )


def _load_projection_for_job(session: Session, job: RagSyncJob, *, rag_service: RagService):
    adapter = _resource_adapter_for_job(job)
    if adapter is None or adapter.load_projection is None:
        return "unsupported"
    return adapter.load_projection(session, job.resource_id, rag_service)


def _ensure_projection_matches_job(projection, job: RagSyncJob) -> None:
    mismatches = [
        field_name
        for field_name, expected in (
            ("scope_kind", job.scope_kind),
            ("resource_type", job.resource_type),
            ("resource_id", job.resource_id),
        )
        if str(getattr(projection, field_name, "") or "") != str(expected or "")
    ]
    if mismatches:
        raise RagProjectionIdentityError(
            f"RAG projection identity mismatch for job {job.id}: {', '.join(mismatches)}"
        )


def _projection_with_job_fence(projection, job: RagSyncJob):
    retrieval_partition_id = getattr(job, "retrieval_partition_id", None)
    projection_version = getattr(job, "projection_version", None)
    if retrieval_partition_id is None and projection_version is None:
        return projection
    if retrieval_partition_id is None or projection_version is None:
        raise RagProjectionIdentityError("incomplete_job_fence")

    mismatches = [
        field
        for field, current, expected in (
            (
                "retrieval_partition_id",
                getattr(projection, "retrieval_partition_id", None),
                retrieval_partition_id,
            ),
            (
                "projection_version",
                getattr(projection, "projection_version", None),
                projection_version,
            ),
        )
        if current is not None and current != expected
    ]
    if mismatches:
        raise RagProjectionIdentityError(
            f"RAG projection fence mismatch for job {job.id}: {', '.join(mismatches)}"
        )
    return projection.model_copy(
        update={
            "retrieval_partition_id": retrieval_partition_id,
            "projection_version": projection_version,
        }
    )


def _resource_adapter_for_job(job: RagSyncJob):
    ensure_rag_source_adapters_registered()
    return get_rag_resource_adapter(job.resource_type)


def _sync_job_app_enabled(session: Session, job: RagSyncJob) -> bool:
    return _disabled_app_id_for_job(session, job) is None


def _disabled_app_id_for_job(session: Session, job: RagSyncJob) -> str | None:
    adapter = _resource_adapter_for_job(job)
    app_id = getattr(adapter, "app_id", None)
    if not app_id:
        return None
    enabled = is_company_app_enabled(session, app_id)
    return None if enabled else app_id


def _disabled_company_rag_resource_types(session: Session) -> tuple[str, ...]:
    ensure_rag_source_adapters_registered()
    disabled: list[str] = []
    for adapter in rag_resource_adapters():
        app_id = adapter.app_id
        if app_id and not is_company_app_enabled(session, app_id):
            disabled.append(adapter.resource_type)
    return tuple(disabled)


def _process_visibility_job(
    session: Session,
    job: RagVisibilityRecomputeJob,
) -> tuple[str, str | None]:
    adapter = _visibility_scope_adapter_for_job(job)
    if adapter is None:
        logger.warning("Unsupported RAG visibility recompute scope: %s", job.scope_type)
        return "unsupported_scope_type", f"unsupported scope_type: {job.scope_type}"

    resource_ids = [
        str(resource_id) for resource_id in adapter.resource_ids(session, job) if resource_id
    ]
    if not resource_ids:
        logger.info(
            "No affected resources for RAG visibility recompute %s scope: %s",
            adapter.scope_label or adapter.scope_type,
            job.scope_id,
        )
        return "noop", None
    _enqueue_resource_sync_jobs(
        session,
        resource_type=adapter.resource_type,
        resource_ids=resource_ids,
        operation=RagSyncOperation(adapter.operation),
        lane=RagSyncLane(adapter.lane),
    )
    session.commit()
    logger.info(
        "Queued %s RAG sync job(s) for %s scope %s",
        len(resource_ids),
        adapter.scope_label or adapter.scope_type,
        job.scope_id,
    )
    return "queued", None


def _visibility_scope_adapter_for_job(job: RagVisibilityRecomputeJob):
    ensure_rag_source_adapters_registered()
    return get_rag_visibility_scope_adapter(job.scope_type)


def _disabled_app_id_for_visibility_job(
    session: Session,
    job: RagVisibilityRecomputeJob,
) -> str | None:
    visibility_adapter = _visibility_scope_adapter_for_job(job)
    if visibility_adapter is None:
        return None
    ensure_rag_source_adapters_registered()
    resource_adapter = get_rag_resource_adapter(visibility_adapter.resource_type)
    app_id = getattr(resource_adapter, "app_id", None)
    if not app_id:
        return None
    return (
        None
        if is_company_app_enabled(
            session,
            app_id,
        )
        else app_id
    )


def _enqueue_resource_sync_jobs(
    session: Session,
    *,
    resource_type: str,
    resource_ids: list[str],
    operation: RagSyncOperation,
    lane: RagSyncLane = RagSyncLane.REALTIME,
) -> None:
    for resource_id in resource_ids:
        enqueue_rag_sync_job(
            session,
            resource_type=resource_type,
            resource_id=resource_id,
            operation=operation,
            lane=lane,
        )


def _mark_sync_job(
    session: Session,
    job: RagSyncJob,
    *,
    status: str,
    increment_attempts: bool = False,
    last_error: str | None = None,
    next_retry_at: datetime | None = None,
) -> None:
    job.status = status
    if increment_attempts:
        job.attempts += 1
    job.last_error = last_error
    job.next_retry_at = next_retry_at
    session.add(job)
    session.commit()
    _record_sync_queue_depth_snapshot(
        session,
        scope_kind=job.scope_kind,
        lane=job.lane,
    )


def _latest_superseding_sync_job(
    session: Session,
    job: RagSyncJob,
) -> RagSyncJob | None:
    query = select(RagSyncJob).where(
        RagSyncJob.id != job.id,
        RagSyncJob.resource_type == job.resource_type,
        RagSyncJob.resource_id == job.resource_id,
        RagSyncJob.status != RagJobStatus.CANCELLED.value,
    )
    if job.projection_version is None:
        query = query.where(
            RagSyncJob.scope_kind == job.scope_kind,
            RagSyncJob.created_at > job.created_at,
        ).order_by(RagSyncJob.created_at.desc(), RagSyncJob.id.desc())
    else:
        query = query.where(
            RagSyncJob.projection_version.is_not(None),
            RagSyncJob.projection_version > job.projection_version,
        ).order_by(
            RagSyncJob.projection_version.desc(),
            RagSyncJob.created_at.desc(),
            RagSyncJob.id.desc(),
        )
    return session.scalar(query.limit(1))


def _initial_projection_fence_stale_reason(
    session: Session,
    job: RagSyncJob,
) -> str | None:
    try:
        projection_event = _projection_event_ref_for_job(session, job)
    except RagProjectionIdentityError as error:
        return str(error)
    if projection_event is None:
        return None
    head = session.get(
        RetrievalProjectionHead,
        (job.resource_type, job.resource_id),
    )
    return _projection_head_stale_reason(head, job)


def _lock_projection_head_for_vector_mutation(
    session: Session,
    job: RagSyncJob,
) -> None:
    """Recheck company execution policy and serialize against newer source events."""

    disabled_app_id = _disabled_app_id_for_job(session, job)
    if disabled_app_id is not None:
        raise RagAppDisabled(disabled_app_id)
    projection_event = _projection_event_ref_for_job(session, job)
    if projection_event is None:
        return
    head = session.scalar(
        select(RetrievalProjectionHead)
        .where(
            RetrievalProjectionHead.resource_type == job.resource_type,
            RetrievalProjectionHead.resource_id == job.resource_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    stale_reason = _projection_head_stale_reason(head, job)
    if stale_reason is not None:
        raise RagProjectionSuperseded(stale_reason)


def _projection_head_stale_reason(
    head: RetrievalProjectionHead | None,
    job: RagSyncJob,
) -> str | None:
    if head is None:
        return "missing_head"
    mismatches = [
        field
        for field, current, expected in (
            ("projection_version", head.projection_version, job.projection_version),
            (
                "retrieval_partition_id",
                head.retrieval_partition_id,
                job.retrieval_partition_id,
            ),
            ("desired_state", head.desired_state, job.desired_state),
        )
        if current != expected
    ]
    if mismatches:
        return "head_mismatch:" + ",".join(mismatches)
    return None


def _projection_event_ref_for_job(
    session: Session,
    job: RagSyncJob,
) -> ProjectionEventRef | None:
    fence = (
        getattr(job, "retrieval_partition_id", None),
        getattr(job, "projection_event_sequence", None),
        getattr(job, "projection_version", None),
        getattr(job, "desired_state", None),
    )
    if not any(value is not None for value in fence):
        return None
    if not all(value is not None for value in fence):
        raise RagProjectionIdentityError("incomplete_job_fence")
    event = session.get(RetrievalProjectionEvent, job.projection_event_sequence)
    if event is None:
        raise RagProjectionIdentityError("missing_projection_event")
    mismatches = [
        field
        for field, current, expected in (
            ("resource_type", event.resource_type, job.resource_type),
            ("resource_id", event.resource_id, job.resource_id),
            ("projection_version", event.projection_version, job.projection_version),
            (
                "retrieval_partition_id",
                event.retrieval_partition_id,
                job.retrieval_partition_id,
            ),
            ("desired_state", event.desired_state, job.desired_state),
            ("content_checksum", event.content_checksum, job.content_checksum),
            (
                "visibility_checksum",
                event.visibility_checksum,
                job.visibility_checksum,
            ),
        )
        if current != expected
    ]
    if mismatches:
        raise RagProjectionIdentityError("job_event_mismatch:" + ",".join(mismatches))
    return ProjectionEventRef(
        event_sequence=event.event_sequence,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        projection_version=event.projection_version,
        retrieval_partition_id=event.retrieval_partition_id,
        change_kind=event.change_kind,
        desired_state=event.desired_state,
        content_checksum=event.content_checksum,
        visibility_checksum=event.visibility_checksum,
    )


def _cancel_superseded_sync_job(
    session: Session,
    job: RagSyncJob,
    *,
    superseding_job: RagSyncJob,
    phase: str,
) -> None:
    _mark_sync_job(
        session,
        job,
        status=RagJobStatus.CANCELLED.value,
        last_error=f"superseded_by:{superseding_job.id}:{phase}",
    )


def _claim_sync_job(
    session: Session,
    job_id: str,
) -> tuple[RagSyncJob | None, str]:
    existing = session.get(RagSyncJob, job_id)
    if (
        existing is not None
        and existing.status == RagJobStatus.PENDING.value
        and not _sync_job_app_enabled(session, existing)
    ):
        return existing, "app-disabled"

    settings = get_settings()
    now = datetime.now(UTC).replace(tzinfo=None)
    lease_cutoff = now - timedelta(seconds=settings.rag_job_processing_lease_seconds)
    claimed = session.execute(
        update(RagSyncJob)
        .where(
            RagSyncJob.id == job_id,
            _sync_claimable_clause(now=now, lease_cutoff=lease_cutoff),
        )
        .values(
            status=RagJobStatus.PROCESSING.value,
            attempts=RagSyncJob.attempts + 1,
            last_error=None,
            next_retry_at=None,
            updated_at=now,
        )
    )
    session.commit()
    session.expire_all()
    if claimed.rowcount == 1:
        job = session.get(RagSyncJob, job_id)
        if job is not None:
            _record_sync_queue_depth_snapshot(
                session,
                scope_kind=job.scope_kind,
                lane=job.lane,
            )
        return job, "claimed"

    existing = session.get(RagSyncJob, job_id)
    if existing is None:
        return None, "missing"
    return existing, "ignored"


def _mark_visibility_job(
    session: Session,
    job: RagVisibilityRecomputeJob,
    *,
    status: str,
    increment_attempts: bool = False,
    last_error: str | None = None,
    next_retry_at: datetime | None = None,
) -> None:
    job.status = status
    if increment_attempts:
        job.attempts += 1
    job.last_error = last_error
    job.next_retry_at = next_retry_at
    session.add(job)
    session.commit()
    _record_visibility_queue_depth_snapshot(
        session,
    )


def _claim_visibility_job(
    session: Session,
    job_id: str,
) -> tuple[RagVisibilityRecomputeJob | None, str]:
    existing = session.get(RagVisibilityRecomputeJob, job_id)
    if (
        existing is not None
        and existing.status == RagJobStatus.PENDING.value
        and _disabled_app_id_for_visibility_job(session, existing) is not None
    ):
        return existing, "app-disabled"

    settings = get_settings()
    now = datetime.now(UTC).replace(tzinfo=None)
    lease_cutoff = now - timedelta(seconds=settings.rag_job_processing_lease_seconds)
    claimed = session.execute(
        update(RagVisibilityRecomputeJob)
        .where(
            RagVisibilityRecomputeJob.id == job_id,
            _visibility_claimable_clause(now=now, lease_cutoff=lease_cutoff),
        )
        .values(
            status=RagJobStatus.PROCESSING.value,
            attempts=RagVisibilityRecomputeJob.attempts + 1,
            last_error=None,
            next_retry_at=None,
            updated_at=now,
        )
    )
    session.commit()
    session.expire_all()
    if claimed.rowcount == 1:
        job = session.get(RagVisibilityRecomputeJob, job_id)
        if job is not None:
            _record_visibility_queue_depth_snapshot(
                session,
            )
        return job, "claimed"

    existing = session.get(RagVisibilityRecomputeJob, job_id)
    if existing is None:
        return None, "missing"
    return existing, "ignored"


def collection_name() -> str:
    return resolve_default_collection_name(get_settings())


def _claim_next_sync_job(
    session: Session,
    *,
    lane: str,
) -> RagSyncJob | None:
    settings = get_settings()
    now = datetime.now(UTC).replace(tzinfo=None)
    lease_cutoff = now - timedelta(seconds=settings.rag_job_processing_lease_seconds)
    disabled_resource_types = _disabled_company_rag_resource_types(session)
    query = select(RagSyncJob.id).where(
        RagSyncJob.lane == lane,
        _sync_claimable_clause(now=now, lease_cutoff=lease_cutoff),
    )
    if disabled_resource_types:
        query = query.where(RagSyncJob.resource_type.not_in(disabled_resource_types))
    candidate_ids = list(
        session.scalars(
            query.order_by(RagSyncJob.created_at.asc(), RagSyncJob.id.asc()).limit(
                max(settings.rag_backfill_batch_size, 1)
            )
        )
    )
    for candidate_id in candidate_ids:
        job, outcome = _claim_sync_job(session, candidate_id)
        if outcome == "claimed":
            return job
    return None


def _sync_claimable_clause(*, now: datetime, lease_cutoff: datetime):
    return or_(
        and_(
            RagSyncJob.status == RagJobStatus.PENDING.value,
            or_(RagSyncJob.next_retry_at.is_(None), RagSyncJob.next_retry_at <= now),
        ),
        and_(
            RagSyncJob.status == RagJobStatus.PROCESSING.value,
            RagSyncJob.updated_at <= lease_cutoff,
        ),
    )


def _visibility_claimable_clause(*, now: datetime, lease_cutoff: datetime):
    return or_(
        and_(
            RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value,
            or_(
                RagVisibilityRecomputeJob.next_retry_at.is_(None),
                RagVisibilityRecomputeJob.next_retry_at <= now,
            ),
        ),
        and_(
            RagVisibilityRecomputeJob.status == RagJobStatus.PROCESSING.value,
            RagVisibilityRecomputeJob.updated_at <= lease_cutoff,
        ),
    )


def _due_pending_rag_publications(
    session: Session,
    *,
    limit: int,
) -> list[RagJobPublication]:
    remaining = max(int(limit), 1)
    publications: list[RagJobPublication] = []
    now = datetime.now(UTC).replace(tzinfo=None)
    lease_cutoff = now - timedelta(seconds=get_settings().rag_job_processing_lease_seconds)

    disabled_resource_types = _disabled_company_rag_resource_types(session)
    sync_query = select(RagSyncJob).where(
        _sync_claimable_clause(now=now, lease_cutoff=lease_cutoff),
    )
    if disabled_resource_types:
        sync_query = sync_query.where(RagSyncJob.resource_type.not_in(disabled_resource_types))
    sync_jobs = list(
        session.scalars(
            sync_query.order_by(
                RagSyncJob.updated_at.asc(),
                RagSyncJob.created_at.asc(),
                RagSyncJob.id.asc(),
            ).limit(remaining)
        )
    )
    publications.extend(RagJobPublication.sync(job_id=job.id, lane=job.lane) for job in sync_jobs)
    remaining -= len(sync_jobs)
    if remaining <= 0:
        return publications

    visibility_jobs = list(
        session.scalars(
            select(RagVisibilityRecomputeJob)
            .where(
                _visibility_claimable_clause(now=now, lease_cutoff=lease_cutoff),
            )
            .order_by(
                RagVisibilityRecomputeJob.updated_at.asc(),
                RagVisibilityRecomputeJob.created_at.asc(),
                RagVisibilityRecomputeJob.id.asc(),
            )
            .limit(remaining)
        )
    )
    publications.extend(
        RagJobPublication.visibility_recompute(job_id=job.id) for job in visibility_jobs
    )
    return publications


def _publish_rag_job_publication(publication: RagJobPublication) -> None:
    target = resolve_publication_target(publication)
    celery_app.signature(
        target.task_name,
        args=[publication.job_id],
        immutable=True,
    ).apply_async(
        queue=target.queue,
        retry=False,
    )


def _handle_sync_job_failure(
    session: Session,
    *,
    task,
    job: RagSyncJob,
    error: Exception,
    job_kind: str,
) -> str:
    settings = get_settings()
    error_text = str(error)
    retrieval_failure_phase = str(getattr(error, "retrieval_failure_phase", "rag"))
    adapter = _resource_adapter_for_job(job)
    if _is_files_operator_gate_pause(error=error, job=job):
        superseding = _latest_superseding_sync_job(session, job)
        if superseding is not None:
            _cancel_superseded_sync_job(
                session,
                job,
                superseding_job=superseding,
                phase="operator_gate_disabled",
            )
            return "superseded"
        job.status = RagJobStatus.PENDING.value
        job.attempts = max(job.attempts - 1, 0)
        job.last_error = "operator_gate_disabled"
        job.next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            seconds=FILES_OPERATOR_GATE_PAUSE_SECONDS
        )
        session.add(job)
        session.commit()
        _record_sync_queue_depth_snapshot(
            session,
            scope_kind=job.scope_kind,
            lane=job.lane,
        )
        record_sync_job_result(
            status="operator_gate_paused",
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=job.operation,
            job_lane=job.lane,
            job_kind=job_kind,
        )
        logger.info("Paused Files RAG sync job while operator gate is disabled: %s", job.id)
        return "operator_gate_paused"
    if _is_non_retryable_rag_error(error):
        if adapter is not None and adapter.on_projection_failed is not None:
            adapter.on_projection_failed(
                session,
                job.resource_id,
                error_text,
                retrieval_failure_phase,
            )
        record_sync_job_result(
            status="non_retryable_error",
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=job.operation,
            job_lane=job.lane,
            job_kind=job_kind,
        )
        _mark_sync_job(
            session,
            job,
            status=RagJobStatus.CANCELLED.value,
            last_error=f"non_retryable: {error_text}",
        )
        logger.error(
            "Cancelling non-retryable RAG sync job %s after failure: %s", job.id, error_text
        )
        return "non_retryable_error"
    if job.attempts >= settings.rag_job_max_attempts:
        if adapter is not None and adapter.on_projection_failed is not None:
            adapter.on_projection_failed(
                session,
                job.resource_id,
                error_text,
                retrieval_failure_phase,
            )
        record_sync_job_result(
            status="dead_letter",
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=job.operation,
            job_lane=job.lane,
            job_kind=job_kind,
        )
        _mark_sync_job(
            session,
            job,
            status=RagJobStatus.CANCELLED.value,
            last_error=f"dead_letter: {error_text}",
        )
        logger.error("Dead-lettered RAG sync job %s after %s attempts", job.id, job.attempts)
        return "dead_letter"

    countdown = _resolve_retry_countdown_seconds(
        error,
        default_backoff_seconds=settings.rag_job_retry_backoff_seconds,
        attempts=job.attempts,
    )
    next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=countdown)
    record_sync_job_result(
        status="retry_scheduled",
        resource_type=job.resource_type,
        resource_id=job.resource_id,
        operation=job.operation,
        job_lane=job.lane,
        job_kind=job_kind,
    )
    try:
        _mark_sync_job(
            session,
            job,
            status=RagJobStatus.PENDING.value,
            last_error=error_text,
            next_retry_at=next_retry_at,
        )
    except IntegrityError:
        session.rollback()
        merged_job = enqueue_rag_sync_job(
            session,
            scope_kind=job.scope_kind,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=RagSyncOperation(job.operation),
            lane=RagSyncLane(job.lane),
            content_checksum=job.content_checksum,
            visibility_checksum=job.visibility_checksum,
            trace_context=job.trace_context,
            projection_event=_projection_event_ref_for_job(session, job),
        )
        current_job = session.get(RagSyncJob, job.id)
        if current_job is not None:
            current_job.status = RagJobStatus.CANCELLED.value
            current_job.last_error = f"merged_retry_into:{merged_job.id}: {error_text}"
            current_job.next_retry_at = None
            session.add(current_job)
            session.commit()
            _record_sync_queue_depth_snapshot(
                session,
                scope_kind=current_job.scope_kind,
                lane=current_job.lane,
            )
        logger.warning(
            "Merged retry for RAG sync job %s into pending job %s after failure: %s",
            job.id,
            merged_job.id,
            error_text,
        )
        return "retry_merged"
    logger.warning(
        "Retrying RAG sync job %s in %ss after failure: %s",
        job.id,
        countdown,
        error_text,
    )
    raise task.retry(exc=error, countdown=countdown)


def _is_files_operator_gate_pause(*, error: Exception, job: RagSyncJob) -> bool:
    return bool(
        job.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE
        and isinstance(error, PartitionedRetrievalRuntimeUnavailable)
        and error.reason == "operator_gate_disabled"
    )


def _handle_visibility_job_failure(
    session: Session,
    *,
    task,
    job: RagVisibilityRecomputeJob,
    error: Exception,
) -> str:
    settings = get_settings()
    error_text = str(error)
    if job.attempts >= settings.rag_job_max_attempts:
        record_sync_job_result(
            status="dead_letter",
            scope_type=job.scope_type,
            scope_id=job.scope_id,
            job_kind="visibility_recompute",
        )
        _mark_visibility_job(
            session,
            job,
            status=RagJobStatus.CANCELLED.value,
            last_error=f"dead_letter: {error_text}",
        )
        logger.error(
            "Dead-lettered RAG visibility job %s after %s attempts",
            job.id,
            job.attempts,
        )
        return "dead_letter"

    countdown = _resolve_retry_countdown_seconds(
        error,
        default_backoff_seconds=settings.rag_job_retry_backoff_seconds,
        attempts=job.attempts,
    )
    next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=countdown)
    job_id = job.id
    scope_type = job.scope_type
    scope_id = job.scope_id
    trace_context = job.trace_context
    cursor = job.cursor
    record_sync_job_result(
        status="retry_scheduled",
        scope_type=scope_type,
        scope_id=scope_id,
        job_kind="visibility_recompute",
    )
    try:
        _mark_visibility_job(
            session,
            job,
            status=RagJobStatus.PENDING.value,
            last_error=error_text,
            next_retry_at=next_retry_at,
        )
    except IntegrityError:
        session.rollback()
        merged_job = _select_pending_visibility_job(
            session,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        if merged_job is None:
            raise
        merged_job.trace_context = trace_context
        merged_job.cursor = merge_recompute_cursor(merged_job.cursor, cursor)
        session.add(merged_job)
        current_job = session.get(RagVisibilityRecomputeJob, job_id)
        if current_job is not None:
            current_job.status = RagJobStatus.CANCELLED.value
            current_job.last_error = f"merged_retry_into:{merged_job.id}: {error_text}"
            current_job.next_retry_at = None
            session.add(current_job)
        session.commit()
        _record_visibility_queue_depth_snapshot(
            session,
        )
        logger.warning(
            "Merged retry for RAG visibility job %s into pending job %s after failure: %s",
            job_id,
            merged_job.id,
            error_text,
        )
        return "retry_merged"
    logger.warning(
        "Retrying RAG visibility job %s in %ss after failure: %s",
        job_id,
        countdown,
        error_text,
    )
    raise task.retry(exc=error, countdown=countdown)


def _select_pending_visibility_job(
    session: Session,
    *,
    scope_type: str,
    scope_id: str,
) -> RagVisibilityRecomputeJob | None:
    return session.scalar(
        select(RagVisibilityRecomputeJob)
        .where(
            RagVisibilityRecomputeJob.scope_type == scope_type,
            RagVisibilityRecomputeJob.scope_id == scope_id,
            RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value,
        )
        .limit(1)
    )


def _record_sync_queue_depth_snapshot(
    session: Session,
    *,
    scope_kind: str,
    lane: str,
) -> None:
    pending_count = session.scalar(
        select(func.count())
        .select_from(RagSyncJob)
        .where(
            RagSyncJob.scope_kind == scope_kind,
            RagSyncJob.lane == lane,
            RagSyncJob.status == RagJobStatus.PENDING.value,
        )
    )
    record_sync_queue_depth(
        depth=int(pending_count or 0),
        job_lane=lane,
        job_kind="resource_sync" if lane == RagSyncLane.REALTIME.value else "backfill_sync",
    )


def _record_visibility_queue_depth_snapshot(
    session: Session,
) -> None:
    pending_count = session.scalar(
        select(func.count())
        .select_from(RagVisibilityRecomputeJob)
        .where(
            RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value,
        )
    )
    record_sync_queue_depth(
        depth=int(pending_count or 0),
        job_lane="visibility_recompute",
        job_kind="visibility_recompute",
    )


def _is_non_retryable_rag_error(error: Exception) -> bool:
    if isinstance(error, RagProjectionIdentityError):
        return True
    if isinstance(error, RagProviderConfigurationError):
        return True
    if isinstance(error, (RagProviderTransientError, RagProviderTimeoutError)):
        return False
    return isinstance(error, RagProviderError)


def _resolve_retry_countdown_seconds(
    error: Exception,
    *,
    default_backoff_seconds: int,
    attempts: int,
) -> int:
    retry_after_seconds = getattr(error, "retry_after_seconds", None)
    if isinstance(retry_after_seconds, int) and retry_after_seconds > 0:
        return retry_after_seconds
    return default_backoff_seconds * max(attempts, 1)
