"""Service layer for the news aggregator.

Reads/writes ``NewsArticle`` and the single-row ``NewsFilterSetting``. Article
collection itself runs in the worker (see ``apps/worker`` ``news.collect_all``);
this layer serves the cached rows and performs on-demand article body crawling.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import utcnow_naive
from open_alm_api.domains.auth.security import new_id

from . import config_data as cfg
from . import crawler
from .models import (
    NewsArticle,
    NewsArticleScrap,
    NewsFilterSetting,
    NewsRecommendedArticle,
)

logger = logging.getLogger(__name__)

_SETTINGS_ID = "singleton"
# 키워드·자동차·신문사는 오늘 포함 최근 RECENT_DAYS(14)일 유지.
PRUNE_DAYS = cfg.RECENT_DAYS


# ── Filter settings ──────────────────────────────────────────
def _default_filter_settings() -> dict[str, list[str]]:
    return {
        "keyword_filter": list(cfg.SEARCH_KEYWORDS),
        "car_filter": list(cfg.CAR_KEYWORDS),
        "keyword_ui_filters": list(cfg.DEFAULT_KEYWORD_UI_FILTERS),
    }


def get_or_create_filter_settings(db: Session) -> NewsFilterSetting:
    row = db.get(NewsFilterSetting, _SETTINGS_ID)
    if row is None:
        defaults = _default_filter_settings()
        row = NewsFilterSetting(
            id=_SETTINGS_ID,
            keyword_filter=defaults["keyword_filter"],
            car_filter=defaults["car_filter"],
            keyword_ui_filters=defaults["keyword_ui_filters"],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_filter_settings(db: Session) -> dict[str, list[str]]:
    row = get_or_create_filter_settings(db)
    return {
        "keyword_filter": list(row.keyword_filter),
        "car_filter": list(row.car_filter),
        "keyword_ui_filters": list(row.keyword_ui_filters),
    }


def _clean(words: list[str] | None, fallback: list[str]) -> list[str]:
    if words is None:
        return fallback
    return [w.strip() for w in words if w and w.strip()]


def update_filter_settings(
    db: Session,
    *,
    keyword_filter: list[str] | None,
    car_filter: list[str] | None,
    keyword_ui_filters: list[str] | None,
) -> dict[str, list[str]]:
    row = get_or_create_filter_settings(db)
    row.keyword_filter = _clean(keyword_filter, list(row.keyword_filter))
    row.car_filter = _clean(car_filter, list(row.car_filter))
    row.keyword_ui_filters = _clean(keyword_ui_filters, list(row.keyword_ui_filters))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "keyword_filter": list(row.keyword_filter),
        "car_filter": list(row.car_filter),
        "keyword_ui_filters": list(row.keyword_ui_filters),
    }


# ── Article reads ────────────────────────────────────────────
def list_articles(
    db: Session, channel: str, limit: int = 50
) -> tuple[list[NewsArticle], datetime | None]:
    rows, collected_at, _ = list_articles_page(
        db,
        channel,
        limit=limit,
        offset=0,
    )
    return rows, collected_at


def list_articles_page(
    db: Session,
    channel: str,
    *,
    limit: int,
    offset: int,
) -> tuple[list[NewsArticle], datetime | None, int]:
    filters = [NewsArticle.channel == channel]

    rows = list(
        db.scalars(
            select(NewsArticle)
            .where(*filters)
            .order_by(
                NewsArticle.published_date.desc(),
                NewsArticle.created_at.desc(),
                NewsArticle.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )
    collected_at = db.scalar(
        select(func.max(NewsArticle.collected_at)).where(NewsArticle.channel == channel)
    )
    total = db.scalar(select(func.count()).select_from(NewsArticle).where(*filters)) or 0
    return rows, collected_at, total


def _article_snapshot_for_url(
    db: Session,
    url: str,
) -> NewsRecommendedArticle | NewsArticleScrap | None:
    row = db.scalar(
        select(NewsRecommendedArticle)
        .where(NewsRecommendedArticle.original_url == url)
        .limit(1)
    )
    return row


def get_article_detail(
    db: Session,
    url: str,
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Return the cached body for a collected article, crawling it on demand.

    If the rolling cache was pruned but the URL still exists as a
    recommendation or this user's scrap, return the stored snapshot summary
    instead of 404. We do not crawl arbitrary snapshot-only URLs.
    """
    row = db.scalar(select(NewsArticle).where(NewsArticle.original_url == url).limit(1))
    if row is None:
        snapshot = _article_snapshot_for_url(db, url)
        if snapshot is None and user_id:
            snapshot = db.scalar(
                select(NewsArticleScrap)
                .where(
                    NewsArticleScrap.user_id == user_id,
                    NewsArticleScrap.original_url == url,
                )
                .limit(1)
            )
        if snapshot is None:
            return {}
        return {
            "full_text": "",
            "summary": snapshot.summary or "",
            "images": [],
            "tables": [],
        }
    if row.full_text:
        return {
            "full_text": row.full_text,
            "summary": row.summary or "",
            "images": row.images or [],
            "tables": row.tables or [],
        }

    crawled = crawler.crawl_article(url)
    if row is not None and crawled.get("full_text"):
        row.full_text = crawled["full_text"]
        row.summary = crawled.get("summary") or row.summary
        row.images = crawled.get("images") or []
        row.tables = crawled.get("tables") or []
        row.article_fetched_at = utcnow_naive()
        db.add(row)
        db.commit()
    return crawled


