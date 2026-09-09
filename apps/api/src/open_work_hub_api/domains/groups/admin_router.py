from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.dependencies import AuthContext, require_permission
from open_work_hub_api.domains.auth.realtime import publish_app_availability_access_changed
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.groups import service
from open_work_hub_api.domains.groups.models import Group, GroupMember
from open_work_hub_api.domains.groups.schemas import (
    GroupCreateRequest,
    GroupListResponse,
    GroupMembersRequest,
    GroupMembersResponse,
    GroupResponse,
    GroupUpdateRequest,
)

router = APIRouter(prefix="/admin/groups", tags=["admin-groups"])


def _load(db: Session, group_id: str, *, write: bool = False) -> Group:
    try:
        group = service.load_group(db, group_id, for_update=write)
        if write:
            service.require_manual_group(group)
        return group
    except service.GroupError as error:
        raise localized_http_exception(status_code=error.status_code, code=error.code) from error


def _commit(
    db: Session,
    request: Request,
    context: AuthContext,
    group: Group,
    action: str,
    *,
    before: dict | None = None,
) -> None:
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action=action,
        entity_kind="group",
        entity_id=group.id,
        summary=action,
        payload={
            "before": before,
            "after": {"name": group.name, "description": group.description, "active": group.active},
        },
    )
    affected = (
        _stored_member_ids(db, group)
        if before is not None and before["active"] != group.active
        else []
    )
    db.commit()
    publish_app_availability_access_changed(
        getattr(request.app.state, "app_realtime", None), affected
    )


@router.get("", response_model=GroupListResponse)
def list_groups(
    q: str = Query(default="", max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    include_inactive: bool = False,
    _context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupListResponse:
    return service.list_groups(
        db, query=q, page=page, page_size=page_size, include_inactive=include_inactive
    )


@router.post("", response_model=GroupResponse, status_code=201)
def create_group(
    payload: GroupCreateRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupResponse:
    group = Group(id=new_id(), kind="manual", name=payload.name, description=payload.description)
    db.add(group)
    _commit(db, request, context, group, "admin.group.create")
    return service.serialize_group(db, group)


@router.patch("/{group_id}", response_model=GroupResponse)
def update_group(
    group_id: str,
    payload: GroupUpdateRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupResponse:
    group = _load(db, group_id, write=True)
    before = {"name": group.name, "description": group.description, "active": group.active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, field, value)
    _commit(db, request, context, group, "admin.group.update", before=before)
    return service.serialize_group(db, group)


@router.get("/{group_id}/members", response_model=GroupMembersResponse)
def get_members(
    group_id: str,
    _context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupMembersResponse:
    group = _load(db, group_id)
    return GroupMembersResponse(
        group_id=group.id,
        user_ids=_stored_member_ids(db, group),
    )


@router.put("/{group_id}/members", response_model=GroupMembersResponse)
def replace_members(
    group_id: str,
    payload: GroupMembersRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupMembersResponse:
    group = _load(db, group_id, write=True)
    before = {"user_ids": _stored_member_ids(db, group)}
    try:
        service.replace_manual_members(db, group, payload.user_ids)
    except service.GroupError as error:
        raise localized_http_exception(status_code=error.status_code, code=error.code) from error
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.group.members.replace",
        entity_kind="group",
        entity_id=group.id,
        summary="Updated manual group members",
        payload={"before": before, "after": {"user_ids": sorted(set(payload.user_ids))}},
    )
    affected = set(before["user_ids"]) ^ set(payload.user_ids)
    db.commit()
    publish_app_availability_access_changed(
        getattr(request.app.state, "app_realtime", None), affected
    )
    return GroupMembersResponse(group_id=group.id, user_ids=sorted(set(payload.user_ids)))


def _stored_member_ids(db: Session, group: Group) -> list[str]:
    if group.kind == "manual":
        return sorted(
            db.scalars(select(GroupMember.user_id).where(GroupMember.group_id == group.id))
        )
    return sorted(user.id for user in db.scalars(service.group_members_query(group)))
