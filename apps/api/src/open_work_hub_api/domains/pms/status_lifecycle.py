from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.pms.models import SpaceStatus, TaskList, TaskListStatus
from open_work_hub_api.domains.pms.workflow import normalize_status_category

DEFAULT_TASK_LIST_STATUSES: list[tuple[str, str, str, str, int]] = [
    ("todo", "To Do", "#9ca3af", "not_started", 0),
    ("in_progress", "In Progress", "#3b82f6", "active", 1),
    ("review", "Review", "#8b5cf6", "active", 2),
    ("done", "Done", "#22c55e", "done", 3),
    ("complete", "Complete", "#16a34a", "closed", 4),
]


def create_default_task_list_statuses(db: Session, list_id: str) -> None:
    for slug, name, color, category, sort_order in DEFAULT_TASK_LIST_STATUSES:
        db.add(
            TaskListStatus(
                id=new_id(),
                list_id=list_id,
                slug=slug,
                name=name,
                color=color,
                category=category,
                sort_order=sort_order,
            )
        )


def create_default_space_statuses(db: Session, team_id: str) -> None:
    for slug, name, color, category, sort_order in DEFAULT_TASK_LIST_STATUSES:
        db.add(
            SpaceStatus(
                id=new_id(),
                team_id=team_id,
                slug=slug,
                name=name,
                color=color,
                category=category,
                sort_order=sort_order,
            )
        )


def ensure_space_statuses(db: Session, team_id: str) -> list[SpaceStatus]:
    statuses = list(
        db.scalars(
            select(SpaceStatus)
            .where(SpaceStatus.team_id == team_id)
            .order_by(SpaceStatus.sort_order)
        )
    )
    if not statuses:
        create_default_space_statuses(db, team_id)
        db.flush()
        statuses = list(
            db.scalars(
                select(SpaceStatus)
                .where(SpaceStatus.team_id == team_id)
                .order_by(SpaceStatus.sort_order)
            )
        )
    return statuses


def ensure_task_list_custom_statuses(
    db: Session,
    task_list: TaskList,
) -> list[TaskListStatus]:
    statuses = list(
        db.scalars(
            select(TaskListStatus)
            .where(TaskListStatus.list_id == task_list.id)
            .order_by(TaskListStatus.sort_order)
        )
    )
    if not statuses:
        create_default_task_list_statuses(db, task_list.id)
        db.flush()
        statuses = list(
            db.scalars(
                select(TaskListStatus)
                .where(TaskListStatus.list_id == task_list.id)
                .order_by(TaskListStatus.sort_order)
            )
        )
    return statuses


def copy_space_statuses_to_task_list(
    db: Session,
    task_list: TaskList,
) -> list[TaskListStatus]:
    if not task_list.team_id:
        return ensure_task_list_custom_statuses(db, task_list)
    source_statuses = ensure_space_statuses(db, task_list.team_id)
    for existing in list(task_list.statuses):
        db.delete(existing)
    db.flush()
    copied: list[TaskListStatus] = []
    for source in source_statuses:
        copied_status = TaskListStatus(
            id=new_id(),
            list_id=task_list.id,
            slug=source.slug,
            name=source.name,
            color=source.color,
            category=normalize_status_category(source.category),
            sort_order=source.sort_order,
        )
        db.add(copied_status)
        copied.append(copied_status)
    db.flush()
    task_list.statuses = copied
    return copied
