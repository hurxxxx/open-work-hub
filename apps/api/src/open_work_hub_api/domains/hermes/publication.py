from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from uuid import uuid4

from celery import Celery
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.worker_queue_contract import HERMES_QUEUE, HERMES_RUN_TASK_NAME
from open_work_hub_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from open_work_hub_api.domains.hermes.models import HermesRunProjection
from open_work_hub_api.domains.hermes.repository import (
    TERMINAL_RUN_STATUSES,
    HermesDispatchRepository,
    utcnow_naive,
)


@lru_cache(maxsize=1)
def get_hermes_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "open_work_hub_api_hermes",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )


def publish_pending_hermes_dispatches(
    db: Session,
    *,
    limit: int = 25,
    publisher: Celery | None = None,
) -> int:
    repository = HermesDispatchRepository(db)
    claim_token = uuid4().hex
    claimed = repository.claim_due(claim_token=claim_token, limit=limit)
    publishable = []
    for item in claimed:
        run = db.get(HermesRunProjection, item.run_id)
        if run is None or run.status in TERMINAL_RUN_STATUSES:
            repository.mark_cancelled(
                item.id,
                claim_token=claim_token,
                error_code=f"run_{run.status if run is not None else 'missing'}",
            )
        else:
            publishable.append(item)
    db.commit()
    if not publishable:
        return 0

    try:
        client = publisher or get_hermes_celery_client()
    except Exception as error:
        for item in publishable:
            repository.mark_retry(
                item.id,
                claim_token=claim_token,
                error_code=f"publisher_init.{type(error).__name__}",
                retry_at=utcnow_naive() + timedelta(minutes=1),
            )
        db.commit()
        return 0

    published = 0
    for item in publishable:
        try:
            result = client.send_task(
                HERMES_RUN_TASK_NAME,
                args=[item.run_id],
                queue=HERMES_QUEUE,
            )
            repository.mark_dispatched(
                item.id,
                claim_token=claim_token,
                celery_task_id=str(getattr(result, "id", "") or ""),
            )
            db.commit()
            published += 1
        except Exception as error:
            db.rollback()
            repository.mark_retry(
                item.id,
                claim_token=claim_token,
                error_code=f"publish.{type(error).__name__}",
                retry_at=utcnow_naive() + timedelta(minutes=1),
            )
            db.commit()
    return published


__all__ = ["get_hermes_celery_client", "publish_pending_hermes_dispatches"]
