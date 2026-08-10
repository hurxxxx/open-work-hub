from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.meeting.models import MeetingTaskLink
from open_alm_api.domains.pms.models import Task, TaskLabel, TaskUserAccess, Label, Milestone, TaskList
from open_alm_api.domains.rag.contracts import RagSyncOperation
from open_alm_api.domains.search.hooks import (
    enqueue_task_search_index,
    enqueue_task_search_index_by_id,
    enqueue_label_task_search_recompute,
    enqueue_task_list_task_search_recompute,
)


PMS_MEETING_VISIBILITY_SCOPE = "pms_meeting"
PMS_TASK_LIST_RECOMPUTE_SCOPE = "pms_task_list"
PMS_LABEL_RECOMPUTE_SCOPE = "pms_label"
PMS_MILESTONE_RECOMPUTE_SCOPE = "pms_milestone"


def enqueue_task_rag_sync(
    db: Session,
    *,
    task: Task,
    operation: RagSyncOperation,
) -> None:
    enqueue_task_search_index(
        db,
        task=task,
        operation="delete" if operation == RagSyncOperation.DELETE else "upsert",
    )


def enqueue_task_rag_sync_by_id(
    db: Session,
    *,
    task_id: str,
    operation: RagSyncOperation,
) -> None:
    task = db.get(Task, task_id)
    if task is None:
        return
    enqueue_task_rag_sync(
        db,
        task=task,
        operation=operation,
    )


def enqueue_meeting_task_visibility_recompute(
    db: Session,
    *,
    meeting_id: str,
    task_ids: list[str] | None = None,
) -> None:
    for task_id in collect_meeting_task_ids(db, meeting_id=meeting_id, task_ids=task_ids):
        enqueue_task_search_index_by_id(
            db,
            task_id=task_id,
            operation="upsert",
        )


def enqueue_task_list_task_recompute(
    db: Session,
    *,
    task_list: TaskList,
) -> None:
    enqueue_task_list_task_search_recompute(db, task_list=task_list)


def enqueue_label_task_recompute(
    db: Session,
    *,
    label: Label,
    task_ids: list[str] | None = None,
) -> None:
    enqueue_label_task_search_recompute(db, label=label, task_ids=task_ids)


def enqueue_milestone_task_recompute(
    db: Session,
    *,
    milestone: Milestone,
) -> None:
    del db, milestone


def collect_label_task_ids(
    db: Session,
    *,
    label_id: str,
    cursor: dict | None = None,
) -> list[str]:
    task_ids = {
        str(task_id)
        for task_id in (cursor or {}).get("task_ids", [])
        if task_id
    }
    task_ids.update(
        str(task_id)
        for task_id in db.scalars(select(TaskLabel.task_id).where(TaskLabel.label_id == label_id))
        if task_id
    )
    return sorted(task_ids)


def collect_meeting_task_ids(
    db: Session,
    *,
    meeting_id: str,
    task_ids: list[str] | None = None,
    cursor: dict | None = None,
) -> list[str]:
    explicit_task_ids = {str(task_id) for task_id in task_ids or [] if task_id}
    if explicit_task_ids:
        return sorted(explicit_task_ids)

    resolved = {
        str(task_id)
        for task_id in (cursor or {}).get("task_ids", [])
        if task_id
    }
    resolved.update(
        str(task_id)
        for task_id in db.scalars(select(MeetingTaskLink.task_id).where(MeetingTaskLink.meeting_id == meeting_id))
        if task_id
    )
    resolved.update(
        str(task_id)
        for task_id in db.scalars(
            select(TaskUserAccess.task_id).where(
                TaskUserAccess.granted_by_meeting_id == meeting_id,
                TaskUserAccess.revoked_at.is_(None),
            )
        )
        if task_id
    )
    return sorted(resolved)


def collect_task_list_task_ids(
    db: Session,
    *,
    list_id: str,
) -> list[str]:
    return sorted(
        str(task_id)
        for task_id in db.scalars(select(Task.id).where(Task.list_id == list_id))
        if task_id
    )


def collect_milestone_task_ids(
    db: Session,
    *,
    milestone_id: str,
) -> list[str]:
    return sorted(
        str(task_id)
        for task_id in db.scalars(select(Task.id).where(Task.milestone_id == milestone_id))
        if task_id
    )
