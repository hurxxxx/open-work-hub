from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchEntityDescriptor:
    entity_type: str
    resource_type: str
    label: str
    label_key: str


_descriptors_by_entity_type: dict[str, SearchEntityDescriptor] = {}


def register_search_entity_descriptor(descriptor: SearchEntityDescriptor) -> None:
    entity_type = normalize_search_entity_type(descriptor.entity_type)
    if not entity_type:
        raise ValueError("Search entity descriptor must declare entity_type")
    resource_type = str(descriptor.resource_type).strip()
    label = str(descriptor.label).strip()
    label_key = str(descriptor.label_key).strip()
    if not resource_type:
        raise ValueError(f"Search entity descriptor {entity_type} must declare resource_type")
    if not label:
        raise ValueError(f"Search entity descriptor {entity_type} must declare label")
    if not label_key:
        raise ValueError(f"Search entity descriptor {entity_type} must declare label_key")
    existing = _descriptors_by_entity_type.get(entity_type)
    normalized = SearchEntityDescriptor(
        entity_type=entity_type,
        resource_type=resource_type,
        label=label,
        label_key=label_key,
    )
    if existing is not None and existing != normalized:
        raise ValueError(f"Search entity descriptor already registered: {entity_type}")
    _descriptors_by_entity_type[entity_type] = normalized


def get_search_entity_descriptor(entity_type: str) -> SearchEntityDescriptor | None:
    return _descriptors_by_entity_type.get(normalize_search_entity_type(entity_type))


def search_entity_descriptors() -> tuple[SearchEntityDescriptor, ...]:
    return tuple(_descriptors_by_entity_type.values())


def label_for_search_entity(entity_type: str) -> str:
    normalized = normalize_search_entity_type(entity_type)
    descriptor = get_search_entity_descriptor(normalized)
    if descriptor is not None:
        return descriptor.label
    return normalized.replace("_", " ").title()


def resource_type_for_registered_search_entity(entity_type: str) -> str:
    normalized = normalize_search_entity_type(entity_type)
    descriptor = get_search_entity_descriptor(normalized)
    if descriptor is None:
        raise KeyError(normalized)
    return descriptor.resource_type


def normalize_search_entity_type(entity_type: object) -> str:
    return str(entity_type).strip()


def reset_search_entity_descriptors() -> None:
    _descriptors_by_entity_type.clear()


__all__ = [
    "SearchEntityDescriptor",
    "get_search_entity_descriptor",
    "label_for_search_entity",
    "normalize_search_entity_type",
    "register_search_entity_descriptor",
    "reset_search_entity_descriptors",
    "resource_type_for_registered_search_entity",
    "search_entity_descriptors",
]
