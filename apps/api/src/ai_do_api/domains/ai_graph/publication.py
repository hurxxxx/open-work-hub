from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import uuid4

from celery import Celery
from sqlalchemy.orm import Session

from ai_do_api.core.settings import get_settings
from ai_do_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from ai_do_api.domains.ai_graph.repository import AiGraphDispatchRepository


@lru_cache(maxsize=1)
def get_ai_graph_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "ai_do_api_ai_graph",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )


def publish_pending_graph_dispatches(
    db: Session,
    *,
    limit: int = 25,
    publisher: Celery | None = None,
) -> int:
    """Claim and publish due outbox rows with retryable at-least-once semantics."""

    repository = AiGraphDispatchRepository(db)
    claim_token = uuid4().hex
    claimed = repository.claim_due(claim_token=claim_token, limit=limit)
    db.commit()
    if not claimed:
        return 0

    try:
        client = publisher or get_ai_graph_celery_client()
    except Exception as error:
        for item in claimed:
            repository.mark_retry(
                item.id,
                claim_token=claim_token,
                error_code=f"publisher_init.{type(error).__name__}",
                retry_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=1),
            )
        db.commit()
        return 0
    published = 0
    for item in claimed:
        try:
            result = client.send_task(
                item.task_name,
                args=[item.graph_run_id],
                queue=item.queue_name,
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
                retry_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=1),
            )
            db.commit()
    return published


__all__ = [
    "get_ai_graph_celery_client",
    "publish_pending_graph_dispatches",
]
