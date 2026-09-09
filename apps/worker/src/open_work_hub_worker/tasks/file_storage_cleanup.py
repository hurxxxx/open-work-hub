"""Durable cleanup of Files objects that could not be removed inline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from open_work_hub_worker.celery_app import celery_app
from open_work_hub_worker.queue_contract import (
    DEFAULT_QUEUE,
    FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME,
    FILE_STORAGE_CLEANUP_TASK_NAME,
)
from open_work_hub_worker.runtime import (
    db_session as _db_session,
)
from open_work_hub_worker.runtime import (
    ensure_api_src_on_path as _ensure_api_src_on_path,
)
from open_work_hub_worker.runtime import (
    minio_client as _minio_client,
)
from open_work_hub_worker.settings import get_settings

_ensure_api_src_on_path()

from open_work_hub_api.domains.files.models import FileManagerStorageCleanupJob  # noqa: E402

logger = logging.getLogger(__name__)

CLAIM_LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = 30
MAX_RETRY_BACKOFF_SECONDS = 3600
REPUBLISH_BATCH_SIZE = 100
_MISSING_OBJECT_ERROR_CODES = frozenset({"NoSuchKey", "NoSuchObject", "NoSuchVersion"})


@dataclass(frozen=True)
class _CleanupClaim:
    job_id: str
    storage_key: str
    attempt: int


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _safe_error_code(error: Exception) -> str:
    return f"minio_delete:{type(error).__name__}"[:120]


def _is_missing_object_error(error: Exception) -> bool:
    return str(getattr(error, "code", "")) in _MISSING_OBJECT_ERROR_CODES


def _claim_cleanup_job(
    session: Session,
    *,
    job_id: str,
    now: datetime | None = None,
) -> tuple[str, _CleanupClaim | None]:
    claimed_at = now or _utcnow()
    job = session.scalar(
        select(FileManagerStorageCleanupJob)
        .where(
            FileManagerStorageCleanupJob.id == job_id,
            FileManagerStorageCleanupJob.status == "pending",
            or_(
                FileManagerStorageCleanupJob.next_retry_at.is_(None),
                FileManagerStorageCleanupJob.next_retry_at <= claimed_at,
            ),
        )
        .with_for_update(skip_locked=True)
    )
    if job is None:
        session.rollback()
        current = session.get(FileManagerStorageCleanupJob, job_id)
        if current is None:
            return "missing", None
        if current.status != "pending":
            return current.status, None
        return "leased", None

    if job.attempts >= MAX_ATTEMPTS:
        job.status = "failed"
        job.last_error = "dead_letter:max_attempts_exhausted"
        job.next_retry_at = None
        session.add(job)
        session.commit()
        logger.error("Dead-lettered Files storage cleanup job %s before claim", job.id)
        return "dead_letter", None

    job.attempts += 1
    job.next_retry_at = claimed_at + CLAIM_LEASE
    session.add(job)
    session.commit()
    return (
        "claimed",
        _CleanupClaim(
            job_id=job.id,
            storage_key=job.storage_key,
            attempt=job.attempts,
        ),
    )


def _complete_cleanup_job(session: Session, *, claim: _CleanupClaim) -> bool:
    job = session.scalar(
        select(FileManagerStorageCleanupJob)
        .where(FileManagerStorageCleanupJob.id == claim.job_id)
        .with_for_update()
    )
    if job is None or job.status != "pending" or job.attempts != claim.attempt:
        session.rollback()
        return False
    job.status = "succeeded"
    job.last_error = None
    job.next_retry_at = None
    session.add(job)
    session.commit()
    return True


def _fail_cleanup_job(
    session: Session,
    *,
    claim: _CleanupClaim,
    error: Exception,
    now: datetime | None = None,
) -> str:
    failed_at = now or _utcnow()
    job = session.scalar(
        select(FileManagerStorageCleanupJob)
        .where(FileManagerStorageCleanupJob.id == claim.job_id)
        .with_for_update()
    )
    if job is None or job.status != "pending" or job.attempts != claim.attempt:
        session.rollback()
        return "lost_lease"

    error_code = _safe_error_code(error)
    if job.attempts >= MAX_ATTEMPTS:
        job.status = "failed"
        job.last_error = f"dead_letter:{error_code}"
        job.next_retry_at = None
        result = "dead_letter"
    else:
        retry_exponent = max(job.attempts - 2, 0)
        countdown = min(
            RETRY_BACKOFF_SECONDS * (2**retry_exponent),
            MAX_RETRY_BACKOFF_SECONDS,
        )
        job.status = "pending"
        job.last_error = error_code
        job.next_retry_at = failed_at + timedelta(seconds=countdown)
        result = "retry_scheduled"

    session.add(job)
    session.commit()
    return result


@celery_app.task(
    name=FILE_STORAGE_CLEANUP_TASK_NAME,
    acks_late=True,
    task_time_limit=120,
    task_soft_time_limit=90,
)
def cleanup_file_storage_object(job_id: str) -> str:
    """Claim and idempotently delete one deferred Files object."""

    session = _db_session()
    try:
        claim_status, claim = _claim_cleanup_job(session, job_id=job_id)
        if claim is None:
            return claim_status

        try:
            settings = get_settings()
            _minio_client().remove_object(settings.minio_bucket, claim.storage_key)
        except Exception as error:
            if _is_missing_object_error(error):
                completed = _complete_cleanup_job(session, claim=claim)
                return "succeeded" if completed else "lost_lease"
            result = _fail_cleanup_job(session, claim=claim, error=error)
            logger.warning(
                "Files storage cleanup job %s attempt %s failed; outcome=%s error_type=%s",
                claim.job_id,
                claim.attempt,
                result,
                type(error).__name__,
            )
            return result

        completed = _complete_cleanup_job(session, claim=claim)
        return "succeeded" if completed else "lost_lease"
    finally:
        session.close()


def _due_cleanup_job_ids(
    session: Session,
    *,
    limit: int,
    now: datetime | None = None,
) -> list[str]:
    due_at = now or _utcnow()
    return list(
        session.scalars(
            select(FileManagerStorageCleanupJob.id)
            .where(
                FileManagerStorageCleanupJob.status == "pending",
                or_(
                    FileManagerStorageCleanupJob.next_retry_at.is_(None),
                    FileManagerStorageCleanupJob.next_retry_at <= due_at,
                ),
            )
            .order_by(
                FileManagerStorageCleanupJob.created_at.asc(),
                FileManagerStorageCleanupJob.id.asc(),
            )
            .limit(max(1, min(int(limit), 500)))
        )
    )


def _publish_cleanup_job(job_id: str) -> None:
    celery_app.signature(
        FILE_STORAGE_CLEANUP_TASK_NAME,
        args=[job_id],
        immutable=True,
    ).apply_async(queue=DEFAULT_QUEUE, retry=False)


@celery_app.task(
    name=FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME,
    task_time_limit=60,
    task_soft_time_limit=45,
)
def republish_file_storage_cleanup_jobs(limit: int = REPUBLISH_BATCH_SIZE) -> int:
    """Republish new, retryable, and stale-leased cleanup jobs."""

    session = _db_session()
    try:
        job_ids = _due_cleanup_job_ids(session, limit=limit)
    finally:
        session.close()

    for job_id in job_ids:
        _publish_cleanup_job(job_id)
    if job_ids:
        logger.info("Republished %s Files storage cleanup job(s)", len(job_ids))
    return len(job_ids)


__all__ = [
    "cleanup_file_storage_object",
    "republish_file_storage_cleanup_jobs",
]
