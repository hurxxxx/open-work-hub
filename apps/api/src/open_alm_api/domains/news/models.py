"""SQLAlchemy models for the news aggregator.

News content is global (identical for every user), so these tables are not
workspace-scoped. ``NewsArticle`` holds collected/cached articles per channel;
``NewsRecommendedArticle`` holds global admin/AI recommendations independent of
the rolling cache. ``NewsArticleScrap`` is retained for existing legacy rows but
is no longer exposed by the news app. ``NewsFilterSetting`` is a single-row
table holding the admin-editable keyword and relevance filters.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive

JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('keyword','front','car')",
            name="ck_news_articles_channel",
        ),
        UniqueConstraint("channel", "original_url", name="uq_news_articles_channel_url"),
        Index("ix_news_articles_channel_date", "channel", "published_date"),
        Index(
            "ix_news_articles_channel_published_collected",
            "channel",
            "published_date",
            "collected_at",
        ),
        Index(
            "ix_news_articles_unevaluated_channel_date",
            "channel",
            "published_date",
            "collected_at",
            postgresql_where=text("ai_evaluated = false"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)

    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    images: Mapped[list | None] = mapped_column(JSONB_COMPAT, nullable=True)
    tables: Mapped[list | None] = mapped_column(JSONB_COMPAT, nullable=True)
    article_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # AI 추천 큐레이션이 이미 평가한 기사 여부(저장/거부 무관). True면 재평가하지 않는다.
    ai_evaluated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class NewsRecommendedArticle(Base):
    """전역 추천 뉴스(관리자/AI, 채널 무관, prune 대상 아님).

    수집 캐시(``NewsArticle``)와 독립된 스냅샷이라 원본이 prune 되어도 계속 조회된다.
    ``original_url`` 기준 유니크(중복 추천 방지), 관리자 추천과 AI 추천을 ``origin``으로
    구분한다.
    """

    __tablename__ = "news_recommended_articles"
    __table_args__ = (
        UniqueConstraint("original_url", name="uq_news_recommended_articles_url"),
        Index(
            "ix_news_recommended_origin_date",
            "origin",
            "published_date",
            "recommended_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    keyword: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    recommended_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recommended_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    # 'manual' = 관리자가 직접 추천(추천 뉴스 탭), 'ai' = AI 큐레이션 자동 추천(AI 추천 뉴스 탭).
    origin: Mapped[str] = mapped_column(String(8), default="manual", nullable=False)
    # AI 추천 시 관련성 사유 분류값(유사제품/기술내용/경쟁사). 수동 추천은 빈 문자열.
    reason: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    # AI가 덧붙인 한 줄 근거 설명(선택).
    reason_detail: Mapped[str] = mapped_column(Text, default="", nullable=False)


class NewsArticleScrap(Base):
    """Legacy per-user news scrap snapshot table."""

    __tablename__ = "news_article_scraps"
    __table_args__ = (
        UniqueConstraint("user_id", "original_url", name="uq_news_article_scraps_user_url"),
        Index("ix_news_article_scraps_user_date", "user_id", "scrapped_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    keyword: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    scrapped_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class NewsFilterSetting(Base):
    __tablename__ = "news_filter_settings"

    # Single-row table; ``id`` is always ``"singleton"``.
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default="singleton")
    keyword_filter: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False)
    car_filter: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False)
    keyword_ui_filters: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False)
    # AI 추천 뉴스 큐레이션 기준 프로필(관리자 편집). 빈 문자열이면 cfg.DEFAULT_AI_PROFILE 사용.
    ai_profile: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # AI 큐레이션 자동 실행 on/off.
    ai_curate_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 마지막 AI 큐레이션 실행 시각(수집보다 오래되면 stale → 재실행 트리거).
    ai_curated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )
