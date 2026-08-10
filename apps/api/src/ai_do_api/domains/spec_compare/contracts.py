from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re
from typing import Literal


RowStatus = Literal["same", "different", "base_only", "target_only", "unknown"]


@dataclass(frozen=True)
class ComparisonRow:
    spec_name: str
    base_value: str
    target_value: str
    status: RowStatus
    summary: str
    base_evidence_ids: list[str]
    target_evidence_ids: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SpecCompareCancelled(RuntimeError):
    """Raised when a running comparison job is cancelled while the pipeline is active."""


def _normalize_key(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", value.casefold())


def _normalize_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _compact_value(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value.casefold())


def _key_similarity(left: str, right: str) -> float:
    left_key = _normalize_key(left)
    right_key = _normalize_key(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    if min(len(left_key), len(right_key)) >= 3 and (
        left_key in right_key or right_key in left_key
    ):
        return 0.82
    return max(
        SequenceMatcher(None, left_key, right_key).ratio(),
        _token_overlap_similarity(left, right),
    )


def _token_overlap_similarity(left: str, right: str) -> float:
    left_tokens = _key_tokens(left)
    right_tokens = _key_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _key_tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in re.split(r"[^0-9A-Za-z가-힣]+", value)
        if len(token) >= 2
    }
