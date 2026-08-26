from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.models import User, utcnow_naive
from open_work_hub_api.domains.integrations.platform_api_keys import (
    PlatformApiPrincipal,
    platform_api_scope_openapi,
    require_platform_api_scope,
)
from open_work_hub_api.domains.organization.models import OrganizationUnit


router = APIRouter(prefix="/integrations/directory", tags=["directory-integrations"])
require_organization_read = require_platform_api_scope("organization:read")
require_people_read = require_platform_api_scope("people:read")


class DirectoryOrganizationUnitResponse(BaseModel):
    id: str
    name: str
    slug: str
    unit_type: str
    parent_id: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class DirectoryPersonResponse(BaseModel):
    id: str
    login_id: str
    email: str
    full_name: str
    display_name: str
    employee_code: str | None
    job_title: str | None
    status: str
    primary_organization_unit_id: str | None
    created_at: datetime
    updated_at: datetime


class DirectoryOrganizationUnitsResponse(BaseModel):
    items: list[DirectoryOrganizationUnitResponse]
    total: int
    page: int
    page_size: int
    generated_at: datetime


class DirectoryPeopleResponse(BaseModel):
    items: list[DirectoryPersonResponse]
    total: int
    page: int
    page_size: int
    generated_at: datetime


def _set_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


def _audit_read(
    db: Session,
    *,
    principal: PlatformApiPrincipal,
    action: str,
    page: int,
    page_size: int,
    result_count: int,
) -> None:
    record_audit_log(
        db,
        actor_user_id=None,
        action=action,
        entity_kind="directory_integration",
        entity_id=None,
        summary="Read external directory projection",
        payload={
            "api_key_id": principal.key_id,
            "page": page,
            "page_size": page_size,
            "result_count": result_count,
            "outcome": "succeeded",
        },
    )
    db.commit()


@router.get(
    "/organization-units",
    response_model=DirectoryOrganizationUnitsResponse,
    openapi_extra=platform_api_scope_openapi("organization:read"),
)
def list_directory_organization_units(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    include_inactive: bool = Query(default=False),
    principal: PlatformApiPrincipal = Depends(require_organization_read),
    db: Session = Depends(get_db_session),
) -> DirectoryOrganizationUnitsResponse:
    _set_no_store_headers(response)
    filters = [] if include_inactive else [OrganizationUnit.active.is_(True)]
    total = db.scalar(select(func.count()).select_from(OrganizationUnit).where(*filters)) or 0
    items = list(
        db.scalars(
            select(OrganizationUnit)
            .where(*filters)
            .order_by(OrganizationUnit.name, OrganizationUnit.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    _audit_read(
        db,
        principal=principal,
        action="integration.directory.organization_units.read",
        page=page,
        page_size=page_size,
        result_count=len(items),
    )
    return DirectoryOrganizationUnitsResponse(
        items=[
            DirectoryOrganizationUnitResponse.model_validate(item, from_attributes=True)
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
        generated_at=utcnow_naive(),
    )


@router.get(
    "/people",
    response_model=DirectoryPeopleResponse,
    openapi_extra=platform_api_scope_openapi("people:read"),
)
def list_directory_people(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    include_inactive: bool = Query(default=False),
    principal: PlatformApiPrincipal = Depends(require_people_read),
    db: Session = Depends(get_db_session),
) -> DirectoryPeopleResponse:
    _set_no_store_headers(response)
    filters = [User.status != "system"]
    if not include_inactive:
        filters.append(User.status == "active")
    total = db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    people = list(
        db.scalars(
            select(User)
            .where(*filters)
            .order_by(User.full_name, User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    _audit_read(
        db,
        principal=principal,
        action="integration.directory.people.read",
        page=page,
        page_size=page_size,
        result_count=len(people),
    )
    return DirectoryPeopleResponse(
        items=[
            DirectoryPersonResponse(
                id=person.id,
                login_id=person.login_id,
                email=person.email,
                full_name=person.full_name,
                display_name=person.display_name or person.full_name,
                employee_code=person.employee_code,
                job_title=person.job_title,
                status=person.status,
                primary_organization_unit_id=person.primary_organization_unit_id,
                created_at=person.created_at,
                updated_at=person.updated_at,
            )
            for person in people
        ],
        total=total,
        page=page,
        page_size=page_size,
        generated_at=utcnow_naive(),
    )