# ── Article writes (worker) ──────────────────────────────────
def upsert_articles(db: Session, channel: str, articles: list[dict]) -> int:
    """Merge a fresh batch into ``channel`` and prune old rows.

    Unlike a wholesale replace, existing rows are updated in place so any
    on-demand-fetched ``full_text``/images stay cached. Rows whose
    ``published_date`` aged out are pruned for the Naver-backed rolling cache.
    """
    now = utcnow_naive()
    cutoff = (datetime.now() - timedelta(days=PRUNE_DAYS)).strftime("%Y-%m-%d")

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in articles:
        url = item.get("original_url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)

    existing = {
        row.original_url: row
        for row in db.scalars(
            select(NewsArticle).where(
                NewsArticle.channel == channel,
                NewsArticle.original_url.in_(seen),
            )
        )
    }

    upserted = 0
    for item in deduped:
        url = item.get("original_url") or ""
        row = existing.get(url)
        if row is None:
            db.add(
                NewsArticle(
                    id=new_id(),
                    channel=channel,
                    keyword=item.get("keyword", "") or "",
                    source=item.get("source", "") or "",
                    title=item.get("title", "") or "",
                    summary=item.get("summary", "") or "",
                    original_url=url,
                    published_date=item.get("date", "") or "",
                    full_text=item.get("full_text") or None,
                    images=item.get("images") or None,
                    tables=item.get("tables") or None,
                    collected_at=now,
                )
            )
        else:
            # Update metadata but preserve cached article bodies.
            row.keyword = item.get("keyword", "") or ""
            row.source = item.get("source", "") or ""
            row.title = item.get("title", "") or row.title
            incoming_summary = item.get("summary", "") or ""
            row.summary = incoming_summary or row.summary
            incoming_full_text = item.get("full_text") or ""
            row.full_text = row.full_text or incoming_full_text or None
            row.published_date = item.get("date", "") or row.published_date
            row.images = row.images or item.get("images") or None
            row.tables = row.tables or item.get("tables") or None
            row.collected_at = now
            db.add(row)
        upserted += 1

    db.execute(
        delete(NewsArticle).where(
            NewsArticle.channel == channel,
            NewsArticle.published_date != "",
            NewsArticle.published_date < cutoff,
        )
    )
    db.commit()
    return upserted


# ── Full collection (worker / local) ─────────────────────────
def run_full_collection(db: Session, client_id: str, client_secret: str) -> dict[str, int]:
    """Collect all news channels and replace their cached rows.

    Shared by the Celery worker task and the local news worker so collection
    behaviour is identical in both. Each channel is collected and committed
    independently: one channel failing (e.g. a Naver rate limit) does not roll
    back or skip the others. A failed channel reports ``-1``.
    """
    filters = get_filter_settings(db)

    def _run(channel: str, collect) -> int:
        try:
            articles = collect()
            return upsert_articles(db, channel, articles)
        except Exception:
            db.rollback()
            logger.exception("news collection failed for channel %s", channel)
            return -1

    counts: dict[str, int] = {}
    if client_id and client_secret:
        counts.update(
            {
                "keyword": _run(
                    "keyword",
                    lambda: crawler.collect_keyword(
                        client_id,
                        client_secret,
                        keyword_filter=filters["keyword_filter"],
                        keyword_ui_filters=filters["keyword_ui_filters"],
                    ),
                ),
                "car": _run(
                    "car",
                    lambda: crawler.collect_car(
                        client_id, client_secret, car_filter=filters["car_filter"]
                    ),
                ),
                "front": _run(
                    "front", lambda: crawler.collect_front(client_id, client_secret)
                ),
            }
        )
    else:
        logger.warning("news collection skipped Naver channels: credentials are not configured")
        counts.update({"keyword": -1, "car": -1, "front": -1})
    return counts


# ── 전역 추천 뉴스 (관리자/AI, 채널 무관, 영구 보관) ──────────
def list_recommended(
    db: Session, *, origin: str | None = None
) -> list[NewsRecommendedArticle]:
    """전역 추천 뉴스 조회.

    ``origin='manual'`` = 관리자 추천(추천 뉴스 탭),
    ``origin='ai'`` = AI 큐레이션(AI 추천 뉴스 탭). None 이면 전체.
    """
    # 최신 뉴스가 상단에 오도록 발행일 우선 정렬(동일 발행일은 저장 시각 최신순).
    stmt = select(NewsRecommendedArticle).order_by(
        NewsRecommendedArticle.published_date.desc(),
        NewsRecommendedArticle.recommended_at.desc(),
    )
    if origin is not None:
        stmt = stmt.where(NewsRecommendedArticle.origin == origin)
    return list(db.scalars(stmt))


def recommended_urls(db: Session) -> set[str]:
    return set(db.scalars(select(NewsRecommendedArticle.original_url)).all())


def recommend_article(
    db: Session,
    *,
    channel: str,
    keyword: str,
    source: str,
    title: str,
    summary: str,
    original_url: str,
    published_date: str,
    user_id: str | None,
    origin: str = "manual",
    reason: str = "",
    reason_detail: str = "",
) -> NewsRecommendedArticle:
    url = (original_url or "").strip()
    row = db.scalar(
        select(NewsRecommendedArticle).where(NewsRecommendedArticle.original_url == url)
    )
    if row is None:
        row = NewsRecommendedArticle(id=new_id(), original_url=url)
        db.add(row)
    row.channel = (channel or "")[:16]
    row.keyword = (keyword or "")[:120]
    row.source = (source or "")[:120]
    row.title = (title or "")[:512]
    row.summary = summary or ""
    row.published_date = (published_date or "")[:10]
    row.recommended_by_id = user_id
    row.origin = (origin or "manual")[:8]
    row.reason = (reason or "")[:16]
    row.reason_detail = reason_detail or ""
    db.commit()
    db.refresh(row)
    return row


def delete_recommended(db: Session, recommended_id: str) -> bool:
    row = db.get(NewsRecommendedArticle, recommended_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ── 사용자별 뉴스 스크랩 ─────────────────────────────────────
def list_scraps(db: Session, *, user_id: str) -> list[NewsArticleScrap]:
    stmt = (
        select(NewsArticleScrap)
        .where(NewsArticleScrap.user_id == user_id)
        .order_by(
            NewsArticleScrap.published_date.desc(),
            NewsArticleScrap.scrapped_at.desc(),
        )
    )
    return list(db.scalars(stmt))


def scrap_article(
    db: Session,
    *,
    channel: str,
    keyword: str,
    source: str,
    title: str,
    summary: str,
    original_url: str,
    published_date: str,
    user_id: str,
) -> NewsArticleScrap:
    url = (original_url or "").strip()
    row = db.scalar(
        select(NewsArticleScrap).where(
            NewsArticleScrap.user_id == user_id,
            NewsArticleScrap.original_url == url,
        )
    )
    if row is None:
        row = NewsArticleScrap(id=new_id(), user_id=user_id, original_url=url)
        db.add(row)
    row.channel = (channel or "")[:16]
    row.keyword = (keyword or "")[:120]
    row.source = (source or "")[:120]
    row.title = (title or "")[:512]
    row.summary = summary or ""
    row.published_date = (published_date or "")[:10]
    db.commit()
    db.refresh(row)
    return row


def delete_scrap(db: Session, scrap_id: str, *, user_id: str) -> bool:
    row = db.get(NewsArticleScrap, scrap_id)
    if row is None or row.user_id != user_id:
        return False
    db.delete(row)
    db.commit()
    return True


# ── Status ───────────────────────────────────────────────────
def get_status(db: Session) -> dict[str, Any]:
    latest = db.scalar(
        select(NewsArticle.collected_at)
        .order_by(NewsArticle.collected_at.desc())
        .limit(1)
    )
    collected_at = latest.strftime("%Y-%m-%d %H:%M") if latest else None
    is_today = bool(latest and latest.strftime("%Y-%m-%d") == datetime.now().strftime("%Y-%m-%d"))
    return {"collecting": False, "collected_at": collected_at, "is_today": is_today}
