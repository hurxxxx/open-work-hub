from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.app_registry import AppRegistration
from open_work_hub_api.domains.search.entity_registry import (
    SearchEntityDescriptor,
    get_search_entity_descriptor,
    normalize_search_entity_type,
    register_search_entity_descriptor,
)
from open_work_hub_api.domains.search.projection_registry import (
    get_search_projection_adapter,
    register_search_projection_adapter,
)


@dataclass(frozen=True)
class SearchIndexLifecycleHooks:
    create: tuple[str, ...] = ()
    update: tuple[str, ...] = ()
    delete: tuple[str, ...] = ()

    def for_operation(self, operation: str) -> tuple[str, ...]:
        if operation not in {"create", "update", "delete"}:
            raise ValueError(f"Unsupported search index lifecycle operation: {operation}")
        return getattr(self, operation)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.create, *self.update, *self.delete)))


@dataclass(frozen=True)
class SearchEntityAdapter:
    owner_app: AppRegistration
    entity_type: str
    resource_type: str
    label: str
    label_key: str
    company_loader: Any
    document_loader: Any
    partition_adapter_id: str | None = None
    active: bool = True
    index_hooks: SearchIndexLifecycleHooks = SearchIndexLifecycleHooks()
    date_fields: tuple[str, ...] = ()
    person_roles: tuple[str, ...] = ()
    sort_fields: tuple[str, ...] = ()

    @property
    def owner_app_id(self) -> str:
        return self.owner_app.app_id

    @property
    def index_hook_names(self) -> tuple[str, ...]:
        return self.index_hooks.names

    @property
    def entity_types(self) -> tuple[str, ...]:
        return (normalize_search_entity_type(self.entity_type),)

    @property
    def descriptor(self) -> SearchEntityDescriptor:
        return SearchEntityDescriptor(
            entity_type=normalize_search_entity_type(self.entity_type),
            resource_type=self.resource_type,
            label=self.label,
            label_key=self.label_key,
        )

    def load_documents(
        self,
        db: Session,
    ) -> list[dict[str, Any]]:
        if not self.active:
            return []
        return self.company_loader(
            db,
        )

    def load_document(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any] | None:
        if not self.active:
            return None
        return self.document_loader(db, entity_type=entity_type, entity_id=entity_id)


@dataclass(frozen=True)
class CompanyKeywordSearchScope:
    descriptors: tuple[SearchEntityDescriptor, ...]

    @property
    def entity_types(self) -> tuple[str, ...]:
        return tuple(descriptor.entity_type for descriptor in self.descriptors)

    @property
    def has_sources(self) -> bool:
        return bool(self.descriptors)

    def constrain_entity_types(self, requested: Iterable[object]) -> tuple[str, ...]:
        allowed = set(self.entity_types)
        normalized_requested = tuple(
            dict.fromkeys(normalize_search_entity_type(value) for value in requested)
        )
        if not normalized_requested:
            return self.entity_types
        return tuple(value for value in normalized_requested if value in allowed)


_adapters_by_entity_type: dict[str, SearchEntityAdapter] = {}


def register_search_entity_adapter(adapter: SearchEntityAdapter) -> None:
    normalized = _normalize_adapter(adapter)
    entity_type = normalized.entity_type
    existing = _adapters_by_entity_type.get(entity_type)
    if existing is not None and existing != normalized:
        raise ValueError(f"Search entity adapter already registered: {entity_type}")

    descriptor = get_search_entity_descriptor(entity_type)
    if descriptor is not None and descriptor != normalized.descriptor:
        raise ValueError(f"Search entity descriptor already registered: {entity_type}")

    _adapters_by_entity_type[entity_type] = normalized
    if descriptor is None:
        register_search_entity_descriptor(normalized.descriptor)
    if get_search_projection_adapter(entity_type) is None:
        register_search_projection_adapter(normalized)


def get_search_entity_adapter(entity_type: object) -> SearchEntityAdapter | None:
    return _adapters_by_entity_type.get(normalize_search_entity_type(entity_type))


def has_search_entity_adapter(entity_type: object) -> bool:
    return normalize_search_entity_type(entity_type) in _adapters_by_entity_type


