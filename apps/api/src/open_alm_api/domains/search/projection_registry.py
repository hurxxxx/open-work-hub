from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import Workspace
from open_alm_api.domains.search.entity_registry import normalize_search_entity_type


class SearchProjectionAdapter(Protocol):
    entity_types: tuple[str, ...]

    def load_workspace_documents(
        self,
        db: Session,
        *,
        workspace: Workspace,
    ) -> list[dict[str, Any]]: ...

    def load_document(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class FunctionSearchProjectionAdapter:
    entity_types: tuple[str, ...]
    workspace_loader: Any
    document_loader: Any

    def load_workspace_documents(
        self,
        db: Session,
        *,
        workspace: Workspace,
    ) -> list[dict[str, Any]]:
        return self.workspace_loader(db, workspace=workspace)

    def load_document(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any] | None:
        return self.document_loader(db, entity_type=entity_type, entity_id=entity_id)


_projection_adapters_by_entity_type: dict[str, SearchProjectionAdapter] = {}


def register_search_projection_adapter(adapter: SearchProjectionAdapter) -> None:
    for entity_type in adapter.entity_types:
        normalized_entity_type = normalize_search_entity_type(entity_type)
        if normalized_entity_type in _projection_adapters_by_entity_type:
            raise ValueError(f"Search projection adapter already registered for {normalized_entity_type}")
        _projection_adapters_by_entity_type[normalized_entity_type] = adapter


def get_search_projection_adapter(entity_type: object) -> SearchProjectionAdapter | None:
    return _projection_adapters_by_entity_type.get(normalize_search_entity_type(entity_type))


def has_search_projection_adapter(entity_type: object) -> bool:
    return normalize_search_entity_type(entity_type) in _projection_adapters_by_entity_type


def get_search_projection_adapters() -> tuple[SearchProjectionAdapter, ...]:
    return tuple(dict.fromkeys(_projection_adapters_by_entity_type.values()))


def reset_search_projection_adapters() -> None:
    _projection_adapters_by_entity_type.clear()


__all__ = [
    "FunctionSearchProjectionAdapter",
    "SearchProjectionAdapter",
    "get_search_projection_adapter",
    "get_search_projection_adapters",
    "has_search_projection_adapter",
    "register_search_projection_adapter",
    "reset_search_projection_adapters",
]
