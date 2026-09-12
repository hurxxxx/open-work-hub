from __future__ import annotations

from typing import Literal

from sqlalchemy.exc import IntegrityError

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.dependencies import AuthContext, require_permission
from open_work_hub_api.domains.auth.realtime import (
    publish_app_availability_access_changed,
    publish_principal_access_changed,
)
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.groups.hr import lock_group_hierarchy
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.groups import service
from open_work_hub_api.domains.groups.models import Group, GroupMember
from open_work_hub_api.domains.groups.schemas import (
    GroupCreateRequest,
    GroupListResponse,
    GroupMembersRequest,
    GroupMembersResponse,
    GroupMemberResponse,
    GroupMemberUpdateRequest,
    GroupResponse,
    GroupUpdateRequest,
)

router = APIRouter(prefix="/admin/groups", tags=["admin-groups"])


def _load(db: Session, group_id: str, *, write: bool = False) -> Group:
    try:
        group = service.load_group(db, group_id, for_update=write)
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
    after = _snapshot(group)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action=action,
        entity_kind="group",
        entity_id=group.id,
        summary=action,
        payload={"before": before, "after": after},
    )
    changed = {key for key in after if before is None or before[key] != after[key]}
    affected: set[str] = set()
    if group.source == "hr":
        if before is not None and changed.intersection({"name", "slug", "unit_type", "active"}):
            affected.update(
                db.scalars(select(User.id).where(User.primary_organization_unit_id == group.id))
            )
        if changed.intersection({"head_user_id", "active"}):
            affected.update(
                snapshot["head_user_id"]
                for snapshot in (before, after)
                if snapshot and snapshot["active"] and snapshot["head_user_id"]
            )
    elif before is not None and "active" in changed:
        affected.update(_stored_member_ids(db, group))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_groups_source_reference":
            code = "group.source_reference_exists"
        elif constraint in {"uq_groups_slug", "groups_slug_key"}:
            code = "organization.slug_exists"
        else:
            raise
        raise localized_http_exception(status_code=409, code=code) from error
    publisher = (
        publish_principal_access_changed
        if group.source == "hr"
        else publish_app_availability_access_changed
    )
    publisher(getattr(request.app.state, "app_realtime", None), affected)


def _snapshot(group: Group) -> dict:
    return {
        field: getattr(group, field)
        for field in (
            "name",
            "description",
            "source",
            "source_reference",
            "active",
            "slug",
            "unit_type",
            "parent_id",
            "head_user_id",
        )
    }


def _validate_metadata(db: Session, group: Group, changes: dict) -> dict:
    try:
        return service.validate_metadata(db, group, changes)
    except service.GroupError as error:
        db.rollback()
        raise localized_http_exception(status_code=error.status_code, code=error.code) from error


@router.get("", response_model=GroupListResponse)
def list_groups(
    q: str = Query(default="", max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    include_inactive: bool = False,
    source: Literal["local", "hr"] | None = None,
    member_user_id: str | None = Query(default=None, min_length=1, max_length=36),
    _context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupListResponse:
    return service.list_groups(
        db,
        query=q,
        page=page,
        page_size=page_size,
        include_inactive=include_inactive,
        source=source,
        member_user_id=member_user_id,
    )


@router.post("", response_model=GroupResponse, status_code=201)
def create_group(
    payload: GroupCreateRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupResponse:
    lock_group_hierarchy(db)
    group = Group(
        id=new_id(),
        source=payload.source,
        name=payload.name,
        description=payload.description,
        active=payload.active,
    )
    changes = _validate_metadata(
        db, group, payload.model_dump(exclude={"source"}, exclude_unset=True)
    )
    for field, value in changes.items():
        setattr(group, field, value)
    db.add(group)
    _commit(db, request, context, group, "admin.group.create")
    return service.serialize_group(group)


@router.patch("/{group_id}", response_model=GroupResponse)
def update_group(
    group_id: str,
    payload: GroupUpdateRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupResponse:
    lock_group_hierarchy(db)
    group = _load(db, group_id, write=True)
    before = _snapshot(group)
    changes = _validate_metadata(db, group, payload.model_dump(exclude_unset=True))
    for field, value in changes.items():
        setattr(group, field, value)
    _commit(db, request, context, group, "admin.group.update", before=before)
    return service.serialize_group(group)


@router.get("/{group_id}/members", response_model=GroupMembersResponse)
def get_members(
    group_id: str,
    _context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupMembersResponse:
    group = _load(db, group_id)
    return _serialize_members(db, group)


@router.put("/{group_id}/members/{user_id}", response_model=GroupMembersResponse)
def update_member(
    group_id: str,
    user_id: str,
    payload: GroupMemberUpdateRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> GroupMembersResponse:
    # Use the same group lock as full membership replacement; change only this user.
    group = _load(db, group_id, write=True)
    before = set(_stored_member_ids(db, group))
    after = before | {user_id} if payload.assigned else before - {user_id}
    return _replace_members(group, sorted(after), request, context, db)


def _serialize_members(db: Session, group: Group) -> GroupMembersResponse:
    ids = _stored_member_ids(db, group)
    users = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.display_name, User.id))
    return GroupMembersResponse(
        group_id=group.id,
        user_ids=ids,
        items=[GroupMemberResponse.model_validate(user, from_attributes=True) for user in users],
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
    return _replace_members(group, payload.user_ids, request, context, db)


def _replace_members(
    group: Group, user_ids: list[str], request: Request, context: AuthContext, db: Session
) -> GroupMembersResponse:
    before = {"user_ids": _stored_member_ids(db, group)}
    try:
        service.replace_manual_members(db, group, user_ids)
    except service.GroupError as error:
        raise localized_http_exception(status_code=error.status_code, code=error.code) from error
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.group.members.replace",
        entity_kind="group",
        entity_id=group.id,
        summary="Updated manual group members",
        payload={"before": before, "after": {"user_ids": sorted(set(user_ids))}},
    )
    affected = set(before["user_ids"]) ^ set(user_ids)
    db.commit()
    publish_app_availability_access_changed(
        getattr(request.app.state, "app_realtime", None), affected
    )
    return _serialize_members(db, group)


def _stored_member_ids(db: Session, group: Group) -> list[str]:
    if group.source == "local":
        return sorted(
            db.scalars(select(GroupMember.user_id).where(GroupMember.group_id == group.id))
        )
    return sorted(user.id for user in db.scalars(service.group_members_query(group)))
