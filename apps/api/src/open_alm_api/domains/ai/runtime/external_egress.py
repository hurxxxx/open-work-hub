from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_alm_api.core.llm_provider_registry import (
    normalize_external_llm_provider_id,
    parse_external_llm_provider_allowlist,
)
from open_alm_api.core.pii import scan_pii
from open_alm_api.core.settings import Settings
from open_alm_api.domains.ai.runtime.external_egress_sanitizer import (
    build_external_egress_sanitization,
)


ExternalCapability = Literal["planning", "reasoning", "quality_review", "search"]
ExternalProvider = str
ExternalEgressReason = Literal[
    "allowed",
    "external_llm_disabled",
    "capability_disabled",
    "provider_not_allowed",
    "user_no_external_search",
    "pii_detected",
    "sensitive_entity_blocked",
    "sanitized_empty",
]

class ExternalEgressDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["external_egress.v1"] = "external_egress.v1"
    capability: ExternalCapability
    requested_provider: str
    provider: ExternalProvider | None = None
    allow_external: bool
    reason: ExternalEgressReason
    removed_entity_types: list[str] = Field(default_factory=list)
    blocked_entity_types: list[str] = Field(default_factory=list)
    pii_hits: list[str] = Field(default_factory=list)
    sanitized_query: str = ""
    sanitized_prompt: str = ""


@dataclass(frozen=True)
class _ExternalEgressContext:
    capability: ExternalCapability
    requested_provider: str
    provider: ExternalProvider | None
    removed_entity_types: list[str]
    blocked_entity_types: list[str]
    disallows_external_search: bool
    pii_hits: list[str]
    sanitized_prompt: str
    sanitized_query: str


def evaluate_external_egress(
    *,
    capability: ExternalCapability,
    provider: str | None,
    text: str,
    settings: Settings,
) -> ExternalEgressDecision:
    context = _build_external_egress_context(
        capability=capability,
        provider=provider,
        text=text,
        settings=settings,
    )

    if capability != "search" and not settings.ai_external_llm_enabled:
        return _deny(context, reason="external_llm_disabled")
    if not _capability_enabled(capability, settings):
        return _deny(context, reason="capability_disabled")
    if context.provider is None or context.provider not in allowed_external_providers(
        settings,
        capability=capability,
    ):
        return _deny(context, reason="provider_not_allowed")
    if capability == "search" and context.disallows_external_search:
        return _deny(context, reason="user_no_external_search")
    if context.pii_hits:
        return _deny(context, reason="pii_detected")
    if context.blocked_entity_types:
        return _deny(context, reason="sensitive_entity_blocked")

    sanitized_output = (
        context.sanitized_query if capability == "search" else context.sanitized_prompt
    )
    if not sanitized_output:
        return _deny(context, reason="sanitized_empty")

    return _allow(context)


def normalize_external_provider(
    provider: str | None,
    *,
    capability: ExternalCapability | None = None,
) -> ExternalProvider | None:
    llm_provider = normalize_external_llm_provider_id(provider)
    if llm_provider is not None:
        return llm_provider
    if capability == "search":
        search_provider = _normalize_external_search_provider(provider)
        if search_provider is not None:
            return search_provider
    return None


def allowed_external_providers(
    settings: Settings,
    *,
    capability: ExternalCapability | None = None,
) -> tuple[ExternalProvider, ...]:
    if capability != "search":
        return parse_external_llm_provider_allowlist(settings.ai_allowed_external_providers)

    providers: list[ExternalProvider] = []
    for raw_provider in str(settings.ai_allowed_external_providers or "").split(","):
        provider = normalize_external_provider(raw_provider, capability="search")
        if provider is not None and provider not in providers:
            providers.append(provider)
    return tuple(providers)


def _build_external_egress_context(
    *,
    capability: ExternalCapability,
    provider: str | None,
    text: str,
    settings: Settings,
) -> _ExternalEgressContext:
    requested_provider = (provider or _default_provider(capability, settings)).strip()
    normalized_provider = normalize_external_provider(
        requested_provider,
        capability=capability,
    )
    sanitization = build_external_egress_sanitization(text)
    return _ExternalEgressContext(
        capability=capability,
        requested_provider=requested_provider,
        provider=normalized_provider,
        removed_entity_types=sanitization.removed_entity_types,
        blocked_entity_types=sanitization.blocked_entity_types,
        disallows_external_search=sanitization.disallows_external_search,
        pii_hits=[hit.pattern for hit in scan_pii([text])],
        sanitized_prompt=sanitization.sanitized_prompt,
        sanitized_query=sanitization.sanitized_query,
    )


def _deny(
    context: _ExternalEgressContext,
    *,
    reason: ExternalEgressReason,
) -> ExternalEgressDecision:
    return ExternalEgressDecision(
        capability=context.capability,
        requested_provider=context.requested_provider,
        provider=context.provider,
        allow_external=False,
        reason=reason,
        removed_entity_types=context.removed_entity_types,
        blocked_entity_types=context.blocked_entity_types,
        pii_hits=context.pii_hits,
        sanitized_prompt="",
        sanitized_query="",
    )


def _allow(context: _ExternalEgressContext) -> ExternalEgressDecision:
    return ExternalEgressDecision(
        capability=context.capability,
        requested_provider=context.requested_provider,
        provider=context.provider,
        allow_external=True,
        reason="allowed",
        removed_entity_types=context.removed_entity_types,
        blocked_entity_types=context.blocked_entity_types,
        pii_hits=context.pii_hits,
        sanitized_prompt=context.sanitized_prompt,
        sanitized_query=context.sanitized_query,
    )


def _default_provider(capability: ExternalCapability, settings: Settings) -> str:
    if capability == "search":
        return settings.ai_default_external_search_provider
    return settings.ai_default_external_llm_provider


def _capability_enabled(capability: ExternalCapability, settings: Settings) -> bool:
    if capability == "planning":
        return settings.ai_external_planning_enabled
    if capability == "reasoning":
        return settings.ai_external_reasoning_enabled
    if capability == "quality_review":
        return settings.ai_external_quality_review_enabled
    return settings.ai_external_search_enabled


def _normalize_external_search_provider(provider: str | None) -> ExternalProvider | None:
    from open_alm_api.domains.ai.runtime.external_adapters import (
        normalize_external_execution_adapter_name,
        supported_external_search_execution_adapters,
    )

    normalized = normalize_external_execution_adapter_name(provider)
    if normalized in set(supported_external_search_execution_adapters()):
        return normalized
    return None


__all__ = [
    "ExternalCapability",
    "ExternalEgressDecision",
    "ExternalEgressReason",
    "ExternalProvider",
    "allowed_external_providers",
    "evaluate_external_egress",
    "normalize_external_provider",
]
