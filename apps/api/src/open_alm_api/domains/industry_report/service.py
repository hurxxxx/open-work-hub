"""Service layer for the industry-report aggregator.

Trend files are admin-uploaded (bytes in object storage, metadata in
``IndustryReportFile``). Autojournal/KDI items are crawled in the worker (see
``apps/worker`` ``industry_report.collect_all``) and cached in
``IndustryReportItem``; this layer serves the cached rows and performs the
on-demand Autojournal issue-text fetch.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_alm_api.core.settings import get_settings
from open_alm_api.domains.auth.models import utcnow_naive
from open_alm_api.domains.auth.security import new_id

from . import config_data as cfg
from . import crawler, storage
from .models import (
    IndustryReportAiEvaluation,
    IndustryReportFile,
    IndustryReportItem,
    IndustryReportRecommended,
    IndustryReportScrap,
)

logger = logging.getLogger(__name__)


# ── 전역 추천/사용자 스크랩 리포트 ───────────────────────────
def _content_ref(kind: str, *, url: str, file_id: str | None) -> str:
    if kind == "trend":
        return f"trend:{file_id or ''}"
    return (url or "").strip()


def content_ref(kind: str, *, url: str = "", file_id: str | None = None) -> str:
    return _content_ref(kind, url=url, file_id=file_id)


def list_recommended_reports(
    db: Session, *, origin: str | None = None
) -> list[IndustryReportRecommended]:
    """``origin='manual'`` = 관리자 추천 리포트, ``origin='ai'`` = AI 추천 리포트."""
    stmt = select(IndustryReportRecommended).order_by(
        IndustryReportRecommended.published_date.desc(),
        IndustryReportRecommended.recommended_at.desc(),
    )
    if origin is not None:
        stmt = stmt.where(IndustryReportRecommended.origin == origin)
    return list(db.scalars(stmt))


def recommended_refs(db: Session) -> set[str]:
    """이미 추천된(수동/AI) 항목의 ref 집합 — 큐레이션 후보 제외용."""
    return set(db.scalars(select(IndustryReportRecommended.ref)).all())


def ai_evaluated_report_refs(db: Session) -> set[str]:
    """AI가 이미 관련/비관련 판정을 끝낸 리포트 ref 집합."""
    return set(db.scalars(select(IndustryReportAiEvaluation.ref)).all())


def record_ai_report_evaluation(
    db: Session,
    *,
    kind: str,
    url: str,
    file_id: str | None,
    relevant: bool,
    reason: str = "",
    reason_detail: str = "",
) -> IndustryReportAiEvaluation:
    ref = _content_ref(kind, url=url, file_id=file_id)
    row = db.scalar(
        select(IndustryReportAiEvaluation).where(IndustryReportAiEvaluation.ref == ref)
    )
    if row is None:
        row = IndustryReportAiEvaluation(id=new_id(), ref=ref)
        db.add(row)
    row.kind = (kind or "")[:24]
    row.relevant = bool(relevant)
    row.reason = (reason or "")[:16]
    row.reason_detail = reason_detail or ""
    row.evaluated_at = utcnow_naive()
    db.commit()
    db.refresh(row)
    return row


def reset_ai_report_evaluations(db: Session) -> None:
    """회사 프로필 변경 시 기존 AI 리포트 판단 결과를 폐기한다."""
    db.execute(delete(IndustryReportRecommended).where(IndustryReportRecommended.origin == "ai"))
    db.execute(delete(IndustryReportAiEvaluation))


def recommend_report(
    db: Session,
    *,
    kind: str,
    title: str,
    org: str,
    published_date: str,
    url: str,
    file_id: str | None,
    company: str,
    user_id: str | None,
    origin: str = "manual",
    reason: str = "",
    reason_detail: str = "",
) -> IndustryReportRecommended:
    ref = _content_ref(kind, url=url, file_id=file_id)
    row = db.scalar(
        select(IndustryReportRecommended).where(IndustryReportRecommended.ref == ref)
    )
    if row is None:
        row = IndustryReportRecommended(id=new_id(), ref=ref)
        db.add(row)
    row.kind = (kind or "")[:24]
    row.title = (title or "")[:512]
    row.org = (org or "")[:255]
    row.published_date = (published_date or "")[:32]
    row.url = (url or "")[:2048]
    row.file_id = file_id
    row.company = (company or "")[:32]
    row.origin = (origin or "manual")[:8]
    row.reason = (reason or "")[:16]
    row.reason_detail = reason_detail or ""
    row.recommended_by_id = user_id
    db.commit()
    db.refresh(row)
    return row


def delete_recommended_report(db: Session, recommended_id: str) -> bool:
    row = db.get(IndustryReportRecommended, recommended_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def list_scrap_reports(db: Session, *, user_id: str) -> list[IndustryReportScrap]:
    stmt = (
        select(IndustryReportScrap)
        .where(IndustryReportScrap.user_id == user_id)
        .order_by(
            IndustryReportScrap.published_date.desc(),
            IndustryReportScrap.scrapped_at.desc(),
        )
    )
    return list(db.scalars(stmt))


def scrap_report(
    db: Session,
    *,
    kind: str,
    title: str,
    org: str,
    published_date: str,
    url: str,
    file_id: str | None,
    company: str,
    user_id: str,
) -> IndustryReportScrap:
    ref = _content_ref(kind, url=url, file_id=file_id)
    row = db.scalar(
        select(IndustryReportScrap).where(
            IndustryReportScrap.user_id == user_id,
            IndustryReportScrap.ref == ref,
        )
    )
    if row is None:
        row = IndustryReportScrap(id=new_id(), user_id=user_id, ref=ref)
        db.add(row)
    row.kind = (kind or "")[:24]
    row.title = (title or "")[:512]
    row.org = (org or "")[:255]
    row.published_date = (published_date or "")[:32]
    row.url = (url or "")[:2048]
    row.file_id = file_id
    row.company = (company or "")[:32]
    db.commit()
    db.refresh(row)
    return row


def delete_scrap_report(db: Session, scrap_id: str, *, user_id: str) -> bool:
    row = db.get(IndustryReportScrap, scrap_id)
    if row is None or row.user_id != user_id:
        return False
    db.delete(row)
    db.commit()
    return True


# ── Trend files (자동차 리서치 자료) ──────────────────────────
def list_companies(db: Session) -> list[dict[str, Any]]:
    counts = dict(
        db.execute(
            select(IndustryReportFile.company, func.count(IndustryReportFile.id)).group_by(
                IndustryReportFile.company
            )
        ).all()
    )
    return [
        {"code": code, "label": label, "file_count": int(counts.get(code, 0))}
        for code, label in cfg.COMPANY_MAP.items()
    ]


def list_files(db: Session, company: str) -> list[IndustryReportFile]:
    return list(
        db.scalars(
            select(IndustryReportFile)
            .where(IndustryReportFile.company == company)
            .order_by(
                IndustryReportFile.published_date.desc(),
                IndustryReportFile.created_at.desc(),
            )
        )
    )


def create_file(
    db: Session,
    *,
    company: str,
    title: str,
    filename: str,
    data: bytes,
    content_type: str | None,
    uploaded_by_id: str | None,
    published_date: str = "",
) -> IndustryReportFile:
    file_id = new_id()
    storage_key = storage.build_report_storage_key(file_id=file_id, filename=filename)
    row = IndustryReportFile(
        id=file_id,
        company=company,
        title=title or filename,
        filename=filename,
        storage_key=storage_key,
        content_type=content_type or storage.DEFAULT_REPORT_CONTENT_TYPE,
        size_bytes=len(data),
        published_date=published_date or "",
        uploaded_by_id=uploaded_by_id,
    )
    db.add(row)
    db.flush()
    # Upload bytes before committing so a storage failure rolls back the row.
    storage.put_report_object(
        storage_key=storage_key, data=data, content_type=row.content_type
    )
    db.commit()
    db.refresh(row)
    return row


def create_crawled_file(
    db: Session,
    *,
    company: str,
    source: str,
    source_key: str,
    title: str,
    filename: str,
    data: bytes,
    content_type: str,
    published_date: str = "",
) -> IndustryReportFile:
    """Store a crawler-fetched file (e.g. KATECH). Mirrors ``create_file`` but
    tags ``source``/``source_key`` so re-runs dedup by external id."""
    file_id = new_id()
    storage_key = storage.build_report_storage_key(file_id=file_id, filename=filename)
    row = IndustryReportFile(
        id=file_id,
        company=company,
        title=title or filename,
        filename=filename,
        storage_key=storage_key,
        content_type=content_type or storage.DEFAULT_REPORT_CONTENT_TYPE,
        size_bytes=len(data),
        published_date=published_date or "",
        source=source,
        source_key=source_key,
        uploaded_by_id=None,
    )
    db.add(row)
    db.flush()
    storage.put_report_object(storage_key=storage_key, data=data, content_type=row.content_type)
    db.commit()
    db.refresh(row)
    return row


def existing_source_keys(db: Session, company: str) -> set[str]:
    """Return the set of stored ``source_key`` values for ``company``."""
    return {
        key
        for key in db.scalars(
            select(IndustryReportFile.source_key).where(
                IndustryReportFile.company == company,
                IndustryReportFile.source_key.is_not(None),
            )
        )
    }


def collect_katech(
    db: Session,
    *,
    max_pages: int | None = None,
    max_new: int | None = None,
    max_file_bytes: int | None = None,
) -> int:
    """Crawl 자동차연구원 and store any new reports. Returns the count added."""
    existing = existing_source_keys(db, cfg.KATECH_COMPANY)
    kwargs: dict[str, int] = {}
    if max_pages is not None:
        kwargs["max_pages"] = max_pages
    if max_new is not None:
        kwargs["max_new"] = max_new
    kwargs["max_file_bytes"] = (
        max_file_bytes
        if max_file_bytes is not None
        else get_settings().industry_report_crawl_max_file_bytes
    )
    added = 0
    for item in crawler.iter_katech(existing, **kwargs):
        try:
            create_crawled_file(
                db,
                company=cfg.KATECH_COMPANY,
                source=cfg.KATECH_SOURCE,
                source_key=item["source_key"],
                title=item["title"],
                filename=item["filename"],
                data=item["data"],
                content_type=item["content_type"],
                published_date=item["published_date"],
            )
            added += 1
        except IntegrityError:
            db.rollback()
            existing.add(item["source_key"])
            logger.info("KATECH file already exists for %s", item.get("source_key"))
        except Exception:
            db.rollback()
            logger.exception("KATECH file insert failed for %s", item.get("source_key"))
    return added


def get_file(db: Session, file_id: str) -> IndustryReportFile | None:
    return db.get(IndustryReportFile, file_id)


def delete_file(db: Session, file_id: str) -> bool:
    row = db.get(IndustryReportFile, file_id)
    if row is None:
        return False
    storage.remove_report_object(storage_key=row.storage_key)
    db.delete(row)
    db.commit()
    return True


# ── Crawled items (오토저널 / KDI) ────────────────────────────
def list_items(
    db: Session, source: str, keyword: str | None = None, limit: int = 200
) -> tuple[list[IndustryReportItem], datetime | None]:
    stmt = (
        select(IndustryReportItem)
        .where(IndustryReportItem.source == source)
        .order_by(
            IndustryReportItem.published_date.desc(),
            IndustryReportItem.collected_at.desc(),
        )
        .limit(limit)
    )
    rows = list(db.scalars(stmt))
    if keyword:
        needle = keyword.strip().lower()
        rows = [
            r
            for r in rows
            if needle in r.title.lower()
            or needle in (r.org or "").lower()
            or needle == (r.keyword or "").lower()
        ]
    collected_at = max((r.collected_at for r in rows), default=None)
    return rows, collected_at


def replace_items(db: Session, source: str, items: list[dict]) -> int:
    """Replace all cached rows for ``source`` with a fresh batch.

    Items have no on-demand-cached body (Autojournal text is fetched live), so a
    clean replace mirrors the legacy per-source cache overwrite. Deduplicates the
    batch by ``url``.

    An empty batch is treated as "nothing new collected" (e.g. a transient
    upstream failure) and leaves the existing cache untouched rather than wiping
    it.
    """
    if not items:
        return 0

    now = utcnow_naive()
    db.execute(delete(IndustryReportItem).where(IndustryReportItem.source == source))

    seen: set[str] = set()
    inserted = 0
    for item in items:
        url = item.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        db.add(
            IndustryReportItem(
                id=new_id(),
                source=source,
                keyword=item.get("keyword", "") or "",
                title=item.get("title", "") or "",
                org=item.get("org", "") or "",
                summary=item.get("summary", "") or "",
                url=url,
                published_date=item.get("published_date", "") or "",
                extra=item.get("extra"),
                collected_at=now,
            )
        )
        inserted += 1
    db.commit()
    return inserted


def get_autojournal_issue(db: Session, issue_id: str) -> dict | None:
    """Fetch + parse one Autojournal issue's page text on demand."""
    return crawler.fetch_autojournal_issue_text(issue_id)


