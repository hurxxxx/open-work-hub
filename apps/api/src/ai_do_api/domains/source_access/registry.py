from __future__ import annotations

from typing import Any, Protocol

from ai_do_api.domains.search.backend_contracts import KeywordAclBranch


class SourceAccessAdapter(Protocol):
    partition_adapter_id: str | None
    resource_types: tuple[str, ...]
    keyword_acl_entity_types: tuple[str, ...]

    def can_read_resource(
        self,
        policy: Any,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool: ...

    def can_read_rag_resource(
        self,
        policy: Any,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool: ...

    def authorize_many_rag_resources(
        self,
        policy: Any,
        *,
        resource_type: str,
        resource_ids: tuple[str, ...],
    ) -> set[str]: ...

    def has_accessible_source(
        self,
        policy: Any,
        *,
        resource_type: str,
    ) -> bool: ...

    def keyword_acl_branches(self, policy: Any) -> list[KeywordAclBranch]: ...


_adapters_by_resource_type: dict[str, SourceAccessAdapter] = {}


def register_source_access_adapter(adapter: SourceAccessAdapter) -> None:
    for resource_type in adapter.resource_types:
        if resource_type in _adapters_by_resource_type:
            raise ValueError(f"Source access adapter already registered for {resource_type}")
        _adapters_by_resource_type[resource_type] = adapter


def get_source_access_adapter(resource_type: str) -> SourceAccessAdapter | None:
    return _adapters_by_resource_type.get(resource_type)


def has_source_access_adapter(resource_type: str) -> bool:
    return resource_type in _adapters_by_resource_type


def get_source_access_adapters() -> tuple[SourceAccessAdapter, ...]:
    return tuple(dict.fromkeys(_adapters_by_resource_type.values()))


def reset_source_access_adapters() -> None:
    _adapters_by_resource_type.clear()


__all__ = [
    "SourceAccessAdapter",
    "get_source_access_adapter",
    "get_source_access_adapters",
    "has_source_access_adapter",
    "register_source_access_adapter",
    "reset_source_access_adapters",
]
