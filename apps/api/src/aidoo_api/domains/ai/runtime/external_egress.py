from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aidoo_api.core.pii import scan_pii
from aidoo_api.core.settings import Settings


ExternalCapability = Literal["planning", "reasoning", "quality_review", "search"]
ExternalProvider = Literal["openai", "anthropic"]
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

_PROVIDER_ALIASES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
}
_SENSITIVE_BLOCK_ENTITY_TYPES = frozenset(
    {
        "bom",
        "cost",
        "contract_term",
    }
)
_ENTITY_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("order_id", re.compile(r"\bORD-[A-Z0-9-]+\b", re.IGNORECASE)),
    ("product_code", re.compile(r"\b[A-Z]{2,}-[A-Z0-9-]*\d[A-Z0-9-]*\b")),
    ("customer", re.compile(r"[가-힣A-Za-z0-9_-]*고객[A-Za-z0-9_-]*")),
)


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


def evaluate_external_egress(
    *,
    capability: ExternalCapability,
    provider: str | None,
    text: str,
    settings: Settings,
) -> ExternalEgressDecision:
    requested_provider = (provider or _default_provider(capability, settings)).strip()
    normalized_provider = normalize_external_provider(requested_provider)
    removed_entity_types = _detected_enterprise_entity_types(text)
    blocked_entity_types = sorted(
        entity_type
        for entity_type in removed_entity_types
        if entity_type in _SENSITIVE_BLOCK_ENTITY_TYPES
    )
    pii_hits = [hit.pattern for hit in scan_pii([text])]
    sanitized_prompt = _sanitize_external_prompt(text)
    sanitized_query = _sanitize_external_search_query(text)

    if capability != "search" and not settings.ai_external_llm_enabled:
        return _deny(
            capability=capability,
            requested_provider=requested_provider,
            provider=normalized_provider,
            reason="external_llm_disabled",
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            pii_hits=pii_hits,
            sanitized_prompt=sanitized_prompt,
            sanitized_query=sanitized_query,
        )
    if not _capability_enabled(capability, settings):
        return _deny(
            capability=capability,
            requested_provider=requested_provider,
            provider=normalized_provider,
            reason="capability_disabled",
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            pii_hits=pii_hits,
            sanitized_prompt=sanitized_prompt,
            sanitized_query=sanitized_query,
        )
    if normalized_provider is None or normalized_provider not in allowed_external_providers(
        settings
    ):
        return _deny(
            capability=capability,
            requested_provider=requested_provider,
            provider=normalized_provider,
            reason="provider_not_allowed",
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            pii_hits=pii_hits,
            sanitized_prompt=sanitized_prompt,
            sanitized_query=sanitized_query,
        )
    if capability == "search" and _explicitly_disallows_external_search(text):
        return _deny(
            capability=capability,
            requested_provider=requested_provider,
            provider=normalized_provider,
            reason="user_no_external_search",
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            pii_hits=pii_hits,
            sanitized_prompt=sanitized_prompt,
            sanitized_query=sanitized_query,
        )
    if pii_hits:
        return _deny(
            capability=capability,
            requested_provider=requested_provider,
            provider=normalized_provider,
            reason="pii_detected",
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            pii_hits=pii_hits,
            sanitized_prompt=sanitized_prompt,
            sanitized_query=sanitized_query,
        )
    if blocked_entity_types:
        return _deny(
            capability=capability,
            requested_provider=requested_provider,
            provider=normalized_provider,
            reason="sensitive_entity_blocked",
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            pii_hits=pii_hits,
            sanitized_prompt=sanitized_prompt,
            sanitized_query=sanitized_query,
        )

    sanitized_output = sanitized_query if capability == "search" else sanitized_prompt
    if not sanitized_output:
        return _deny(
            capability=capability,
            requested_provider=requested_provider,
            provider=normalized_provider,
            reason="sanitized_empty",
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            pii_hits=pii_hits,
            sanitized_prompt=sanitized_prompt,
            sanitized_query=sanitized_query,
        )

    return ExternalEgressDecision(
        capability=capability,
        requested_provider=requested_provider,
        provider=normalized_provider,
        allow_external=True,
        reason="allowed",
        removed_entity_types=removed_entity_types,
        blocked_entity_types=blocked_entity_types,
        pii_hits=pii_hits,
        sanitized_prompt=sanitized_prompt,
        sanitized_query=sanitized_query,
    )


def normalize_external_provider(provider: str | None) -> ExternalProvider | None:
    if provider is None:
        return None
    normalized = provider.strip().lower()
    return _PROVIDER_ALIASES.get(normalized)  # type: ignore[return-value]


def allowed_external_providers(settings: Settings) -> tuple[ExternalProvider, ...]:
    providers: list[ExternalProvider] = []
    for raw_provider in settings.ai_allowed_external_providers.split(","):
        provider = normalize_external_provider(raw_provider)
        if provider is not None and provider not in providers:
            providers.append(provider)
    return tuple(providers)


