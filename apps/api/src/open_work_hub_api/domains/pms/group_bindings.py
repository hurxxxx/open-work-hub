from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.app_gate import require_app_access
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.realtime import publish_app_availability_access_changed
from open_work_hub_api.domains.groups.models import Group
from open_work_hub_api.domains.groups.service import active_group_predicate, serialize_group
from open_work_hub_api.domains.pms.access import (
    _ensure_space_access,
    _ensure_space_admin_change_allowed,
)
from open_work_hub_api.domains.pms.space_models import SpaceGroupBinding, Team

router = APIRouter(
    prefix="/pms/spaces", tags=["pms"], dependencies=[Depends(require_app_access("pms"))]
)


class SpaceGroupRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["viewer", "member", "admin"]


class SpaceGroupBindingResponse(SpaceGroupRoleRequest):
    group_id: str
    name: str
    active: bool


@router.get("/{space_id}/groups", response_model=list[SpaceGroupBindingResponse])
def list_space_groups(
    space_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
):
    _ensure_space_access(db, current_user, space_id)
    result = []
    for row, group in db.execute(
        select(SpaceGroupBinding, Group)
        .join(Group, Group.id == SpaceGroupBinding.group_id)
        .where(SpaceGroupBinding.team_id == space_id)
        .order_by(SpaceGroupBinding.group_id)
    ):
        entry = serialize_group(db, group)
        result.append(
            SpaceGroupBindingResponse(
                group_id=row.group_id, role=row.role, name=entry.name, active=entry.active
            )
        )
    return result


def _change_binding(
    db: Session, *, user: User, space_id: str, group_id: str, role: str | None
) -> None:
    db.execute(select(Team.id).where(Team.id == space_id).with_for_update()).scalar_one_or_none()
    row = db.get(SpaceGroupBinding, (space_id, group_id), populate_existing=True)
    _ensure_space_admin_change_allowed(
        db, user, space_id, current_role=row.role if row else None, next_role=role
    )
    before = row.role if row else None
    if role is not None:
        if (
            db.scalar(select(Group.id).where(Group.id == group_id, active_group_predicate()))
            is None
        ):
            raise localized_http_exception(status_code=404, code="group.not_found")
        if row is None:
            row = SpaceGroupBinding(team_id=space_id, group_id=group_id, role=role)
        else:
            row.role = role
        db.add(row)
    elif row is not None:
        db.delete(row)
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="pms.space.group.change",
        entity_kind="pms_space",
        entity_id=space_id,
        summary="Updated PMS space group role",
        payload={"group_id": group_id, "before": before, "after": role},
    )


def _commit_and_invalidate(db: Session, request: Request):
    affected = list(db.scalars(select(User.id)))
    db.commit()
    publish_app_availability_access_changed(
        getattr(request.app.state, "app_realtime", None), affected
    )


@router.put("/{space_id}/groups/{group_id}", response_model=SpaceGroupBindingResponse)
def put_space_group(
    space_id: str,
    group_id: str,
    payload: SpaceGroupRoleRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
):
    _change_binding(db, user=current_user, space_id=space_id, group_id=group_id, role=payload.role)
    _commit_and_invalidate(db, request)
    group = serialize_group(db, db.get(Group, group_id))
    return SpaceGroupBindingResponse(
        group_id=group_id, role=payload.role, name=group.name, active=group.active
    )


@router.delete("/{space_id}/groups/{group_id}", status_code=204)
def delete_space_group(
    space_id: str,
    group_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
):
    _change_binding(db, user=current_user, space_id=space_id, group_id=group_id, role=None)
    _commit_and_invalidate(db, request)
    return Response(status_code=204)
