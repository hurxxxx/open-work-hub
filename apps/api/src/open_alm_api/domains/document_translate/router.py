from __future__ import annotations

from typing import cast, get_args

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.domains.auth.dependencies import require_current_user, require_current_workspace
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.document_translate import service
from open_alm_api.domains.document_translate.app_catalog import DOCUMENT_TRANSLATE_WORKSPACE_APP
from open_alm_api.domains.document_translate.schemas import (
    DocMode,
    DocProcessResult,
    DocProcessTextRequest,
    SummaryLevel,
    TargetLang,
)
from open_alm_api.domains.document_translate.service import DocumentTranslateError

require_document_translate_app_enabled = require_workspace_app_enabled(
    DOCUMENT_TRANSLATE_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/document-translate",
    tags=["document-translate"],
    dependencies=[Depends(require_document_translate_app_enabled)],
)

_UPLOAD_CHUNK_BYTES = 1024 * 1024
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_ALLOWED_EXTENSIONS = (".pdf", ".docx", ".xlsx", ".pptx", ".txt")
# Derive the allowed multipart Form values from the same Literals the JSON
# request model validates against, so /process and /process-text stay in sync.
_VALID_MODES = frozenset(get_args(DocMode))
_VALID_LANGS = frozenset(get_args(TargetLang))
_VALID_SUMMARY_LEVELS = frozenset(get_args(SummaryLevel))


def _task_context(user: User, workspace: Workspace) -> LlmTaskContext:
    return LlmTaskContext(
        source="api.document_translate",
        workspace_id=workspace.id,
        task_kind=service.TASK_KIND,
        app_id=DOCUMENT_TRANSLATE_WORKSPACE_APP.app_id,
        actor_user_id=user.id,
        principal_kind="user",
        principal_id=user.id,
    )


def _ensure_supported(filename: str | None) -> str:
    name = filename or ""
    if not name.lower().endswith(_ALLOWED_EXTENSIONS):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="document_translate.unsupported_file_type",
        )
    return name


def _ensure_mode(mode: str) -> DocMode:
    if mode not in _VALID_MODES:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="document_translate.invalid_mode",
        )
    return cast(DocMode, mode)


def _ensure_lang(target_lang: str) -> TargetLang:
    if target_lang not in _VALID_LANGS:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="document_translate.invalid_language",
        )
    return cast(TargetLang, target_lang)


def _ensure_summary_level(summary_level: str) -> SummaryLevel:
    if summary_level not in _VALID_SUMMARY_LEVELS:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="document_translate.invalid_summary_level",
        )
    return cast(SummaryLevel, summary_level)


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
                code="document_translate.upload_too_large",
            )
    return bytes(data)


@router.post("/process", response_model=DocProcessResult)
async def process_file(
    file: UploadFile = File(...),
    mode: str = Form("summarize"),
    target_lang: str = Form("ko"),
    summary_level: str = Form("detailed"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> DocProcessResult:
    filename = _ensure_supported(file.filename)
    validated_mode = _ensure_mode(mode)
    validated_lang = _ensure_lang(target_lang)
    validated_summary_level = _ensure_summary_level(summary_level)
    content = await _read_upload(file)
    context = _task_context(current_user, workspace)
    try:
        text = service.extract_text(
            content=content,
            filename=filename,
            mime_type=file.content_type or "",
        )
        return service.process(
            db,
            context,
            text=text,
            mode=validated_mode,
            target_lang=validated_lang,
            summary_level=validated_summary_level,
        )
    except DocumentTranslateError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=error.code,
        ) from error


@router.post("/process-text", response_model=DocProcessResult)
def process_text(
    payload: DocProcessTextRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> DocProcessResult:
    context = _task_context(current_user, workspace)
    try:
        return service.process(
            db,
            context,
            text=payload.text,
            mode=payload.mode,
            target_lang=payload.target_lang,
            summary_level=payload.summary_level,
        )
    except DocumentTranslateError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=error.code,
        ) from error
