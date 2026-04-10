from typing import Literal

from fastapi import APIRouter, HTTPException, status
from openai import OpenAIError
from pydantic import BaseModel, Field

from aidoo_api.core.llm import check_llm_health, get_llm_client, require_llm_ready
from aidoo_api.core.settings import get_settings


class LlmHealthResponse(BaseModel):
    provider: str
    base_url: str
    model: str
    status: str
    ready: bool
    detail: str | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
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


router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/llm-health", response_model=LlmHealthResponse)
def llm_health() -> LlmHealthResponse:
    return LlmHealthResponse.model_validate(check_llm_health().public_dict())


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    settings = get_settings()
    require_llm_ready(settings)
    model = payload.model or settings.llm_default_model

    try:
        response = get_llm_client().chat.completions.create(
            model=model,
            messages=[message.model_dump() for message in payload.messages],
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            extra_body={"reasoning_effort": payload.reasoning_effort},
        )
    except OpenAIError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM request failed: {error}",
        ) from error

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
    )
