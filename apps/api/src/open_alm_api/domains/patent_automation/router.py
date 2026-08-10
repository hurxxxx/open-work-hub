from __future__ import annotations

from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.dependencies import require_current_user, require_current_workspace
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.patent_automation import approval_html
from open_alm_api.domains.patent_automation import field_defs as fd
from open_alm_api.domains.patent_automation import history, invoice_pipeline, service, summary_xlsx
from open_alm_api.domains.patent_automation.app_catalog import PATENT_AUTOMATION_WORKSPACE_APP
from open_alm_api.domains.patent_automation.models import PatentCostLine, PatentCostRun
from open_alm_api.domains.patent_automation.schemas import (
    ApprovalHtmlOut,
    CostLineOut,
    CostRunOut,
    HistoryEntryOut,
    HistoryListResponse,
    ImportPreviewResponse,
    ImportResultResponse,
    PatentFieldDefOut,
    PatentFieldsResponse,
    PatentRecordListResponse,
    PatentRecordOut,
    PatentRecordUpsert,
    ProgressEventIn,
)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 파일 1개 한도
_MAX_UPLOAD_FILES = 200  # 한 번에 첨부 가능한 청구서 파일 수
_MAX_TOTAL_UPLOAD_BYTES = 300 * 1024 * 1024  # 업로드 전체 합 한도
_INVALID_FILE = "patent_automation.invalid_file"
_TOO_LARGE = "patent_automation.upload_too_large"


require_patent_automation_app_enabled = require_workspace_app_enabled(
    PATENT_AUTOMATION_WORKSPACE_APP.app_id,
    error_code="patent_automation.app_disabled",
)


router = APIRouter(
    prefix="/patent-automation",
    tags=["patent-automation"],
    dependencies=[Depends(require_patent_automation_app_enabled)],
)


