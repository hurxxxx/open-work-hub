from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.pms.access import (
    _ensure_list_member,
    _ensure_list_owner,
    _ensure_space_access,
    _ensure_space_manager,
)
from open_work_hub_api.domains.pms.models import SpaceStatus, Task, TaskList, TaskListStatus
from open_work_hub_api.domains.pms.rag_sync import enqueue_task_list_task_recompute
from open_work_hub_api.domains.pms.status_lifecycle import (
    copy_space_statuses_to_task_list,
    ensure_space_statuses,
    ensure_task_list_custom_statuses,
)
from open_work_hub_api.domains.pms.workflow import (
    incompatible_statuses_for_inherit,
    normalize_status_category,
    status_slug,
    violates_single_closed_status_rule,
)
from open_work_hub_api.domains.search.hooks import enqueue_task_list_status_task_search_recompute

router = APIRouter()

StatusCategory = Literal["not_started", "active", "done", "closed"]


class TaskListStatusItem(BaseModel):
    id: str
    slug: str
    name: str
    color: str
    category: StatusCategory
    sort_order: int


class TaskListStatusesResponse(BaseModel):
    mode: Literal["inherit", "custom"] = "custom"
    source: Literal["space", "list"] = "list"
    items: list[TaskListStatusItem]


class SpaceStatusesResponse(BaseModel):
    items: list[TaskListStatusItem]


class TaskListStatusCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    color: str = Field(default="#6b7280", max_length=24)
    category: StatusCategory = "active"
    sort_order: int = 0


class TaskListStatusUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, max_length=24)
    category: StatusCategory | None = None
    sort_order: int | None = None


class TaskListStatusModeUpdateRequest(BaseModel):
    mode: Literal["inherit", "custom"]


def _serialize_status(s: TaskListStatus | SpaceStatus) -> TaskListStatusItem:
    return TaskListStatusItem(
        id=s.id,
        slug=s.slug,
        name=s.name,
        color=s.color,
        category=normalize_status_category(s.category),
        sort_order=s.sort_order,
    )


def _ensure_closed_status_rule(
    statuses: list[TaskListStatus | SpaceStatus],
    *,
    next_category: str,
    exclude_id: str | None = None,
) -> None:
    if violates_single_closed_status_rule(
        statuses,
        next_category=next_category,
        exclude_id=exclude_id,
    ):
        raise localized_http_exception(status_code=409, code="pms.closed_status_single")


