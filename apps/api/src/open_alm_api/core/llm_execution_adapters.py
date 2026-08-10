from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAIError,
)

from open_alm_api.core.i18n import LocalizedApiMessage
from open_alm_api.core.llm_adapters import StreamChunk, get_stream_adapter
from open_alm_api.core.llm_errors import LlmProviderError
from open_alm_api.core.llm_official_providers import (
    check_official_provider_health,
    complete_official_provider_chat,
    stream_official_provider_chat,
)
from open_alm_api.core.llm_provider_registry import external_llm_provider_descriptor
from open_alm_api.core.llm_provider_registry import external_llm_provider_ids


LlmExecutionHealthStatus = Literal["ready", "unavailable", "model_missing"]
SyncPoolClientFactory = Callable[[str, str | None], Any]
AsyncPoolClientFactory = Callable[[str, str | None], Any]


class LlmExecutionConfig(Protocol):
    pool: str
    provider: str
    base_url: str
    api_key: str
    default_model: str
    canonical_model: str
    healthcheck_timeout_seconds: float
    long_generation_timeout_seconds: float


class LlmExecutionAdapter(Protocol):
    adapter_id: str
    supports_tools: bool

    def complete(
        self,
        config: LlmExecutionConfig,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
        sync_client_factory: SyncPoolClientFactory,
    ) -> Any: ...

    async def stream(
        self,
        config: LlmExecutionConfig,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
        sync_client_factory: SyncPoolClientFactory,
        async_client_factory: AsyncPoolClientFactory,
    ) -> AsyncIterator[StreamChunk]: ...

    def check_health(
        self,
        config: LlmExecutionConfig,
        *,
        sync_client_factory: SyncPoolClientFactory,
    ) -> "LlmExecutionHealthResult": ...


@dataclass(frozen=True)
class LlmExecutionHealthResult:
    status: LlmExecutionHealthStatus
    detail: str | LocalizedApiMessage | None = None


_adapters_by_key: dict[tuple[str, str | None], LlmExecutionAdapter] = {}
_SYNC_ITERATOR_DONE = object()


def register_llm_execution_adapter(
    *,
    pool: str,
    provider: str | None,
    adapter: LlmExecutionAdapter,
) -> None:
    key = (_normalize_key(pool), _normalize_optional_key(provider))
    if key in _adapters_by_key:
        raise ValueError(f"LLM execution adapter already registered for {key}")
    _adapters_by_key[key] = adapter


def select_llm_execution_adapter(
    pool: str,
    provider: str | None,
) -> LlmExecutionAdapter:
    ensure_default_llm_execution_adapters_registered()
    normalized_pool = _normalize_key(pool)
    normalized_provider = _normalize_optional_key(provider)
    adapter = _adapters_by_key.get((normalized_pool, normalized_provider))
    if adapter is not None:
        return adapter
    if _can_use_pool_fallback(normalized_pool, normalized_provider):
        adapter = _adapters_by_key.get((normalized_pool, None))
        if adapter is not None:
            return adapter
    raise ValueError(f"no LLM execution adapter registered for {normalized_pool}/{normalized_provider}")


def supports_tool_calling(pool: str, provider: str | None = None) -> bool:
    return select_llm_execution_adapter(pool, provider).supports_tools


def llm_execution_adapter_keys() -> tuple[str, ...]:
    ensure_default_llm_execution_adapters_registered()
    return tuple(
        sorted(
            f"{pool}:{provider or '*'}"
            for pool, provider in _adapters_by_key
        )
    )


def reset_llm_execution_adapters() -> None:
    _adapters_by_key.clear()


def ensure_default_llm_execution_adapters_registered() -> None:
    openai_compatible = OpenAICompatibleLlmExecutionAdapter()
    official = OfficialProviderLlmExecutionAdapter()
    _register_default_adapter(
        pool="local",
        provider=None,
        adapter=openai_compatible,
    )
    _register_default_adapter(
        pool="external",
        provider=None,
        adapter=openai_compatible,
    )
    for provider in external_llm_provider_ids():
        descriptor = external_llm_provider_descriptor(provider)
        adapter = (
            openai_compatible
            if descriptor is not None and descriptor.execution_adapter_id == "openai_compatible"
            else official
            if descriptor is not None and descriptor.execution_adapter_id == "official"
            else None
        )
        if adapter is None:
            continue
        _register_default_adapter(
            pool="external",
            provider=provider,
            adapter=adapter,
        )