def search_entity_adapters() -> tuple[SearchEntityAdapter, ...]:
    return tuple(_adapters_by_entity_type.values())


def resolve_keyword_search_scope(
    enabled_app_ids: Collection[str],
    *,
    include_inactive_entity_types: Collection[str] = (),
) -> CompanyKeywordSearchScope:
    from open_work_hub_api.domains.search.default_entity_adapters import (
        ensure_search_entity_adapters_registered,
    )

    ensure_search_entity_adapters_registered()
    enabled = {str(app_id).strip() for app_id in enabled_app_ids if str(app_id).strip()}
    included_inactive = {
        normalize_search_entity_type(entity_type)
        for entity_type in include_inactive_entity_types
        if normalize_search_entity_type(entity_type)
    }
    return CompanyKeywordSearchScope(
        descriptors=tuple(
            adapter.descriptor
            for adapter in _adapters_by_entity_type.values()
            if adapter.owner_app_id in enabled
            and (adapter.active or adapter.entity_type in included_inactive)
        )
    )


def reset_search_entity_adapters() -> None:
    _adapters_by_entity_type.clear()


def _normalize_adapter(adapter: SearchEntityAdapter) -> SearchEntityAdapter:
    owner_app = adapter.owner_app
    entity_type = normalize_search_entity_type(adapter.entity_type)
    resource_type = str(adapter.resource_type).strip()
    label = str(adapter.label).strip()
    label_key = str(adapter.label_key).strip()
    partition_adapter_id = str(adapter.partition_adapter_id or "").strip() or None
    if not isinstance(owner_app, AppRegistration):
        raise ValueError("Search entity adapter must declare owner_app registration")
    if not entity_type:
        raise ValueError("Search entity adapter must declare entity_type")
    if not resource_type:
        raise ValueError(f"Search entity adapter {entity_type} must declare resource_type")
    if not label:
        raise ValueError(f"Search entity adapter {entity_type} must declare label")
    if not label_key:
        raise ValueError(f"Search entity adapter {entity_type} must declare label_key")
    if not callable(adapter.company_loader):
        raise ValueError(f"Search entity adapter {entity_type} must declare company_loader")
    if not callable(adapter.document_loader):
        raise ValueError(f"Search entity adapter {entity_type} must declare document_loader")
    return SearchEntityAdapter(
        owner_app=owner_app,
        entity_type=entity_type,
        resource_type=resource_type,
        label=label,
        label_key=label_key,
        company_loader=adapter.company_loader,
        document_loader=adapter.document_loader,
        partition_adapter_id=partition_adapter_id,
        active=bool(adapter.active),
        index_hooks=SearchIndexLifecycleHooks(
            create=_normalize_string_tuple(adapter.index_hooks.create),
            update=_normalize_string_tuple(adapter.index_hooks.update),
            delete=_normalize_string_tuple(adapter.index_hooks.delete),
        ),
        date_fields=_normalize_string_tuple(adapter.date_fields),
        person_roles=_normalize_string_tuple(adapter.person_roles),
        sort_fields=_normalize_string_tuple(adapter.sort_fields),
    )


def search_date_filter_fields() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                "updated_at",
                "created_at",
                *(
                    field
                    for adapter in _adapters_by_entity_type.values()
                    for field in adapter.date_fields
                ),
            )
        )
    )


def search_people_roles() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                "any",
                *(
                    role
                    for adapter in _adapters_by_entity_type.values()
                    for role in adapter.person_roles
                ),
            )
        )
    )


def search_sort_fields() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                "relevance",
                "updated_at",
                "created_at",
                *(
                    field
                    for adapter in _adapters_by_entity_type.values()
                    for field in adapter.sort_fields
                ),
            )
        )
    )


def _normalize_string_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


__all__ = [
    "SearchIndexLifecycleHooks",
    "SearchEntityAdapter",
    "CompanyKeywordSearchScope",
    "get_search_entity_adapter",
    "has_search_entity_adapter",
    "register_search_entity_adapter",
    "reset_search_entity_adapters",
    "resolve_keyword_search_scope",
    "search_entity_adapters",
    "search_date_filter_fields",
    "search_people_roles",
    "search_sort_fields",
]
