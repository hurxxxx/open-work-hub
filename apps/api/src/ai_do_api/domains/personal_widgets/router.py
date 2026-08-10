from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.domains.auth.dependencies import require_current_user
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.pms.service import list_personal_widget_assigned_tasks

from .schemas import (
    PersonalMemoOut,
    PersonalMemoUpdateRequest,
    PersonalPmsAssignedTasksResponse,
    PersonalTodoCreateRequest,
    PersonalTodoItemOut,
    PersonalTodoListResponse,
    PersonalTodoUpdateRequest,
)
from .service import create_todo, delete_todo, get_memo, list_todos, save_memo, update_todo


router = APIRouter(prefix="/personal-widgets", tags=["personal-widgets"])


@router.get("/pms/tasks/assigned", response_model=PersonalPmsAssignedTasksResponse)
def list_personal_pms_assigned_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PersonalPmsAssignedTasksResponse:
    return PersonalPmsAssignedTasksResponse.model_validate(
        list_personal_widget_assigned_tasks(
            db,
            user=current_user,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/todos", response_model=PersonalTodoListResponse)
def list_personal_todos(
    include_completed: bool = Query(default=True),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PersonalTodoListResponse:
    return list_todos(db, user=current_user, include_completed=include_completed)


@router.post(
    "/todos",
    response_model=PersonalTodoItemOut,
    status_code=status.HTTP_201_CREATED,
)
def create_personal_todo(
    payload: PersonalTodoCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PersonalTodoItemOut:
    return create_todo(db, user=current_user, title=payload.title)


@router.patch("/todos/{todo_id}", response_model=PersonalTodoItemOut)
def update_personal_todo(
    todo_id: str,
    payload: PersonalTodoUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PersonalTodoItemOut:
    return update_todo(
        db,
        user=current_user,
        todo_id=todo_id,
        title=payload.title,
        completed=payload.completed,
    )


@router.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_personal_todo(
    todo_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    delete_todo(db, user=current_user, todo_id=todo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/memo", response_model=PersonalMemoOut)
def get_personal_memo(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PersonalMemoOut:
    return get_memo(db, user=current_user)


@router.put("/memo", response_model=PersonalMemoOut)
def save_personal_memo(
    payload: PersonalMemoUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PersonalMemoOut:
    return save_memo(db, user=current_user, body=payload.body)