def _deny(
    *,
    capability: ExternalCapability,
    requested_provider: str,
    provider: ExternalProvider | None,
    reason: ExternalEgressReason,
    removed_entity_types: list[str],
    blocked_entity_types: list[str],
    pii_hits: list[str],
    sanitized_prompt: str,
    sanitized_query: str,
) -> ExternalEgressDecision:
    return ExternalEgressDecision(
        capability=capability,
        requested_provider=requested_provider,
        provider=provider,
        allow_external=False,
        reason=reason,
        removed_entity_types=removed_entity_types,
        blocked_entity_types=blocked_entity_types,
        pii_hits=pii_hits,
        sanitized_prompt=sanitized_prompt,
        sanitized_query=""
        if reason in {"sensitive_entity_blocked", "user_no_external_search"}
        else sanitized_query,
    )


def _default_provider(capability: ExternalCapability, settings: Settings) -> str:
    if capability == "search":
        return settings.ai_default_external_search_provider
    return "openai"


def _capability_enabled(capability: ExternalCapability, settings: Settings) -> bool:
    if capability == "planning":
        return settings.ai_external_planning_enabled
    if capability == "reasoning":
        return settings.ai_external_reasoning_enabled
    if capability == "quality_review":
        return settings.ai_external_quality_review_enabled
    return settings.ai_external_search_enabled


def _detected_enterprise_entity_types(text: str) -> list[str]:
    lowered = text.lower()
    entity_types: list[str] = []
    if "bom" in lowered:
        entity_types.append("bom")
    if "원가" in text or "cost" in lowered:
        entity_types.append("cost")
    if "계약" in text or "contract" in lowered:
        entity_types.append("contract_term")
    for entity_type, pattern in _ENTITY_TOKEN_PATTERNS:
        if pattern.search(text):
            entity_types.append(entity_type)
    return _dedupe(entity_types)


def _explicitly_disallows_external_search(text: str) -> bool:
    lowered = text.lower()
    compact = re.sub(r"\s+", "", lowered)
    return any(
        marker in lowered or marker in compact
        for marker in (
            "no external search",
            "no-external-search",
            "no web search",
            "no internet search",
            "without web search",
            "without internet search",
            "do not use external search",
            "do not search the web",
            "do not search online",
            "don't search the web",
            "don't search online",
            "dont search the web",
            "dont search online",
            "외부 검색 없이",
            "외부검색없이",
            "외부 검색 금지",
            "외부검색금지",
            "외부 검색하지 말고",
            "외부검색하지말고",
            "외부 자료 검색 없이",
            "외부자료검색없이",
            "인터넷 검색 없이",
            "인터넷검색없이",
            "인터넷 검색하지 말고",
            "인터넷검색하지말고",
            "웹 검색 없이",
            "웹검색없이",
            "웹 검색하지 말고",
            "웹검색하지말고",
            "온라인 검색 없이",
            "온라인검색없이",
            "온라인 검색하지 말고",
            "온라인검색하지말고",
        )
    )


def _sanitize_external_prompt(text: str) -> str:
    sanitized = _remove_enterprise_tokens(text)
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .,\n\t")
    return sanitized[:1200]


def _sanitize_external_search_query(text: str) -> str:
    if _SENSITIVE_BLOCK_ENTITY_TYPES.intersection(_detected_enterprise_entity_types(text)):
        return ""
    tokens: list[str] = []
    if "product_code" in _detected_enterprise_entity_types(text):
        tokens.extend(["industrial", "electronic", "component"])
    upper_text = text.upper()
    if "EU" in upper_text:
        tokens.append("EU")
    if "CE" in upper_text:
        tokens.extend(["CE", "certification"])
    elif "인증" in text or "certification" in text.lower():
        tokens.append("certification")
    if "리스크" in text or "규제" in text or "requirements" in text.lower():
        tokens.extend(["regulatory", "requirements"])
    tokens = _dedupe(tokens)
    if tokens:
        return " ".join(tokens)
    return _sanitize_external_prompt(text)


def _remove_enterprise_tokens(text: str) -> str:
    sanitized = text
    for _entity_type, pattern in _ENTITY_TOKEN_PATTERNS:
        sanitized = pattern.sub(" ", sanitized)
    sanitized = re.sub(r"\b\d+(?:원|krw|usd|eur)?\b", " ", sanitized, flags=re.IGNORECASE)
    return sanitized


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


__all__ = [
    "ExternalCapability",
    "ExternalEgressDecision",
    "ExternalEgressReason",
    "ExternalProvider",
    "allowed_external_providers",
    "evaluate_external_egress",
    "normalize_external_provider",
]
