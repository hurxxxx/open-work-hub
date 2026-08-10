"""HTTP router for the news aggregator.

News content is global (not workspace-scoped); registered in ``api_registry``
as a protected ``api`` router (every endpoint requires an authenticated user).
Admin-only endpoints additionally gate on platform-admin role.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session, get_session_factory
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.settings import get_settings
from ai_do_api.domains.auth.access import is_platform_admin_user
from ai_do_api.domains.auth.dependencies import require_current_user
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.auth.workspace_app_gate import (
    is_platform_app_enabled,
    require_platform_app_enabled,
)
from ai_do_api.domains.usage.service import (
    USAGE_EVENT_CONTENT_VIEW,
    USAGE_EVENT_SEARCH_QUERY,
    record_usage_event,
    usage_query_metadata,
)

from . import ai_curator
from . import config_data as cfg
from . import crawler, service
from .app_catalog import NEWS_WORKSPACE_APP
from .dispatch import dispatch_collect_all
from .schemas import (
    NewsAiProfileResponse,
    NewsAiProfileUpdateRequest,
    NewsArticleDetail,
    NewsArticleOut,
    NewsCurateResponse,
    NewsFetchResponse,
    NewsFilterSettings,
    NewsFilterUpdateRequest,
    NewsListResponse,
    NewsRecommendedArticleOut,
    NewsRecommendedListResponse,
    NewsScrapArticleOut,
    NewsScrapListResponse,
    NewsSearchResponse,
    NewsSnapshotRequest,
    NewsStatusResponse,
)

logger = logging.getLogger(__name__)

require_news_app_enabled = require_platform_app_enabled(
    NEWS_WORKSPACE_APP.app_id,
    error_code="platform.app_disabled",
)

router = APIRouter(
    prefix="/news",
    tags=["news"],
    dependencies=[Depends(require_news_app_enabled)],
)
DEFAULT_LIST_PAGE_SIZE = 50

# Throttle background-refresh enqueues so concurrent stale reads don't spam the
# broker (per API process; good enough — duplicate collects are idempotent).
_REFRESH_THROTTLE_SECONDS = 600
_last_refresh_enqueue_monotonic = 0.0


def _maybe_trigger_refresh(collected_at: datetime | None) -> None:
    global _last_refresh_enqueue_monotonic
    settings = get_settings()
    now_naive = datetime.now(UTC).replace(tzinfo=None)
    stale = collected_at is None or (
        now_naive - collected_at > timedelta(hours=settings.news_stale_after_hours)
    )
    if not stale:
        return
    monotonic = time.monotonic()
    if monotonic - _last_refresh_enqueue_monotonic < _REFRESH_THROTTLE_SECONDS:
        return
    _last_refresh_enqueue_monotonic = monotonic
    try:
        dispatch_collect_all()
    except Exception as error:  # noqa: BLE001 - broker best-effort
        logger.warning("news stale-refresh enqueue failed: %s", error)


def _require_admin(
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db_session),
) -> User:
    if not is_platform_admin_user(current_user, db):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="news.admin_only",
        )
    return current_user


def _to_out(row) -> NewsArticleOut:
    return NewsArticleOut(
        keyword=row.keyword,
        source=row.source,
        date=row.published_date,
        title=row.title,
        summary=row.summary or "",
        original_url=row.original_url,
    )


@router.get("/article", response_model=NewsArticleDetail)
def get_article(
    url: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NewsArticleDetail:
    resolved = unquote(url).strip()
    if not resolved:
        raise localized_http_exception(status_code=400, code="news.missing_url")
    crawled = service.get_article_detail(db, resolved, user_id=current_user.id)
    if not crawled:
        raise localized_http_exception(status_code=404, code="news.article_not_found")
    summary = crawled.get("summary") or ""
    if not crawled.get("full_text"):
        summary = summary or ""
    record_usage_event(
        db,
        actor_user_id=current_user.id,
        app_id="news",
        event_type=USAGE_EVENT_CONTENT_VIEW,
        content_kind="news_article",
        content_id=resolved,
        content_title=summary[:120] if summary else None,
        source="news.article",
    )
    db.commit()
    return NewsArticleDetail(
        url=resolved,
        full_text=crawled.get("full_text", ""),
        summary=summary,
        images=crawled.get("images", []),
        tables=crawled.get("tables", []),
    )


@router.get("/search", response_model=NewsSearchResponse)
def search_news(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NewsSearchResponse:
    query = q.strip()
    if not query:
        raise localized_http_exception(status_code=400, code="news.missing_query")
    settings = get_settings()
    items = crawler.search_query(settings.naver_client_id, settings.naver_client_secret, query)
    articles = [
        NewsArticleOut(
            keyword=item["keyword"],
            source=item["source"],
            date=item["date"],
            title=item["title"],
            summary=item.get("summary", ""),
            original_url=item["original_url"],
        )
        for item in items
    ]
    record_usage_event(
        db,
        actor_user_id=current_user.id,
        app_id="news",
        event_type=USAGE_EVENT_SEARCH_QUERY,
        content_kind="news_article",
        source="news.search",
        metadata={**usage_query_metadata(query), "result_count": len(articles)},
    )
    db.commit()
    return NewsSearchResponse(query=query, articles=articles)


@router.get("/filter-settings", response_model=NewsFilterSettings)
def read_filter_settings(db: Session = Depends(get_db_session)) -> NewsFilterSettings:
    return NewsFilterSettings(**service.get_filter_settings(db))


@router.post("/filter-settings", response_model=NewsFilterSettings)
def write_filter_settings(
    payload: NewsFilterUpdateRequest,
    db: Session = Depends(get_db_session),
    _admin: User = Depends(_require_admin),
) -> NewsFilterSettings:
    updated = service.update_filter_settings(
        db,
        keyword_filter=payload.keyword_filter,
        car_filter=payload.car_filter,
        keyword_ui_filters=payload.keyword_ui_filters,
    )
    return NewsFilterSettings(**updated)


@router.post("/fetch", response_model=NewsFetchResponse)
def trigger_fetch(
    _admin: User = Depends(_require_admin),
) -> NewsFetchResponse:
    dispatch_collect_all(force=True)
    return NewsFetchResponse(status="success", message="news.fetch_started")


@router.get("/status", response_model=NewsStatusResponse)
def read_status(db: Session = Depends(get_db_session)) -> NewsStatusResponse:
    return NewsStatusResponse(**service.get_status(db))


def _recommended_to_out(row) -> NewsRecommendedArticleOut:
    return NewsRecommendedArticleOut(
        id=row.id,
        channel=row.channel,
        keyword=row.keyword,
        source=row.source,
        date=row.published_date,
        title=row.title,
        summary=row.summary or "",
        original_url=row.original_url,
        origin=getattr(row, "origin", "manual") or "manual",
        reason=getattr(row, "reason", "") or "",
        reason_detail=getattr(row, "reason_detail", "") or "",
    )


def _scrap_to_out(row) -> NewsScrapArticleOut:
    return NewsScrapArticleOut(
        id=row.id,
        channel=row.channel,
        keyword=row.keyword,
        source=row.source,
        date=row.published_date,
        title=row.title,
        summary=row.summary or "",
        original_url=row.original_url,
    )


# 동시 AI-탭 조회가 큐레이션을 중복 실행하지 않도록 in-process 가드.
_curation_lock = threading.Lock()


def _run_curation_background(actor_user_id: str | None) -> None:
    if not _curation_lock.acquire(blocking=False):
        return  # 이미 실행 중
    try:
        session_factory = get_session_factory()
        with session_factory() as db:
            if not is_platform_app_enabled(db, NEWS_WORKSPACE_APP.app_id):
                return
            ai_curator.curate_recent(db, actor_user_id=actor_user_id)
    except Exception:  # noqa: BLE001 - 백그라운드 best-effort
        logger.exception("news AI curation background run failed")
    finally:
        _curation_lock.release()


@router.get("/recommended", response_model=NewsRecommendedListResponse)
def list_recommended_news(
    db: Session = Depends(get_db_session),
    _user: User = Depends(require_current_user),
) -> NewsRecommendedListResponse:
    rows = service.list_recommended(db, origin="manual")
    return NewsRecommendedListResponse(articles=[_recommended_to_out(r) for r in rows])


@router.get("/ai-recommended", response_model=NewsRecommendedListResponse)
def list_ai_recommended(
    background: BackgroundTasks,
    db: Session = Depends(get_db_session),
    _user: User = Depends(require_current_user),
) -> NewsRecommendedListResponse:
    # 수집 이후 아직 큐레이션 안 했으면 백그라운드로 자동 실행(응답은 즉시 현재 목록).
    if ai_curator.needs_curation(db):
        background.add_task(_run_curation_background, None)
    rows = service.list_recommended(db, origin="ai")
    return NewsRecommendedListResponse(articles=[_recommended_to_out(r) for r in rows])


@router.post("/curate", response_model=NewsCurateResponse)
def curate_now(
    db: Session = Depends(get_db_session),
    admin: User = Depends(_require_admin),
) -> NewsCurateResponse:
    result = ai_curator.curate_recent(db, actor_user_id=admin.id)
    return NewsCurateResponse(
        status="error" if result.get("error") else "success",
        evaluated=result.get("evaluated", 0),
        saved=result.get("saved", 0),
        by_reason=result.get("by_reason", {}),
        error=result.get("error"),
    )


@router.get("/ai-profile", response_model=NewsAiProfileResponse)
def read_ai_profile(
    db: Session = Depends(get_db_session),
    _user: User = Depends(require_current_user),
) -> NewsAiProfileResponse:
    return NewsAiProfileResponse(**ai_curator.get_settings_payload(db))


@router.post("/ai-profile", response_model=NewsAiProfileResponse)
def write_ai_profile(
    payload: NewsAiProfileUpdateRequest,
    db: Session = Depends(get_db_session),
    _admin: User = Depends(_require_admin),
) -> NewsAiProfileResponse:
    updated = ai_curator.update_ai_profile(
        db,
        ai_profile=payload.ai_profile,
        ai_curate_enabled=payload.ai_curate_enabled,
    )
    return NewsAiProfileResponse(**updated)


@router.post(
    "/recommended",
    response_model=NewsRecommendedArticleOut,
    status_code=status.HTTP_201_CREATED,
)
def recommend_news(
    payload: NewsSnapshotRequest,
    db: Session = Depends(get_db_session),
    admin: User = Depends(_require_admin),
) -> NewsRecommendedArticleOut:
    if not payload.original_url.strip() or not payload.title.strip():
        raise localized_http_exception(status_code=400, code="news.missing_url")
    row = service.recommend_article(
        db,
        channel=payload.channel,
        keyword=payload.keyword,
        source=payload.source,
        title=payload.title,
        summary=payload.summary,
        original_url=payload.original_url,
        published_date=payload.date,
        user_id=admin.id,
    )
    return _recommended_to_out(row)


@router.delete("/recommended/{recommended_id}")
def delete_recommended_news(
    recommended_id: str,
    db: Session = Depends(get_db_session),
    _admin: User = Depends(_require_admin),
) -> dict[str, str]:
    if not service.delete_recommended(db, recommended_id):
        raise localized_http_exception(status_code=404, code="news.recommended_not_found")
    return {"status": "deleted"}


@router.get("/scraps", response_model=NewsScrapListResponse)
def list_news_scraps(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NewsScrapListResponse:
    rows = service.list_scraps(db, user_id=current_user.id)
    return NewsScrapListResponse(articles=[_scrap_to_out(r) for r in rows])


@router.post(
    "/scraps",
    response_model=NewsScrapArticleOut,
    status_code=status.HTTP_201_CREATED,
)
def scrap_news(
    payload: NewsSnapshotRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NewsScrapArticleOut:
    if not payload.original_url.strip() or not payload.title.strip():
        raise localized_http_exception(status_code=400, code="news.missing_url")
    row = service.scrap_article(
        db,
        channel=payload.channel,
        keyword=payload.keyword,
        source=payload.source,
        title=payload.title,
        summary=payload.summary,
        original_url=payload.original_url,
        published_date=payload.date,
        user_id=current_user.id,
    )
    return _scrap_to_out(row)


@router.delete("/scraps/{scrap_id}")
def delete_news_scrap(
    scrap_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> dict[str, str]:
    if not service.delete_scrap(db, scrap_id, user_id=current_user.id):
        raise localized_http_exception(status_code=404, code="news.scrap_not_found")
    return {"status": "deleted"}


@router.get("/{channel}", response_model=NewsListResponse)
def list_channel(
    channel: str,
    page: Annotated[int, Query(ge=1)] = 1,
    db: Session = Depends(get_db_session),
) -> NewsListResponse:
    if channel not in cfg.CHANNELS:
        raise localized_http_exception(status_code=404, code="news.unknown_channel")
    rows, collected_at, total = service.list_articles_page(
        db,
        channel,
        limit=DEFAULT_LIST_PAGE_SIZE,
        offset=(page - 1) * DEFAULT_LIST_PAGE_SIZE,
    )
    _maybe_trigger_refresh(collected_at)
    return NewsListResponse(
        channel=channel,
        collected_at=collected_at.strftime("%Y-%m-%d %H:%M") if collected_at else None,
        page=page,
        page_size=DEFAULT_LIST_PAGE_SIZE,
        total=total,
        total_pages=(total + DEFAULT_LIST_PAGE_SIZE - 1) // DEFAULT_LIST_PAGE_SIZE,
        has_next=page * DEFAULT_LIST_PAGE_SIZE < total,
        articles=[_to_out(row) for row in rows],
    )
