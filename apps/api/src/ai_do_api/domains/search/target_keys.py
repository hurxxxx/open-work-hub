from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def search_target_key(
    *,
    app: object | None = None,
    target_type: object,
    target_id: object,
) -> str:
    normalized_type = _normalize_token(target_type)
    normalized_id = _normalize_token(target_id)
    normalized_app = _normalize_token(app)
    if normalized_app:
        return f"{normalized_app}:{normalized_type}:{normalized_id}"
    return search_target_legacy_key(
        target_type=normalized_type,
        target_id=normalized_id,
    )


def search_target_legacy_key(
    *,
    target_type: object,
    target_id: object,
) -> str:
    return f"{_normalize_token(target_type)}:{_normalize_token(target_id)}"


def search_target_document_keys(target: Mapping[str, Any]) -> tuple[str, ...]:
    target_type = _normalize_token(target.get("type"))
    target_id = _normalize_token(target.get("id"))
    if not target_type or not target_id:
        return ()
    keys = [
        search_target_key(
            app=target.get("app"),
            target_type=target_type,
            target_id=target_id,
        ),
        search_target_legacy_key(
            target_type=target_type,
            target_id=target_id,
        ),
    ]
    return tuple(dict.fromkeys(key for key in keys if key))


def search_target_filter_keys(
    *,
    app: object | None = None,
    target_type: object,
    target_id: object,
) -> tuple[str, ...]:
    return (
        search_target_key(
            app=app,
            target_type=target_type,
            target_id=target_id,
        ),
    )


def _normalize_token(value: object | None) -> str:
    return str(value or "").strip()


__all__ = [
    "search_target_document_keys",
    "search_target_filter_keys",
    "search_target_key",
    "search_target_legacy_key",
]
