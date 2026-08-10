from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from open_alm_api.domains.meeting.models import Meeting
from open_alm_api.domains.retrieval.partitioning import assign_default_partition
from open_alm_api.domains.retrieval.projection_fencing import (
    ProjectionEventRef,
    record_projection_event,
)
from open_alm_api.domains.search.outbox import enqueue_search_index_job
from open_alm_api.domains.search.schemas import SearchEntityType
from open_alm_api.domains.source_access.resource_types import MEETING_RESOURCE_TYPE


def enqueue_meeting_search_index(
    db: Session,
    *,
    meeting: Any,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    resolved_projection_event = projection_event or _record_meeting_projection_event(
        db,
        meeting=meeting,
        operation=operation,
    )
    _enqueue_search_target(
        db,
        workspace_id=meeting.workspace_id,
        entity_id=meeting.id,
        operation=operation,
        projection_event=resolved_projection_event,
    )


def enqueue_meeting_search_index_by_id(
    db: Session,
    *,
    meeting_id: str,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        return
    enqueue_meeting_search_index(
        db,
        meeting=meeting,
        operation=operation,
        projection_event=projection_event,
    )


def _enqueue_search_target(
    db: Session,
    *,
    workspace_id: str | None,
    entity_id: str,
    operation: str,
    projection_event: ProjectionEventRef | None,
) -> None:
    if workspace_id is None:
        return
    enqueue_search_index_job(
        db,
        workspace_id=workspace_id,
        entity_type=SearchEntityType.MEETING,
        entity_id=entity_id,
        operation=operation,
        projection_event=projection_event,
    )


def _record_meeting_projection_event(
    db: Session,
    *,
    meeting: Any,
    operation: str,
) -> ProjectionEventRef | None:
    if operation not in {"upsert", "delete"}:
        raise ValueError(f"Unsupported search index operation: {operation}")
    partition_id = str(getattr(meeting, "retrieval_partition_id", None) or "").strip()
    if not partition_id:
        workspace_id = str(getattr(meeting, "workspace_id", None) or "").strip()
        if not workspace_id:
            return None
        partition_id = assign_default_partition(
            db,
            target=meeting,
            source_namespace="meeting",
            candidate_scope_kind="workspace",
            workspace_id=workspace_id,
        )
    deleted = operation == "delete"
    return record_projection_event(
        db,
        resource_type=MEETING_RESOURCE_TYPE,
        resource_id=meeting.id,
        retrieval_partition_id=partition_id,
        change_kind="delete" if deleted else "content",
        desired_state="deleted" if deleted else "active",
        diagnostic_workspace_id=meeting.workspace_id,
    )


__all__ = ["enqueue_meeting_search_index", "enqueue_meeting_search_index_by_id"]
