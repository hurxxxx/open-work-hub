from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from open_work_hub_api.domains.rag.contracts import RagSyncLane, RagSyncOperation


RagProjectionLoader = Callable[[Any, str, Any], Any | None]
RagWorkspaceResourceIdsLoader = Callable[[Any, Any], Iterable[str]]
RagCompanyResourceIdsLoader = Callable[[Any], Iterable[str]]
RagSourceVisibilityPredicate = Callable[[Any, "RagSourceAdapter"], bool]
RagVisibilityScopeResourceIdsLoader = Callable[[Any, Any], Iterable[str]]
RagProjectionDeletedHook = Callable[[Any, str], None]
RagProjectionPreparedHook = Callable[[Any, str], None]
RagProjectionPreparedEventHook = Callable[[Any, str, Any], None]
RagProjectionSyncedHook = Callable[[Any, str, int], None]
RagProjectionFailedHook = Callable[[Any, str, str, str], None]


@dataclass(frozen=True)
class RagSourceAdapter:
    source_kind: str
    resource_type: str
    app_id: str | None = None
    label: str | None = None
    include_in_source_listing: bool = False
    visible: RagSourceVisibilityPredicate | None = None


@dataclass(frozen=True)
class RagResourceAdapter:
    resource_type: str
    app_id: str | None = None
    partition_adapter_id: str | None = None
    load_projection: RagProjectionLoader | None = None
    workspace_resource_ids: RagWorkspaceResourceIdsLoader | None = None
    company_resource_ids: RagCompanyResourceIdsLoader | None = None
    on_projection_deleted: RagProjectionDeletedHook | None = None
    on_projection_prepared: RagProjectionPreparedHook | None = None
    on_projection_prepared_event: RagProjectionPreparedEventHook | None = None
    on_projection_synced: RagProjectionSyncedHook | None = None
    on_projection_failed: RagProjectionFailedHook | None = None
    include_in_default_query: bool = False
    include_in_workspace_reindex: bool = False
    include_in_company_reindex: bool = False


@dataclass(frozen=True)
class RagVisibilityScopeAdapter:
    scope_type: str
    resource_type: str
    resource_ids: RagVisibilityScopeResourceIdsLoader
    operation: str = "visibility_update"
    lane: str = "backfill"
    scope_label: str | None = None


_adapters_by_source_kind: dict[str, RagSourceAdapter] = {}
_resource_adapters_by_resource_type: dict[str, RagResourceAdapter] = {}
_visibility_scope_adapters_by_scope_type: dict[str, RagVisibilityScopeAdapter] = {}
_default_resource_types: list[str] = []


def register_rag_source_adapter(adapter: RagSourceAdapter) -> None:
    existing = _adapters_by_source_kind.get(adapter.source_kind)
    if existing is not None and existing != adapter:
        raise ValueError(
            f"RAG source kind {adapter.source_kind!r} is already registered for {existing.resource_type!r}"
        )
    _adapters_by_source_kind[adapter.source_kind] = adapter


def register_rag_resource_adapter(adapter: RagResourceAdapter) -> None:
    existing = _resource_adapters_by_resource_type.get(adapter.resource_type)
    if existing is not None and existing != adapter:
        raise ValueError(f"RAG resource adapter is already registered for {adapter.resource_type!r}")
    _resource_adapters_by_resource_type[adapter.resource_type] = adapter
    if adapter.include_in_default_query:
        register_default_rag_resource_type(adapter.resource_type)


def register_rag_visibility_scope_adapter(adapter: RagVisibilityScopeAdapter) -> None:
    scope_type = adapter.scope_type.strip()
    if not scope_type:
        raise ValueError("RAG visibility scope adapter must declare scope_type")
    resource_type = adapter.resource_type.strip()
    if not resource_type:
        raise ValueError(
            f"RAG visibility scope adapter {scope_type!r} must declare resource_type"
        )
    normalized = RagVisibilityScopeAdapter(
        scope_type=scope_type,
        resource_type=resource_type,
        resource_ids=adapter.resource_ids,
        operation=_normalize_visibility_operation(adapter.operation),
        lane=_normalize_visibility_lane(adapter.lane),
        scope_label=(adapter.scope_label or scope_type).strip(),
    )
    existing = _visibility_scope_adapters_by_scope_type.get(scope_type)
    if existing is not None and existing != normalized:
        raise ValueError(f"RAG visibility scope adapter is already registered for {scope_type!r}")
    _visibility_scope_adapters_by_scope_type[scope_type] = normalized


def register_default_rag_resource_type(resource_type: str) -> None:
    if resource_type not in _default_resource_types:
        _default_resource_types.append(resource_type)


