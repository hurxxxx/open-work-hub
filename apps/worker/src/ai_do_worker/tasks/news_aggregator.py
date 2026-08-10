"""Worker task for scheduled news collection.

Runs the legacy channels (keyword / front / car) using the Naver API
credentials, then updates cached articles in Postgres. Scheduled via Celery
beat; also triggered on demand by the admin ``POST /api/v1/news/fetch``
endpoint.
"""

from __future__ import annotations

import logging

from ai_do_worker.celery_app import celery_app
from ai_do_worker.runtime import (
    db_session as _db_session,
    ensure_api_src_on_path as _ensure_api_src_on_path,
)
from ai_do_worker.settings import get_settings


_ensure_api_src_on_path()

from ai_do_api.domains.auth.workspace_app_gate import is_platform_app_enabled  # noqa: E402
from ai_do_api.domains.news import service  # noqa: E402
from ai_do_api.domains.news.app_catalog import NEWS_WORKSPACE_APP  # noqa: E402


logger = logging.getLogger(__name__)

_NEWS_TASK_TIME_LIMIT = 1800
_NEWS_TASK_SOFT_TIME_LIMIT = 1740


@celery_app.task(
    name="news.collect_all",
    bind=True,
    acks_late=True,
    task_time_limit=_NEWS_TASK_TIME_LIMIT,
    task_soft_time_limit=_NEWS_TASK_SOFT_TIME_LIMIT,
)
def collect_all(self, force: bool = False) -> str:
    del self
    settings = get_settings()
    if not settings.news_crawl_enabled and not force:
        return "disabled"
    session = _db_session()
    try:
        if not is_platform_app_enabled(session, NEWS_WORKSPACE_APP.app_id):
            return "cancelled:app-disabled"
        counts = service.run_full_collection(
            session, settings.naver_client_id, settings.naver_client_secret
        )
        logger.info(
            "news.collect_all done: keyword=%s front=%s car=%s",
            counts["keyword"],
            counts["front"],
            counts["car"],
        )
        return (
            f"collected:keyword={counts['keyword']},"
            f"front={counts['front']},car={counts['car']}"
        )
    except Exception:
        session.rollback()
        logger.exception("news.collect_all failed")
        raise
    finally:
        session.close()
