"""SQLAlchemy models for the industry-report aggregator.

Like the news aggregator, industry-report content is global (identical for
every user), so these tables are not workspace-scoped.

* ``IndustryReportFile`` — admin-uploaded Trend report files (자동차 리서치
  자료). Bytes live in object storage; this row holds the metadata + storage key.
* ``IndustryReportItem`` — crawled+cached items from the Autojournal and KDI
  sources, one row per external document.
* ``IndustryReportRecommended`` — global admin/AI recommendations, independent
  of the rolling crawled cache.
* ``IndustryReportScrap`` — per-user persistent scraps.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive

JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")

# Keep the CHECK constraint in sync with ``config_data.ITEM_SOURCES``.
_ITEM_SOURCE_CHECK = (
    "source IN ('autojournal','kdi_nara','kdi_material','kdi_domestic')"
)


class IndustryReportFile(Base):
    """A company research file (Trend / 자동차 리서치 자료).

    ``source`` distinguishes admin uploads (``"upload"``) from files pulled by a
    crawler (e.g. ``"katech"``). ``source_key`` holds the crawler's stable
    external id (KATECH ``post_key``) so the collector can skip already-imported
    posts; it is NULL for manual uploads. Because Postgres/SQLite treat NULLs as
    distinct in a unique constraint, multiple uploads coexist under
    ``uq_industry_report_files_company_source_key`` while crawled posts dedup.
    """

    __tablename__ = "industry_report_files"
    __table_args__ = (
        UniqueConstraint(
            "company", "source_key", name="uq_industry_report_files_company_source_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="upload", nullable=False)
    source_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uploaded_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )


class IndustryReportRecommended(Base):
    """전역 추천 산업 리포트(분류 무관, 영구 보관 — 수집/prune과 독립).

    트렌드(자동차연구원 파일)·오토저널·KDI 등 어떤 항목이든 추천할 수 있고,
    ``kind`` 가 미리보기 방식을 결정한다(trend=첨부파일, autojournal=플립북,
    kdi_*=PDF/문서 페이지). ``ref`` 는 중복 저장 방지용 유니크 키
    (트렌드는 ``trend:{file_id}``, 그 외는 원본 ``url``).
    """

    __tablename__ = "industry_report_recommended"
    __table_args__ = (
        UniqueConstraint("ref", name="uq_industry_report_recommended_ref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    ref: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    org: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    published_date: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    # 미리보기 소스: autojournal/kdi 는 원본 url, trend 는 빈 문자열(file_id 사용).
    url: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    # 트렌드(첨부파일) 미리보기용 IndustryReportFile id.
    file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    company: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    # 'manual' = 관리자 추천(추천 산업 리포트), 'ai' = AI 큐레이션(AI 추천 리포트).
    origin: Mapped[str] = mapped_column(String(8), default="manual", nullable=False)
    # AI 추천 시 관련성 사유(유사제품/기술내용/경쟁사). 수동 추천은 빈 문자열.
    reason: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    reason_detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recommended_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recommended_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )


class IndustryReportScrap(Base):
    """사용자별 산업 리포트 스크랩."""

    __tablename__ = "industry_report_scraps"
    __table_args__ = (
        UniqueConstraint("user_id", "ref", name="uq_industry_report_scraps_user_ref"),
        Index("ix_industry_report_scraps_user_date", "user_id", "scrapped_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    ref: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    org: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    published_date: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    url: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    company: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    scrapped_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )


class IndustryReportAiEvaluation(Base):
    """AI 큐레이션 평가 이력.

    관련 없음(relevant=False) 판정도 기록해 같은 리포트를 주기적으로 다시 LLM
    평가하지 않도록 한다. 실제 추천 탭 노출은 ``IndustryReportRecommended`` 가 맡는다.
    """

    __tablename__ = "industry_report_ai_evaluations"
    __table_args__ = (
        UniqueConstraint("ref", name="uq_industry_report_ai_evaluations_ref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ref: Mapped[str] = mapped_column(String(2048), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    relevant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    reason_detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )


class IndustryReportItem(Base):
    """A crawled+cached external item (Autojournal issue or KDI document)."""

    __tablename__ = "industry_report_items"
    __table_args__ = (
        CheckConstraint(_ITEM_SOURCE_CHECK, name="ck_industry_report_items_source"),
        UniqueConstraint("source", "url", name="uq_industry_report_items_source_url"),
        Index("ix_industry_report_items_source_date", "source", "published_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    org: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_date: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    # Source-specific metadata: Autojournal issue_id/cover/pages/year/month, etc.
    extra: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)

    collected_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
