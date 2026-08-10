from __future__ import annotations

from functools import lru_cache
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from open_alm_worker.celery_app import celery_app
from open_alm_worker.settings import get_settings as get_worker_settings
from open_alm_api.domains.mail.service import (
    MailSyncRetryScheduled,
    mail_background_sync_enabled,
    process_mail_sync_job,
    publish_due_mail_sync_jobs,
    sync_account,
)


logger = logging.getLogger(__name__)
_MAIL_SYNC_TASK_TIME_LIMIT = get_worker_settings().mail_sync_processing_lease_seconds
_MAIL_SYNC_SOFT_TIME_LIMIT = max(1, _MAIL_SYNC_TASK_TIME_LIMIT - 60)


@lru_cache(maxsize=1)
def _session_factory():
    settings = get_worker_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    return sessionmaker(bind=engine, class_=Session)


@celery_app.task(
    name="mail.sync_job",
    bind=True,
    acks_late=True,
    max_retries=None,
    task_time_limit=_MAIL_SYNC_TASK_TIME_LIMIT,
    task_soft_time_limit=_MAIL_SYNC_SOFT_TIME_LIMIT,
)
def sync_mail_job(self, job_id: str) -> str:
    session = _session_factory()()
    try:
        lease_owner = getattr(getattr(self, "request", None), "id", None)
        return process_mail_sync_job(session, job_id=job_id, lease_owner=lease_owner)
    except MailSyncRetryScheduled as retry:
        logger.warning("mail sync job %s scheduled for retry in %ss", job_id, retry.countdown)
        raise self.retry(exc=retry, countdown=retry.countdown)
    except Exception:
        logger.exception("mail sync task failed for job %s", job_id)
        raise
    finally:
        session.close()


@celery_app.task(
    name="mail.sync_account",
    bind=True,
    acks_late=True,
    max_retries=None,
    task_time_limit=_MAIL_SYNC_TASK_TIME_LIMIT,
    task_soft_time_limit=_MAIL_SYNC_SOFT_TIME_LIMIT,
)
def sync_mail_account(self, account_id: str) -> str:
    del self
    session = _session_factory()()
    try:
        if not mail_background_sync_enabled(session):
            return "cancelled:disabled"
        result = sync_account(session, account_id=account_id)
        return f"synced:{result.changed_count}"
    finally:
        session.close()


@celery_app.task(name="mail.dispatch_due_sync_jobs")
def dispatch_due_sync_jobs() -> str:
    session = _session_factory()()
    try:
        count = publish_due_mail_sync_jobs(session)
        return f"published:{count}"
    finally:
        session.close()
