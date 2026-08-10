from __future__ import annotations

from functools import lru_cache

from celery import Celery
from sqlalchemy.orm import Session

from open_alm_api.core.settings import get_settings
from open_alm_api.core.worker_queue_contract import HR_MASTER_QUEUE, HR_MASTER_TASK_NAME
from open_alm_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from open_alm_api.domains.hr.master import list_hr_master_runs
from open_alm_api.domains.hr.models import HrMasterRun


@lru_cache(maxsize=1)
def get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "open_alm_api_hr_master",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )


def dispatch_hr_master_build(
    *,
    force: bool = True,
    erp_run_id: str | None = None,
    groupware_run_id: str | None = None,
) -> str | None:
    if (erp_run_id is None) != (groupware_run_id is None):
        raise ValueError("erp_run_id and groupware_run_id must be provided together")
    task_kwargs: dict[str, object] = {"force": force}
    if erp_run_id is not None and groupware_run_id is not None:
        task_kwargs.update(
            {
                "erp_run_id": erp_run_id,
                "groupware_run_id": groupware_run_id,
            }
        )
    async_result = (
        get_celery_client()
        .signature(
            HR_MASTER_TASK_NAME,
            kwargs=task_kwargs,
            immutable=True,
        )
        .apply_async(
            queue=HR_MASTER_QUEUE,
            retry=False,
        )
    )
    return getattr(async_result, "id", None)


def load_latest_hr_master_run(db: Session) -> HrMasterRun | None:
    runs = list_hr_master_runs(db, limit=1)
    return runs[0] if runs else None


__all__ = [
    "HR_MASTER_QUEUE",
    "HR_MASTER_TASK_NAME",
    "dispatch_hr_master_build",
    "load_latest_hr_master_run",
]