@router.get("/lists/{list_id}/statuses", response_model=TaskListStatusesResponse)
def list_task_list_statuses(
    list_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListStatusesResponse:
    task_list, _ = _ensure_list_member(db, current_user, list_id)
    if task_list.status_mode == "inherit" and task_list.team_id:
        statuses = ensure_space_statuses(db, task_list.team_id)
        db.commit()
        return TaskListStatusesResponse(
            mode="inherit",
            source="space",
            items=[_serialize_status(s) for s in statuses],
        )
    statuses = ensure_task_list_custom_statuses(db, task_list)
    db.commit()
    return TaskListStatusesResponse(
        mode="custom",
        source="list",
        items=[_serialize_status(s) for s in statuses],
    )


@router.patch("/lists/{list_id}/status-mode", response_model=TaskListStatusesResponse)
def update_task_list_status_mode(
    list_id: str,
    payload: TaskListStatusModeUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListStatusesResponse:
    task_list, _role = _ensure_list_owner(db, current_user, list_id)
    if payload.mode == "inherit":
        if not task_list.team_id:
            raise localized_http_exception(
                status_code=409, code="pms.status_inherit_requires_space"
            )
        space_statuses = ensure_space_statuses(db, task_list.team_id)
        used_statuses = {
            status_value
            for status_value in db.scalars(
                select(Task.status).where(Task.list_id == task_list.id).distinct()
            )
        }
        incompatible = incompatible_statuses_for_inherit(
            used_statuses,
            (status.slug for status in space_statuses),
        )
        if incompatible:
            raise localized_http_exception(
                status_code=409,
                code="pms.status_mode_incompatible",
                statuses=", ".join(incompatible),
            )
        task_list.status_mode = "inherit"
        db.commit()
        return TaskListStatusesResponse(
            mode="inherit",
            source="space",
            items=[_serialize_status(s) for s in space_statuses],
        )

    statuses = copy_space_statuses_to_task_list(db, task_list)
    task_list.status_mode = "custom"
    db.commit()
    return TaskListStatusesResponse(
        mode="custom",
        source="list",
        items=[_serialize_status(s) for s in statuses],
    )


@router.get("/spaces/{space_id}/statuses", response_model=SpaceStatusesResponse)
def list_space_statuses(
    space_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceStatusesResponse:
    _ensure_space_access(db, current_user, space_id)
    statuses = ensure_space_statuses(db, space_id)
    db.commit()
    return SpaceStatusesResponse(items=[_serialize_status(s) for s in statuses])


@router.post(
    "/spaces/{space_id}/statuses",
    response_model=TaskListStatusItem,
    status_code=status.HTTP_201_CREATED,
)
def create_space_status(
    space_id: str,
    payload: TaskListStatusCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListStatusItem:
    _ensure_space_manager(db, current_user, space_id)
    statuses = ensure_space_statuses(db, space_id)
    category = normalize_status_category(payload.category)
    _ensure_closed_status_rule(statuses, next_category=category)
    slug = status_slug(payload.name)
    existing = db.scalar(
        select(SpaceStatus).where(
            SpaceStatus.team_id == space_id,
            SpaceStatus.slug == slug,
        )
    )
    if existing is not None:
        raise localized_http_exception(status_code=409, code="pms.status_name_exists")
    ps = SpaceStatus(
        id=new_id(),
        team_id=space_id,
        slug=slug,
        name=payload.name.strip(),
        color=payload.color,
        category=category,
        sort_order=payload.sort_order,
    )
    db.add(ps)
    for task_list in db.scalars(
        select(TaskList).where(TaskList.team_id == space_id, TaskList.status_mode == "inherit")
    ):
        enqueue_task_list_task_recompute(db, task_list=task_list)
    db.commit()
    db.refresh(ps)
    return _serialize_status(ps)


@router.patch("/space-statuses/{status_id}", response_model=TaskListStatusItem)
def update_space_status(
    status_id: str,
    payload: TaskListStatusUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListStatusItem:
    ps = db.scalar(select(SpaceStatus).where(SpaceStatus.id == status_id))
    if ps is None:
        raise localized_http_exception(status_code=404, code="pms.status_not_found")
    _ensure_space_manager(db, current_user, ps.team_id)
    statuses = ensure_space_statuses(db, ps.team_id)
    next_category = normalize_status_category(payload.category or ps.category)
    _ensure_closed_status_rule(statuses, next_category=next_category, exclude_id=ps.id)

    if payload.name is not None:
        normalized_name = payload.name.strip()
        existing = db.scalar(
            select(SpaceStatus).where(
                SpaceStatus.team_id == ps.team_id,
                SpaceStatus.id != ps.id,
                func.lower(SpaceStatus.name) == normalized_name.lower(),
            )
        )
        if existing is not None:
            raise localized_http_exception(status_code=409, code="pms.status_name_exists")
        ps.name = normalized_name
    if payload.color is not None:
        ps.color = payload.color
    if payload.category is not None:
        ps.category = next_category
    if payload.sort_order is not None:
        ps.sort_order = payload.sort_order

    for task_list in db.scalars(
        select(TaskList).where(TaskList.team_id == ps.team_id, TaskList.status_mode == "inherit")
    ):
        enqueue_task_list_task_recompute(db, task_list=task_list)
    db.commit()
    db.refresh(ps)
    return _serialize_status(ps)


@router.delete("/space-statuses/{status_id}")
def delete_space_status(
    status_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    ps = db.scalar(select(SpaceStatus).where(SpaceStatus.id == status_id))
    if ps is None:
        raise localized_http_exception(status_code=404, code="pms.status_not_found")
    _ensure_space_manager(db, current_user, ps.team_id)
    if normalize_status_category(ps.category) == "closed":
        raise localized_http_exception(status_code=409, code="pms.closed_status_required")
    count = db.scalar(
        select(func.count())
        .select_from(Task)
        .join(TaskList, TaskList.id == Task.list_id)
        .where(
            TaskList.team_id == ps.team_id,
            TaskList.status_mode == "inherit",
            Task.status == ps.slug,
        )
    )
    if count and count > 0:
        raise localized_http_exception(
            status_code=409,
            code="pms.status_in_use",
            count=count,
        )
    db.delete(ps)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/lists/{list_id}/statuses",
    response_model=TaskListStatusItem,
    status_code=status.HTTP_201_CREATED,
)
def create_task_list_status(
    list_id: str,
    payload: TaskListStatusCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListStatusItem:
    task_list, _role = _ensure_list_owner(db, current_user, list_id)
    if task_list.status_mode != "custom":
        copy_space_statuses_to_task_list(db, task_list)
        task_list.status_mode = "custom"
        db.flush()
    statuses = ensure_task_list_custom_statuses(db, task_list)
    category = normalize_status_category(payload.category)
    _ensure_closed_status_rule(statuses, next_category=category)
    slug = status_slug(payload.name)
    existing = db.scalar(
        select(TaskListStatus).where(
            TaskListStatus.list_id == list_id,
            TaskListStatus.slug == slug,
        )
    )
    if existing is not None:
        raise localized_http_exception(status_code=409, code="pms.status_name_exists")

    ps = TaskListStatus(
        id=new_id(),
        list_id=list_id,
        slug=slug,
        name=payload.name.strip(),
        color=payload.color,
        category=category,
        sort_order=payload.sort_order,
    )
    db.add(ps)
    enqueue_task_list_status_task_search_recompute(db, task_status=ps)
    db.commit()
    db.refresh(ps)
    return _serialize_status(ps)


@router.patch("/task-list-statuses/{status_id}", response_model=TaskListStatusItem)
def update_task_list_status(
    status_id: str,
    payload: TaskListStatusUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListStatusItem:
    ps = db.scalar(select(TaskListStatus).where(TaskListStatus.id == status_id))
    if ps is None:
        raise localized_http_exception(status_code=404, code="pms.status_not_found")
    task_list, _role = _ensure_list_owner(db, current_user, ps.list_id)
    statuses = ensure_task_list_custom_statuses(db, task_list)
    next_category = normalize_status_category(payload.category or ps.category)
    _ensure_closed_status_rule(statuses, next_category=next_category, exclude_id=ps.id)

    if payload.name is not None:
        normalized_name = payload.name.strip()
        existing = db.scalar(
            select(TaskListStatus).where(
                TaskListStatus.list_id == ps.list_id,
                TaskListStatus.id != ps.id,
                func.lower(TaskListStatus.name) == normalized_name.lower(),
            )
        )
        if existing is not None:
            raise localized_http_exception(status_code=409, code="pms.status_name_exists")
        ps.name = normalized_name
    if payload.color is not None:
        ps.color = payload.color
    if payload.category is not None:
        ps.category = next_category
    if payload.sort_order is not None:
        ps.sort_order = payload.sort_order

    enqueue_task_list_status_task_search_recompute(db, task_status=ps)
    db.commit()
    db.refresh(ps)
    return _serialize_status(ps)


@router.delete("/task-list-statuses/{status_id}")
def delete_task_list_status(
    status_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    ps = db.scalar(select(TaskListStatus).where(TaskListStatus.id == status_id))
    if ps is None:
        raise localized_http_exception(status_code=404, code="pms.status_not_found")
    _ensure_list_owner(db, current_user, ps.list_id)
    if normalize_status_category(ps.category) == "closed":
        raise localized_http_exception(status_code=409, code="pms.closed_status_required")

    count = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.list_id == ps.list_id, Task.status == ps.slug)
    )
    if count and count > 0:
        raise localized_http_exception(
            status_code=409,
            code="pms.status_in_use",
            count=count,
        )

    db.delete(ps)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
