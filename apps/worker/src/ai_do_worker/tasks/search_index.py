from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ai_do_worker.celery_app import celery_app
from ai_do_worker.queue_contract import (
    SEARCH_INDEX_REALTIME_QUEUE,
    SEARCH_INDEX_RESOURCE_TASK_NAME,
)
from ai_do_worker.settings import get_settings


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[5]


def _ensure_api_src_on_path() -> None:
    api_src = _workspace_root() / "apps" / "api" / "src"
    if str(api_src) not in sys.path:
        sys.path.insert(0, str(api_src))


_ensure_api_src_on_path()

from ai_do_api.domains.search.indexing import (  # noqa: E402
    SearchProjectionIdentityError,
    UnsupportedSearchEntityError,
    process_search_index_job,
)
from ai_do_api.domains.search.backend_contracts import KeywordSearchClient  # noqa: E402
from ai_do_api.domains.search.backend_factory import build_keyword_search_client  # noqa: E402
from ai_do_api.domains.search.backend_factory import (  # noqa: E402
    build_partitioned_keyword_search_client,
)
from ai_do_api.domains.search.models import SearchIndexJob  # noqa: E402
from ai_do_api.domains.search.schemas import SearchEntityType  # noqa: E402
from ai_do_api.domains.retrieval.runtime_binding import (  # noqa: E402
    PartitionedRetrievalRuntimeUnavailable,
    resolve_active_partitioned_generation_pair,
)
from ai_do_api.domains.source_access.resource_types import (  # noqa: E402
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)


logger = logging.getLogger(__name__)
OUTBOX_REPUBLISH_BATCH_SIZE = 100
FILES_OPERATOR_GATE_PAUSE_SECONDS = 60


@lru_cache(maxsize=1)
def _session_factory():
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    return sessionmaker(bind=engine, class_=Session)


def _db_session() -> Session:
    return _session_factory()()


def _search_client() -> KeywordSearchClient:
    return build_keyword_search_client(get_settings())


def _search_client_for_job(
    session: Session,
    job: SearchIndexJob | None,
) -> KeywordSearchClient:
    if job is None or str(job.entity_type) != SearchEntityType.FILE.value:
        return _search_client()
    settings = get_settings()
    if not settings.files_retrieval_enabled:
        raise PartitionedRetrievalRuntimeUnavailable(reason="operator_gate_disabled")
    if not _file_job_has_complete_projection_fence(job):
        raise PartitionedRetrievalRuntimeUnavailable(reason="unfenced_file_job")
    pair = resolve_active_partitioned_generation_pair(session, settings=settings)
    return build_partitioned_keyword_search_client(
        settings,
        physical_index_name=pair.opensearch_physical_name,
    )


def _file_job_has_complete_projection_fence(job: SearchIndexJob) -> bool:
    return bool(
        getattr(job, "resource_type", None) == FILE_MANAGER_FILE_RESOURCE_TYPE
        and getattr(job, "retrieval_partition_id", None) is not None
        and getattr(job, "projection_event_sequence", None) is not None
        and getattr(job, "projection_version", None) is not None
        and getattr(job, "desired_state", None) in {"active", "deleted"}
    )


@celery_app.task(
    name="search.index_resource",
    bind=True,
    acks_late=True,
    task_time_limit=300,
    task_soft_time_limit=240,
)
def index_resource(self, job_id: str) -> str:
    session = _db_session()
    try:
        job = session.get(SearchIndexJob, job_id)
        return process_search_index_job(
            session,
            job_id,
            client=_search_client_for_job(session, job),
        )
    except Exception as error:
        return _handle_job_failure(session, task=self, job_id=job_id, error=error)
    finally:
        session.close()


@celery_app.task(
    name="search.republish_pending_index_jobs",
    task_time_limit=60,
    task_soft_time_limit=45,
)
def republish_pending_index_jobs(limit: int = OUTBOX_REPUBLISH_BATCH_SIZE) -> int:
    session = _db_session()
    try:
        job_ids = _due_pending_search_job_ids(session, limit=limit)
    finally:
        session.close()

    for job_id in job_ids:
        _publish_search_index_job(job_id)
    if job_ids:
        logger.info("Republished %s pending search index job(s)", len(job_ids))
    return len(job_ids)


