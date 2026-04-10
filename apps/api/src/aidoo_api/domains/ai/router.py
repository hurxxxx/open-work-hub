from typing import Literal

from fastapi import APIRouter, HTTPException, status
from openai import OpenAIError
from pydantic import BaseModel, Field

from aidoo_api.core.llm import (
    LlmBackendName,
    LlmHealth,
    check_llm_health,
    check_llm_stack_health,
    get_llm_backend,
    get_llm_client,
)
from aidoo_api.core.settings import get_settings


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


router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/llm-health", response_model=LlmHealthResponse)
def llm_health() -> LlmHealthResponse:
    return LlmHealthResponse.model_validate(check_llm_stack_health().public_dict())


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    settings = get_settings()
    _ensure_configured_model(payload.model, settings)

    if payload.backend_mode == "local":
        return _complete_single_backend(payload, "primary")

    if payload.backend_mode == "openrouter":
        return _complete_single_backend(payload, "fallback")

    primary_health = check_llm_health(settings, "primary")
    primary_error: str | None = None

    if primary_health.ready:
        try:
            return _complete_chat(payload, "primary")
        except OpenAIError as error:
            primary_error = str(error)
    else:
        primary_error = primary_health.detail or primary_health.status

    fallback_health = check_llm_health(settings, "fallback")
    if fallback_health.ready:
        try:
            return _complete_chat(payload, "fallback")
        except OpenAIError as error:
            raise _llm_unavailable(
                primary_health, fallback_health, primary_error, str(error)
            ) from error

    raise _llm_unavailable(
        primary_health,
        fallback_health,
        primary_error,
        fallback_health.detail or fallback_health.status,
    )


def _ensure_configured_model(requested_model: str | None, settings) -> None:
    if requested_model is None:
        return

    allowed_models = {
        settings.llm_default_model,
        settings.llm_canonical_model,
        settings.llm_fallback_model,
    }
    if requested_model in allowed_models:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Only the configured LLM model is allowed. "
            f"Use {settings.llm_canonical_model} for quality control."
        ),
    )


def _complete_single_backend(payload: ChatRequest, backend: LlmBackendName) -> ChatResponse:
    settings = get_settings()
    health = check_llm_health(settings, backend)
    if not health.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": f"Requested LLM backend is not ready: {backend}",
                "llm": health.public_dict(),
            },
        )

    try:
        return _complete_chat(payload, backend)
    except OpenAIError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": f"Requested LLM backend failed: {backend}",
                "error": str(error),
                "llm": health.public_dict(),
            },
        ) from error


def _complete_chat(payload: ChatRequest, backend: LlmBackendName) -> ChatResponse:
    config = get_llm_backend(backend)
    response = get_llm_client(backend).chat.completions.create(
        model=config.model,
        messages=[message.model_dump() for message in payload.messages],
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        extra_body=_extra_body(payload, backend),
    )

    message = response.choices[0].message
    usage = None
    if response.usage is not None:
        usage = ChatUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
        )

    return ChatResponse(
        model=response.model,
        content=message.content or "",
        usage=usage,
        provider=config.provider,
        backend=config.name,
        fallback_used=config.name == "fallback",
        canonical_model=config.canonical_model,
        requested_backend_mode=payload.backend_mode,
    )


def _extra_body(payload: ChatRequest, backend: LlmBackendName) -> dict[str, object]:
    if payload.reasoning_effort == "none":
        return {"think": False} if backend == "primary" else {}

    if backend == "fallback":
        return {"reasoning": {"effort": payload.reasoning_effort}}

    return {"reasoning_effort": payload.reasoning_effort}


def _llm_unavailable(
    primary_health: LlmHealth,
    fallback_health: LlmHealth,
    primary_error: str | None,
    fallback_error: str | None,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "message": "LLM request failed on both local Ollama and OpenRouter fallback.",
            "primary_error": primary_error,
            "fallback_error": fallback_error,
            "llm": {
                "primary": primary_health.public_dict(),
                "fallback": fallback_health.public_dict(),
            },
        },
    )
