from __future__ import annotations

from collections.abc import Iterable


def _registered_business_chat_app_ids() -> tuple[str, ...]:
    from open_alm_api.domains.ai.registry import get_chatbot_capable_app_ids

    return get_chatbot_capable_app_ids()


def default_business_chat_allowed_app_ids() -> list[str]:
    return list(_registered_business_chat_app_ids())


def normalize_business_chat_allowed_app_ids(
    requested_app_ids: Iterable[str] | None,
) -> list[str]:
    if requested_app_ids is None:
        return default_business_chat_allowed_app_ids()

    allowed_app_ids = frozenset(_registered_business_chat_app_ids())
    seen: set[str] = set()
    normalized_app_ids: list[str] = []
    for item in requested_app_ids:
        normalized = str(item).strip()
        if not normalized or normalized in seen or normalized not in allowed_app_ids:
            continue
        normalized_app_ids.append(normalized)
        seen.add(normalized)
    return normalized_app_ids


def filter_business_chat_context_app_ids(app_ids: Iterable[str]) -> list[str]:
    return normalize_business_chat_allowed_app_ids(app_ids)
