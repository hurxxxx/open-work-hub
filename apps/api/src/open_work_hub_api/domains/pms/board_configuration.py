from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.pms.access import (
    _ensure_list_editor,
    _ensure_list_manager,
    _ensure_list_member,
    _ensure_space_editor,
    _ensure_task_list_active,
    _load_space_members,
)
from open_work_hub_api.domains.pms.models import CustomFieldValue, Task, TaskList
from open_work_hub_api.domains.pms.rag_sync import enqueue_task_list_task_recompute
from open_work_hub_api.domains.pms.service import (
    _serialize_task_list,
    _validate_folder_membership,
    delete_loaded_tasks,
)
from open_work_hub_api.domains.pms.space_models import Team


@dataclass(frozen=True)
class TaskListUpdateFields:
    provided_fields: set[str]
    name: str | None = None
    description: str | None = None
    status: Literal["planned", "active", "on_hold", "done"] | None = None
    archived: bool | None = None
    folder_id: str | None = None
    sort_order: int | None = None


@dataclass(frozen=True)
class TaskListReorderItem:
    id: str
    folder_id: str | None
    sort_order: int


def get_task_list(
    db: Session,
    *,
    user: User,
    list_id: str,
) -> dict[str, Any]:
    task_list, role = _ensure_list_member(db, user, list_id)
    task_list = _load_task_list_for_response(db, task_list.id)
    return _serialize_task_list_for_response(db, task_list=task_list, role=role)


def update_task_list(
    db: Session,
    *,
    user: User,
    list_id: str,
    fields: TaskListUpdateFields,
) -> dict[str, Any]:
    if _is_reorder_only_update(fields.provided_fields):
        task_list, role = _ensure_list_editor(db, user, list_id)
    else:
        task_list, role = _ensure_list_manager(db, user, list_id)
        if fields.provided_fields - {"archived"}:
            _ensure_task_list_active(task_list)

    if "folder_id" in fields.provided_fields:
        _validate_folder_membership(db, task_list.team_id, fields.folder_id)
        task_list.folder_id = fields.folder_id
    if fields.sort_order is not None:
        task_list.sort_order = fields.sort_order

    for field_name in ("name", "description", "status", "archived"):
        if field_name not in fields.provided_fields:
            continue
        value = getattr(fields, field_name)
        if value is None:
            continue
        setattr(task_list, field_name, value.strip() if isinstance(value, str) else value)

    if fields.provided_fields - {"folder_id", "sort_order"}:
        enqueue_task_list_task_recompute(db, task_list=task_list)

    db.commit()
    db.refresh(task_list)
    task_list = _load_task_list_for_response(db, task_list.id)
    return _serialize_task_list_for_response(db, task_list=task_list, role=role)


def delete_task_list(
    db: Session,
    *,
    user: User,
    list_id: str,
) -> None:
    task_list, _role = _ensure_list_manager(db, user, list_id)
    if not task_list.archived:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="pms.task_list_archive_before_delete",
        )
    task_list = _load_task_list_for_response(db, task_list.id)
    tasks = list(task_list.tasks)
    task_ids = [task.id for task in tasks]
    field_ids = [field.id for field in task_list.custom_fields]

    if task_ids:
        db.execute(delete(CustomFieldValue).where(CustomFieldValue.task_id.in_(task_ids)))
    if field_ids:
        db.execute(delete(CustomFieldValue).where(CustomFieldValue.field_id.in_(field_ids)))

    if tasks:
        delete_loaded_tasks(db, tasks)

    task_list = db.get(TaskList, list_id)
    if task_list is None:
        return
    db.delete(task_list)
    db.commit()


def reorder_space_task_lists(
    db: Session,
    *,
    user: User,
    space_id: str,
    items: list[TaskListReorderItem],
) -> None:
    _ensure_space_editor(db, user, space_id)
    item_ids = [item.id for item in items]
    if len(set(item_ids)) != len(item_ids):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="pms.duplicate_task_list_ids",
        )

    task_lists = list(
        db.scalars(
            select(TaskList).where(
                TaskList.team_id == space_id,
                TaskList.id.in_(item_ids),
            )
        )
    )
    task_list_map = {task_list.id: task_list for task_list in task_lists}
    if len(task_list_map) != len(item_ids):
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="pms.task_list_not_found",
        )

    for task_list in task_lists:
        _ensure_task_list_active(task_list)

    for item in items:
        _validate_folder_membership(db, space_id, item.folder_id)
        task_list = task_list_map[item.id]
        task_list.folder_id = item.folder_id
        task_list.sort_order = item.sort_order

    db.commit()


def _is_reorder_only_update(provided_fields: set[str]) -> bool:
    return bool(provided_fields) and provided_fields.issubset({"folder_id", "sort_order"})


def _load_task_list_for_response(db: Session, list_id: str) -> TaskList:
    task_list = db.scalar(
        select(TaskList)
        .options(
            selectinload(TaskList.milestones),
            selectinload(TaskList.statuses),
            selectinload(TaskList.space_statuses),
            selectinload(TaskList.tasks).selectinload(Task.comments),
            selectinload(TaskList.custom_fields),
            joinedload(TaskList.folder),
        )
        .where(TaskList.id == list_id)
    )
    if task_list is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="pms.task_list_not_found",
        )
    return task_list


def _serialize_task_list_for_response(
    db: Session,
    *,
    task_list: TaskList,
    role: str,
) -> dict[str, Any]:
    team_name = (
        db.scalar(select(Team.name).where(Team.id == task_list.team_id))
        if task_list.team_id
        else None
    )
    member_count = len(_load_space_members(db, task_list.team_id)) if task_list.team_id else 0
    return _serialize_task_list(task_list, role, team_name, member_count)
