from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.app_access_models import (
    AppAccessPolicy,
    AppGroupGrant,
    AppUserGrant,
)
from open_work_hub_api.domains.auth.app_catalog import get_app_catalog_item
from open_work_hub_api.domains.auth.dependencies import AuthContext, require_permission
from open_work_hub_api.domains.auth.models import CompanyAppControl, User
from open_work_hub_api.domains.auth.realtime import publish_app_availability_access_changed
from open_work_hub_api.domains.groups.models import Group
from open_work_hub_api.domains.groups.service import active_group_predicate

router = APIRouter(prefix="/admin/apps", tags=["admin-app-access"])


class AppAccessPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    audience: Literal["all", "selected"]
    user_ids: list[str] = Field(default_factory=list, max_length=10000)
    group_ids: list[str] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def validate_selectors(self):
        if self.audience == "all" and (self.user_ids or self.group_ids):
            raise ValueError("An all-users audience cannot include selected principals.")
        return self


class AppAccessPolicyResponse(AppAccessPolicyRequest):
    app_id: str


def _ensure_app(app_id: str) -> None:
    if get_app_catalog_item(app_id) is None:
        raise localized_http_exception(status_code=404, code="app.not_found")


def _read_policy(db: Session, app_id: str) -> AppAccessPolicyResponse:
    control = db.get(CompanyAppControl, app_id)
    audience = db.scalar(select(AppAccessPolicy.audience).where(AppAccessPolicy.app_id == app_id))
    return AppAccessPolicyResponse(
        app_id=app_id,
        enabled=bool(control and control.enabled),
        audience=audience if audience in {"all", "selected"} else "selected",
        user_ids=sorted(
            db.scalars(select(AppUserGrant.user_id).where(AppUserGrant.app_id == app_id))
        ),
        group_ids=sorted(
            db.scalars(select(AppGroupGrant.group_id).where(AppGroupGrant.app_id == app_id))
        ),
    )


@router.get("/{app_id}/access-policy", response_model=AppAccessPolicyResponse)
def get_policy(
    app_id: str,
    _context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> AppAccessPolicyResponse:
    _ensure_app(app_id)
    return _read_policy(db, app_id)


@router.put("/{app_id}/access-policy", response_model=AppAccessPolicyResponse)
def replace_policy(
    app_id: str,
    payload: AppAccessPolicyRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> AppAccessPolicyResponse:
    _ensure_app(app_id)
    db.execute(
        insert(CompanyAppControl).values(app_id=app_id, enabled=False).on_conflict_do_nothing()
    )
    control = db.scalar(
        select(CompanyAppControl).where(CompanyAppControl.app_id == app_id).with_for_update()
    )
    assert control is not None
    before = _read_policy(db, app_id).model_dump()
    requested_users, requested_groups = set(payload.user_ids), set(payload.group_ids)
    valid_users = set(
        db.scalars(
            select(User.id).where(
                User.id.in_(requested_users), User.status == "active", User.login_blocked.is_(False)
            )
        )
    )
    valid_groups = set(
        db.scalars(select(Group.id).where(Group.id.in_(requested_groups), active_group_predicate()))
    )
    if not requested_users.issubset(
        valid_users | set(before["user_ids"])
    ) or not requested_groups.issubset(valid_groups | set(before["group_ids"])):
        raise localized_http_exception(status_code=400, code="app.invalid_audience")
    control.enabled, control.updated_by_user_id = payload.enabled, context.user.id
    db.execute(
        insert(AppAccessPolicy)
        .values(app_id=app_id, audience=payload.audience)
        .on_conflict_do_update(
            index_elements=[AppAccessPolicy.app_id], set_={"audience": payload.audience}
        )
    )
    db.execute(delete(AppUserGrant).where(AppUserGrant.app_id == app_id))
    db.execute(delete(AppGroupGrant).where(AppGroupGrant.app_id == app_id))
    db.add_all(AppUserGrant(app_id=app_id, user_id=user_id) for user_id in sorted(requested_users))
    db.add_all(
        AppGroupGrant(app_id=app_id, group_id=group_id) for group_id in sorted(requested_groups)
    )
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.app.access_policy.replace",
        entity_kind="app",
        entity_id=app_id,
        summary="Updated app access policy",
        payload={
            "before": before,
            "enabled": payload.enabled,
            "audience": payload.audience,
            "user_ids": sorted(requested_users),
            "group_ids": sorted(requested_groups),
        },
    )
    affected = list(db.scalars(select(User.id).where(User.status == "active")))
    db.commit()
    publish_app_availability_access_changed(
        getattr(request.app.state, "app_realtime", None), affected
    )
    return _read_policy(db, app_id)
