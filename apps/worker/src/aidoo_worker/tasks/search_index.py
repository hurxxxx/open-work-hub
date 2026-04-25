from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from aidoo_worker.celery_app import celery_app
from aidoo_worker.settings import get_settings


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

from aidoo_api.domains.search.indexing import process_search_index_job  # noqa: E402
from aidoo_api.domains.search.models import SearchIndexJob  # noqa: E402
from aidoo_api.domains.search.opensearch import OpenSearchKeywordClient  # noqa: E402


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _session_factory():
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    return sessionmaker(bind=engine, class_=Session)


def _db_session() -> Session:
    return _session_factory()()


def _search_client() -> OpenSearchKeywordClient:
    settings = get_settings()
    return OpenSearchKeywordClient(
        base_url=settings.opensearch_url,
        index_prefix=settings.opensearch_index_prefix,
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
        return process_search_index_job(session, job_id, client=_search_client())
    except Exception as error:
        return _handle_job_failure(session, task=self, job_id=job_id, error=error)
    finally:
        session.close()


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
    if _has_superseding_pending_job(session, job=job):
        job.status = "cancelled"
        job.last_error = f"superseded_after_failure: {error_text}"
        job.next_retry_at = None
        job.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(job)
        session.commit()
        logger.warning("Cancelled superseded search index job %s after failure", job.id)
        return "superseded"

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
    session.commit()
    logger.warning("Retrying search index job %s in %ss after failure: %s", job.id, countdown, error_text)
    raise task.retry(exc=error, countdown=countdown)


def _has_superseding_pending_job(session: Session, *, job: SearchIndexJob) -> bool:
    return (
        session.scalar(
            select(SearchIndexJob.id)
            .where(
                SearchIndexJob.id != job.id,
                SearchIndexJob.workspace_id == job.workspace_id,
                SearchIndexJob.entity_type == job.entity_type,
                SearchIndexJob.entity_id == job.entity_id,
                SearchIndexJob.status == "pending",
            )
            .limit(1)
        )
        is not None
    )
