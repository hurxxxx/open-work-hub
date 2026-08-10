from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import re

from open_alm_api.core.pii import PII_PATTERNS, scan_pii


_BLOCKING_SENSITIVITY_LABELS = frozenset(
    {
        "confidential",
        "internal",
        "restricted",
        "secret",
        "security",
        "unknown",
    }
)
_BLOCKING_CONTENT_ORIGINS = frozenset(
    {
        "internal_context",
        "workspace",
        "rag",
        "docs",
        "knowledge",
        "unknown",
    }
)
_SAFE_CONTENT_ORIGINS = frozenset(
    {
        "public",
        "public_web",
        "low_risk",
        "user_prompt",
    }
)


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
    (
        "credential",
        re.compile(
            r"(?:"
            r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\b"
            r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
            r"|\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"
            r"|\bAKIA[0-9A-Z]{16}\b"
            r"|\bsk-[A-Za-z0-9_-]{20,}\b"
            r")",
            re.IGNORECASE,
        ),
    ),
    (
        "security_document",
        re.compile(
            r"(?:"
            r"보안\s*문서|접근\s*제어|권한\s*정책|취약점|방화벽|네트워크\s*구성|VPN|"
            r"\bsecurity\s+(?:policy|architecture|runbook|incident|credential|control)\b|"
            r"\bvulnerability\b|\bfirewall\b|\bnetwork\s+topology\b"
            r")",
            re.IGNORECASE,
        ),
    ),
)
_REDACTED_TOKEN_PATTERN = re.compile(
    r"\[(?:redacted|masked):[a-z0-9_:-]+\]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExternalPayloadSafetyDecision:
    allow_external: bool
    reason_code: str
    pii_hits: tuple[str, ...] = ()
    removed_entity_types: tuple[str, ...] = ()
    blocked_entity_types: tuple[str, ...] = ()
    sensitivity_labels: tuple[str, ...] = ()
    content_origin: str = "user_prompt"
    source_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExternalPayloadTextSpan:
    text_index: int
    start: int
    end: int
    entity_type: str


def evaluate_external_payload_safety(
    texts: list[str] | tuple[str, ...],
    *,
    content_origin: str | None = None,
    source_kinds: list[str] | tuple[str, ...] = (),
    sensitivity_labels: list[str] | tuple[str, ...] = (),
) -> ExternalPayloadSafetyDecision:
    resolved_origin = normalize_content_origin(content_origin)
    resolved_source_kinds = normalize_external_safety_values(source_kinds)
    resolved_labels = normalize_external_safety_values(sensitivity_labels)
    pii_hits = tuple(hit.pattern for hit in scan_pii(texts))
    entity_types = tuple(detect_forbidden_external_payload_entities("\n".join(texts)))
    blocking_labels = tuple(
        label for label in resolved_labels if label in _BLOCKING_SENSITIVITY_LABELS
    )

    if resolved_origin in _BLOCKING_CONTENT_ORIGINS:
        return _external_payload_decision(
            allow_external=False,
            reason_code="internal_context_blocked",
            pii_hits=pii_hits,
            entity_types=entity_types,
            sensitivity_labels=resolved_labels,
            content_origin=resolved_origin,
            source_kinds=resolved_source_kinds,
        )
    if blocking_labels:
        return _external_payload_decision(
            allow_external=False,
            reason_code="sensitivity_label_blocked",
            pii_hits=pii_hits,
            entity_types=entity_types,
            sensitivity_labels=resolved_labels,
            content_origin=resolved_origin,
            source_kinds=resolved_source_kinds,
        )
    if pii_hits:
        return _external_payload_decision(
            allow_external=False,
            reason_code="pii_detected",
            pii_hits=pii_hits,
            entity_types=entity_types,
            sensitivity_labels=resolved_labels,
            content_origin=resolved_origin,
            source_kinds=resolved_source_kinds,
        )
    if entity_types:
        return _external_payload_decision(
            allow_external=False,
            reason_code="sensitive_entity_blocked",
            pii_hits=pii_hits,
            entity_types=entity_types,
            sensitivity_labels=resolved_labels,
            content_origin=resolved_origin,
            source_kinds=resolved_source_kinds,
        )
    return _external_payload_decision(
        allow_external=True,
        reason_code="allowed",
        pii_hits=pii_hits,
        entity_types=entity_types,
        sensitivity_labels=resolved_labels,
        content_origin=resolved_origin,
        source_kinds=resolved_source_kinds,
    )


def normalize_content_origin(value: str | None) -> str:
    normalized = (value or "user_prompt").strip().lower().replace("-", "_")
    if not normalized:
        return "user_prompt"
    if normalized in _SAFE_CONTENT_ORIGINS or normalized in _BLOCKING_CONTENT_ORIGINS:
        return normalized
    return normalized


def known_content_origins() -> tuple[str, ...]:
    return tuple(sorted({*_SAFE_CONTENT_ORIGINS, *_BLOCKING_CONTENT_ORIGINS}))


def normalize_external_safety_values(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        item = str(value or "").strip().lower().replace("-", "_")
        if not item or item in normalized:
            continue
        normalized.append(item)
    return tuple(normalized)


def assert_external_manager_payload_safe(value: str) -> None:
    detected = detect_forbidden_external_payload_entities(value)
    if detected:
        raise ValueError(f"payload contains forbidden entity types: {', '.join(detected)}")


def detect_forbidden_external_payload_entities(value: str) -> list[str]:
    normalized = _REDACTED_TOKEN_PATTERN.sub("", value)
    detected: list[str] = []
    for entity_type, pattern in _iter_external_payload_rules():
        if pattern.search(normalized):
            detected.append(entity_type)
    return _dedupe(detected)


def detect_external_payload_text_spans(
    texts: list[str] | tuple[str, ...],
) -> tuple[ExternalPayloadTextSpan, ...]:
    spans: list[ExternalPayloadTextSpan] = []
    for text_index, text in enumerate(texts):
        normalized = text or ""
        if not normalized:
            continue
        for entity_type, pattern in _iter_external_payload_rules():
            for match in pattern.finditer(normalized):
                spans.append(
                    ExternalPayloadTextSpan(
                        text_index=text_index,
                        start=match.start(),
                        end=match.end(),
                        entity_type=entity_type,
                    )
                )
    return tuple(spans)


def redact_external_manager_payload(value: str) -> str:
    redacted = value
    for entity_type, pattern in _iter_external_payload_rules():
        redacted = pattern.sub(f"[redacted:{entity_type}]", redacted)
    return redacted


def has_meaningful_text_after_redaction(value: str) -> bool:
    without_redactions = _REDACTED_TOKEN_PATTERN.sub("", value)
    return bool(re.search(r"[A-Za-z0-9가-힣]", without_redactions))


def _iter_external_payload_rules() -> Iterator[tuple[str, re.Pattern[str]]]:
    yield from _FORBIDDEN_PATTERNS
    for entity_type, pattern in PII_PATTERNS.items():
        yield f"pii:{entity_type}", pattern


def _external_payload_decision(
    *,
    allow_external: bool,
    reason_code: str,
    pii_hits: tuple[str, ...],
    entity_types: tuple[str, ...],
    sensitivity_labels: tuple[str, ...],
    content_origin: str,
    source_kinds: tuple[str, ...],
) -> ExternalPayloadSafetyDecision:
    return ExternalPayloadSafetyDecision(
        allow_external=allow_external,
        reason_code=reason_code,
        pii_hits=pii_hits,
        removed_entity_types=entity_types,
        blocked_entity_types=entity_types,
        sensitivity_labels=sensitivity_labels,
        content_origin=content_origin,
        source_kinds=source_kinds,
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
