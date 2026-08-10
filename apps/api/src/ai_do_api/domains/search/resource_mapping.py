from __future__ import annotations

from ai_do_api.domains.search.default_entity_adapters import (
    ensure_search_entity_descriptors_registered,
)
from ai_do_api.domains.search.entity_registry import (
    resource_type_for_registered_search_entity,
)


def resource_type_for_search_entity(entity_type: object) -> str:
    ensure_search_entity_descriptors_registered()
    return resource_type_for_registered_search_entity(str(entity_type))


def maybe_resource_type_for_search_entity(entity_type: object) -> str | None:
    ensure_search_entity_descriptors_registered()
    try:
        return resource_type_for_registered_search_entity(str(entity_type))
    except KeyError:
        return None


__all__ = [
    "maybe_resource_type_for_search_entity",
    "resource_type_for_search_entity",
]
