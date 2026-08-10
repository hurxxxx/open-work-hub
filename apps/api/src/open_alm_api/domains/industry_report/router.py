"""HTTP router for the industry-report aggregator.

Industry-report content is global (not workspace-scoped); registered in
``api_registry`` as a protected ``api`` router (every endpoint requires an
authenticated user). Admin-only endpoints additionally gate on platform-admin
role, mirroring the news router.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session, get_session_factory
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.settings import get_settings
from open_alm_api.domains.auth.access import is_platform_admin_user
from open_alm_api.domains.auth.dependencies import require_current_user
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.auth.workspace_app_gate import (
    is_platform_app_enabled,
    require_platform_app_enabled,
)
from open_alm_api.domains.news.app_catalog import NEWS_WORKSPACE_APP

from . import config_data as cfg
from . import crawler, report_curator, service, storage
from .dispatch import dispatch_collect_all
from .schemas import (
    AutojournalIssueDetail,
    IndustryReportItemOut,
    ItemListResponse,
    KdiPdfUrlResponse,
    RecommendedReportListResponse,
    RecommendedReportOut,
    ReportCurateResponse,
    ReportFetchResponse,
    ReportSnapshotRequest,
    ReportStatusResponse,
    ScrapReportListResponse,
    ScrapReportOut,
    TrendCompanyListResponse,
    TrendCompanyOut,
    TrendFileListResponse,
    TrendFileOut,
)

require_news_app_enabled = require_platform_app_enabled(
    NEWS_WORKSPACE_APP.app_id,
    error_code="platform.app_disabled",
)

router = APIRouter(
    prefix="/industry-report",
    tags=["industry-report"],
    dependencies=[Depends(require_news_app_enabled)],
)
_UPLOAD_CHUNK_BYTES = 1024 * 1024

logger = logging.getLogger(__name__)

_AUTO_THROTTLE_SECONDS = 6 * 3600
_last_auto_collect_monotonic = 0.0


def _maybe_auto_collect() -> None:
    """trend 탭 조회 시 최신 자료를 worker에 enqueue한다(throttle)."""
    global _last_auto_collect_monotonic
    now = time.monotonic()
    if now - _last_auto_collect_monotonic < _AUTO_THROTTLE_SECONDS:
        return
    _last_auto_collect_monotonic = now
    try:
        dispatch_collect_all()
    except Exception as error:  # noqa: BLE001 - broker best-effort
        logger.warning("industry-report stale-refresh enqueue failed: %s", error)


# AI 추천 리포트 큐레이션 — 별도 워커 없이 API 프로세스에서 직접 수행.
_curation_lock = threading.Lock()
_last_auto_curate_monotonic = 0.0


def _run_curation_background(actor_user_id: str | None = None) -> None:
    if not _curation_lock.acquire(blocking=False):
        return
    try:
        session_factory = get_session_factory()
        with session_factory() as db:
            if not is_platform_app_enabled(db, NEWS_WORKSPACE_APP.app_id):
                return
            report_curator.curate_recent(db, actor_user_id=actor_user_id)
    except Exception:  # noqa: BLE001 - 백그라운드 best-effort
        logger.exception("industry-report AI curation failed")
    finally:
        _curation_lock.release()


def _maybe_auto_curate(background: BackgroundTasks) -> None:
    """AI 추천 리포트 탭 조회 시 큐레이션 자동 실행(throttle, 백그라운드)."""
    global _last_auto_curate_monotonic
    now = time.monotonic()
    if now - _last_auto_curate_monotonic < _AUTO_THROTTLE_SECONDS:
        return
    _last_auto_curate_monotonic = now
    background.add_task(_run_curation_background, None)


async def _read_upload(file: UploadFile, *, max_bytes: int) -> bytes:
    data = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise localized_http_exception(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                code="industry_report.file_too_large",
            )
    return bytes(data)


def _require_admin(
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db_session),
) -> User:
    if not is_platform_admin_user(current_user, db):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="industry_report.admin_only",
        )
    return current_user


# ── Trend (자동차 리서치 자료) ────────────────────────────────
@router.get("/trend/companies", response_model=TrendCompanyListResponse)
def list_companies(
    db: Session = Depends(get_db_session),
) -> TrendCompanyListResponse:
    _maybe_auto_collect()
    return TrendCompanyListResponse(
        companies=[TrendCompanyOut(**c) for c in service.list_companies(db)]
    )


@router.get("/trend/{company}/files", response_model=TrendFileListResponse)
def list_company_files(
    company: str, db: Session = Depends(get_db_session)
) -> TrendFileListResponse:
    if company not in cfg.COMPANY_MAP:
        raise localized_http_exception(status_code=404, code="industry_report.unknown_company")
    rows = service.list_files(db, company)
    return TrendFileListResponse(
        company=company,
        company_label=cfg.COMPANY_MAP[company],
        files=[TrendFileOut.model_validate(row) for row in rows],
    )


@router.get("/trend/file/{file_id}/content")
def download_file(file_id: str, db: Session = Depends(get_db_session)) -> StreamingResponse:
    row = service.get_file(db, file_id)
    if row is None:
        raise localized_http_exception(status_code=404, code="industry_report.file_not_found")
    stream = storage.open_report_stream(row.storage_key)
    encoded_name = quote(row.filename)
    inline_pdf = storage.is_pdf_report(filename=row.filename, content_type=row.content_type)
    disposition = "inline" if inline_pdf else "attachment"
    return StreamingResponse(
        stream,
        media_type=storage.DEFAULT_REPORT_CONTENT_TYPE if inline_pdf else "application/octet-stream",
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_name}",
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/trend/{company}/upload",
    response_model=TrendFileOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    company: str,
    file: UploadFile = File(...),
    title: str = Form(""),
    published_date: str = Form(""),
    db: Session = Depends(get_db_session),
    admin: User = Depends(_require_admin),
) -> TrendFileOut:
    if company not in cfg.COMPANY_MAP:
        raise localized_http_exception(status_code=404, code="industry_report.unknown_company")
    settings = get_settings()
    data = await _read_upload(file, max_bytes=settings.industry_report_upload_max_bytes)
    if not data:
        raise localized_http_exception(status_code=400, code="industry_report.empty_file")
    if not storage.is_pdf_upload(
        filename=file.filename,
        content_type=file.content_type,
        data=data,
    ):
        raise localized_http_exception(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="industry_report.unsupported_file_type",
        )
    row = service.create_file(
        db,
        company=company,
        title=title.strip() or (file.filename or "report"),
        filename=file.filename or "report",
        data=data,
        content_type=storage.DEFAULT_REPORT_CONTENT_TYPE,
        uploaded_by_id=admin.id,
        published_date=published_date.strip(),
    )
    return TrendFileOut.model_validate(row)


@router.delete("/trend/file/{file_id}")
def delete_file(
    file_id: str,
    db: Session = Depends(get_db_session),
    _admin: User = Depends(_require_admin),
) -> dict[str, str]:
    if not service.delete_file(db, file_id):
        raise localized_http_exception(status_code=404, code="industry_report.file_not_found")
    return {"status": "success"}


# ── Autojournal (오토저널) ────────────────────────────────────
@router.get("/autojournal/issues", response_model=ItemListResponse)
def list_autojournal_issues(db: Session = Depends(get_db_session)) -> ItemListResponse:
    rows, collected_at = service.list_items(db, cfg.AUTOJOURNAL_SOURCE)
    return ItemListResponse(
        source=cfg.AUTOJOURNAL_SOURCE,
        collected_at=collected_at.strftime("%Y-%m-%d %H:%M") if collected_at else None,
        items=[IndustryReportItemOut.model_validate(row) for row in rows],
    )


@router.get("/autojournal/issue/{issue_id}", response_model=AutojournalIssueDetail)
def get_autojournal_issue(issue_id: str) -> AutojournalIssueDetail:
    if not re.match(cfg.AJ_ISSUE_ID_RE, issue_id):
        raise localized_http_exception(status_code=400, code="industry_report.invalid_issue_id")
    data = crawler.fetch_autojournal_issue_text(issue_id)
    if not data:
        raise localized_http_exception(status_code=404, code="industry_report.issue_unavailable")
    return AutojournalIssueDetail(
        issue_id=issue_id,
        total_pages=data["total_pages"],
        toc=data["toc"],
        pages=data["pages"],
    )


# ── KDI (경제연구 자료) ───────────────────────────────────────
@router.get("/kdi/pdf-url", response_model=KdiPdfUrlResponse)
def kdi_pdf_url(page: str = Query(..., min_length=1)) -> KdiPdfUrlResponse:
    if not crawler.is_kdi_url(page):
        raise localized_http_exception(status_code=400, code="industry_report.invalid_kdi_url")
    return KdiPdfUrlResponse(page_url=page, pdf_url=crawler.resolve_kdi_pdf_url(page))


@router.get("/kdi/{source}", response_model=ItemListResponse)
def list_kdi_items(
    source: str,
    keyword: str | None = Query(None),
    db: Session = Depends(get_db_session),
) -> ItemListResponse:
    stored_source = cfg.KDI_PATH_TO_SOURCE.get(source)
    if stored_source is None:
        raise localized_http_exception(status_code=404, code="industry_report.unknown_source")
    rows, collected_at = service.list_items(db, stored_source, keyword=keyword)
    return ItemListResponse(
        source=stored_source,
        collected_at=collected_at.strftime("%Y-%m-%d %H:%M") if collected_at else None,
        items=[IndustryReportItemOut.model_validate(row) for row in rows],
    )


# ── Status / collection ───────────────────────────────────────
@router.get("/status", response_model=ReportStatusResponse)
def read_status(db: Session = Depends(get_db_session)) -> ReportStatusResponse:
    return ReportStatusResponse(**service.get_status(db))


@router.post("/fetch", response_model=ReportFetchResponse)
def trigger_fetch(
    _admin: User = Depends(_require_admin),
) -> ReportFetchResponse:
    dispatch_collect_all(force=True)
    return ReportFetchResponse(status="success", message="industry_report.fetch_started")


# ── 전역 추천 / 개인 스크랩 ──
@router.get("/recommended", response_model=RecommendedReportListResponse)
def list_recommended_reports(
    db: Session = Depends(get_db_session),
    _user: User = Depends(require_current_user),
) -> RecommendedReportListResponse:
    rows = service.list_recommended_reports(db, origin="manual")
    return RecommendedReportListResponse(
        items=[RecommendedReportOut.model_validate(r) for r in rows]
    )


@router.get("/ai-recommended", response_model=RecommendedReportListResponse)
def list_ai_recommended_reports(
    background: BackgroundTasks,
    db: Session = Depends(get_db_session),
    _user: User = Depends(require_current_user),
) -> RecommendedReportListResponse:
    _maybe_auto_curate(background)
    rows = service.list_recommended_reports(db, origin="ai")
    return RecommendedReportListResponse(
        items=[RecommendedReportOut.model_validate(r) for r in rows]
    )


@router.post("/curate", response_model=ReportCurateResponse)
def curate_reports_now(
    db: Session = Depends(get_db_session),
    admin: User = Depends(_require_admin),
) -> ReportCurateResponse:
    result = report_curator.curate_recent(db, actor_user_id=admin.id)
    return ReportCurateResponse(
        status="error" if result.get("error") else "success",
        evaluated=result.get("evaluated", 0),
        saved=result.get("saved", 0),
        by_reason=result.get("by_reason", {}),
        error=result.get("error"),
    )


@router.post(
    "/recommended",
    response_model=RecommendedReportOut,
    status_code=status.HTTP_201_CREATED,
)
def recommend_report(
    payload: ReportSnapshotRequest,
    db: Session = Depends(get_db_session),
    admin: User = Depends(_require_admin),
) -> RecommendedReportOut:
    if not payload.title.strip() or (not payload.url.strip() and not payload.file_id):
        raise localized_http_exception(status_code=400, code="industry_report.save_invalid")
    row = service.recommend_report(
        db,
        kind=payload.kind,
        title=payload.title,
        org=payload.org,
        published_date=payload.published_date,
        url=payload.url,
        file_id=payload.file_id,
        company=payload.company,
        user_id=admin.id,
    )
    return RecommendedReportOut.model_validate(row)


@router.delete("/recommended/{recommended_id}")
def delete_recommended_report(
    recommended_id: str,
    db: Session = Depends(get_db_session),
    _admin: User = Depends(_require_admin),
) -> dict[str, str]:
    if not service.delete_recommended_report(db, recommended_id):
        raise localized_http_exception(
            status_code=404, code="industry_report.recommended_not_found"
        )
    return {"status": "deleted"}


@router.get("/scraps", response_model=ScrapReportListResponse)
def list_report_scraps(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ScrapReportListResponse:
    rows = service.list_scrap_reports(db, user_id=current_user.id)
    return ScrapReportListResponse(items=[ScrapReportOut.model_validate(r) for r in rows])


@router.post("/scraps", response_model=ScrapReportOut, status_code=status.HTTP_201_CREATED)
def scrap_report(
    payload: ReportSnapshotRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ScrapReportOut:
    if not payload.title.strip() or (not payload.url.strip() and not payload.file_id):
        raise localized_http_exception(status_code=400, code="industry_report.save_invalid")
    row = service.scrap_report(
        db,
        kind=payload.kind,
        title=payload.title,
        org=payload.org,
        published_date=payload.published_date,
        url=payload.url,
        file_id=payload.file_id,
        company=payload.company,
        user_id=current_user.id,
    )
    return ScrapReportOut.model_validate(row)


@router.delete("/scraps/{scrap_id}")
def delete_scrap_report(
    scrap_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> dict[str, str]:
    if not service.delete_scrap_report(db, scrap_id, user_id=current_user.id):
        raise localized_http_exception(status_code=404, code="industry_report.scrap_not_found")
    return {"status": "deleted"}
