from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import Team
from open_alm_api.domains.pms.models import Task, TaskLabel, TaskList
from open_alm_api.domains.retrieval.partitioning import assign_default_partition
from open_alm_api.domains.retrieval.projection_fencing import (
    ProjectionEventRef,
    record_projection_event,
)
from open_alm_api.domains.search.outbox import enqueue_search_index_job
from open_alm_api.domains.search.schemas import SearchEntityType
from open_alm_api.domains.source_access.resource_types import PMS_TASK_RESOURCE_TYPE


def enqueue_task_search_index(
    db: Session,
    *,
    task: Any,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    workspace_id = load_task_workspace_id(db, task_id=task.id)
    resolved_projection_event = projection_event or _record_task_projection_event(
        db,
        task=task,
        workspace_id=workspace_id,
        operation=operation,
    )
    _enqueue_search_target(
        db,
        workspace_id=workspace_id,
        entity_id=task.id,
        operation=operation,
        projection_event=resolved_projection_event,
    )


def enqueue_task_search_index_by_id(
    db: Session,
    *,
    task_id: str,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    workspace_id = load_task_workspace_id(db, task_id=task_id)
    if workspace_id is None:
        return
    task = db.get(Task, task_id)
    if task is None:
        return
    resolved_projection_event = projection_event or _record_task_projection_event(
        db,
        task=task,
        workspace_id=workspace_id,
        operation=operation,
    )
    _enqueue_search_target(
        db,
        workspace_id=workspace_id,
        entity_id=task_id,
        operation=operation,
        projection_event=resolved_projection_event,
    )


def enqueue_task_list_task_search_recompute(
    db: Session,
    *,
    task_list: Any,
    operation: str = "upsert",
) -> None:
    workspace_id = load_task_list_workspace_id(db, list_id=task_list.id)
    task_ids = db.scalars(select(Task.id).where(Task.list_id == task_list.id)).all()
    _enqueue_pms_task_targets(db, workspace_id=workspace_id, task_ids=task_ids, operation=operation)


def enqueue_label_task_search_recompute(
    db: Session,
    *,
    label: Any,
    task_ids: list[str] | None = None,
    operation: str = "upsert",
) -> None:
    workspace_id = load_task_list_workspace_id(db, list_id=label.list_id)
    if workspace_id is None:
        return
    resolved_task_ids = task_ids
    if resolved_task_ids is None:
        resolved_task_ids = list(
            db.scalars(select(TaskLabel.task_id).where(TaskLabel.label_id == label.id))
        )
    _enqueue_pms_task_targets(
        db,
        workspace_id=workspace_id,
        task_ids=resolved_task_ids,
        operation=operation,
        unique=True,
    )


def enqueue_task_list_status_task_search_recompute(
    db: Session,
    *,
    task_status: Any,
    operation: str = "upsert",
) -> None:
    task_list = db.get(TaskList, task_status.list_id)
    if task_list is None:
        return
    enqueue_task_list_task_search_recompute(db, task_list=task_list, operation=operation)


def load_task_workspace_id(db: Session, *, task_id: str) -> str | None:
    return db.scalar(
        select(Team.workspace_id)
        .join(TaskList, TaskList.team_id == Team.id)
        .join(Task, Task.list_id == TaskList.id)
        .where(Task.id == task_id)
    )


def load_task_list_workspace_id(db: Session, *, list_id: str) -> str | None:
    return db.scalar(
        select(Team.workspace_id)
        .join(TaskList, TaskList.team_id == Team.id)
        .where(TaskList.id == list_id)
    )


def _enqueue_pms_task_targets(
    db: Session,
    *,
    workspace_id: str | None,
    task_ids: Iterable[str | None],
    operation: str,
    unique: bool = False,
) -> None:
    present_task_ids = [str(task_id) for task_id in task_ids if task_id]
    resolved_task_ids = set(present_task_ids) if unique else present_task_ids
    for task_id in sorted(resolved_task_ids):
        task = db.get(Task, task_id)
        if task is None:
            continue
        _enqueue_search_target(
            db,
            workspace_id=workspace_id,
            entity_id=task_id,
            operation=operation,
            projection_event=_record_task_projection_event(
                db,
                task=task,
                workspace_id=workspace_id,
                operation=operation,
            ),
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
        entity_type=SearchEntityType.PMS_TASK,
        entity_id=entity_id,
        operation=operation,
        projection_event=projection_event,
    )


def _record_task_projection_event(
    db: Session,
    *,
    task: Any,
    workspace_id: str | None,
    operation: str,
) -> ProjectionEventRef | None:
    if operation not in {"upsert", "delete"}:
        raise ValueError(f"Unsupported search index operation: {operation}")
    partition_id = str(getattr(task, "retrieval_partition_id", None) or "").strip()
    if workspace_id is None:
        return None
    if not partition_id:
        partition_id = assign_default_partition(
            db,
            target=task,
            source_namespace="pms",
            candidate_scope_kind="workspace",
            workspace_id=workspace_id,
        )
    deleted = operation == "delete"
    return record_projection_event(
        db,
        resource_type=PMS_TASK_RESOURCE_TYPE,
        resource_id=task.id,
        retrieval_partition_id=partition_id,
        change_kind="delete" if deleted else "content",
        desired_state="deleted" if deleted else "active",
        diagnostic_workspace_id=workspace_id,
    )


__all__ = [
    "enqueue_label_task_search_recompute",
    "enqueue_task_list_status_task_search_recompute",
    "enqueue_task_list_task_search_recompute",
    "enqueue_task_search_index",
    "enqueue_task_search_index_by_id",
    "load_task_list_workspace_id",
    "load_task_workspace_id",
]
