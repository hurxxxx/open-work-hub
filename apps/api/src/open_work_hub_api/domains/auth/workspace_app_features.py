from __future__ import annotations

from collections.abc import Mapping


def is_workspace_catalog_feature_enabled(settings: object, key: str) -> bool:
    if isinstance(settings, Mapping):
        return bool(settings.get(key, False))
    return bool(getattr(settings, key, False))
