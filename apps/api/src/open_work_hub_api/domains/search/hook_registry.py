from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from open_work_hub_api.core.app_registry import AppRegistration
from open_work_hub_api.domains.search.entity_registry import normalize_search_entity_type

SearchIndexHook = Callable[..., Any]
SearchIndexOperation = Literal["create", "update", "delete"]
SEARCH_INDEX_OPERATIONS: frozenset[str] = frozenset({"create", "update", "delete"})


@dataclass(frozen=True)
class SearchIndexHookRegistration:
    name: str
    owner_app: AppRegistration
    entity_type: str
    operations: frozenset[SearchIndexOperation]
    hook: SearchIndexHook


_search_index_hooks: dict[str, SearchIndexHookRegistration] = {}


def register_search_index_hook(
    name: str,
    hook: SearchIndexHook,
    *,
    owner_app: AppRegistration,
    entity_type: str,
    operations: tuple[SearchIndexOperation, ...],
) -> None:
    normalized_name = str(name).strip()
    normalized_entity_type = normalize_search_entity_type(entity_type)
    normalized_operations = frozenset(operations)
    if not normalized_name:
        raise ValueError("Search index hook name is required")
    if normalized_name in _search_index_hooks:
        raise ValueError(f"Search index hook already registered: {normalized_name}")
    if not callable(hook):
        raise ValueError(f"Search index hook must be callable: {normalized_name}")
    if not isinstance(owner_app, AppRegistration):
        raise ValueError(
            f"Search index hook must declare owner_app registration: {normalized_name}"
        )
    if not normalized_entity_type:
        raise ValueError(f"Search index hook must declare entity_type: {normalized_name}")
    unsupported_operations = normalized_operations - SEARCH_INDEX_OPERATIONS
    if unsupported_operations:
        raise ValueError(
            f"Search index hook {normalized_name} declares unsupported operations: "
            + ", ".join(sorted(unsupported_operations))
        )
    if not normalized_operations:
        raise ValueError(f"Search index hook must declare operations: {normalized_name}")
    _search_index_hooks[normalized_name] = SearchIndexHookRegistration(
        name=normalized_name,
        owner_app=owner_app,
        entity_type=normalized_entity_type,
        operations=normalized_operations,
        hook=hook,
    )


def resolve_search_index_hook(name: str) -> SearchIndexHook:
    registration = _search_index_hooks.get(name)
    if registration is None:
        raise LookupError(f"Search index hook is not registered: {name}")
    return registration.hook


def get_search_index_hook_registration(name: str) -> SearchIndexHookRegistration | None:
    return _search_index_hooks.get(name)


def has_search_index_hook(name: str) -> bool:
    return name in _search_index_hooks


def search_index_hooks_registered() -> bool:
    return bool(_search_index_hooks)


def reset_search_index_hooks() -> None:
    _search_index_hooks.clear()


__all__ = [
    "SEARCH_INDEX_OPERATIONS",
    "SearchIndexHook",
    "SearchIndexHookRegistration",
    "SearchIndexOperation",
    "get_search_index_hook_registration",
    "has_search_index_hook",
    "register_search_index_hook",
    "reset_search_index_hooks",
    "resolve_search_index_hook",
    "search_index_hooks_registered",
]
