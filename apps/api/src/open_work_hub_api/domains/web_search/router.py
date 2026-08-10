from __future__ import annotations

from dataclasses import replace
import json
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.dependencies import require_current_user, require_current_workspace
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_work_hub_api.domains.conversations import app_persistence
from open_work_hub_api.domains.conversations.app_scope_adapters import (
    WEB_SEARCH_SCOPE_REF,
)
from open_work_hub_api.domains.web_search import service
from open_work_hub_api.domains.web_search.app_catalog import (
    WEB_SEARCH_WORKSPACE_APP,
)
from open_work_hub_api.domains.web_search.schemas import WebSearchAskRequest


logger = logging.getLogger(__name__)


def build_web_search_router(
    *,
    prefix: str,
    app_id: str,
    profile_id: str,
    conversation_scope_ref: str,
    tag: str,
) -> APIRouter:
    app_enabled = require_workspace_app_enabled(
        app_id,
        error_code="web_search.app_disabled",
    )
    app_router = APIRouter(
        prefix=prefix,
        tags=[tag],
        dependencies=[Depends(app_enabled)],
    )

    @app_router.post("/ask/stream")
    async def ask_stream(
        payload: WebSearchAskRequest,
        db: Session = Depends(get_db_session),
        current_user: User = Depends(require_current_user),
        current_workspace: Workspace = Depends(require_current_workspace),
    ) -> EventSourceResponse:
        if not payload.question.strip():
            raise localized_http_exception(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="request.invalid_payload",
            )
        return EventSourceResponse(
            _ask_stream_publisher(
                payload=payload,
                app_id=app_id,
                profile_id=profile_id,
                conversation_scope_ref=conversation_scope_ref,
                db=db,
                current_user=current_user,
                current_workspace=current_workspace,
            ),
            ping=25,
        )

    return app_router


async def _ask_stream_publisher(
    *,
    payload: WebSearchAskRequest,
    app_id: str,
    profile_id: str,
    conversation_scope_ref: str,
    db: Session,
    current_user: User,
    current_workspace: Workspace,
):
    conversation = None
    question = payload.question.strip()
    source = f"api.{profile_id}.web_search"
    try:
        prepared_execution = service.prepare_web_search_execution(
            question=question,
            max_uses=payload.max_uses,
            profile_id=profile_id,
            workspace_id=current_workspace.id,
            app_id=app_id,
            actor_user_id=current_user.id,
            principal_id=current_user.id,
            source=source,
            conversation_id=payload.conversation_id,
            db=db,
        )
        persisted_question = (
            prepared_execution.provider_question
            if prepared_execution.external_execution.decision.mask_applied
            else question
        )
        conversation = app_persistence.append_user_and_attach(
            db,
            workspace=current_workspace,
            user=current_user,
            conversation_id=payload.conversation_id,
            scope_ref=conversation_scope_ref,
            scope_resource_id="default",
            content=persisted_question,
            meta={"kind": "web_search", "profile_id": profile_id},
        ).conversation
        prepared_execution.external_execution.request = replace(
            prepared_execution.external_execution.request,
            conversation_id=conversation.id,
        )
        prepared_execution = replace(
            prepared_execution,
            conversation_id=conversation.id,
        )
        yield _web_search_sse(
            "conversation_attached",
            {
                "conversation_id": conversation.id,
                "display_question": persisted_question,
            },
        )
        async for event in service.stream_web_search_answer(
            question=question,
            max_uses=payload.max_uses,
            profile_id=profile_id,
            conversation_id=conversation.id,
            db=db,
            prepared_execution=prepared_execution,
        ):
            if isinstance(event, service.WebSearchAnswerDelta):
                yield _web_search_sse("content_delta", {"text": event.text})
            else:
                response = event.response.model_copy(update={"conversation_id": conversation.id})
                _append_web_search_assistant_turn(
                    db,
                    conversation=conversation,
                    response=response,
                    profile_id=profile_id,
                )
                yield _web_search_sse(
                    "web_search_response",
                    {"response": response.model_dump(mode="json")},
                )
                yield _web_search_sse("done", {"finish_reason": "stop"})
    except service.WebSearchConfigurationError:
        _append_web_search_error_turn(
            db,
            conversation=conversation,
            message="Web search is not configured.",
        )
        yield _web_search_sse_error(
            "web_search.not_configured",
            "Web search is not configured.",
            retryable=False,
        )
    except service.WebSearchGenerationError:
        _append_web_search_error_turn(
            db,
            conversation=conversation,
            message="Web search answer generation failed.",
        )
        yield _web_search_sse_error(
            "web_search.generation_failed",
            "Web search answer generation failed.",
        )
    except service.WebSearchPolicyError as error:
        message = _web_search_policy_denied_message(str(error))
        _append_web_search_error_turn(
            db,
            conversation=conversation,
            message=message,
        )
        yield _web_search_sse_error(
            "web_search.policy_denied",
            message,
            retryable=False,
        )
    except Exception:
        logger.exception("web_search.ask_stream_failed")
        _append_web_search_error_turn(
            db,
            conversation=conversation,
            message="Web search streaming failed.",
        )
        yield _web_search_sse_error(
            "web_search.stream_failed",
            "Web search streaming failed.",
        )


