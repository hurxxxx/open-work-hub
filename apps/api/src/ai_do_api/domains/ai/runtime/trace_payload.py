from __future__ import annotations

import json
import re
from typing import Any

from ai_do_api.core.settings import get_settings


SENSITIVE_PAYLOAD_KEYS = {
    "api_key",
    "args",
    "arguments",
    "authorization",
    "completion",
    "content",
    "cookie",
    "headers",
    "messages",
    "password",
    "prompt",
    "provider_response",
    "raw",
    "raw_provider_payload",
    "raw_reasoning",
    "reasoning",
    "result",
    "output",
    "secret",
    "token",
    "tool_secret",
}
SAFE_PAYLOAD_KEYS = {
    "output_kind",
    "output_kind_hint",
    "raw_output_persisted",
    "result_count",
    "result_refs",
}
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[-._~+/=a-z0-9]+"),
    re.compile(r"(?i)\b(api[_-]?key|x-api-key|authorization)\s*[:=]\s*[^,\s;]+"),
    re.compile(r"(?i)\b(session|access|refresh|id)[_-]?token\s*[:=]\s*[^,\s;]+"),
    re.compile(r"(?i)\b(cookie|set-cookie)\s*[:=]\s*[^,\s;]+"),
)


def scrub_trace_payload(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in SAFE_PAYLOAD_KEYS:
                scrubbed[key] = scrub_trace_payload(item)
            elif any(marker in normalized_key for marker in SENSITIVE_PAYLOAD_KEYS):
                scrubbed[key] = "[redacted]"
            else:
                scrubbed[key] = scrub_trace_payload(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_trace_payload(item) for item in value]
    if isinstance(value, str):
        return _scrub_sensitive_string(value)
    return value


def prepare_trace_payload(
    payload: dict[str, Any] | None,
    *,
    max_bytes: int | None = None,
) -> tuple[dict[str, Any], bool]:
    raw_payload = payload or {}
    limit = (
        max_bytes
        if max_bytes is not None
        else get_settings().ai_runtime_trace_payload_max_bytes
    )
    size_bytes = _payload_size_bytes(raw_payload)
    if size_bytes > limit:
        return (
            {
                "truncated": True,
                "original_size_bytes": size_bytes,
                "reason": "payload_too_large",
            },
            True,
        )
    return scrub_trace_payload(raw_payload), False


def _scrub_sensitive_string(value: str) -> str:
    scrubbed = value
    for pattern in SENSITIVE_VALUE_PATTERNS:
        scrubbed = pattern.sub("[redacted]", scrubbed)
    return scrubbed


def _payload_size_bytes(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    )


__all__ = [
    "prepare_trace_payload",
    "scrub_trace_payload",
]
