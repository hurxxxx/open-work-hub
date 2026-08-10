from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from open_alm_api.domains.auth.workspace_apps import (
    WORKSPACE_APP_BAR_FIXED_APP_IDS,
    WORKSPACE_APP_BAR_PERSONAL_TOOLS_APP_IDS,
    WORKSPACE_APP_BAR_PINNED_BY_DEFAULT_APP_IDS,
    WORKSPACE_APP_IDS,
)


MAX_APP_BAR_PINNED_APP_IDS = 8


def normalize_app_bar_pinned_app_ids(
    value: Sequence[Any],
    *,
    reject_unknown: bool = False,
) -> list[str]:
    known_app_ids = set(WORKSPACE_APP_IDS)
    normalized_items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            if reject_unknown:
                raise ValueError("Invalid app bar app id.")
            continue
        app_id = item
        if app_id not in known_app_ids:
            if reject_unknown:
                raise ValueError("Invalid app bar app id.")
            continue
        normalized_items.append(app_id)

    normalized: list[str] = []
    for app_id in normalized_items:
        if app_id in WORKSPACE_APP_BAR_FIXED_APP_IDS:
            continue
        if app_id in WORKSPACE_APP_BAR_PERSONAL_TOOLS_APP_IDS:
            continue
        if app_id not in normalized:
            normalized.append(app_id)
            if len(normalized) >= MAX_APP_BAR_PINNED_APP_IDS:
                break
    return normalized


def serialize_app_bar_layout(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {"pinned_app_ids": list(WORKSPACE_APP_BAR_PINNED_BY_DEFAULT_APP_IDS)}

    pinned_app_ids = value.get("pinned_app_ids")
    if not isinstance(pinned_app_ids, list):
        return {"pinned_app_ids": list(WORKSPACE_APP_BAR_PINNED_BY_DEFAULT_APP_IDS)}

    return {"pinned_app_ids": normalize_app_bar_pinned_app_ids(pinned_app_ids)}
