from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.domains.auth.dependencies import require_current_user, require_current_workspace
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.fmea_compare import service
from open_alm_api.domains.fmea_compare.app_catalog import FMEA_COMPARE_WORKSPACE_APP
from open_alm_api.domains.fmea_compare.excel import FmeaParseError
from open_alm_api.domains.fmea_compare.schemas import (
    FmeaAiAnalyzeRequest,
    FmeaAiAnalyzeResult,
    FmeaAnalyzeResult,
    FmeaCompareResult,
)

require_fmea_compare_app_enabled = require_workspace_app_enabled(
    FMEA_COMPARE_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/fmea-compare",
    tags=["fmea-compare"],
    dependencies=[Depends(require_fmea_compare_app_enabled)],
)

_UPLOAD_CHUNK_BYTES = 1024 * 1024
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_ALLOWED_EXTENSIONS = (".xls", ".xlsx")


def _task_context(user: User, workspace: Workspace) -> LlmTaskContext:
    return LlmTaskContext(
        source="api.fmea_compare",
        workspace_id=workspace.id,
        task_kind=service.TASK_KIND,
        app_id=FMEA_COMPARE_WORKSPACE_APP.app_id,
        actor_user_id=user.id,
        principal_kind="user",
        principal_id=user.id,
    )


def _ensure_excel(filename: str | None) -> str:
    name = filename or ""
    if not name.lower().endswith(_ALLOWED_EXTENSIONS):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="fmea_compare.invalid_file_type",
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
                code="fmea_compare.upload_too_large",
            )
    return bytes(data)


@router.post("/analyze", response_model=FmeaAnalyzeResult)
async def analyze(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> FmeaAnalyzeResult:
    filename = _ensure_excel(file.filename)
    content = await _read_upload(file)
    try:
        return service.analyze(content, filename)
    except FmeaParseError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="fmea_compare.parse_failed",
        ) from error


@router.post("/ai-analyze", response_model=FmeaAiAnalyzeResult)
def ai_analyze(
    payload: FmeaAiAnalyzeRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> FmeaAiAnalyzeResult:
    if not payload.items:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="fmea_compare.empty_data",
        )
    context = _task_context(current_user, workspace)
    return service.ai_analyze(db, context, items=payload.items, mode=payload.mode)


@router.post("/compare", response_model=FmeaCompareResult)
async def compare(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> FmeaCompareResult:
    filename_a = _ensure_excel(file_a.filename)
    filename_b = _ensure_excel(file_b.filename)
    content_a = await _read_upload(file_a)
    content_b = await _read_upload(file_b)
    context = _task_context(current_user, workspace)
    try:
        return service.compare(
            db,
            context,
            content_a=content_a,
            filename_a=filename_a,
            content_b=content_b,
            filename_b=filename_b,
        )
    except FmeaParseError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="fmea_compare.parse_failed",
        ) from error
