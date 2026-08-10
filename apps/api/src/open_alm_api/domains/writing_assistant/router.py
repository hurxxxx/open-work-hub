from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.domains.auth.access import resolve_workspace_enabled_app_ids
from open_alm_api.domains.auth.dependencies import require_current_user, require_current_workspace
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.writing_assistant import documents, service
from open_alm_api.domains.writing_assistant.app_catalog import (
    DRAFTING_WORKSPACE_APP,
    EMAIL_ASSISTANT_WORKSPACE_APP,
)
from open_alm_api.domains.writing_assistant.schemas import (
    DocumentDownloadRequest,
    DraftGenerateRequest,
    MailGenerateRequest,
    TranslateRequest,
    WritingResult,
)

router = APIRouter(prefix="/writing-assistant", tags=["writing-assistant"])

require_drafting_app_enabled = require_workspace_app_enabled(
    DRAFTING_WORKSPACE_APP.app_id,
    error_code="writing_assistant.app_disabled",
)
require_email_assistant_app_enabled = require_workspace_app_enabled(
    EMAIL_ASSISTANT_WORKSPACE_APP.app_id,
    error_code="writing_assistant.app_disabled",
)


def require_any_writing_assistant_app_enabled(
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> None:
    enabled_app_ids = set(resolve_workspace_enabled_app_ids(db, workspace.id))
    writing_assistant_app_ids = {
        DRAFTING_WORKSPACE_APP.app_id,
        EMAIL_ASSISTANT_WORKSPACE_APP.app_id,
    }
    if enabled_app_ids.isdisjoint(writing_assistant_app_ids):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="writing_assistant.app_disabled",
        )


def _task_context(task_kind: str, user: User, workspace: Workspace) -> LlmTaskContext:
    app_id = (
        EMAIL_ASSISTANT_WORKSPACE_APP.app_id
        if task_kind == service.MAIL_TASK_KIND
        else DRAFTING_WORKSPACE_APP.app_id
    )
    return LlmTaskContext(
        source="api.writing_assistant",
        workspace_id=workspace.id,
        task_kind=task_kind,
        app_id=app_id,
        actor_user_id=user.id,
        principal_kind="user",
        principal_id=user.id,
    )


@router.post(
    "/draft/generate",
    response_model=WritingResult,
    dependencies=[Depends(require_drafting_app_enabled)],
)
def generate_draft(
    payload: DraftGenerateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> WritingResult:
    context = _task_context(service.DRAFT_TASK_KIND, current_user, workspace)
    return service.generate_draft(
        db, context, text=payload.text, draft_type=payload.type, lang=payload.lang
    )


@router.post(
    "/mail/generate",
    response_model=WritingResult,
    dependencies=[Depends(require_email_assistant_app_enabled)],
)
def generate_mail(
    payload: MailGenerateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> WritingResult:
    context = _task_context(service.MAIL_TASK_KIND, current_user, workspace)
    return service.generate_mail(
        db,
        context,
        intent=payload.intent,
        original_mail=payload.original_mail,
        tone=payload.tone,
        lang=payload.lang,
    )


@router.post(
    "/translate",
    response_model=WritingResult,
    dependencies=[Depends(require_any_writing_assistant_app_enabled)],
)
def translate(
    payload: TranslateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> WritingResult:
    context = _task_context(service.TRANSLATE_TASK_KIND, current_user, workspace)
    return service.translate(db, context, source=payload.source, target_lang=payload.target_lang)


@router.post(
    "/download",
    dependencies=[Depends(require_any_writing_assistant_app_enabled)],
)
def download(
    payload: DocumentDownloadRequest,
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    try:
        data, media_type, ext = documents.render_document(payload.content, payload.format)
    except ValueError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="writing_assistant.download_render_failed",
        ) from error

    safe_name = (payload.filename or "문서").strip() or "문서"
    encoded = quote(f"{safe_name}.{ext}")
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
