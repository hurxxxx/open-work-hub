from __future__ import annotations

import json
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.access import (
    load_active_workspace_by_key,
    resolve_workspace_role,
    workspace_role_allows,
)
from ai_do_api.domains.auth.dependencies import require_admin_context, require_current_user
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.workspace_app_gate import require_platform_app_enabled
from ai_do_api.domains.conversations import app_persistence
from ai_do_api.domains.conversations.app_scope_adapters import QNA_ASSISTANT_SCOPE_REF
from ai_do_api.domains.document_processing.extractors import UnsupportedDocumentType
from ai_do_api.domains.qna import service
from ai_do_api.domains.qna.app_catalog import QA_ASSISTANT_WORKSPACE_APP
from ai_do_api.domains.qna.constants import (
    QNA_DEFAULT_CATEGORY,
    QNA_KIND_NOTICE,
    QNA_KIND_UPLOAD,
)
from ai_do_api.domains.qna.schemas import (
    QnaAskRequest,
    QnaBoardSyncResponse,
    QnaDocumentDetailResponse,
    QnaDocumentListResponse,
    QnaDocumentResponse,
    QnaNoticeListResponse,
)
from ai_do_api.domains.rag import application as rag_application
from ai_do_api.domains.rag.contracts import RagQueryResponse


require_qna_app_enabled = require_platform_app_enabled(
    QA_ASSISTANT_WORKSPACE_APP.app_id,
    error_code="platform.app_disabled",
)
router = APIRouter(
    prefix="/qna",
    tags=["qna"],
    dependencies=[Depends(require_qna_app_enabled)],
)

_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 1024 * 1024
logger = logging.getLogger(__name__)


async def _read_upload_limited(file: UploadFile, *, max_bytes: int = _MAX_UPLOAD_BYTES) -> bytes:
    data = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise localized_http_exception(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                code="qna.file_too_large",
            )
    return bytes(data)


@router.post("/ask", response_model=RagQueryResponse)
def ask(
    payload: QnaAskRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RagQueryResponse:
    workspace = _qna_conversation_workspace(
        db,
        current_user,
        workspace_key=payload.workspace_key,
    )
    conversation = None
    try:
        if workspace is not None:
            conversation = app_persistence.append_user_and_attach(
                db,
                workspace=workspace,
                user=current_user,
                conversation_id=payload.conversation_id,
                scope_ref=QNA_ASSISTANT_SCOPE_REF,
                scope_resource_id="company",
                content=payload.question.strip(),
                meta={"kind": "qna"},
            ).conversation
        response = service.ask_question(
            db,
            user=current_user,
            question=payload.question,
            top_k=payload.top_k,
            conversation_id=conversation.id if conversation is not None else None,
        )
        _append_qna_assistant_turn(db, conversation=conversation, response=response)
        return response
    except rag_application.RagAccessDeniedError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.access_denied")
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN, code=code, **params
        ) from error
    except rag_application.RagUnavailableError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.unavailable")
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, code=code, **params
        ) from error
    except service.QnaAnswerGenerationError as error:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="qna.answer_generation_failed",
        ) from error


