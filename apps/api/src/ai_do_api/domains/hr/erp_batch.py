from __future__ import annotations

from functools import lru_cache

from celery import Celery
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.core.settings import get_settings
from ai_do_api.core.worker_queue_contract import (
    ERP_HR_SNAPSHOT_QUEUE,
    ERP_HR_SNAPSHOT_TASK_NAME,
)
from ai_do_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from ai_do_api.domains.auth.models import AuditLog
from ai_do_api.domains.hr.erp_snapshot import (
    ERP_EMPLOYEE_SNAPSHOT_AUDIT_ACTION,
    list_erp_hr_snapshot_runs,
)
from ai_do_api.domains.hr.models import HrSyncRun


@lru_cache(maxsize=1)
def get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "ai_do_api_erp_hr",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )


def dispatch_erp_hr_snapshot(*, force: bool = True) -> str | None:
    async_result = (
        get_celery_client()
        .signature(
            ERP_HR_SNAPSHOT_TASK_NAME,
            kwargs={"force": force},
            immutable=True,
        )
        .apply_async(
            queue=ERP_HR_SNAPSHOT_QUEUE,
            retry=False,
        )
    )
    return getattr(async_result, "id", None)


def load_latest_erp_hr_snapshot_audit(db: Session) -> AuditLog | None:
    return db.scalar(
        select(AuditLog)
        .where(AuditLog.action == ERP_EMPLOYEE_SNAPSHOT_AUDIT_ACTION)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )


def load_latest_erp_hr_snapshot_run(db: Session) -> HrSyncRun | None:
    runs = list_erp_hr_snapshot_runs(db, limit=1)
    return runs[0] if runs else None


__all__ = [
    "ERP_HR_SNAPSHOT_QUEUE",
    "ERP_HR_SNAPSHOT_TASK_NAME",
    "dispatch_erp_hr_snapshot",
    "load_latest_erp_hr_snapshot_audit",
    "load_latest_erp_hr_snapshot_run",
]