def _web_search_sse(event_type: str, data: dict) -> dict[str, str]:
    return {
        "event": event_type,
        "data": json.dumps(
            {"type": event_type, "data": data},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def _web_search_sse_error(
    code: str,
    message: str,
    *,
    retryable: bool = True,
) -> dict[str, str]:
    return _web_search_sse(
        "error",
        {"code": code, "message": message, "retryable": retryable},
    )


def _web_search_policy_denied_message(reason_code: str) -> str:
    normalized = (reason_code or "").strip()
    if normalized in {
        "pii_detected",
        "sensitive_entity_blocked",
        "internal_context_blocked",
        "sensitivity_label_blocked",
        "ai_security_policy_denied",
        "ai_security_policy_block_external",
        "ai_security_policy_local_only",
    }:
        return (
            "이 요청은 웹 검색으로 처리하기 어렵습니다. "
            "공개 가능한 내용만 남겨 다시 시도하거나, 일반 AI 대화에서 이어서 진행해 주세요."
        )
    return "현재 입력은 웹 검색으로 처리할 수 없습니다. 내용을 줄이거나 공개 가능한 정보만 포함해 다시 시도해 주세요."


def _append_web_search_assistant_turn(
    db: Session,
    *,
    conversation,
    response,
    profile_id: str,
) -> None:
    try:
        app_persistence.append_assistant_app_turn(
            db,
            conversation=conversation,
            content=service.format_answer_for_history(response),
            meta={
                "kind": "web_search",
                "profile_id": profile_id,
                "model": response.model,
                "usage": (
                    response.usage.model_dump(mode="json") if response.usage is not None else None
                ),
                "citations": [citation.model_dump(mode="json") for citation in response.citations],
                "response_status": "done",
            },
        )
    except Exception:  # noqa: BLE001 - history persistence must not break SSE delivery
        db.rollback()
        logger.exception("web_search.assistant_turn_persist_failed")


def _append_web_search_error_turn(
    db: Session,
    *,
    conversation,
    message: str,
) -> None:
    if conversation is None:
        return
    try:
        app_persistence.append_assistant_app_turn(
            db,
            conversation=conversation,
            content=message,
            meta={"kind": "web_search", "response_status": "error"},
        )
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("web_search.error_turn_persist_failed")


router = build_web_search_router(
    prefix="/web-search",
    app_id=WEB_SEARCH_WORKSPACE_APP.app_id,
    profile_id="general",
    conversation_scope_ref=WEB_SEARCH_SCOPE_REF,
    tag="web-search",
)
