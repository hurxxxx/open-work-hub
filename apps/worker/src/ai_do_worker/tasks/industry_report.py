"""Worker task for scheduled industry-report collection.

Crawls the Autojournal (오토저널) and KDI (경제연구 자료) sources and replaces the
cached items for each source in Postgres. Scheduled daily via Celery beat; also
triggered on demand by the admin ``POST /api/v1/industry-report/fetch`` endpoint.
The Trend (자동차 리서치 자료) source is admin-uploaded and not crawled.
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
from ai_do_api.domains.industry_report import service  # noqa: E402
from ai_do_api.domains.news.app_catalog import NEWS_WORKSPACE_APP  # noqa: E402

logger = logging.getLogger(__name__)

_TASK_TIME_LIMIT = 1800
_TASK_SOFT_TIME_LIMIT = 1740


@celery_app.task(
    name="industry_report.collect_all",
    bind=True,
    acks_late=True,
    task_time_limit=_TASK_TIME_LIMIT,
    task_soft_time_limit=_TASK_SOFT_TIME_LIMIT,
)
def collect_all(self, force: bool = False) -> str:
    del self
    settings = get_settings()
    if not settings.industry_report_crawl_enabled and not force:
        return "disabled"

    session = _db_session()
    try:
        if not is_platform_app_enabled(session, NEWS_WORKSPACE_APP.app_id):
            return "cancelled:app-disabled"
        counts = service.run_full_collection(session)
        logger.info(
            "industry_report.collect_all done: autojournal=%s nara=%s material=%s domestic=%s",
            counts.get("autojournal"),
            counts.get("kdi_nara"),
            counts.get("kdi_material"),
            counts.get("kdi_domestic"),
        )
        return "collected:" + ",".join(f"{k}={v}" for k, v in counts.items())
    except Exception:
        session.rollback()
        logger.exception("industry_report.collect_all failed")
        raise
    finally:
        session.close()
