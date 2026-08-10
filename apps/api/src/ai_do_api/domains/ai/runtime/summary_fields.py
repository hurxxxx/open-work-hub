from __future__ import annotations

from collections.abc import Mapping


def summary_string(summary: Mapping[str, object] | None, key: str) -> str | None:
    if summary is None:
        return None
    value = summary.get(key)
    return value if isinstance(value, str) and value else None


def summary_int(summary: Mapping[str, object] | None, key: str) -> int:
    if summary is None:
        return 0
    try:
        return int(summary.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def summary_string_list(summary: Mapping[str, object] | None, key: str) -> list[str]:
    if summary is None:
        return []
    value = summary.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


__all__ = ["summary_int", "summary_string", "summary_string_list"]
