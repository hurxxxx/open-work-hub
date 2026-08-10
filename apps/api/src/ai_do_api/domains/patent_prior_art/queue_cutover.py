from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.core.worker_queue_contract import (
    LEGACY_PATENT_PRIOR_ART_QUEUE,
    PATENT_PRIOR_ART_QUEUE,
)
from ai_do_api.domains.patent_prior_art.dispatch import PatentPriorArtJobDispatcher
from ai_do_api.domains.patent_prior_art.models import PatentPriorArtJob
from ai_do_api.domains.patent_prior_art.service import (
    _MAX_DISPATCH_BATCH,
    _utcnow,
    republish_pending_jobs,
)


PATENT_PRIOR_ART_QUEUE_CUTOVER_MARKER = "ai-do:queue-cutover:patent-prior-art-to-server-v1"


class PatentPriorArtQueueBroker(Protocol):
    def delete(self, *names: str) -> int: ...

    def exists(self, name: str) -> int: ...

    def llen(self, name: str) -> int: ...

    def set(self, name: str, value: str) -> object: ...

    def type(self, name: str) -> bytes | str: ...


class PatentPriorArtQueueCutoverError(RuntimeError):
    pass


@dataclass(frozen=True)
class PatentPriorArtQueueCutoverResult:
    cutover_performed: bool
    legacy_messages_removed: int
    jobs_fenced: int
    jobs_published: int
    final_legacy_queue_length: int

    def status_line(self) -> str:
        return (
            "status=ok"
            f" cutover_performed={int(self.cutover_performed)}"
            f" legacy_messages_removed={self.legacy_messages_removed}"
            f" jobs_fenced={self.jobs_fenced}"
            f" jobs_published={self.jobs_published}"
            f" final_legacy_queue_length={self.final_legacy_queue_length}"
        )


@dataclass(frozen=True)
class PatentPriorArtQueueRollbackResult:
    new_messages_removed: int
    legacy_messages_removed: int
    jobs_fenced: int
    jobs_published: int
    final_new_queue_length: int
    final_legacy_queue_length: int

    def status_line(self) -> str:
        return (
            "status=ok"
            f" new_messages_removed={self.new_messages_removed}"
            f" legacy_messages_removed={self.legacy_messages_removed}"
            f" jobs_fenced={self.jobs_fenced}"
            f" jobs_published={self.jobs_published}"
            f" final_new_queue_length={self.final_new_queue_length}"
            f" final_legacy_queue_length={self.final_legacy_queue_length}"
        )


