from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Literal

from fastapi import HTTPException, status
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, OpenAIError

from aidoo_api.core.settings import Settings, get_settings


LlmBackendName = Literal["primary", "fallback"]
LlmHealthStatus = Literal["ready", "unavailable", "model_missing", "not_configured", "disabled"]


@dataclass(frozen=True)
class LlmBackendConfig:
    name: LlmBackendName
    provider: str
    base_url: str
    api_key: str
    model: str
    canonical_model: str
    enabled: bool = True
    default_headers: dict[str, str] | None = None

    @property
    def configured(self) -> bool:
        return (
            self.enabled
            and bool(self.base_url.strip())
            and bool(self.api_key.strip())
            and bool(self.model.strip())
        )


@dataclass(frozen=True)
class LlmHealth:
    name: LlmBackendName
    provider: str
    base_url: str
    model: str
    canonical_model: str
    status: LlmHealthStatus
    detail: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def public_dict(self) -> dict[str, str | bool | None]:
        return {**asdict(self), "ready": self.ready}


@dataclass(frozen=True)
class LlmStackHealth:
    primary: LlmHealth
    fallback: LlmHealth | None

    @property
    def ready(self) -> bool:
        return self.primary.ready or bool(self.fallback and self.fallback.ready)

    @property
    def active(self) -> LlmHealth:
        if self.primary.ready:
            return self.primary
        if self.fallback and self.fallback.ready:
            return self.fallback
        return self.primary

    def public_dict(self) -> dict[str, object]:
        active = self.active
        return {
            **active.public_dict(),
            "ready": self.ready,
            "active_backend": active.name if active.ready else None,
            "primary": self.primary.public_dict(),
            "fallback": self.fallback.public_dict() if self.fallback else None,
        }


def get_llm_backend(
    backend: LlmBackendName = "primary", settings: Settings | None = None
) -> LlmBackendConfig:
    settings = settings or get_settings()
    if backend == "primary":
        return LlmBackendConfig(
            name="primary",
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_default_model,
            canonical_model=settings.llm_canonical_model,
        )

    default_headers: dict[str, str] = {}
    if settings.llm_fallback_http_referer.strip():
        default_headers["HTTP-Referer"] = settings.llm_fallback_http_referer.strip()
    if settings.llm_fallback_title.strip():
        default_headers["X-OpenRouter-Title"] = settings.llm_fallback_title.strip()

    return LlmBackendConfig(
        name="fallback",
        provider=settings.llm_fallback_provider,
        base_url=settings.llm_fallback_base_url,
        api_key=settings.llm_fallback_api_key,
        model=settings.llm_fallback_model,
        canonical_model=settings.llm_canonical_model,
        enabled=settings.llm_fallback_enabled,
        default_headers=default_headers or None,
    )


@lru_cache(maxsize=2)
def get_llm_client(backend: LlmBackendName = "primary") -> OpenAI:
    config = get_llm_backend(backend)
    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        default_headers=config.default_headers,
        max_retries=0,
        timeout=get_settings().llm_request_timeout_seconds,
    )


def check_llm_health(
    settings: Settings | None = None, backend: LlmBackendName = "primary"
) -> LlmHealth:
    settings = settings or get_settings()
    config = get_llm_backend(backend, settings)

    if not config.enabled:
        return LlmHealth(
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            canonical_model=config.canonical_model,
            status="disabled",
            detail="LLM fallback is disabled.",
        )

    if not config.configured:
        missing = [
            name
            for name, value in {
                "base_url": config.base_url,
                "api_key": config.api_key,
                "model": config.model,
            }.items()
            if not value.strip()
        ]
        return LlmHealth(
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            canonical_model=config.canonical_model,
            status="not_configured",
            detail=f"Missing LLM {config.name} setting(s): {', '.join(missing)}",
        )

    try:
        models = get_llm_client(backend).models.list()
    except (APIConnectionError, APITimeoutError) as error:
        return LlmHealth(
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            canonical_model=config.canonical_model,
            status="unavailable",
            detail=str(error),
        )
    except APIStatusError as error:
        return LlmHealth(
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            canonical_model=config.canonical_model,
            status="unavailable",
            detail=f"{error.status_code}: {error.message}",
        )
    except OpenAIError as error:
        return LlmHealth(
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            canonical_model=config.canonical_model,
            status="unavailable",
            detail=str(error),
        )

    model_ids = {model.id for model in models.data}
    if config.model not in model_ids:
        return LlmHealth(
            name=config.name,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            canonical_model=config.canonical_model,
            status="model_missing",
            detail=f"Configured model was not found. Available models: {', '.join(sorted(model_ids))}",
        )

    return LlmHealth(
        name=config.name,
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        canonical_model=config.canonical_model,
        status="ready",
    )


def check_llm_stack_health(
    settings: Settings | None = None, check_fallback: bool = True
) -> LlmStackHealth:
    settings = settings or get_settings()
    primary = check_llm_health(settings, "primary")
    fallback = check_llm_health(settings, "fallback") if check_fallback else None
    return LlmStackHealth(primary=primary, fallback=fallback)


def require_llm_ready(settings: Settings | None = None) -> LlmStackHealth:
    health = check_llm_stack_health(settings)
    if health.ready:
        return health

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "message": "No LLM backend is ready.",
            "llm": health.public_dict(),
        },
    )
