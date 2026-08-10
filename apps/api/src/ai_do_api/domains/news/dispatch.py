"""Enqueue the news collection task onto the Celery worker."""
from __future__ import annotations

from celery import Celery

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.settings import get_settings
from ai_do_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from ai_do_api.core.worker_queue_contract import (
    NEWS_COLLECT_QUEUE,
    NEWS_COLLECT_TASK_NAME,
)
from ai_do_api.domains.auth.workspace_app_gate import is_platform_app_enabled

from .app_catalog import NEWS_WORKSPACE_APP


def _news_app_enabled() -> bool:
    session_factory = get_session_factory()
    with session_factory() as db:
        return is_platform_app_enabled(db, NEWS_WORKSPACE_APP.app_id)


def get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "ai_do_news",
        broker=settings.worker_broker_url,
        ignore_result=True,
    )


def dispatch_collect_all(*, force: bool = False) -> str | None:
    """Send ``news.collect_all`` to the worker; returns the task id if known."""
    if not _news_app_enabled():
        return None
    queue = get_settings().news_collect_queue_override or NEWS_COLLECT_QUEUE
    async_result = get_celery_client().send_task(
        NEWS_COLLECT_TASK_NAME,
        kwargs={"force": force},
        queue=queue,
    )
    return getattr(async_result, "id", None)
