from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import Workspace
from ai_do_api.domains.search.default_projection_adapters import (
    ensure_search_projection_adapters_registered,
)
from ai_do_api.domains.search.projection_registry import (
    get_search_projection_adapter,
    get_search_projection_adapters,
)
from ai_do_api.domains.search.projection_identity import ensure_search_document_identity
from ai_do_api.domains.search.schemas import SearchEntityType


def all_workspace_search_documents(db: Session, *, workspace: Workspace) -> list[dict[str, Any]]:
    ensure_search_projection_adapters_registered()
    documents: list[dict[str, Any]] = []
    for adapter in get_search_projection_adapters():
        adapter_documents = adapter.load_workspace_documents(db, workspace=workspace)
        for document in adapter_documents:
            ensure_search_document_identity(
                document,
                workspace_id=workspace.id,
                allowed_entity_types=adapter.entity_types,
                context=f"workspace {workspace.id}",
            )
        documents.extend(adapter_documents)
    return documents


def load_search_document(
    db: Session,
    *,
    entity_type: SearchEntityType | str,
    entity_id: str,
) -> dict[str, Any] | None:
    resolved_entity_type = str(entity_type)
    ensure_search_projection_adapters_registered()
    adapter = get_search_projection_adapter(resolved_entity_type)
    if adapter is None:
        return None
    return adapter.load_document(db, entity_type=resolved_entity_type, entity_id=entity_id)


def load_doc_search_document(db: Session, *, doc_id: str) -> dict[str, Any] | None:
    return load_search_document(db, entity_type=SearchEntityType.DOC, entity_id=doc_id)


__all__ = [
    "all_workspace_search_documents",
    "load_doc_search_document",
    "load_search_document",
]
