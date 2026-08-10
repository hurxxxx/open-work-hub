from __future__ import annotations

import re
from dataclasses import dataclass


SENSITIVE_BLOCK_ENTITY_TYPES = frozenset(
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
_NO_EXTERNAL_SEARCH_MARKERS = (
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


@dataclass(frozen=True)
class ExternalEgressSanitization:
    removed_entity_types: list[str]
    blocked_entity_types: list[str]
    disallows_external_search: bool
    sanitized_prompt: str
    sanitized_query: str


def build_external_egress_sanitization(text: str) -> ExternalEgressSanitization:
    removed_entity_types = detect_enterprise_entity_types(text)
    return ExternalEgressSanitization(
        removed_entity_types=removed_entity_types,
        blocked_entity_types=sorted(
            entity_type
            for entity_type in removed_entity_types
            if entity_type in SENSITIVE_BLOCK_ENTITY_TYPES
        ),
        disallows_external_search=explicitly_disallows_external_search(text),
        sanitized_prompt=sanitize_external_prompt(text),
        sanitized_query=sanitize_external_search_query(text),
    )


def detect_enterprise_entity_types(text: str) -> list[str]:
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


def explicitly_disallows_external_search(text: str) -> bool:
    lowered = text.lower()
    compact = re.sub(r"\s+", "", lowered)
    return any(
        marker in lowered or marker in compact
        for marker in _NO_EXTERNAL_SEARCH_MARKERS
    )


def sanitize_external_prompt(text: str) -> str:
    sanitized = _remove_enterprise_tokens(text)
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .,\n\t")
    return sanitized[:1200]


def sanitize_external_search_query(text: str) -> str:
    entity_types = detect_enterprise_entity_types(text)
    if SENSITIVE_BLOCK_ENTITY_TYPES.intersection(entity_types):
        return ""
    tokens: list[str] = []
    if "product_code" in entity_types:
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
    return sanitize_external_prompt(text)


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
    "ExternalEgressSanitization",
    "SENSITIVE_BLOCK_ENTITY_TYPES",
    "build_external_egress_sanitization",
    "detect_enterprise_entity_types",
    "explicitly_disallows_external_search",
    "sanitize_external_prompt",
    "sanitize_external_search_query",
]
