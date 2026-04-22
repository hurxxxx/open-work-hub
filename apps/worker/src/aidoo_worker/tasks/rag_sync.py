from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
import logging

from opentelemetry.trace import SpanKind
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from aidoo_api.core.telemetry import start_as_current_span
from aidoo_api.domains.rag.contracts import RagJobStatus, RagSyncOperation
from aidoo_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE, load_native_doc_projection
from aidoo_api.domains.rag.metrics import record_sync_job_lag, record_sync_job_result
from aidoo_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
from aidoo_api.domains.rag.providers.base import RagProviderBundle
from aidoo_api.domains.rag.providers.fake import FakeEmbeddingClient, FakeVectorIndexClient
from aidoo_api.domains.rag.service import RagService
from aidoo_api.domains.rag.telemetry import rag_span_attributes
from aidoo_worker.celery_app import celery_app
from aidoo_worker.settings import get_settings


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.postgres_dsn, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _session_factory():
    return sessionmaker(bind=_engine(), class_=Session)


def _db_session() -> Session:
    return _session_factory()()


@lru_cache(maxsize=1)
def _provider_bundle() -> RagProviderBundle:
    settings = get_settings()
    if settings.rag_embedding_provider != "fake":
        raise RuntimeError(
            f"Unsupported RAG embedding provider for worker scaffold: {settings.rag_embedding_provider}"
        )
    return RagProviderBundle(
        vector_index=FakeVectorIndexClient(),
        embedding=FakeEmbeddingClient(),
    )


@lru_cache(maxsize=1)
def _rag_service() -> RagService:
    providers = _provider_bundle()
    return RagService(
        vector_index=providers.vector_index,
        embedding_client=providers.embedding,
    )


def _job_lag_ms(created_at: datetime) -> int:
    now = datetime.now(UTC).replace(tzinfo=None)
    return max(int((now - created_at).total_seconds() * 1000), 0)


