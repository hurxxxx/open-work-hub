from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.app_gate import require_app_access
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.docs.realtime_protocol import publish_doc_access_changed
from open_work_hub_api.domains.groups.models import Group
from open_work_hub_api.domains.groups.service import active_group_predicate, serialize_group
from open_work_hub_api.domains.docs.models import NativeDoc, NativeDocGroupShare
from open_work_hub_api.domains.docs.access_context import (
    native_doc_from_item_or_404,
    normalize_doc_id,
)

router = APIRouter(
    prefix="/docs/items", tags=["docs"], dependencies=[Depends(require_app_access("docs"))]
)


class DocGroupShareRequest(BaseModel):
    access_level: Literal["read", "edit"]


class DocGroupShareResponse(BaseModel):
    group_id: str
    name: str
    active: bool
    access_level: Literal["read", "edit"]


def _resource(db: Session, item_id: str, user: User, *, write: bool = False) -> NativeDoc:
    if write:
        db.scalar(
            select(NativeDoc)
            .where(NativeDoc.id == normalize_doc_id(item_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    resource, access = native_doc_from_item_or_404(db, item_id, user, share_token=None)
    if not access.can_share:
        raise localized_http_exception(status_code=403, code="docs.doc_share_access_required")
    return resource


def _changed(
    db: Session,
    request: Request,
    user: User,
    resource: NativeDoc,
    group_id: str,
    before: str | None,
    after: str | None,
) -> None:
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="docs.group_share.update",
        entity_kind="docs",
        entity_id=resource.id,
        summary="Updated content group sharing",
        payload={"group_id": group_id, "before": before, "after": after},
    )
    from open_work_hub_api.domains.docs.rag_sync import enqueue_native_doc_rag_sync
    from open_work_hub_api.domains.rag.contracts import RagSyncOperation

    enqueue_native_doc_rag_sync(db, doc=resource, operation=RagSyncOperation.UPSERT)
    db.commit()
    publish_doc_access_changed(getattr(request.app.state, "app_realtime", None), resource.id)


@router.get("/{item_id}/sharing/groups", response_model=list[DocGroupShareResponse])
def list_group_shares(
    item_id: str, db: Session = Depends(get_db_session), user: User = Depends(require_current_user)
):
    resource = _resource(db, item_id, user)
    rows = db.execute(
        select(NativeDocGroupShare, Group)
        .join(Group, Group.id == NativeDocGroupShare.group_id)
        .where(NativeDocGroupShare.doc_id == resource.id)
        .order_by(Group.id)
    )
    result = []
    for share, group in rows:
        entry = serialize_group(group)
        result.append(
            DocGroupShareResponse(
                group_id=group.id,
                name=entry.name,
                active=entry.active,
                access_level=share.access_level,
            )
        )
    return result


@router.put("/{item_id}/sharing/groups/{group_id}", response_model=DocGroupShareResponse)
def upsert_group_share(
    item_id: str,
    group_id: str,
    payload: DocGroupShareRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_current_user),
):
    resource = _resource(db, item_id, user, write=True)
    group = db.scalar(select(Group).where(Group.id == group_id, active_group_predicate()))
    if group is None:
        raise localized_http_exception(status_code=404, code="group.not_found")
    entry = serialize_group(group)
    share = db.get(NativeDocGroupShare, (resource.id, group_id))
    before = share.access_level if share else None
    if share is None:
        share = NativeDocGroupShare(doc_id=resource.id, group_id=group_id, created_by_id=user.id)
        db.add(share)
    share.access_level = payload.access_level
    _changed(db, request, user, resource, group_id, before, payload.access_level)
    return DocGroupShareResponse(
        group_id=group_id, name=entry.name, active=entry.active, access_level=payload.access_level
    )


@router.delete("/{item_id}/sharing/groups/{group_id}", status_code=204)
def delete_group_share(
    item_id: str,
    group_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_current_user),
):
    resource = _resource(db, item_id, user, write=True)
    share = db.get(NativeDocGroupShare, (resource.id, group_id))
    if share is not None:
        before = share.access_level
        db.delete(share)
        _changed(db, request, user, resource, group_id, before, None)
    return Response(status_code=204)


class DocCompanySharingRequest(BaseModel):
    enabled: bool
    company_admin_read_acknowledged: bool = False


@router.put("/{item_id}/sharing/company", status_code=204)
def update_company_sharing(
    item_id: str,
    payload: DocCompanySharingRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_current_user),
) -> Response:
    from open_work_hub_api.domains.content_access.ownership import record_ownership_transition

    resource = _resource(db, item_id, user, write=True)
    before = resource.company_visible
    if payload.enabled:
        record_ownership_transition(
            db,
            actor_user_id=user.id,
            resource_kind="native_doc",
            resource_id=resource.id,
            current_kind=resource.ownership_kind,
            next_kind="company",
            company_admin_read_acknowledged=payload.company_admin_read_acknowledged,
        )
        resource.ownership_kind = "company"
    resource.company_visible = payload.enabled
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="docs.company_sharing.update",
        entity_kind="docs",
        entity_id=resource.id,
        summary="Updated company read audience",
        payload={"before": before, "after": payload.enabled},
    )
    from open_work_hub_api.domains.docs.rag_sync import enqueue_native_doc_rag_sync
    from open_work_hub_api.domains.rag.contracts import RagSyncOperation

    enqueue_native_doc_rag_sync(db, doc=resource, operation=RagSyncOperation.UPSERT)
    db.commit()
    publish_doc_access_changed(getattr(request.app.state, "app_realtime", None), resource.id)
    return Response(status_code=204)
