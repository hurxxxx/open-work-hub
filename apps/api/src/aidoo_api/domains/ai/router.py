from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from openai import OpenAIError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.core.llm import (
    LlmPoolHint,
    LlmPoolName,
    LlmTaskContext,
    check_all_pools_health,
    check_llm_stack_health,
    complete_chat,
)
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.auth.dependencies import require_current_user
from aidoo_api.domains.auth.models import User


LlmRequestBackendMode = Literal["auto", "local", "openrouter"]


class LlmBackendHealthResponse(BaseModel):
    name: str
    provider: str
    base_url: str
    model: str
    canonical_model: str
    status: str
    ready: bool
    detail: str | None = None


class LlmHealthResponse(LlmBackendHealthResponse):
    active_backend: str | None = None
    primary: LlmBackendHealthResponse
    fallback: LlmBackendHealthResponse | None = None


class LlmPoolHealthResponse(BaseModel):
    pool: str
    provider: str
    base_url: str
    model: str
    canonical_model: str
    status: str
    ready: bool
    detail: str | None = None


class LlmDualHealthResponse(BaseModel):
    ready: bool
    local: LlmPoolHealthResponse
    external: LlmPoolHealthResponse | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
    backend_mode: LlmRequestBackendMode = "auto"
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    reasoning_effort: Literal["none", "low", "medium", "high"] = "none"


class ChatUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatResponse(BaseModel):
    model: str
    content: str
    usage: ChatUsage | None = None
    provider: str
    backend: str
    fallback_used: bool = False
    canonical_model: str
    requested_backend_mode: str
    policy: str | None = None
    chosen_pool: str | None = None
    decision_reason: str | None = None
    forced_local: bool = False
    pii_hits: list[str] = Field(default_factory=list)


router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/llm-health", response_model=LlmHealthResponse)
def llm_health() -> LlmHealthResponse:
    """Deprecated legacy shape. Kept for the current web UI until it migrates
    to ``/ai/health``; backed by the same pool-scoped checks underneath.
    """
    return LlmHealthResponse.model_validate(check_llm_stack_health().public_dict())


@router.get("/health", response_model=LlmDualHealthResponse)
def ai_health() -> LlmDualHealthResponse:
    """Pool-scoped AI readiness. Each pool's status is reported independently;
    overall ``ready`` is true if at least one pool is usable. Routing decisions
    are still policy-driven, not fallback-driven.
    """
    return LlmDualHealthResponse.model_validate(check_all_pools_health().public_dict())


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ChatResponse:
    _ensure_configured_model(payload.model)
    _ensure_supported_backend_mode(payload.backend_mode)
    context = _build_task_context(current_user, request)
    return _complete_via_policy(
        context,
        payload,
        db,
        pool_hint="local" if payload.backend_mode == "local" else None,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_task_context(current_user: User, request: Request) -> LlmTaskContext:
    workspace = getattr(request.state, "current_workspace", None)
    workspace_id = getattr(workspace, "id", None) if workspace else None
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Workspace context missing on request.state; the AI router "
                "must be mounted behind a workspace membership dependency."
            ),
        )
    return LlmTaskContext(
        source="api.chat",
        actor_user_id=current_user.id,
        workspace_id=workspace_id,
        task_kind="chatbot",
    )


def _complete_via_policy(
    context: LlmTaskContext,
    payload: ChatRequest,
    db: Session,
    *,
    pool_hint: LlmPoolHint | None,
) -> ChatResponse:
    try:
        response, decision, config = complete_chat(
            context,
            db,
            messages=[message.model_dump() for message in payload.messages],
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            reasoning_effort=payload.reasoning_effort,
            model=payload.model,
            pool_hint=pool_hint,
        )
    except OpenAIError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": (
                    "Local LLM pool unavailable for the requested override."
                    if pool_hint == "local"
                    else "LLM pool unavailable for the resolved policy."
                ),
                "error": str(error),
            },
        ) from error

    return _build_response(
        response,
        config,
        payload,
        decision_policy=decision.policy,
        decision_pool=decision.chosen_pool,
        decision_reason=decision.reason,
        decision_forced_local=decision.forced_local,
        decision_pii=list(decision.pii_hits),
    )


def _build_response(
    raw_response,
    config,
    payload: ChatRequest,
    *,
    decision_policy: str | None,
    decision_pool: LlmPoolName | None,
    decision_reason: str | None,
    decision_forced_local: bool,
    decision_pii: list[str],
) -> ChatResponse:
    message = raw_response.choices[0].message
    usage = None
    if raw_response.usage is not None:
        usage = ChatUsage(
            prompt_tokens=raw_response.usage.prompt_tokens,
            completion_tokens=raw_response.usage.completion_tokens,
            total_tokens=raw_response.usage.total_tokens,
        )

    backend_name = "fallback" if decision_pool == "external" else "primary"

    return ChatResponse(
        model=raw_response.model,
        content=message.content or "",
        usage=usage,
        provider=config.provider,
        backend=backend_name,
        fallback_used=backend_name == "fallback",
        canonical_model=config.canonical_model,
        requested_backend_mode=payload.backend_mode,
        policy=decision_policy,
        chosen_pool=decision_pool,
        decision_reason=decision_reason,
        forced_local=decision_forced_local,
        pii_hits=decision_pii,
    )


def _ensure_configured_model(requested_model: str | None) -> None:
    if requested_model is None:
        return

    settings = get_settings()
    allowed_models = {
        settings.llm_local_default_model,
        settings.llm_local_canonical_model,
        settings.llm_external_default_model,
        settings.llm_external_canonical_model,
    }
    if requested_model in allowed_models:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Only the configured LLM model is allowed. "
            f"Use {settings.llm_local_canonical_model} for quality control."
        ),
    )


def _ensure_supported_backend_mode(mode: LlmRequestBackendMode) -> None:
    if mode != "openrouter":
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "backend_mode=openrouter is no longer supported. "
            "Use auto for policy-based routing or local to pin the local pool."
        ),
    )