# ── Full collection (worker / local) ─────────────────────────
def run_full_collection(db: Session) -> dict[str, int]:
    """Collect all crawled sources and replace their cached rows.

    Each source is collected and committed independently so one failing source
    does not roll back or skip the others. A failed source reports ``-1``.
    """

    def _run(source: str, collect) -> int:
        try:
            return replace_items(db, source, collect())
        except Exception:
            db.rollback()
            logger.exception("industry-report collection failed for source %s", source)
            return -1

    def _run_katech() -> int:
        try:
            settings = get_settings()
            return collect_katech(
                db,
                max_file_bytes=settings.industry_report_crawl_max_file_bytes,
            )
        except Exception:
            db.rollback()
            logger.exception("industry-report KATECH collection failed")
            return -1

    return {
        cfg.AUTOJOURNAL_SOURCE: _run(cfg.AUTOJOURNAL_SOURCE, crawler.collect_autojournal),
        cfg.KDI_NARA_SOURCE: _run(cfg.KDI_NARA_SOURCE, crawler.collect_kdi_nara),
        cfg.KDI_MATERIAL_SOURCE: _run(cfg.KDI_MATERIAL_SOURCE, crawler.collect_kdi_material),
        cfg.KDI_DOMESTIC_SOURCE: _run(cfg.KDI_DOMESTIC_SOURCE, crawler.collect_kdi_domestic),
        cfg.KATECH_SOURCE: _run_katech(),
    }


# ── Status ───────────────────────────────────────────────────
def get_status(db: Session) -> dict[str, Any]:
    latest = db.scalar(
        select(IndustryReportItem.collected_at)
        .order_by(IndustryReportItem.collected_at.desc())
        .limit(1)
    )
    collected_at = latest.strftime("%Y-%m-%d %H:%M") if latest else None
    is_today = bool(latest and latest.strftime("%Y-%m-%d") == datetime.now().strftime("%Y-%m-%d"))
    return {"collecting": False, "collected_at": collected_at, "is_today": is_today}
