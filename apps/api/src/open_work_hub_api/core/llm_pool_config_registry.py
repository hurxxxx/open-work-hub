from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from open_work_hub_api.core.llm_provider_registry import (
    external_llm_provider_ids,
    llm_provider_descriptor,
)
from open_work_hub_api.core.settings import Settings


@dataclass(frozen=True)
class LlmPoolConfigValues:
    provider: str
    base_url: str
    api_key: str
    default_model: str
    canonical_model: str
    long_generation_timeout_seconds: float
    enabled: bool = True
    default_headers: Mapping[str, str] | None = None
    requires_credentials: bool = True


LlmPoolConfigResolver = Callable[[Settings], LlmPoolConfigValues]


_resolvers_by_key: dict[tuple[str, str | None], LlmPoolConfigResolver] = {}


def register_llm_pool_config_resolver(
    *,
    pool: str,
    provider: str | None,
    resolver: LlmPoolConfigResolver,
) -> None:
    key = (_normalize_key(pool), _normalize_optional_key(provider))
    if key in _resolvers_by_key:
        raise ValueError(f"LLM pool config resolver already registered for {key}")
    _resolvers_by_key[key] = resolver


def resolve_llm_pool_config_values(
    *,
    pool: str,
    provider: str | None,
    settings: Settings,
) -> LlmPoolConfigValues:
    ensure_default_llm_pool_config_resolvers_registered()
    normalized_pool = _normalize_key(pool)
    normalized_provider = _normalize_optional_key(provider)
    resolver = _resolvers_by_key.get((normalized_pool, normalized_provider))
    if resolver is None:
        raise ValueError(
            f"no LLM pool config resolver registered for "
            f"{normalized_pool}/{normalized_provider or '*'}"
        )
    return resolver(settings)


def llm_pool_config_resolver_keys() -> tuple[str, ...]:
    ensure_default_llm_pool_config_resolvers_registered()
    return tuple(sorted(f"{pool}:{provider or '*'}" for pool, provider in _resolvers_by_key))


def reset_llm_pool_config_resolvers() -> None:
    _resolvers_by_key.clear()


def ensure_default_llm_pool_config_resolvers_registered() -> None:
    _register_default_resolver(
        pool="local",
        provider=None,
        resolver=_local_pool_config,
    )
    for provider_id in external_llm_provider_ids():
        _register_default_resolver(
            pool="external",
            provider=provider_id,
            resolver=lambda settings, provider_id=provider_id: _external_pool_config(
                settings,
                provider_id=provider_id,
            ),
        )


def _register_default_resolver(
    *,
    pool: str,
    provider: str | None,
    resolver: LlmPoolConfigResolver,
) -> None:
    key = (_normalize_key(pool), _normalize_optional_key(provider))
    if key in _resolvers_by_key:
        return
    register_llm_pool_config_resolver(pool=pool, provider=provider, resolver=resolver)


def _local_pool_config(settings: Settings) -> LlmPoolConfigValues:
    return LlmPoolConfigValues(
        provider=settings.llm_local_provider,
        base_url=settings.llm_local_base_url,
        api_key=settings.llm_local_api_key,
        # Model selection belongs to the DB-backed workload control plane.
        default_model="",
        canonical_model="",
        long_generation_timeout_seconds=settings.llm_local_long_generation_timeout_seconds,
        enabled=True,
        requires_credentials=False,
    )


def _external_pool_config(
    settings: Settings,
    *,
    provider_id: str,
) -> LlmPoolConfigValues:
    descriptor = llm_provider_descriptor(provider_id)
    if descriptor is None or descriptor.route_mode != "external":
        raise ValueError(f"unknown external LLM provider: {provider_id}")
    return LlmPoolConfigValues(
        provider=provider_id,
        base_url=descriptor.default_endpoint_url,
        api_key="",
        default_model="",
        canonical_model="",
        long_generation_timeout_seconds=settings.llm_external_long_generation_timeout_seconds,
        enabled=True,
    )


def _normalize_key(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_optional_key(value: str | None) -> str | None:
    normalized = _normalize_key(value)
    return normalized or None


__all__ = [
    "LlmPoolConfigValues",
    "ensure_default_llm_pool_config_resolvers_registered",
    "llm_pool_config_resolver_keys",
    "register_llm_pool_config_resolver",
    "reset_llm_pool_config_resolvers",
    "resolve_llm_pool_config_values",
]
