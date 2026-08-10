from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from celery import Celery
from sqlalchemy.orm import Session

from ai_do_api.core.worker_queue_contract import (
    RAG_SYNC_BACKFILL_QUEUE,
    RAG_SYNC_BACKFILL_RESOURCE_TASK_NAME,
    RAG_SYNC_REALTIME_QUEUE,
    RAG_SYNC_RESOURCE_TASK_NAME,
    RAG_VISIBILITY_RECOMPUTE_QUEUE,
    RAG_VISIBILITY_RECOMPUTE_TASK_NAME,
)
from ai_do_api.domains.rag.contracts import RagSyncLane


RAG_SYNC_PUBLICATION_KIND = "sync"
RAG_VISIBILITY_PUBLICATION_KIND = "visibility"
_PENDING_RAG_PUBLISHES_KEY = "rag_publish_after_commit"


@dataclass(frozen=True)
class RagJobPublication:
    kind: str
    job_id: str
    lane: str | None = None

    @classmethod
    def sync(cls, *, job_id: str, lane: str) -> RagJobPublication:
        return cls(
            kind=RAG_SYNC_PUBLICATION_KIND,
            job_id=job_id,
            lane=lane,
        )

    @classmethod
    def visibility_recompute(cls, *, job_id: str) -> RagJobPublication:
        return cls(
            kind=RAG_VISIBILITY_PUBLICATION_KIND,
            job_id=job_id,
            lane=None,
        )


@dataclass(frozen=True)
class RagJobPublishTarget:
    task_name: str
    queue: str


RagJobPublisher = Callable[[RagJobPublication], None]


def schedule_rag_job_publication_after_commit(
    db: Session,
    publication: RagJobPublication,
) -> None:
    pending = db.info.setdefault(_PENDING_RAG_PUBLISHES_KEY, set())
    if not isinstance(pending, set):
        pending = set()
        db.info[_PENDING_RAG_PUBLISHES_KEY] = pending
    pending.add(publication)


def sort_rag_job_publications(
    publications: Iterable[RagJobPublication],
) -> list[RagJobPublication]:
    return sorted(
        publications,
        key=lambda publication: (
            publication.kind,
            publication.job_id,
            publication.lane or "",
        ),
    )


def pop_pending_rag_job_publications(session: Session) -> list[RagJobPublication]:
    pending = session.info.pop(_PENDING_RAG_PUBLISHES_KEY, None)
    if not isinstance(pending, set):
        return []
    return sort_rag_job_publications(pending)


def clear_pending_rag_job_publications(session: Session) -> None:
    session.info.pop(_PENDING_RAG_PUBLISHES_KEY, None)


def publish_pending_rag_job_publications_after_commit(
    session: Session,
    *,
    publisher: RagJobPublisher,
    logger: logging.Logger,
) -> None:
    # SQLAlchemy emits after_commit for savepoint releases too. Publishing there
    # can let a worker observe the job before the outer transaction is committed.
    if session.in_nested_transaction():
        return
    for publication in pop_pending_rag_job_publications(session):
        try:
            publisher(publication)
        except Exception:
            logger.warning("Failed to publish RAG job after commit", exc_info=True)


def clear_pending_rag_job_publications_after_rollback(session: Session) -> None:
    if session.in_nested_transaction():
        return
    clear_pending_rag_job_publications(session)


def resolve_publish_target(*, kind: str, lane: str | None) -> RagJobPublishTarget:
    if kind == RAG_SYNC_PUBLICATION_KIND:
        if lane == RagSyncLane.BACKFILL.value:
            return RagJobPublishTarget(
                task_name=RAG_SYNC_BACKFILL_RESOURCE_TASK_NAME,
                queue=RAG_SYNC_BACKFILL_QUEUE,
            )
        return RagJobPublishTarget(
            task_name=RAG_SYNC_RESOURCE_TASK_NAME,
            queue=RAG_SYNC_REALTIME_QUEUE,
        )
    return RagJobPublishTarget(
        task_name=RAG_VISIBILITY_RECOMPUTE_TASK_NAME,
        queue=RAG_VISIBILITY_RECOMPUTE_QUEUE,
    )


def resolve_publication_target(publication: RagJobPublication) -> RagJobPublishTarget:
    return resolve_publish_target(kind=publication.kind, lane=publication.lane)


def publish_rag_job_publication(
    celery_client: Celery,
    publication: RagJobPublication,
) -> None:
    target = resolve_publication_target(publication)
    celery_client.signature(
        target.task_name,
        args=[publication.job_id],
        immutable=True,
    ).apply_async(
        queue=target.queue,
        retry=False,
    )
