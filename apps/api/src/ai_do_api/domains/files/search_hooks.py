from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ai_do_api.domains.files.models import FileManagerFile
from ai_do_api.domains.files.retrieval_contract import FILES_RETRIEVAL_ACTIVE
from ai_do_api.domains.retrieval.projection_fencing import ProjectionEventRef
from ai_do_api.domains.search.outbox import enqueue_search_index_job
from ai_do_api.domains.search.schemas import SearchEntityType
from ai_do_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


def enqueue_file_search_index(
    db: Session,
    *,
    file: Any,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    if not FILES_RETRIEVAL_ACTIVE:
        return
    enqueue_search_index_job(
        db,
        workspace_id=file.workspace_id,
        entity_type=SearchEntityType.FILE,
        entity_id=file.id,
        operation=operation,
        projection_event=projection_event,
    )


def enqueue_file_search_index_by_id(
    db: Session,
    *,
    file_id: str,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    file = db.get(FileManagerFile, file_id)
    if file is None:
        return
    enqueue_file_search_index(
        db,
        file=file,
        operation=operation,
        projection_event=projection_event,
    )


def stage_file_search_reconciliation_job(
    db: Session,
    *,
    projection_event: ProjectionEventRef,
    workspace_id: str,
) -> None:
    """Stage a fenced Files keyword job while the normal producer gate is paused."""
    if projection_event.resource_type != FILE_MANAGER_FILE_RESOURCE_TYPE:
        raise ValueError("Files reconciliation requires a Files projection event")
    resolved_workspace_id = str(workspace_id or "").strip()
    if not resolved_workspace_id:
        raise ValueError("Files reconciliation requires current managed workspace")
    if projection_event.desired_state not in {"active", "deleted"}:
        raise ValueError("Files reconciliation projection state is invalid")
    enqueue_search_index_job(
        db,
        workspace_id=resolved_workspace_id,
        entity_type=SearchEntityType.FILE,
        entity_id=projection_event.resource_id,
        operation="delete" if projection_event.desired_state == "deleted" else "upsert",
        projection_event=projection_event,
    )


__all__ = [
    "enqueue_file_search_index",
    "enqueue_file_search_index_by_id",
    "stage_file_search_reconciliation_job",
]