def _decoded_redis_type(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", errors="replace")
    return value


def _fence_active_jobs_for_cutover(
    db: Session,
    *,
    now: datetime,
) -> int:
    rows = list(
        db.scalars(
            select(PatentPriorArtJob)
            .where(
                PatentPriorArtJob.status.in_(("queued", "running")),
                PatentPriorArtJob.deletion_requested_at.is_(None),
            )
            .order_by(PatentPriorArtJob.created_at.asc(), PatentPriorArtJob.id.asc())
            .with_for_update()
        )
    )
    for row in rows:
        row.status = "queued"
        row.stage = "retry_waiting"
        row.failure_code = None
        row.celery_task_id = None
        row.dispatch_published_at = None
        row.execution_id = None
        row.execution_lease_expires_at = None
        row.next_attempt_at = now
        row.completed_at = None
        row.updated_at = now
        db.add(row)
    db.commit()
    return len(rows)


def _require_list_or_missing(
    broker: PatentPriorArtQueueBroker,
    queue_name: str,
) -> None:
    queue_type = _decoded_redis_type(broker.type(queue_name))
    if queue_type not in {"none", "list"}:
        raise PatentPriorArtQueueCutoverError("queue_has_unexpected_type")


def _republish_fenced_jobs(
    db: Session,
    *,
    expected_count: int,
    now: datetime,
    dispatcher: PatentPriorArtJobDispatcher | None = None,
) -> int:
    jobs_published = 0
    while True:
        published = republish_pending_jobs(
            db,
            limit=_MAX_DISPATCH_BATCH,
            now=now,
            dispatcher=dispatcher,
        )
        jobs_published += published
        if published == 0:
            break
    if jobs_published != expected_count:
        raise PatentPriorArtQueueCutoverError("active_jobs_not_fully_republished")
    return jobs_published


def reconcile_patent_prior_art_queue_cutover(
    db: Session,
    broker: PatentPriorArtQueueBroker,
    *,
    now: datetime | None = None,
) -> PatentPriorArtQueueCutoverResult:
    """Empty the legacy queue and republish active jobs with fresh DB fences."""

    cutover_time = now or _utcnow()
    _require_list_or_missing(broker, LEGACY_PATENT_PRIOR_ART_QUEUE)

    legacy_queue_length = int(broker.llen(LEGACY_PATENT_PRIOR_ART_QUEUE))
    marker_exists = bool(broker.exists(PATENT_PRIOR_ART_QUEUE_CUTOVER_MARKER))
    if marker_exists and legacy_queue_length == 0:
        return PatentPriorArtQueueCutoverResult(
            cutover_performed=False,
            legacy_messages_removed=0,
            jobs_fenced=0,
            jobs_published=0,
            final_legacy_queue_length=0,
        )

    jobs_fenced = _fence_active_jobs_for_cutover(db, now=cutover_time)
    broker.delete(LEGACY_PATENT_PRIOR_ART_QUEUE)
    if int(broker.llen(LEGACY_PATENT_PRIOR_ART_QUEUE)) != 0:
        raise PatentPriorArtQueueCutoverError("legacy_queue_not_empty")

    jobs_published = _republish_fenced_jobs(
        db,
        expected_count=jobs_fenced,
        now=cutover_time,
    )

    final_legacy_queue_length = int(broker.llen(LEGACY_PATENT_PRIOR_ART_QUEUE))
    if final_legacy_queue_length != 0:
        raise PatentPriorArtQueueCutoverError("legacy_queue_reappeared")
    if not broker.set(PATENT_PRIOR_ART_QUEUE_CUTOVER_MARKER, "completed"):
        raise PatentPriorArtQueueCutoverError("cutover_marker_not_persisted")

    return PatentPriorArtQueueCutoverResult(
        cutover_performed=True,
        legacy_messages_removed=legacy_queue_length,
        jobs_fenced=jobs_fenced,
        jobs_published=jobs_published,
        final_legacy_queue_length=final_legacy_queue_length,
    )


def rollback_patent_prior_art_queue_cutover(
    db: Session,
    broker: PatentPriorArtQueueBroker,
    *,
    dispatcher: PatentPriorArtJobDispatcher,
    now: datetime | None = None,
) -> PatentPriorArtQueueRollbackResult:
    """Fence active work and republish it to the legacy queue for code rollback."""

    rollback_time = now or _utcnow()
    _require_list_or_missing(broker, PATENT_PRIOR_ART_QUEUE)
    _require_list_or_missing(broker, LEGACY_PATENT_PRIOR_ART_QUEUE)
    new_queue_length = int(broker.llen(PATENT_PRIOR_ART_QUEUE))
    legacy_queue_length = int(broker.llen(LEGACY_PATENT_PRIOR_ART_QUEUE))

    jobs_fenced = _fence_active_jobs_for_cutover(db, now=rollback_time)
    broker.delete(
        PATENT_PRIOR_ART_QUEUE,
        LEGACY_PATENT_PRIOR_ART_QUEUE,
        PATENT_PRIOR_ART_QUEUE_CUTOVER_MARKER,
    )
    if (
        int(broker.llen(PATENT_PRIOR_ART_QUEUE)) != 0
        or int(broker.llen(LEGACY_PATENT_PRIOR_ART_QUEUE)) != 0
    ):
        raise PatentPriorArtQueueCutoverError("rollback_queues_not_empty")

    jobs_published = _republish_fenced_jobs(
        db,
        expected_count=jobs_fenced,
        now=rollback_time,
        dispatcher=dispatcher,
    )
    final_new_queue_length = int(broker.llen(PATENT_PRIOR_ART_QUEUE))
    final_legacy_queue_length = int(broker.llen(LEGACY_PATENT_PRIOR_ART_QUEUE))
    if final_new_queue_length != 0:
        raise PatentPriorArtQueueCutoverError("new_queue_reappeared")
    if final_legacy_queue_length != jobs_published:
        raise PatentPriorArtQueueCutoverError("legacy_queue_publication_mismatch")

    return PatentPriorArtQueueRollbackResult(
        new_messages_removed=new_queue_length,
        legacy_messages_removed=legacy_queue_length,
        jobs_fenced=jobs_fenced,
        jobs_published=jobs_published,
        final_new_queue_length=final_new_queue_length,
        final_legacy_queue_length=final_legacy_queue_length,
    )


__all__ = [
    "PATENT_PRIOR_ART_QUEUE_CUTOVER_MARKER",
    "PatentPriorArtQueueCutoverError",
    "PatentPriorArtQueueRollbackResult",
    "PatentPriorArtQueueCutoverResult",
    "reconcile_patent_prior_art_queue_cutover",
    "rollback_patent_prior_art_queue_cutover",
]
