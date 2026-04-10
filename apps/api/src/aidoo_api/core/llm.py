from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Literal

from fastapi import HTTPException, status
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, OpenAIError

from aidoo_api.core.settings import Settings, get_settings


LlmHealthStatus = Literal["ready", "unavailable", "model_missing"]


@dataclass(frozen=True)
class LlmHealth:
    provider: str
    base_url: str
    model: str
    status: LlmHealthStatus
    detail: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def public_dict(self) -> dict[str, str | bool | None]:
        return {**asdict(self), "ready": self.ready}


@lru_cache(maxsize=1)
def get_llm_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_retries=0,
        timeout=settings.llm_request_timeout_seconds,
    )


def check_llm_health(settings: Settings | None = None) -> LlmHealth:
    settings = settings or get_settings()
    try:
        models = get_llm_client().models.list()
    except (APIConnectionError, APITimeoutError) as error:
        return LlmHealth(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            model=settings.llm_default_model,
            status="unavailable",
            detail=str(error),
        )
    except APIStatusError as error:
        return LlmHealth(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            model=settings.llm_default_model,
            status="unavailable",
            detail=f"{error.status_code}: {error.message}",
        )
    except OpenAIError as error:
        return LlmHealth(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            model=settings.llm_default_model,
            status="unavailable",
            detail=str(error),
        )

    model_ids = {model.id for model in models.data}
    if settings.llm_default_model not in model_ids:
        return LlmHealth(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            model=settings.llm_default_model,
            status="model_missing",
            detail=f"Configured model was not found. Available models: {', '.join(sorted(model_ids))}",
        )

    return LlmHealth(
        provider=settings.llm_provider,
        base_url=settings.llm_base_url,
        model=settings.llm_default_model,
        status="ready",
    )


def require_llm_ready(settings: Settings | None = None) -> LlmHealth:
    health = check_llm_health(settings)
    if health.ready:
        return health

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "message": "LLM backend is not ready.",
            "llm": health.public_dict(),
        },
    )
