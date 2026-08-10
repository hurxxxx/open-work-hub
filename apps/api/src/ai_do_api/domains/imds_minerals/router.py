from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.dependencies import require_current_user, require_current_workspace
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from ai_do_api.domains.imds_minerals.app_catalog import IMDS_MINERALS_WORKSPACE_APP
from ai_do_api.domains.imds_minerals import service
from ai_do_api.domains.imds_minerals.schemas import ImdsAnalyzeResult, ImdsMatchResult
from ai_do_api.domains.imds_minerals.service import (
    ImdsListError,
    ImdsMeta,
    ImdsParseError,
    ImdsSheetNotFoundError,
    ImdsTemplateError,
    ImdsWorkbookError,
)

require_imds_minerals_app_enabled = require_workspace_app_enabled(
    IMDS_MINERALS_WORKSPACE_APP.app_id,
    error_code="imds_minerals.app_disabled",
)

router = APIRouter(
    prefix="/imds-minerals",
    tags=["imds-minerals"],
    dependencies=[Depends(require_imds_minerals_app_enabled)],
)

_UPLOAD_CHUNK_BYTES = 1024 * 1024
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _ensure_extension(filename: str | None, allowed: tuple[str, ...], code: str) -> str:
    name = filename or ""
    if not name.lower().endswith(allowed):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=code,
        )
    return name


async def _read_upload(file: UploadFile) -> bytes:
    data = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > _MAX_UPLOAD_BYTES:
            raise localized_http_exception(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                code="imds_minerals.upload_too_large",
            )
    return bytes(data)


@router.post("/analyze", response_model=ImdsAnalyzeResult)
async def analyze(
    file: UploadFile = File(...),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImdsAnalyzeResult:
    _ensure_extension(file.filename, (".pdf",), "imds_minerals.invalid_pdf_type")
    content = await _read_upload(file)
    try:
        return service.analyze(content)
    except ImdsParseError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="imds_minerals.parse_failed",
        ) from error


@router.post("/match", response_model=ImdsMatchResult)
async def match(
    list_file: UploadFile = File(...),
    oem: str = Form(...),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImdsMatchResult:
    _ensure_extension(list_file.filename, (".xlsx", ".xlsm"), "imds_minerals.invalid_list_type")
    content = await _read_upload(list_file)
    try:
        return service.match_metadata(content, oem)
    except ImdsListError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="imds_minerals.list_parse_failed",
        ) from error


@router.post("/generate")
async def generate(
    pdf: UploadFile = File(...),
    template: UploadFile = File(...),
    sheet: str = Form(...),
    car: str = Form(...),
    end_name: str = Form(...),
    oem: str = Form(...),
    dcc: str = Form(...),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    _ensure_extension(pdf.filename, (".pdf",), "imds_minerals.invalid_pdf_type")
    _ensure_extension(template.filename, (".xlsx", ".xlsm"), "imds_minerals.invalid_template_type")
    pdf_content = await _read_upload(pdf)
    template_content = await _read_upload(template)
    meta = ImdsMeta(car=car, end_name=end_name, oem=oem, dcc=dcc)
    try:
        workbook, _written = service.generate(pdf_content, template_content, sheet, meta)
    except ImdsParseError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="imds_minerals.parse_failed",
        ) from error
    except ImdsTemplateError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="imds_minerals.template_parse_failed",
        ) from error
    except ImdsSheetNotFoundError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="imds_minerals.sheet_not_found",
        ) from error
    except ImdsWorkbookError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="imds_minerals.template_parse_failed",
        ) from error
    filename = urllib.parse.quote("IMDS_책임광물_조사표.xlsx")
    return Response(
        workbook,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
