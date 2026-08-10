from __future__ import annotations

from functools import lru_cache

from celery import Celery

from open_alm_api.core.db import get_session_factory
from open_alm_api.core.settings import get_settings
from open_alm_api.core.worker_queue_contract import (
    QNA_BOARD_SYNC_QUEUE,
    QNA_BOARD_SYNC_TASK_NAME,
)
from open_alm_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from open_alm_api.domains.auth.workspace_app_gate import is_platform_app_enabled
from open_alm_api.domains.qna.app_catalog import QA_ASSISTANT_WORKSPACE_APP


def _qna_app_enabled() -> bool:
    session_factory = get_session_factory()
    with session_factory() as db:
        return is_platform_app_enabled(db, QA_ASSISTANT_WORKSPACE_APP.app_id)


@lru_cache(maxsize=1)
def _get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "open_alm_api_qna",
        broker=settings.worker_broker_url,
        ignore_result=True,
    )


def dispatch_board_sync() -> str | None:
    """Enqueue the groupware board crawl task for the company Q&A corpus."""
    if not _qna_app_enabled():
        return None
    result = _get_celery_client().send_task(
        QNA_BOARD_SYNC_TASK_NAME,
        kwargs={},
        queue=QNA_BOARD_SYNC_QUEUE,
    )
    return getattr(result, "id", None)
