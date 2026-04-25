from __future__ import annotations

from functools import lru_cache
import logging
from typing import Any

from celery import Celery
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.core.telemetry import serialize_current_trace_context
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.search.models import SearchIndexJob
from aidoo_api.domains.search.schemas import SearchEntityType


logger = logging.getLogger(__name__)
PENDING_STATUS = "pending"
_PENDING_SEARCH_PUBLISHES_KEY = "search_index_publish_after_commit"


@lru_cache(maxsize=1)
def _get_celery_client() -> Celery:
    settings = get_settings()
    celery_client = Celery(
        "aidoo_api_search_index",
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


def enqueue_search_index_job(
    db: Session,
    *,
    workspace_id: str,
    entity_type: SearchEntityType | str,
    entity_id: str,
    operation: str = "upsert",
    trace_context: dict[str, Any] | None = None,
) -> SearchIndexJob:
    resolved_entity_type = SearchEntityType(str(entity_type)).value
    if operation not in {"upsert", "delete"}:
        raise ValueError(f"Unsupported search index operation: {operation}")

    resolved_trace_context = serialize_current_trace_context() if trace_context is None else dict(trace_context)
    existing = _select_pending_job(
        db,
        workspace_id=workspace_id,
        entity_type=resolved_entity_type,
        entity_id=entity_id,
    )
    if existing is not None:
        existing.operation = operation
        existing.trace_context = resolved_trace_context
        db.add(existing)
        db.flush()
        _schedule_publish_after_commit(db, job_id=existing.id)
        return existing

    job = SearchIndexJob(
        id=new_id(),
        workspace_id=workspace_id,
        entity_type=resolved_entity_type,
        entity_id=entity_id,
        operation=operation,
        trace_context=resolved_trace_context,
        status=PENDING_STATUS,
        attempts=0,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
        _schedule_publish_after_commit(db, job_id=job.id)
        return job
    except IntegrityError:
        db.expire_all()
        existing = _select_pending_job(
            db,
            workspace_id=workspace_id,
            entity_type=resolved_entity_type,
            entity_id=entity_id,
        )
        if existing is None:
            raise
        existing.operation = operation
        existing.trace_context = resolved_trace_context
        db.add(existing)
        db.flush()
        _schedule_publish_after_commit(db, job_id=existing.id)
        return existing


def _select_pending_job(
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
            SearchIndexJob.status == PENDING_STATUS,
        )
        .order_by(SearchIndexJob.created_at.desc())
        .limit(1)
    )


def _schedule_publish_after_commit(db: Session, *, job_id: str) -> None:
    pending = db.info.setdefault(_PENDING_SEARCH_PUBLISHES_KEY, set())
    if not isinstance(pending, set):
        pending = set()
        db.info[_PENDING_SEARCH_PUBLISHES_KEY] = pending
    pending.add(job_id)


@event.listens_for(Session, "after_commit")
def _publish_pending_search_index_jobs(session: Session) -> None:
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
    session.info.pop(_PENDING_SEARCH_PUBLISHES_KEY, None)


def _publish_job(*, job_id: str) -> None:
    _get_celery_client().signature(
        "search.index_resource",
        args=[job_id],
        immutable=True,
    ).apply_async(
        queue="search_index_realtime",
        retry=False,
    )
