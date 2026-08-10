from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LlmProviderDescriptor:
    provider_id: str
    display_name: str = ""
    default_endpoint_url: str = ""
    route_mode: Literal["local", "external"] = "external"
    credential_kind: Literal["none", "api_key"] = "api_key"
    discovery_adapter_id: str = ""
    execution_adapter_id: str = ""
    aliases: tuple[str, ...] = ()
    official: bool = True
    openai_compatible: bool = False
    control_plane_visible: bool = True


# Compatibility name for existing external-provider extensions.
ExternalLlmProviderDescriptor = LlmProviderDescriptor


_providers_by_id: dict[str, LlmProviderDescriptor] = {}
_provider_ids_by_alias: dict[str, str] = {}


def _normalize_key(value: str | None) -> str:
    return (value or "").strip().lower()


def register_llm_provider(descriptor: LlmProviderDescriptor) -> None:
    provider_id = _normalize_key(descriptor.provider_id)
    if not provider_id:
        raise ValueError("LLM provider id must not be empty")
    if provider_id in _providers_by_id:
        raise ValueError(f"LLM provider already registered: {provider_id}")

    aliases = tuple(
        dict.fromkeys((_normalize_key(provider_id), *map(_normalize_key, descriptor.aliases)))
    )
    discovery_adapter_id = descriptor.discovery_adapter_id.strip().lower()
    if not discovery_adapter_id and descriptor.openai_compatible:
        discovery_adapter_id = "openai_compatible"
    execution_adapter_id = descriptor.execution_adapter_id.strip().lower()
    if not execution_adapter_id and descriptor.openai_compatible:
        execution_adapter_id = "openai_compatible"
    normalized = LlmProviderDescriptor(
        provider_id=provider_id,
        display_name=descriptor.display_name.strip() or provider_id,
        default_endpoint_url=descriptor.default_endpoint_url.strip().rstrip("/"),
        route_mode=descriptor.route_mode,
        credential_kind=descriptor.credential_kind,
        discovery_adapter_id=discovery_adapter_id,
        execution_adapter_id=execution_adapter_id,
        aliases=aliases,
        official=descriptor.official,
        openai_compatible=descriptor.openai_compatible,
        control_plane_visible=descriptor.control_plane_visible,
    )
    for alias in aliases:
        if not alias:
            continue
        if alias in _provider_ids_by_alias:
            raise ValueError(f"LLM provider alias already registered: {alias}")
    _providers_by_id[provider_id] = normalized
    for alias in aliases:
        if alias:
            _provider_ids_by_alias[alias] = provider_id


def register_external_llm_provider(descriptor: ExternalLlmProviderDescriptor) -> None:
    if descriptor.route_mode != "external":
        raise ValueError("External LLM provider must use the external route")
    register_llm_provider(descriptor)


def ensure_default_llm_providers_registered() -> None:
    for descriptor in (
        LlmProviderDescriptor(
            "local",
            display_name="Local",
            route_mode="local",
            credential_kind="none",
            discovery_adapter_id="openai_compatible",
            execution_adapter_id="openai_compatible",
            openai_compatible=True,
        ),
        LlmProviderDescriptor(
            "openai",
            display_name="OpenAI",
            default_endpoint_url="https://api.openai.com/v1",
            discovery_adapter_id="openai_compatible",
            execution_adapter_id="openai_compatible",
            openai_compatible=True,
        ),
        LlmProviderDescriptor(
            "anthropic",
            display_name="Anthropic",
            default_endpoint_url="https://api.anthropic.com",
            discovery_adapter_id="anthropic",
            execution_adapter_id="official",
            aliases=("claude",),
        ),
        LlmProviderDescriptor(
            "gemini",
            display_name="Gemini",
            default_endpoint_url="https://generativelanguage.googleapis.com",
            discovery_adapter_id="gemini",
            execution_adapter_id="official",
            aliases=("google",),
        ),
    ):
        if descriptor.provider_id in _providers_by_id:
            continue
        register_llm_provider(descriptor)


def ensure_default_external_llm_providers_registered() -> None:
    ensure_default_llm_providers_registered()


def normalize_llm_provider_id(provider: str | None) -> str | None:
    ensure_default_llm_providers_registered()
    return _provider_ids_by_alias.get(_normalize_key(provider))


def normalize_external_llm_provider_id(provider: str | None) -> str | None:
    provider_id = normalize_llm_provider_id(provider)
    descriptor = _providers_by_id.get(provider_id or "")
    return provider_id if descriptor is not None and descriptor.route_mode == "external" else None


def llm_provider_ids(*, control_plane_only: bool = False) -> tuple[str, ...]:
    ensure_default_llm_providers_registered()
    return tuple(
        provider_id
        for provider_id, descriptor in _providers_by_id.items()
        if not control_plane_only or descriptor.control_plane_visible
    )


def external_llm_provider_ids(*, official_only: bool = False) -> tuple[str, ...]:
    ensure_default_llm_providers_registered()
    return tuple(
        sorted(
            provider_id
            for provider_id, descriptor in _providers_by_id.items()
            if descriptor.route_mode == "external"
            and (not official_only or descriptor.official)
        )
    )


def llm_provider_descriptor(provider: str | None) -> LlmProviderDescriptor | None:
    provider_id = normalize_llm_provider_id(provider)
    if provider_id is None:
        return None
    return _providers_by_id.get(provider_id)


def external_llm_provider_descriptor(
    provider: str | None,
) -> ExternalLlmProviderDescriptor | None:
    descriptor = llm_provider_descriptor(provider)
    return descriptor if descriptor is not None and descriptor.route_mode == "external" else None


def parse_external_llm_provider_allowlist(value: str) -> tuple[str, ...]:
    providers: list[str] = []
    for raw_provider in value.split(","):
        provider = normalize_external_llm_provider_id(raw_provider)
        if provider is not None and provider not in providers:
            providers.append(provider)
    return tuple(providers)


def reset_external_llm_providers() -> None:
    _providers_by_id.clear()
    _provider_ids_by_alias.clear()


__all__ = [
    "ExternalLlmProviderDescriptor",
    "LlmProviderDescriptor",
    "ensure_default_external_llm_providers_registered",
    "ensure_default_llm_providers_registered",
    "external_llm_provider_descriptor",
    "external_llm_provider_ids",
    "llm_provider_descriptor",
    "llm_provider_ids",
    "normalize_external_llm_provider_id",
    "normalize_llm_provider_id",
    "parse_external_llm_provider_allowlist",
    "register_external_llm_provider",
    "register_llm_provider",
    "reset_external_llm_providers",
]
