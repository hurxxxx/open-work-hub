from __future__ import annotations

import re

from aidoo_api.core.pii import PII_PATTERNS


_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("order_id", re.compile(r"\bORD-[A-Z0-9-]+\b", re.IGNORECASE)),
    ("product_code", re.compile(r"\b[A-Z]{2,}-[A-Z0-9-]*\d[A-Z0-9-]*\b")),
    ("customer", re.compile(r"[가-힣A-Za-z0-9_-]*고객[A-Za-z0-9_-]*")),
    ("price", re.compile(r"(?:\b\d+(?:,\d{3})*\s*원\b|\bprice\b|가격)", re.IGNORECASE)),
    ("cost", re.compile(r"(?:원가|\bcost\b)", re.IGNORECASE)),
    ("contract", re.compile(r"(?:계약|\bcontract\b)", re.IGNORECASE)),
    (
        "internal_url",
        re.compile(
            r"https?://(?:(?:localhost|127\.0\.0\.1|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)"
            r"|(?:[A-Za-z0-9.-]+\.internal\b))[^\s]*",
            re.IGNORECASE,
        ),
    ),
    ("credential", re.compile(r"\b(?:api[_-]?key|token|password|secret)\b", re.IGNORECASE)),
)
_REDACTED_TOKEN_PATTERN = re.compile(r"\[redacted:[a-z0-9_:-]+\]", re.IGNORECASE)


def assert_external_manager_payload_safe(value: str) -> None:
    detected = detect_forbidden_external_payload_entities(value)
    if detected:
        raise ValueError(f"payload contains forbidden entity types: {', '.join(detected)}")


def detect_forbidden_external_payload_entities(value: str) -> list[str]:
    normalized = _REDACTED_TOKEN_PATTERN.sub("", value)
    detected: list[str] = []
    for entity_type, pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(normalized):
            detected.append(entity_type)
    for entity_type, pattern in PII_PATTERNS.items():
        if pattern.search(normalized):
            detected.append(f"pii:{entity_type}")
    return _dedupe(detected)


def redact_external_manager_payload(value: str) -> str:
    redacted = value
    for entity_type, pattern in _FORBIDDEN_PATTERNS:
        redacted = pattern.sub(f"[redacted:{entity_type}]", redacted)
    for entity_type, pattern in PII_PATTERNS.items():
        redacted = pattern.sub(f"[redacted:pii:{entity_type}]", redacted)
    return redacted


def has_meaningful_text_after_redaction(value: str) -> bool:
    without_redactions = _REDACTED_TOKEN_PATTERN.sub("", value)
    return bool(re.search(r"[A-Za-z0-9가-힣]", without_redactions))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
