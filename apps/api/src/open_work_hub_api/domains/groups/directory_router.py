from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.groups.schemas import (
    CompanyDirectoryPeopleResponse,
    CompanyDirectoryPersonResponse,
    GroupListResponse,
)
from open_work_hub_api.domains.groups.service import list_groups, managed_organization_ids

router = APIRouter(
    prefix="/directory", tags=["directory"], dependencies=[Depends(require_current_user)]
)


@router.get("/groups", response_model=GroupListResponse)
def groups(
    q: str = Query(default="", max_length=120),
    ids: list[str] | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> GroupListResponse:
    return list_groups(db, query=q, page=page, page_size=page_size, ids=ids)


@router.get("/people", response_model=CompanyDirectoryPeopleResponse)
def people(
    q: str = Query(default="", max_length=120),
    ids: list[str] | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    organization_unit_id: str | None = None,
    db: Session = Depends(get_db_session),
) -> CompanyDirectoryPeopleResponse:
    statement = select(User).where(User.status == "active", User.login_blocked.is_(False))
    if ids is not None:
        statement = statement.where(User.id.in_(ids))
    if q.strip():
        statement = statement.where(
            or_(
                User.full_name.icontains(q.strip(), autoescape=True),
                User.display_name.icontains(q.strip(), autoescape=True),
            )
        )
    if organization_unit_id:
        statement = statement.where(User.primary_organization_unit_id == organization_unit_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = []
    for user in db.scalars(
        statement.order_by(User.full_name, User.id).offset((page - 1) * page_size).limit(page_size)
    ):
        managed = managed_organization_ids(db, user.id)
        items.append(
            CompanyDirectoryPersonResponse(
                id=user.id,
                display_name=user.display_name or user.full_name,
                primary_organization_unit_id=user.primary_organization_unit_id,
                job_title=user.job_title,
                managed_organization_unit_ids=managed,
                is_department_head=bool(managed),
            )
        )
    return CompanyDirectoryPeopleResponse(items=items, total=total, page=page, page_size=page_size)
