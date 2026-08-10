from __future__ import annotations

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.auth.security import new_id

from .models import PersonalMemo, PersonalTodoItem, utcnow_naive
from .schemas import PersonalMemoOut, PersonalTodoItemOut, PersonalTodoListResponse


TODO_SORT_STEP = 1000


def _project_todo(row: PersonalTodoItem) -> PersonalTodoItemOut:
    return PersonalTodoItemOut(
        id=row.id,
        title=row.title,
        completed=row.completed,
        sort_order=row.sort_order,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _load_todo(db: Session, *, user: User, todo_id: str) -> PersonalTodoItem:
    row = db.scalar(
        select(PersonalTodoItem).where(
            PersonalTodoItem.id == todo_id,
            PersonalTodoItem.user_id == user.id,
        )
    )
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="personal_widgets.todo_not_found",
        )
    return row


def list_todos(
    db: Session,
    *,
    user: User,
    include_completed: bool,
) -> PersonalTodoListResponse:
    query = select(PersonalTodoItem).where(PersonalTodoItem.user_id == user.id)
    if not include_completed:
        query = query.where(PersonalTodoItem.completed == False)  # noqa: E712
    rows = list(
        db.scalars(
            query.order_by(
                PersonalTodoItem.completed.asc(),
                PersonalTodoItem.sort_order.asc(),
                PersonalTodoItem.created_at.desc(),
            )
        )
    )
    return PersonalTodoListResponse(items=[_project_todo(row) for row in rows])


def create_todo(db: Session, *, user: User, title: str) -> PersonalTodoItemOut:
    max_sort_order = db.scalar(
        select(func.max(PersonalTodoItem.sort_order)).where(
            PersonalTodoItem.user_id == user.id
        )
    )
    row = PersonalTodoItem(
        id=new_id(),
        user_id=user.id,
        title=title,
        sort_order=(max_sort_order or 0) + TODO_SORT_STEP,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _project_todo(row)


def update_todo(
    db: Session,
    *,
    user: User,
    todo_id: str,
    title: str | None,
    completed: bool | None,
) -> PersonalTodoItemOut:
    row = _load_todo(db, user=user, todo_id=todo_id)
    if title is not None:
        row.title = title
    if completed is not None and completed != row.completed:
        row.completed = completed
        row.completed_at = utcnow_naive() if completed else None
    db.commit()
    db.refresh(row)
    return _project_todo(row)


def delete_todo(db: Session, *, user: User, todo_id: str) -> None:
    row = _load_todo(db, user=user, todo_id=todo_id)
    db.delete(row)
    db.commit()


def get_memo(db: Session, *, user: User) -> PersonalMemoOut:
    row = db.scalar(select(PersonalMemo).where(PersonalMemo.user_id == user.id))
    if row is None:
        return PersonalMemoOut(id=None, body="", created_at=None, updated_at=None)
    return PersonalMemoOut(
        id=row.id,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def save_memo(db: Session, *, user: User, body: str) -> PersonalMemoOut:
    row = db.scalar(select(PersonalMemo).where(PersonalMemo.user_id == user.id))
    if row is None:
        row = PersonalMemo(id=new_id(), user_id=user.id, body=body)
        db.add(row)
    else:
        row.body = body
    db.commit()
    db.refresh(row)
    return PersonalMemoOut(
        id=row.id,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