def resource_types_for_rag_source_kinds(source_kinds: list[str]) -> tuple[str, ...]:
    if not source_kinds:
        return tuple(_default_resource_types)
    resource_types = [
        _adapters_by_source_kind[source_kind].resource_type
        for source_kind in source_kinds
        if source_kind in _adapters_by_source_kind
    ]
    return tuple(dict.fromkeys(resource_types))


def listed_rag_source_adapters() -> tuple[RagSourceAdapter, ...]:
    return tuple(
        adapter
        for adapter in _adapters_by_source_kind.values()
        if adapter.include_in_source_listing and adapter.app_id is not None
    )


def rag_source_adapters() -> tuple[RagSourceAdapter, ...]:
    return tuple(_adapters_by_source_kind.values())


def get_rag_source_adapter(source_kind: str) -> RagSourceAdapter | None:
    return _adapters_by_source_kind.get(source_kind)


def has_rag_source_adapter(source_kind: str) -> bool:
    return source_kind in _adapters_by_source_kind


def get_rag_resource_adapter(resource_type: str) -> RagResourceAdapter | None:
    return _resource_adapters_by_resource_type.get(resource_type)


def get_rag_visibility_scope_adapter(scope_type: str) -> RagVisibilityScopeAdapter | None:
    return _visibility_scope_adapters_by_scope_type.get(scope_type)


def has_rag_resource_adapter(resource_type: str) -> bool:
    return resource_type in _resource_adapters_by_resource_type


def has_rag_visibility_scope_adapter(scope_type: str) -> bool:
    return scope_type in _visibility_scope_adapters_by_scope_type


def rag_resource_adapters() -> tuple[RagResourceAdapter, ...]:
    return tuple(_resource_adapters_by_resource_type.values())


def rag_visibility_scope_adapters() -> tuple[RagVisibilityScopeAdapter, ...]:
    return tuple(_visibility_scope_adapters_by_scope_type.values())


def workspace_reindex_rag_resource_adapters(enabled_app_ids: set[str]) -> tuple[RagResourceAdapter, ...]:
    return tuple(
        adapter
        for adapter in _resource_adapters_by_resource_type.values()
        if adapter.include_in_workspace_reindex
        and adapter.workspace_resource_ids is not None
        and adapter.app_id in enabled_app_ids
    )


def company_reindex_rag_resource_adapters(
    enabled_app_ids: set[str] | None = None,
) -> tuple[RagResourceAdapter, ...]:
    return tuple(
        adapter
        for adapter in _resource_adapters_by_resource_type.values()
        if adapter.include_in_company_reindex
        and adapter.company_resource_ids is not None
        and (enabled_app_ids is None or adapter.app_id in enabled_app_ids)
    )


def searchable_rag_app_ids() -> frozenset[str]:
    app_ids = {
        adapter.app_id
        for adapter in _resource_adapters_by_resource_type.values()
        if adapter.include_in_default_query
        or adapter.include_in_workspace_reindex
        or adapter.include_in_company_reindex
    }
    app_ids.update(
        adapter.app_id
        for adapter in _adapters_by_source_kind.values()
        if adapter.include_in_source_listing
    )
    return frozenset(app_id for app_id in app_ids if app_id)


def reset_rag_source_adapters() -> None:
    _adapters_by_source_kind.clear()
    _resource_adapters_by_resource_type.clear()
    _visibility_scope_adapters_by_scope_type.clear()
    _default_resource_types.clear()


def _normalize_visibility_operation(value: str) -> str:
    operation = (value or RagSyncOperation.VISIBILITY_UPDATE.value).strip()
    try:
        return RagSyncOperation(operation).value
    except ValueError as exc:
        raise ValueError(f"Unsupported RAG visibility operation: {operation}") from exc


def _normalize_visibility_lane(value: str) -> str:
    lane = (value or RagSyncLane.BACKFILL.value).strip()
    try:
        return RagSyncLane(lane).value
    except ValueError as exc:
        raise ValueError(f"Unsupported RAG visibility lane: {lane}") from exc


__all__ = [
    "RagResourceAdapter",
    "RagSourceAdapter",
    "RagVisibilityScopeAdapter",
    "get_rag_source_adapter",
    "get_rag_resource_adapter",
    "get_rag_visibility_scope_adapter",
    "has_rag_source_adapter",
    "has_rag_resource_adapter",
    "has_rag_visibility_scope_adapter",
    "listed_rag_source_adapters",
    "rag_source_adapters",
    "rag_resource_adapters",
    "rag_visibility_scope_adapters",
    "register_default_rag_resource_type",
    "register_rag_resource_adapter",
    "register_rag_source_adapter",
    "register_rag_visibility_scope_adapter",
    "reset_rag_source_adapters",
    "resource_types_for_rag_source_kinds",
    "searchable_rag_app_ids",
    "workspace_reindex_rag_resource_adapters",
]
