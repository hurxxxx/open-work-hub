from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def graph_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def graph_latest_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return trim_graph_text(content, limit=1400)
    return ""


def graph_candidate_string(
    candidate_summary: Mapping[str, object] | None,
    key: str,
) -> str | None:
    if candidate_summary is None:
        return None
    value = candidate_summary.get(key)
    return value if isinstance(value, str) and value else None


def trim_graph_text(value: str, *, limit: int) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 1]}\u2026"


__all__ = [
    "graph_candidate_string",
    "graph_latest_user_text",
    "graph_string_list",
    "trim_graph_text",
]