@celery_app.task(
    name="rag.sync_resource",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def sync_resource(self, job_id: str) -> str:
    return _run_sync_job(
        job_id=job_id,
        span_name="rag.sync_resource",
        job_kind="resource_sync",
    )


@celery_app.task(
    name="rag.sync_backfill_resource",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def sync_backfill_resource(self, job_id: str) -> str:
    return _run_sync_job(
        job_id=job_id,
        span_name="rag.sync_backfill_resource",
        job_kind="backfill_sync",
    )


def _run_sync_job(
    *,
    job_id: str,
    span_name: str,
    job_kind: str,
) -> str:
    settings = get_settings()
    session = _db_session()
    try:
        job = session.get(RagSyncJob, job_id)
        if job is None:
            logger.warning("RAG sync job not found: %s", job_id)
            record_sync_job_result(status="missing", job_kind=job_kind)
            return "missing"
        record_sync_job_lag(
            lag_ms=_job_lag_ms(job.created_at),
            workspace_id=job.workspace_id,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=job.operation,
            job_lane=job.lane,
            job_kind=job_kind,
        )
        _mark_sync_job(session, job, status=RagJobStatus.PROCESSING.value, increment_attempts=True)
        with start_as_current_span(
            tracer_name="aidoo_worker.rag",
            span_name=span_name,
            kind=SpanKind.CONSUMER,
            parent_trace_context=job.trace_context,
            attributes=rag_span_attributes(
                workspace_id=job.workspace_id,
                resource_type=job.resource_type,
                resource_id=job.resource_id,
                operation=job.operation,
                job_id=job.id,
                job_lane=job.lane,
            ),
        ):
            if not settings.rag_enabled:
                logger.info("Skipping RAG sync because RAG is disabled: %s", job_id)
                record_sync_job_result(
                    status="disabled",
                    workspace_id=job.workspace_id,
                    resource_type=job.resource_type,
                    resource_id=job.resource_id,
                    operation=job.operation,
                    job_lane=job.lane,
                    job_kind=job_kind,
                )
                _mark_sync_job(session, job, status=RagJobStatus.PENDING.value)
                return "disabled"
            result = _process_sync_job(session, job)
            record_sync_job_result(
                status=result,
                workspace_id=job.workspace_id,
                resource_type=job.resource_type,
                resource_id=job.resource_id,
                operation=job.operation,
                job_lane=job.lane,
                job_kind=job_kind,
            )
            final_status = (
                RagJobStatus.CANCELLED.value
                if result == "unsupported_resource_type"
                else RagJobStatus.SUCCEEDED.value
            )
            _mark_sync_job(session, job, status=final_status)
            return result
    except Exception as error:
        if "job" in locals() and job is not None:
            _mark_sync_job(session, job, status=RagJobStatus.FAILED.value, last_error=str(error))
        raise
    finally:
        session.close()


@celery_app.task(
    name="rag.recompute_visibility",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def recompute_visibility(self, job_id: str) -> str:
    settings = get_settings()
    session = _db_session()
    try:
        job = session.get(RagVisibilityRecomputeJob, job_id)
        if job is None:
            logger.warning("RAG visibility recompute job not found: %s", job_id)
            record_sync_job_result(status="missing", job_kind="visibility_recompute")
            return "missing"
        record_sync_job_lag(
            lag_ms=_job_lag_ms(job.created_at),
            workspace_id=job.workspace_id,
            scope_type=job.scope_type,
            scope_id=job.scope_id,
            job_kind="visibility_recompute",
        )
        with start_as_current_span(
            tracer_name="aidoo_worker.rag",
            span_name="rag.recompute_visibility",
            kind=SpanKind.CONSUMER,
            parent_trace_context=job.trace_context,
            attributes=rag_span_attributes(
                workspace_id=job.workspace_id,
                scope_type=job.scope_type,
                scope_id=job.scope_id,
                job_id=job.id,
            ),
        ):
            if not settings.rag_enabled:
                logger.info("Skipping RAG visibility recompute because RAG is disabled: %s", job_id)
                record_sync_job_result(
                    status="disabled",
                    workspace_id=job.workspace_id,
                    scope_type=job.scope_type,
                    scope_id=job.scope_id,
                    job_kind="visibility_recompute",
                )
                return "disabled"
            logger.info("RAG visibility recompute scaffold invoked: %s", job_id)
            record_sync_job_result(
                status="pending_implementation",
                workspace_id=job.workspace_id,
                scope_type=job.scope_type,
                scope_id=job.scope_id,
                job_kind="visibility_recompute",
            )
            return "pending-implementation"
    finally:
        session.close()


def _process_sync_job(session: Session, job: RagSyncJob) -> str:
    collection = _collection_name(job.resource_type)
    service = _rag_service()

    if job.operation == RagSyncOperation.DELETE.value:
        service.delete_projection(
            workspace_id=job.workspace_id,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            collection=collection,
        )
        logger.info("Deleted RAG projection for %s:%s", job.resource_type, job.resource_id)
        return "deleted"

    if job.resource_type != NATIVE_DOC_RESOURCE_TYPE:
        logger.warning("Unsupported RAG resource type: %s", job.resource_type)
        return "unsupported_resource_type"

    projection = load_native_doc_projection(session, doc_id=job.resource_id)
    if projection is None:
        service.delete_projection(
            workspace_id=job.workspace_id,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            collection=collection,
        )
        logger.info(
            "Projection missing during RAG sync; deleted stale vectors for %s:%s",
            job.resource_type,
            job.resource_id,
        )
        return "deleted_missing_projection"

    service.sync_projection(projection, collection=collection)
    logger.info("Synced RAG projection for %s:%s", job.resource_type, job.resource_id)
    return "succeeded"


def _mark_sync_job(
    session: Session,
    job: RagSyncJob,
    *,
    status: str,
    increment_attempts: bool = False,
    last_error: str | None = None,
) -> None:
    job.status = status
    if increment_attempts:
        job.attempts += 1
    job.last_error = last_error
    session.add(job)
    session.commit()


def _collection_name(resource_type: str) -> str:
    settings = get_settings()
    normalized = resource_type.replace("_", "-")
    return f"{settings.rag_qdrant_collection_prefix}-{normalized}"
