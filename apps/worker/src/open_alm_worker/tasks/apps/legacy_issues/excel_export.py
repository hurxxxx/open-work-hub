from __future__ import annotations

import logging

from open_alm_worker.celery_app import celery_app
from open_alm_worker.queue_contract import (
    LEGACY_ISSUE_EXCEL_EXPORT_CLEANUP_TASK_NAME,
    LEGACY_ISSUE_EXCEL_EXPORT_REPUBLISH_TASK_NAME,
    LEGACY_ISSUE_EXCEL_EXPORT_TASK_NAME,
)
from open_alm_worker.runtime import db_session as _db_session
from open_alm_worker.runtime import minio_client as _minio_client
from open_alm_worker.settings import get_settings

from open_alm_api.domains.legacy_issues.excel_exports import (
    EXCEL_EXPORT_RETRY_DELAY,
    cleanup_expired_excel_export_jobs,
    mark_excel_export_job_for_retry,
    process_excel_export_job,
    republish_pending_excel_export_jobs,
)


logger = logging.getLogger(__name__)


@celery_app.task(
    name=LEGACY_ISSUE_EXCEL_EXPORT_TASK_NAME,
    bind=True,
    acks_late=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
)
def generate_legacy_issue_excel_export(self, job_id: str) -> str:
    session = _db_session()
    try:
        settings = get_settings()
        return process_excel_export_job(
            session,
            job_id=job_id,
            client=_minio_client(),
            bucket_name=settings.minio_bucket,
        )
    except Exception as error:
        should_retry = mark_excel_export_job_for_retry(
            session,
            job_id=job_id,
            error=error,
        )
        if should_retry:
            countdown = max(1, int(EXCEL_EXPORT_RETRY_DELAY.total_seconds()))
            logger.warning(
                "Retrying legacy issue Excel export %s after failure",
                job_id,
                exc_info=True,
            )
            raise self.retry(exc=error, countdown=countdown)
        logger.error(
            "Legacy issue Excel export %s failed permanently",
            job_id,
            exc_info=True,
        )
        return "failed"
    finally:
        session.close()


@celery_app.task(
    name=LEGACY_ISSUE_EXCEL_EXPORT_REPUBLISH_TASK_NAME,
    task_time_limit=120,
    task_soft_time_limit=90,
)
def republish_legacy_issue_excel_exports(limit: int = 100) -> int:
    session = _db_session()
    try:
        return republish_pending_excel_export_jobs(session, limit=limit)
    finally:
        session.close()


@celery_app.task(
    name=LEGACY_ISSUE_EXCEL_EXPORT_CLEANUP_TASK_NAME,
    task_time_limit=600,
    task_soft_time_limit=540,
)
def cleanup_legacy_issue_excel_exports(limit: int = 100) -> dict[str, int]:
    session = _db_session()
    try:
        settings = get_settings()
        return cleanup_expired_excel_export_jobs(
            session,
            client=_minio_client(),
            bucket_name=settings.minio_bucket,
            limit=limit,
        )
    finally:
        session.close()
