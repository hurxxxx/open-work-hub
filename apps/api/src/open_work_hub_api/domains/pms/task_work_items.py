from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.pms.access import _ensure_list_editor
from open_work_hub_api.domains.pms.models import ChecklistItem, Task
from open_work_hub_api.domains.pms.service import _get_task_for_user, _log_task_activity


@dataclass(frozen=True)
class ChecklistItemDTO:
    id: str
    task_id: str
    text: str
    completed: bool
    sort_order: int
    created_at: datetime


def _checklist_item_dto(item: ChecklistItem) -> ChecklistItemDTO:
    return ChecklistItemDTO(
        id=item.id,
        task_id=item.task_id,
        text=item.text,
        completed=item.completed,
        sort_order=item.sort_order,
        created_at=item.created_at,
    )

def create_checklist_item(
    db: Session,
    *,
    user: User,
    task_id: str,
    text: str,
    sort_order: int,
) -> ChecklistItemDTO:
    task, _task_list = _get_task_for_user(db, user, task_id, require_editor=True)
    item = ChecklistItem(
        id=new_id(),
        task_id=task.id,
        text=text,
        sort_order=sort_order,
    )
    db.add(item)
    _log_task_activity(
        db,
        task.id,
        user.id,
        "checklist_added",
        f"{user.full_name} added checklist item.",
    )
    db.commit()
    db.refresh(item)
    return _checklist_item_dto(item)


def update_checklist_item(
    db: Session,
    *,
    user: User,
    item_id: str,
    text: str | None = None,
    completed: bool | None = None,
    sort_order: int | None = None,
) -> ChecklistItemDTO:
    item = db.scalar(
        select(ChecklistItem)
        .options(selectinload(ChecklistItem.task).selectinload(Task.task_list))
        .where(ChecklistItem.id == item_id)
    )
    if item is None:
        raise localized_http_exception(status_code=404, code="pms.checklist_item_not_found")
    _ensure_list_editor(db, user, item.task.list_id)

    if text is not None:
        item.text = text
    if completed is not None and completed != item.completed:
        item.completed = completed
        action = "checklist_checked" if completed else "checklist_unchecked"
        _log_task_activity(
            db,
            item.task_id,
            user.id,
            action,
            f'{user.full_name} {"checked" if completed else "unchecked"} "{item.text}".',
        )
    if sort_order is not None:
        item.sort_order = sort_order

    db.commit()
    db.refresh(item)
    return _checklist_item_dto(item)


def delete_checklist_item(
    db: Session,
    *,
    user: User,
    item_id: str,
) -> None:
    item = db.scalar(
        select(ChecklistItem)
        .options(selectinload(ChecklistItem.task).selectinload(Task.task_list))
        .where(ChecklistItem.id == item_id)
    )
    if item is None:
        raise localized_http_exception(status_code=404, code="pms.checklist_item_not_found")
    _ensure_list_editor(db, user, item.task.list_id)
    _log_task_activity(
        db,
        item.task_id,
        user.id,
        "checklist_removed",
        f'{user.full_name} removed checklist item "{item.text}".',
    )
    db.delete(item)
    db.commit()


def reorder_checklist(
    db: Session,
    *,
    user: User,
    task_id: str,
    item_ids: list[str],
) -> None:
    _get_task_for_user(db, user, task_id, require_editor=True)
    items = list(db.scalars(select(ChecklistItem).where(ChecklistItem.task_id == task_id)))
    item_map = {item.id: item for item in items}
    for idx, item_id in enumerate(item_ids):
        if item_id in item_map:
            item_map[item_id].sort_order = idx
    db.commit()