async def _read_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > _MAX_UPLOAD_BYTES:
            raise localized_http_exception(status_code=413, code=_TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


# ── fields ────────────────────────────────────────────────────────────────────
@router.get("/fields", response_model=PatentFieldsResponse)
def get_fields(scope: str = Query(default="domestic")) -> PatentFieldsResponse:
    defs = (
        fd.OVERSEAS_FIELD_DEFINITIONS
        if scope == fd.OVERSEAS_SOURCE_SHEET
        else fd.PATENT_FIELD_DEFINITIONS
    )
    return PatentFieldsResponse(
        fields=[
            PatentFieldDefOut(
                key=d.key,
                label_ko=d.label_ko,
                group_ko=d.group_ko,
                column_letter=d.column_letter,
                type=d.type,
                is_promoted=d.is_promoted,
            )
            for d in defs
        ]
    )


# ── records ───────────────────────────────────────────────────────────────────
@router.get("/records", response_model=PatentRecordListResponse)
def list_records_endpoint(
    q: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> PatentRecordListResponse:
    rows, total = service.list_records(
        db, workspace=current_workspace, query=q, source=source, limit=limit, offset=offset
    )
    return PatentRecordListResponse(
        items=[PatentRecordOut(**service.serialize_record(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/records", response_model=PatentRecordOut, status_code=status.HTTP_201_CREATED)
def create_record_endpoint(
    payload: PatentRecordUpsert,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> PatentRecordOut:
    record = service.create_record(
        db,
        workspace=current_workspace,
        user=current_user,
        values=payload.field_values,
        stable_record_id=payload.stable_record_id,
    )
    return PatentRecordOut(**service.serialize_record(record))


@router.get("/records/{record_id}", response_model=PatentRecordOut)
def get_record_endpoint(
    record_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> PatentRecordOut:
    record = service.get_record(db, workspace=current_workspace, record_id=record_id)
    return PatentRecordOut(**service.serialize_record(record))


@router.patch("/records/{record_id}", response_model=PatentRecordOut)
def update_record_endpoint(
    record_id: str,
    payload: PatentRecordUpsert,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> PatentRecordOut:
    record = service.update_record(
        db,
        workspace=current_workspace,
        user=current_user,
        record_id=record_id,
        values=payload.field_values,
    )
    return PatentRecordOut(**service.serialize_record(record))


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record_endpoint(
    record_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    service.delete_record(db, workspace=current_workspace, user=current_user, record_id=record_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/records/{record_id}/history", response_model=HistoryListResponse)
def record_history_endpoint(
    record_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HistoryListResponse:
    entries = history.list_record_history(db, workspace=current_workspace, record_id=record_id)
    return HistoryListResponse(
        items=[
            HistoryEntryOut(
                id=e.id,
                action=e.action,
                field_key=e.field_key,
                field_label=e.field_label,
                old_value=e.old_value,
                new_value=e.new_value,
                actor_user_id=e.actor_user_id,
                created_at=e.created_at.isoformat() if e.created_at else None,
            )
            for e in entries
        ]
    )


@router.post("/records/{record_id}/progress", response_model=PatentRecordOut)
def add_progress_endpoint(
    record_id: str,
    payload: ProgressEventIn,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> PatentRecordOut:
    record = service.add_progress_event(
        db,
        workspace=current_workspace,
        record_id=record_id,
        kind=payload.kind,
        stage=payload.stage,
        event_date=payload.event_date,
        note=payload.note,
        seq=payload.seq,
    )
    return PatentRecordOut(**service.serialize_record(record))


@router.get("/records-export.xlsx")
def export_records_endpoint(
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    body = service.export_records(db, workspace=current_workspace)
    return StreamingResponse(
        BytesIO(body),
        media_type=_XLSX_MIME,
        headers={
            "Content-Disposition": "attachment; filename=patent-status.xlsx",
            "Cache-Control": "no-store",
        },
    )


# ── import ────────────────────────────────────────────────────────────────────
@router.post("/import-preview", response_model=ImportPreviewResponse)
async def import_preview_endpoint(
    file: UploadFile = File(...),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> ImportPreviewResponse:
    content = await _read_upload(file)
    preview = await run_in_threadpool(
        service.build_import_preview, file.filename or "upload.xlsx", content
    )
    return ImportPreviewResponse(**preview)


@router.post("/imports", response_model=ImportResultResponse)
async def import_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> ImportResultResponse:
    content = await _read_upload(file)
    result = await run_in_threadpool(
        service.import_workbook,
        db,
        workspace=current_workspace,
        user=current_user,
        filename=file.filename or "upload.xlsx",
        content=content,
    )
    return ImportResultResponse(**result)


# ── 직무발명신고서 → 행 추가 ─────────────────────────────────────────────────────
@router.post("/disclosures", response_model=PatentRecordOut, status_code=status.HTTP_201_CREATED)
async def create_disclosure_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> PatentRecordOut:
    content = await _read_upload(file)
    record = await run_in_threadpool(
        service.create_record_from_disclosure,
        db,
        workspace=current_workspace,
        user=current_user,
        filename=file.filename or "disclosure.xlsx",
        content=content,
    )
    return PatentRecordOut(**service.serialize_record(record))


# ── cost runs ─────────────────────────────────────────────────────────────────
def _serialize_run(run: PatentCostRun, lines: list[PatentCostLine]) -> CostRunOut:
    warnings = (run.warnings or {}).get("messages", []) if isinstance(run.warnings, dict) else []
    return CostRunOut(
        id=run.id,
        fiscal_period=run.fiscal_period,
        status=run.status,
        industrial_total=run.industrial_total,
        overseas_total=run.overseas_total,
        warnings=warnings,
        lines=[CostLineOut.model_validate(line) for line in lines],
        has_industrial=any(line.region != "해외" for line in lines),
        has_overseas=any(line.region == "해외" for line in lines),
        created_at=run.created_at.isoformat() if run.created_at else None,
    )


@router.post("/cost-runs/ingest", response_model=CostRunOut)
async def ingest_cost_files_endpoint(
    files: list[UploadFile] = File(...),
    region: str = Form("산업"),
    fiscal_period: str | None = Form(None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> CostRunOut:
    if len(files) > _MAX_UPLOAD_FILES:
        raise localized_http_exception(status_code=413, code=_TOO_LARGE)
    payloads: list[tuple[str, bytes, str]] = []
    total = 0
    for file in files:
        content = await _read_upload(file)
        total += len(content)
        if total > _MAX_TOTAL_UPLOAD_BYTES:
            raise localized_http_exception(status_code=413, code=_TOO_LARGE)
        payloads.append(
            (file.filename or "invoice.pdf", content, file.content_type or "application/pdf")
        )
    run = await run_in_threadpool(
        invoice_pipeline.run_cost_ingest,
        db,
        workspace=current_workspace,
        user=current_user,
        files=payloads,
        region=region,
        fiscal_period=fiscal_period,
    )
    lines = list(
        db.scalars(
            select(PatentCostLine)
            .where(PatentCostLine.run_id == run.id)
            .order_by(PatentCostLine.section, PatentCostLine.seq)
        )
    )
    return _serialize_run(run, lines)


def _load_run(
    db: Session, workspace: Workspace, run_id: str
) -> tuple[PatentCostRun, list[PatentCostLine]]:
    run = db.scalars(
        select(PatentCostRun).where(
            PatentCostRun.workspace_id == workspace.id, PatentCostRun.id == run_id
        )
    ).first()
    if run is None:
        raise localized_http_exception(status_code=404, code="patent_automation.cost_run_not_found")
    lines = list(
        db.scalars(
            select(PatentCostLine)
            .where(PatentCostLine.run_id == run.id)
            .order_by(PatentCostLine.section, PatentCostLine.seq)
        )
    )
    return run, lines


@router.get("/cost-runs/{run_id}", response_model=CostRunOut)
def get_cost_run_endpoint(
    run_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> CostRunOut:
    run, lines = _load_run(db, current_workspace, run_id)
    return _serialize_run(run, lines)


_WEEKDAYS_KR = ("월", "화", "수", "목", "금", "토", "일")


def _period_label(period: str) -> str:
    """'2026-06'|'202606'|'2026.06' → '2026년 6월' (제목용). 형식 불명이면 원본."""
    parsed = summary_xlsx.parse_period(period)
    return f"{parsed[0]}년 {int(parsed[1])}월" if parsed else (period or "")


def _gen_date_label() -> str:
    """파일 생성일(오늘)을 정본 우상단 형식 'YYYY.MM.DD(요일)'로 표기."""
    now = datetime.now()
    return f"{now.year}.{now.month:02d}.{now.day:02d}({_WEEKDAYS_KR[now.weekday()]})"


@router.get("/cost-runs/{run_id}/industrial.xlsx")
def download_industrial_endpoint(
    run_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    run, lines = _load_run(db, current_workspace, run_id)
    label = _period_label(run.fiscal_period or "")
    body = summary_xlsx.build_industrial_summary(
        lines,
        title=f"{label} 산업재산권 지출 비용 요약",
        date_label=_gen_date_label(),
        period=run.fiscal_period or "",
    )
    return StreamingResponse(
        BytesIO(body),
        media_type=_XLSX_MIME,
        headers={
            "Content-Disposition": "attachment; filename=industrial-summary.xlsx",
            "Cache-Control": "no-store",
        },
    )


@router.get("/cost-runs/{run_id}/overseas.xlsx")
def download_overseas_endpoint(
    run_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    run, lines = _load_run(db, current_workspace, run_id)
    label = _period_label(run.fiscal_period or "")
    body = summary_xlsx.build_overseas_summary(
        lines,
        title=f"{label} 해외특허 지출 비용 정리",
        date_label=_gen_date_label(),
        period=run.fiscal_period or "",
    )
    return StreamingResponse(
        BytesIO(body),
        media_type=_XLSX_MIME,
        headers={
            "Content-Disposition": "attachment; filename=overseas-summary.xlsx",
            "Cache-Control": "no-store",
        },
    )


@router.get("/cost-runs/{run_id}/count-amount.xlsx")
def download_count_amount_endpoint(
    run_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    run, lines = _load_run(db, current_workspace, run_id)
    body = summary_xlsx.build_count_amount_summary(
        lines, period=run.fiscal_period or "", date_label=_gen_date_label()
    )
    return StreamingResponse(
        BytesIO(body),
        media_type=_XLSX_MIME,
        headers={
            "Content-Disposition": "attachment; filename=count-amount-summary.xlsx",
            "Cache-Control": "no-store",
        },
    )


@router.post("/cost-runs/{run_id}/approval-html", response_model=ApprovalHtmlOut)
async def generate_approval_html_endpoint(
    run_id: str,
    count_amount_file: UploadFile | None = File(None),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> ApprovalHtmlOut:
    """품의 본문 HTML 생성. 2번 누적표는 첨부된 6번(건수·금액 정리) 파일에서 추출한다."""
    run, lines = _load_run(db, current_workspace, run_id)
    count_amount = None
    if count_amount_file is not None:
        content = await _read_upload(count_amount_file)
        try:
            count_amount = await run_in_threadpool(approval_html.parse_count_amount_xlsx, content)
        except Exception as error:  # noqa: BLE001
            raise localized_http_exception(status_code=400, code=_INVALID_FILE) from error
    html = await run_in_threadpool(
        approval_html.build_approval_html,
        lines,
        period=run.fiscal_period or "",
        count_amount=count_amount,
    )
    label = _period_label(run.fiscal_period or "")
    return ApprovalHtmlOut(html=html, filename=f"{label} 특허비용 품의.txt")
