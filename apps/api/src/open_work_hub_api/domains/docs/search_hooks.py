from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.retrieval.projection_fencing import ProjectionEventRef
from open_work_hub_api.domains.search.outbox import enqueue_search_index_job
from open_work_hub_api.domains.search.schemas import SearchEntityType


def enqueue_doc_search_index(
    db: Session,
    *,
    doc: Any,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    _enqueue_search_target(
        db,
        entity_id=doc.id,
        operation=operation,
        projection_event=projection_event,
    )


def enqueue_doc_search_index_by_id(
    db: Session,
    *,
    doc_id: str,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    doc = db.get(NativeDoc, doc_id)
    if doc is None:
        return
    enqueue_doc_search_index(
        db,
        doc=doc,
        operation=operation,
        projection_event=projection_event,
    )


def _enqueue_search_target(
    db: Session,
    *,
    entity_id: str,
    operation: str,
    projection_event: ProjectionEventRef | None,
) -> None:
    enqueue_search_index_job(
        db,
        entity_type=SearchEntityType.DOC,
        entity_id=entity_id,
        operation=operation,
        projection_event=projection_event,
    )


__all__ = ["enqueue_doc_search_index", "enqueue_doc_search_index_by_id"]