class OpenAICompatibleLlmExecutionAdapter:
    adapter_id = "openai_compatible"
    supports_tools = True

    def complete(
        self,
        config: LlmExecutionConfig,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
        sync_client_factory: SyncPoolClientFactory,
    ) -> Any:
        client = sync_client_factory(
            config.pool,
            config.provider if config.pool == "external" else None,
        ).with_options(timeout=timeout_seconds)
        try:
            return client.chat.completions.create(**payload)
        except OpenAIError as error:
            raise _provider_error(config, error) from error

    async def stream(
        self,
        config: LlmExecutionConfig,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
        sync_client_factory: SyncPoolClientFactory,
        async_client_factory: AsyncPoolClientFactory,
    ) -> AsyncIterator[StreamChunk]:
        del sync_client_factory
        adapter = get_stream_adapter(config.pool, config.provider)
        client = async_client_factory(
            config.pool,
            config.provider if config.pool == "external" else None,
        ).with_options(timeout=timeout_seconds)
        try:
            async for chunk in adapter.open_stream(client, payload):
                yield chunk
        except OpenAIError as error:
            raise _provider_error(config, error) from error

    def check_health(
        self,
        config: LlmExecutionConfig,
        *,
        sync_client_factory: SyncPoolClientFactory,
    ) -> LlmExecutionHealthResult:
        try:
            models = sync_client_factory(
                config.pool,
                config.provider if config.pool == "external" else None,
            ).models.list()
        except (APIConnectionError, APITimeoutError) as error:
            return LlmExecutionHealthResult(
                status="unavailable",
                detail=LocalizedApiMessage(
                    code="llm.provider_unavailable",
                    params={"reason": str(error)},
                ),
            )
        except APIStatusError as error:
            return LlmExecutionHealthResult(
                status="unavailable",
                detail=LocalizedApiMessage(
                    code="llm.provider_status_error",
                    params={"status_code": error.status_code, "message": error.message},
                ),
            )
        except OpenAIError as error:
            return LlmExecutionHealthResult(
                status="unavailable",
                detail=LocalizedApiMessage(
                    code="llm.provider_unavailable",
                    params={"reason": str(error)},
                ),
            )

        model_ids = {model.id for model in models.data}
        if config.default_model not in model_ids:
            return LlmExecutionHealthResult(
                status="model_missing",
                detail=LocalizedApiMessage(
                    code="llm.configured_model_missing",
                    params={"models": ", ".join(sorted(model_ids))},
                ),
            )
        return LlmExecutionHealthResult(status="ready")


class OfficialProviderLlmExecutionAdapter:
    adapter_id = "official_provider"
    supports_tools = False

    def complete(
        self,
        config: LlmExecutionConfig,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
        sync_client_factory: SyncPoolClientFactory,
    ) -> Any:
        del sync_client_factory
        try:
            return complete_official_provider_chat(
                config,
                payload,
                timeout_seconds=timeout_seconds,
            )
        except Exception as error:
            raise _provider_error(config, error) from error

    async def stream(
        self,
        config: LlmExecutionConfig,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
        sync_client_factory: SyncPoolClientFactory,
        async_client_factory: AsyncPoolClientFactory,
    ) -> AsyncIterator[StreamChunk]:
        del sync_client_factory, async_client_factory
        stream = stream_official_provider_chat(
            config,
            payload,
            timeout_seconds=timeout_seconds,
        )
        try:
            async for chunk in _iterate_sync_stream(stream):
                yield chunk
        except Exception as error:
            raise _provider_error(config, error) from error

    def check_health(
        self,
        config: LlmExecutionConfig,
        *,
        sync_client_factory: SyncPoolClientFactory,
    ) -> LlmExecutionHealthResult:
        del sync_client_factory
        health = check_official_provider_health(
            config,
            timeout_seconds=config.healthcheck_timeout_seconds,
        )
        return LlmExecutionHealthResult(
            status=health.status,
            detail=health.detail,
        )


def _register_default_adapter(
    *,
    pool: str,
    provider: str | None,
    adapter: LlmExecutionAdapter,
) -> None:
    key = (_normalize_key(pool), _normalize_optional_key(provider))
    if key in _adapters_by_key:
        return
    register_llm_execution_adapter(pool=pool, provider=provider, adapter=adapter)


def _normalize_key(value: str) -> str:
    return (value or "").strip().lower()


def _normalize_optional_key(value: str | None) -> str | None:
    normalized = _normalize_key(value or "")
    return normalized or None


def _can_use_pool_fallback(pool: str, provider: str | None) -> bool:
    if provider is None or pool != "external":
        return True
    descriptor = external_llm_provider_descriptor(provider)
    return bool(descriptor and descriptor.openai_compatible)


def _provider_error(
    config: LlmExecutionConfig,
    error: Exception,
) -> LlmProviderError:
    return LlmProviderError(
        str(error),
        pool=config.pool,
        provider=config.provider,
    )


async def _iterate_sync_stream(stream: Any) -> AsyncIterator[StreamChunk]:
    try:
        while True:
            chunk = await asyncio.to_thread(_next_sync_stream_chunk, stream)
            if chunk is _SYNC_ITERATOR_DONE:
                break
            yield chunk
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            await asyncio.to_thread(close)


def _next_sync_stream_chunk(stream: Any) -> StreamChunk | object:
    try:
        return next(stream)
    except StopIteration:
        return _SYNC_ITERATOR_DONE


__all__ = [
    "LlmExecutionAdapter",
    "LlmExecutionHealthResult",
    "OfficialProviderLlmExecutionAdapter",
    "OpenAICompatibleLlmExecutionAdapter",
    "ensure_default_llm_execution_adapters_registered",
    "llm_execution_adapter_keys",
    "register_llm_execution_adapter",
    "reset_llm_execution_adapters",
    "select_llm_execution_adapter",
    "supports_tool_calling",
]