def _handle_job_failure(
    session: Session,
    *,
    task,
    job_id: str,
    error: Exception,
) -> str:
    session.rollback()
    job = session.get(SearchIndexJob, job_id)
    if job is None:
        logger.warning("Search index job not found after failure: %s", job_id)
        return "missing"

    settings = get_settings()
    error_text = str(error)
    if _is_files_operator_gate_pause(error=error, job=job):
        if _has_superseding_pending_job(session, job=job):
            job.status = "cancelled"
            job.last_error = "superseded_while_operator_gate_disabled"
            job.next_retry_at = None
            job.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(job)
            session.commit()
            return "superseded"
        job.status = "pending"
        job.last_error = "operator_gate_disabled"
        job.next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            seconds=FILES_OPERATOR_GATE_PAUSE_SECONDS
        )
        job.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(job)
        session.commit()
        logger.info("Paused Files search index job while operator gate is disabled: %s", job.id)
        return "operator_gate_paused"
    if isinstance(error, (UnsupportedSearchEntityError, SearchProjectionIdentityError)):
        job.status = "failed"
        error_prefix = (
            "projection_identity_mismatch"
            if isinstance(error, SearchProjectionIdentityError)
            else "unsupported_entity_type"
        )
        job.last_error = f"{error_prefix}: {error_text}"
        job.next_retry_at = None
        job.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(job)
        session.commit()
        logger.error("Failed non-retryable search index job %s: %s", job.id, error_text)
        return error_prefix

    if _has_superseding_pending_job(session, job=job):
        job.status = "cancelled"
        job.last_error = f"superseded_after_failure: {error_text}"
        job.next_retry_at = None
        job.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(job)
        session.commit()
        logger.warning("Cancelled superseded search index job %s after failure", job.id)
        return "superseded"

    _cancel_older_pending_search_index_jobs(session, job=job)

    if job.attempts >= settings.rag_job_max_attempts:
        job.status = "cancelled"
        job.last_error = f"dead_letter: {error_text}"
        job.next_retry_at = None
        job.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(job)
        session.commit()
        logger.error("Dead-lettered search index job %s after %s attempts", job.id, job.attempts)
        return "dead_letter"

    countdown = min(
        settings.rag_job_retry_backoff_seconds * max(job.attempts, 1),
        3600,
    )
    job.status = "pending"
    job.last_error = error_text
    job.next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=countdown)
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        current_job = session.get(SearchIndexJob, job_id)
        if current_job is None:
            logger.warning("Search index job not found while merging retry: %s", job_id)
            return "missing"
        if _has_superseding_pending_job(session, job=current_job):
            current_job.status = "cancelled"
            current_job.last_error = f"superseded_after_retry_conflict: {error_text}"
            current_job.next_retry_at = None
            current_job.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(current_job)
            session.commit()
            logger.warning(
                "Cancelled superseded search index job %s after retry conflict", current_job.id
            )
            return "superseded"
        _cancel_older_pending_search_index_jobs(session, job=current_job)
        current_job.status = "pending"
        current_job.last_error = error_text
        current_job.next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            seconds=countdown
        )
        current_job.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(current_job)
        session.commit()
    logger.warning(
        "Retrying search index job %s in %ss after failure: %s", job.id, countdown, error_text
    )
    raise task.retry(exc=error, countdown=countdown)


def _is_files_operator_gate_pause(*, error: Exception, job: SearchIndexJob) -> bool:
    return bool(
        job.entity_type == SearchEntityType.FILE.value
        and isinstance(error, PartitionedRetrievalRuntimeUnavailable)
        and error.reason == "operator_gate_disabled"
    )


def _has_superseding_pending_job(session: Session, *, job: SearchIndexJob) -> bool:
    return (
        session.scalar(
            select(SearchIndexJob.id)
            .where(
                SearchIndexJob.id != job.id,
                SearchIndexJob.workspace_id == job.workspace_id,
                SearchIndexJob.entity_type == job.entity_type,
                SearchIndexJob.entity_id == job.entity_id,
                SearchIndexJob.created_at > job.created_at,
                SearchIndexJob.status == "pending",
            )
            .limit(1)
        )
        is not None
    )


def _cancel_older_pending_search_index_jobs(session: Session, *, job: SearchIndexJob) -> None:
    stale_jobs = list(
        session.scalars(
            select(SearchIndexJob).where(
                SearchIndexJob.id != job.id,
                SearchIndexJob.workspace_id == job.workspace_id,
                SearchIndexJob.entity_type == job.entity_type,
                SearchIndexJob.entity_id == job.entity_id,
                SearchIndexJob.created_at <= job.created_at,
                SearchIndexJob.status == "pending",
            )
        )
    )
    if not stale_jobs:
        return
    now = datetime.now(UTC).replace(tzinfo=None)
    for stale_job in stale_jobs:
        stale_job.status = "cancelled"
        stale_job.last_error = f"superseded_by:{job.id}:retry"
        stale_job.next_retry_at = None
        stale_job.updated_at = now
        session.add(stale_job)
    session.commit()


def _due_pending_search_job_ids(session: Session, *, limit: int) -> list[str]:
    now = datetime.now(UTC).replace(tzinfo=None)
    return list(
        session.scalars(
            select(SearchIndexJob.id)
            .where(
                SearchIndexJob.status == "pending",
                ((SearchIndexJob.next_retry_at.is_(None)) | (SearchIndexJob.next_retry_at <= now)),
            )
            .order_by(SearchIndexJob.created_at.asc(), SearchIndexJob.id.asc())
            .limit(max(int(limit), 1))
        )
    )


def _publish_search_index_job(job_id: str) -> None:
    celery_app.signature(
        SEARCH_INDEX_RESOURCE_TASK_NAME,
        args=[job_id],
        immutable=True,
    ).apply_async(
        queue=SEARCH_INDEX_REALTIME_QUEUE,
        retry=False,
    )
