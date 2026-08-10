from __future__ import annotations

from open_alm_api.domains.search.default_entity_adapters import (
    ensure_search_entity_adapters_registered,
)


def ensure_search_projection_adapters_registered() -> None:
    ensure_search_entity_adapters_registered()


__all__ = ["ensure_search_projection_adapters_registered"]
