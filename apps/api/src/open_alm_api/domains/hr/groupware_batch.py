from __future__ import annotations

from functools import lru_cache

from celery import Celery
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.settings import get_settings
from open_alm_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from open_alm_api.core.worker_queue_contract import (
    GROUPWARE_HR_SYNC_QUEUE,
    GROUPWARE_HR_SYNC_TASK_NAME,
)
from open_alm_api.domains.auth.models import AuditLog
from open_alm_api.domains.hr.history import list_groupware_hr_sync_runs
from open_alm_api.domains.hr.models import HrSyncRun


GROUPWARE_HR_SYNC_AUDIT_ACTION = "hr.groupware.sync"


@lru_cache(maxsize=1)
def get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "open_alm_api_hr",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )


def dispatch_groupware_hr_sync(*, force: bool = True) -> str | None:
    async_result = (
        get_celery_client()
        .signature(
            GROUPWARE_HR_SYNC_TASK_NAME,
            kwargs={"force": force},
            immutable=True,
        )
        .apply_async(
            queue=GROUPWARE_HR_SYNC_QUEUE,
            retry=False,
        )
    )
    return getattr(async_result, "id", None)


def load_latest_groupware_hr_sync_audit(db: Session) -> AuditLog | None:
    return db.scalar(
        select(AuditLog)
        .where(AuditLog.action == GROUPWARE_HR_SYNC_AUDIT_ACTION)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )


def load_latest_groupware_hr_sync_run(db: Session) -> HrSyncRun | None:
    runs = list_groupware_hr_sync_runs(db, limit=1)
    return runs[0] if runs else None