@router.post("/ask/stream")
async def ask_stream(
    payload: QnaAskRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> EventSourceResponse:
    return EventSourceResponse(
        _ask_stream_publisher(
            payload=payload,
            db=db,
            current_user=current_user,
        ),
        ping=25,
    )


async def _ask_stream_publisher(
    *,
    payload: QnaAskRequest,
    db: Session,
    current_user: User,
):
    workspace = _qna_conversation_workspace(
        db,
        current_user,
        workspace_key=payload.workspace_key,
    )
    conversation = None
    try:
        if workspace is None:
            yield _qna_sse_error(
                "qna.conversation_workspace_unavailable",
                "Q&A conversation persistence requires an active workspace.",
            )
            return
        conversation = app_persistence.append_user_and_attach(
            db,
            workspace=workspace,
            user=current_user,
            conversation_id=payload.conversation_id,
            scope_ref=QNA_ASSISTANT_SCOPE_REF,
            scope_resource_id="company",
            content=payload.question.strip(),
            meta={"kind": "qna"},
        ).conversation
        yield _qna_sse("conversation_attached", {"conversation_id": conversation.id})
        async for event in service.stream_question_answer(
            db,
            user=current_user,
            question=payload.question,
            top_k=payload.top_k,
            conversation_id=conversation.id,
        ):
            if isinstance(event, service.QnaAnswerDelta):
                yield _qna_sse("content_delta", {"text": event.text})
            else:
                _append_qna_assistant_turn(
                    db,
                    conversation=conversation,
                    response=event.response,
                )
                yield _qna_sse(
                    "qna_response",
                    {"response": event.response.model_dump(mode="json")},
                )
                yield _qna_sse("done", {"finish_reason": "stop"})
    except rag_application.RagAccessDeniedError:
        _append_qna_error_turn(
            db,
            conversation=conversation,
            message="Q&A search access was denied.",
        )
        yield _qna_sse_error("rag.access_denied", "Q&A search access was denied.")
    except rag_application.RagUnavailableError:
        _append_qna_error_turn(
            db,
            conversation=conversation,
            message="Q&A search is unavailable.",
        )
        yield _qna_sse_error("rag.unavailable", "Q&A search is unavailable.")
    except service.QnaAnswerGenerationError:
        _append_qna_error_turn(
            db,
            conversation=conversation,
            message="Q&A answer generation failed.",
        )
        yield _qna_sse_error(
            "qna.answer_generation_failed",
            "Q&A answer generation failed.",
        )
    except Exception:
        logger.exception("qna.ask_stream_failed")
        _append_qna_error_turn(
            db,
            conversation=conversation,
            message="Q&A streaming failed.",
        )
        yield _qna_sse_error("qna.stream_failed", "Q&A streaming failed.")


def _qna_sse(event_type: str, data: dict) -> dict[str, str]:
    return {
        "event": event_type,
        "data": json.dumps(
            {"type": event_type, "data": data},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def _qna_sse_error(code: str, message: str) -> dict[str, str]:
    return _qna_sse(
        "error",
        {"code": code, "message": message, "retryable": code != "rag.access_denied"},
    )


def _qna_conversation_workspace(
    db: Session,
    user: User,
    *,
    workspace_key: str | None,
) -> Workspace | None:
    if workspace_key:
        workspace = load_active_workspace_by_key(db, workspace_key)
        if workspace is None:
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                code="workspace.not_found",
            )
        role = resolve_workspace_role(db, user, workspace.id)
        if not workspace_role_allows(role, "member"):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="workspace.membership_required",
                workspace=workspace.key,
            )
        return workspace
    workspace_id = rag_application.resolve_ai_gateway_workspace_id(db, user)
    if not workspace_id:
        return None
    return db.get(Workspace, workspace_id)


def _append_qna_assistant_turn(
    db: Session,
    *,
    conversation,
    response: RagQueryResponse,
) -> None:
    if conversation is None:
        return
    try:
        app_persistence.append_assistant_app_turn(
            db,
            conversation=conversation,
            content=service.format_answer_for_history(response),
            meta={
                "kind": "qna",
                "response_status": "done",
                "sources_used": list(response.sources_used or []),
                "hit_count": len(response.hits),
                "trace_id": response.trace_id,
                "latency_ms": response.latency_ms,
            },
        )
    except Exception:  # noqa: BLE001 - Q&A response has already been produced
        db.rollback()
        logger.exception("qna.assistant_turn_persist_failed")


def _append_qna_error_turn(db: Session, *, conversation, message: str) -> None:
    if conversation is None:
        return
    try:
        app_persistence.append_assistant_app_turn(
            db,
            conversation=conversation,
            content=message,
            meta={"kind": "qna", "response_status": "error"},
        )
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("qna.error_turn_persist_failed")


@router.get("/documents", response_model=QnaDocumentListResponse)
def list_documents(
    db: Session = Depends(get_db_session),
    _current_user: User = Depends(require_current_user),
) -> QnaDocumentListResponse:
    docs = service.list_documents(db, kind=QNA_KIND_UPLOAD)
    return QnaDocumentListResponse(documents=[QnaDocumentResponse.from_model(doc) for doc in docs])


@router.get("/notices", response_model=QnaNoticeListResponse)
def list_notices(
    db: Session = Depends(get_db_session),
    _current_user: User = Depends(require_current_user),
) -> QnaNoticeListResponse:
    docs = service.list_documents(db, kind=QNA_KIND_NOTICE)
    return QnaNoticeListResponse(notices=[QnaDocumentResponse.from_model(doc) for doc in docs])


@router.post("/documents/upload", response_model=QnaDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(QNA_DEFAULT_CATEGORY),
    _admin=Depends(require_admin_context),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> QnaDocumentResponse:
    content = await _read_upload_limited(file)
    try:
        doc = service.upload_document(
            db,
            uploaded_by=current_user,
            filename=file.filename or "document",
            content=content,
            mime_type=file.content_type,
            category=category or QNA_DEFAULT_CATEGORY,
        )
    except UnsupportedDocumentType as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="qna.unsupported_document_type",
        ) from error
    db.commit()
    db.refresh(doc)
    return QnaDocumentResponse.from_model(doc)


@router.get("/documents/{document_id}", response_model=QnaDocumentDetailResponse)
def get_document_detail(
    document_id: str,
    db: Session = Depends(get_db_session),
    _current_user: User = Depends(require_current_user),
) -> QnaDocumentDetailResponse:
    doc = service.get_document(db, document_id=document_id)
    if doc is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="qna.document_not_found"
        )
    return QnaDocumentDetailResponse.from_model(doc)


@router.get("/documents/{document_id}/files/{filename}/download")
def download_document_file(
    document_id: str,
    filename: str,
    db: Session = Depends(get_db_session),
    _current_user: User = Depends(require_current_user),
) -> Response:
    result = service.read_document_file(db, document_id=document_id, filename=filename)
    if result is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="qna.document_not_found"
        )
    content, content_type, resolved_name = result
    disposition = f"attachment; filename*=UTF-8''{quote(resolved_name)}"
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": disposition},
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    _admin=Depends(require_admin_context),
    db: Session = Depends(get_db_session),
) -> None:
    deleted = service.delete_document(db, document_id=document_id)
    if not deleted:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="qna.document_not_found",
        )
    db.commit()


@router.post("/board/sync", response_model=QnaBoardSyncResponse)
def sync_board(
    _admin=Depends(require_admin_context),
) -> QnaBoardSyncResponse:
    service.trigger_board_sync()
    return QnaBoardSyncResponse(queued=True)
