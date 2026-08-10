"""Shared PII patterns for outbound LLM detection and masking.

Boundary-safety policy uses this conservative regex set to classify payloads.
When the resolved action is ``mask_and_send``, the masking pipeline also uses
the patterns to replace supported spans before external transfer.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import NamedTuple

__all__ = ["PiiHit", "scan_pii", "PII_PATTERNS"]


class PiiHit(NamedTuple):
    pattern: str
    sample: str


# Keys are stable labels stored in audit logs. Only add patterns with a low
# false-positive rate on normal business text; values with heavy FP (e.g. raw
# credit card number inside an SKU) are excluded until we have a full-validator
# pass (Luhn, MOD-11, etc.).
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    # Korean resident registration number (주민등록번호). Match the standard
    # 13-digit form, plus the common high-risk paste/typing case where one
    # extra trailing digit is attached. Foreign-resident 7th digits are also
    # treated as sensitive here because false negatives are worse at egress.
    "rrn_kr": re.compile(r"(?<!\d)\d{6}(?:[-\s]?[1-8]\d{6,7})(?!\d)"),
    # Email addresses (RFC-light; covers the common cases we'd care about).
    "email": re.compile(r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b"),
    # Korean mobile (010/011/016-019) and common landline (02, 0xx).
    "phone_kr": re.compile(r"\b0(?:1[016-9]|2|[3-6][1-5]|70)(?:[-\s]?\d{3,4})(?:[-\s]?\d{4})\b"),
}


def scan_pii(texts: Iterable[str]) -> list[PiiHit]:
    """Return distinct pattern labels and a single sample span per pattern.

    Returns an empty list when no patterns match. Duplicates are coalesced by
    label so the caller can pass the hits into an audit payload without
    accidentally storing many copies of the same value.
    """
    seen: dict[str, PiiHit] = {}
    for text in texts:
        if not text:
            continue
        for label, pattern in PII_PATTERNS.items():
            if label in seen:
                continue
            match = pattern.search(text)
            if match:
                seen[label] = PiiHit(pattern=label, sample=_redact(match.group(0)))
    return list(seen.values())


def _redact(raw: str) -> str:
    """Reduce a match to a non-reversible sample for audit purposes."""
    if len(raw) <= 4:
        return "*" * len(raw)
    return raw[:2] + "*" * (len(raw) - 4) + raw[-2:]
