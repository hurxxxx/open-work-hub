from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.dependencies import AuthContext, require_permission
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.organization.models import OrganizationUnit
from open_work_hub_api.domains.organization.schemas import (
    OrganizationUnitCreateRequest,
    OrganizationUnitResponse,
    OrganizationUnitUpdateRequest,
)
from open_work_hub_api.domains.organization.service import (
    OrganizationDirectoryError,
    ensure_unique_slug,
    ensure_valid_parent,
    load_organization_unit,
    organization_slug,
    serialize_organization_unit,
)


router = APIRouter(prefix="/admin/organization-units", tags=["admin-organization"])


def _raise_organization_error(
    db: Session,
    error: OrganizationDirectoryError,
) -> NoReturn:
    db.rollback()
    status_by_code = {
        "organization.unit_not_found": status.HTTP_404_NOT_FOUND,
        "organization.unit_inactive": status.HTTP_409_CONFLICT,
        "organization.slug_exists": status.HTTP_409_CONFLICT,
        "organization.cycle_detected": status.HTTP_409_CONFLICT,
    }
    raise localized_http_exception(
        status_code=status_by_code.get(error.code, status.HTTP_400_BAD_REQUEST),
        code=error.code,
    ) from error


def _commit_or_slug_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        _raise_organization_error(
            db,
            OrganizationDirectoryError("organization.slug_exists"),
        )
        raise AssertionError("unreachable") from error


@router.get("", response_model=list[OrganizationUnitResponse])
def list_organization_units(
    include_inactive: bool = Query(default=False),
    _context: AuthContext = Depends(require_permission("organization.read")),
    db: Session = Depends(get_db_session),
) -> list[OrganizationUnitResponse]:
    statement = select(OrganizationUnit)
    if not include_inactive:
        statement = statement.where(OrganizationUnit.active.is_(True))
    items = list(db.scalars(statement.order_by(OrganizationUnit.name, OrganizationUnit.id)).all())
    return [
        OrganizationUnitResponse.model_validate(serialize_organization_unit(item)) for item in items
    ]


@router.post("", response_model=OrganizationUnitResponse, status_code=status.HTTP_201_CREATED)
def create_organization_unit(
    payload: OrganizationUnitCreateRequest,
    context: AuthContext = Depends(require_permission("organization.write")),
    db: Session = Depends(get_db_session),
) -> OrganizationUnitResponse:
    slug = organization_slug(payload.slug or payload.name)
    try:
        ensure_unique_slug(db, slug)
        ensure_valid_parent(db, organization_unit_id=None, parent_id=payload.parent_id)
    except OrganizationDirectoryError as error:
        _raise_organization_error(db, error)

    item = OrganizationUnit(
        id=new_id(),
        name=payload.name.strip(),
        slug=slug,
        unit_type=payload.unit_type,
        parent_id=payload.parent_id,
        active=payload.active,
    )
    db.add(item)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.organization_unit.create",
        entity_kind="organization_unit",
        entity_id=item.id,
        summary=f"Created organization unit {item.name}",
        payload={"parent_id": item.parent_id, "unit_type": item.unit_type},
    )
    _commit_or_slug_conflict(db)
    db.refresh(item)
    return OrganizationUnitResponse.model_validate(serialize_organization_unit(item))


@router.patch("/{organization_unit_id}", response_model=OrganizationUnitResponse)
def update_organization_unit(
    organization_unit_id: str,
    payload: OrganizationUnitUpdateRequest,
    context: AuthContext = Depends(require_permission("organization.write")),
    db: Session = Depends(get_db_session),
) -> OrganizationUnitResponse:
    try:
        item = load_organization_unit(db, organization_unit_id, for_update=True)
        next_parent_id = (
            payload.parent_id if "parent_id" in payload.model_fields_set else item.parent_id
        )
        ensure_valid_parent(
            db,
            organization_unit_id=item.id,
            parent_id=next_parent_id,
        )
        if payload.slug is not None:
            next_slug = organization_slug(payload.slug)
            ensure_unique_slug(db, next_slug, exclude_id=item.id)
            item.slug = next_slug
    except OrganizationDirectoryError as error:
        _raise_organization_error(db, error)

    if payload.name is not None:
        item.name = payload.name.strip()
    if payload.unit_type is not None:
        item.unit_type = payload.unit_type
    if "parent_id" in payload.model_fields_set:
        item.parent_id = payload.parent_id
    if payload.active is not None:
        item.active = payload.active
    db.add(item)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.organization_unit.update",
        entity_kind="organization_unit",
        entity_id=item.id,
        summary=f"Updated organization unit {item.name}",
        payload={"changed_fields": sorted(payload.model_fields_set)},
    )
    _commit_or_slug_conflict(db)
    db.refresh(item)
    return OrganizationUnitResponse.model_validate(serialize_organization_unit(item))
