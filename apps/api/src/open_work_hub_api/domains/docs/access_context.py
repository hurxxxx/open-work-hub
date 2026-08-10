from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.auth.access import (
    bind_current_workspace,
    get_current_workspace,
    resolve_workspaces,
)
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.docs.hub_projection import select_primary_target
from open_work_hub_api.domains.docs.models import (
    DocMeetingAccess,
    NativeDoc,
    NativeDocTarget,
    NativeDocLinkShare,
    NativeDocPage,
    NativeDocUserShare,
)
from open_work_hub_api.domains.source_access.targets import (
    TargetRef,
    project_target_access,
)

SOURCE_NATIVE_DOC = "native_doc"
PAGE_SOURCE_NATIVE_DOC = "native_doc_page"

TEAM_ACCESS_LEVEL_RANK = {
    "read": 10,
    "edit": 20,
}
NativePageRequirement = Literal["view", "edit"]


@dataclass
class NativeAccess:
    access_level: str | None
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool
    matched_link: NativeDocLinkShare | None


@dataclass(frozen=True)
class NativePageContext:
    page: NativeDocPage
    doc: NativeDoc
    access: NativeAccess


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def split_prefixed_id(value: str) -> tuple[str | None, str]:
    if "__" not in value:
        return None, value
    prefix, raw_id = value.split("__", 1)
    return prefix, raw_id


def normalize_doc_id(value: str) -> str:
    prefix, raw_id = split_prefixed_id(value)
    if prefix not in {None, SOURCE_NATIVE_DOC}:
        raise localized_http_exception(status_code=404, code="docs.doc_not_found")
    return raw_id


def normalize_page_id(value: str) -> str:
    prefix, raw_id = split_prefixed_id(value)
    if prefix not in {None, PAGE_SOURCE_NATIVE_DOC}:
        raise localized_http_exception(status_code=404, code="docs.page_not_found")
    return raw_id


def share_token_allows_item_without_docs_access(item_id: str) -> bool:
    prefix, _raw_id = split_prefixed_id(item_id)
    return prefix in {None, SOURCE_NATIVE_DOC}


def share_token_allows_page_without_docs_access(page_id: str) -> bool:
    prefix, _raw_id = split_prefixed_id(page_id)
    return prefix in {None, PAGE_SOURCE_NATIVE_DOC}


def ensure_workspace_for_item_request(
    db: Session,
    user: User,
    *,
    item_id: str,
    share_token: str | None = None,
) -> Workspace | None:
    if share_token is not None and share_token_allows_item_without_docs_access(item_id):
        return get_current_workspace(db)
    return ensure_docs_workspace_access(db, user)


def ensure_workspace_for_page_request(
    db: Session,
    user: User,
    *,
    page_id: str,
    share_token: str | None = None,
) -> Workspace | None:
    if share_token is not None and share_token_allows_page_without_docs_access(page_id):
        return get_current_workspace(db)
    return ensure_docs_workspace_access(db, user)


def ensure_docs_workspace_access(db: Session, user: User) -> Workspace:
    current_workspace = get_current_workspace(db)
    if current_workspace is not None:
        return current_workspace

    for summary in resolve_workspaces(db, user):
        workspace = db.scalar(
            select(Workspace).where(
                Workspace.id == summary["id"],
                Workspace.active.is_(True),
            )
        )
        if workspace is None:
            continue
        bind_current_workspace(db, workspace)
        return workspace

    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="docs.requests_workspace_context_required",
    )


def bind_workspace_context(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
) -> None:
    bind_current_workspace(db, workspace)
    if principal.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="docs.principal_workspace_mismatch",
        )
    if principal.kind == "user" and principal.user_id not in {None, user.id}:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="docs.principal_user_mismatch",
        )


def require_user_write_principal(principal: CallerPrincipal) -> None:
    if principal.kind != "user":
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="docs.write_user_principal_required",
        )


def max_access_level(*levels: str | None) -> str | None:
    ranked = [level for level in levels if level in TEAM_ACCESS_LEVEL_RANK]
    if not ranked:
        return None
    return max(ranked, key=lambda item: TEAM_ACCESS_LEVEL_RANK[item])


def workspace_for_doc(db: Session, doc: NativeDoc) -> Workspace:
    current_workspace = get_current_workspace(db)
    if current_workspace is not None and current_workspace.id == doc.workspace_id:
        return current_workspace
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == doc.workspace_id,
            Workspace.active.is_(True),
        )
    )
    if workspace is None:
        raise localized_http_exception(status_code=404, code="workspace.not_found")
    return workspace


def target_access_level(
    db: Session,
    doc: NativeDoc,
    user: User,
) -> tuple[str | None, bool]:
    workspace = workspace_for_doc(db, doc)
    best_level: str | None = None
    can_manage = False
    for target in doc.targets:
        projection = project_target_access(
            db=db,
            user=user,
            workspace=workspace,
            ref=TargetRef(
                app=target.target_app,
                type=target.target_type,
                id=target.target_id,
            ),
        )
        if projection.can_manage:
            can_manage = True
        candidate = (
            "edit"
            if projection.can_edit or projection.can_manage
            else "read"
            if projection.can_view
            else None
        )
        best_level = max_access_level(best_level, candidate)
    return best_level, can_manage


def resolve_native_doc_access(
    db: Session,
    doc: NativeDoc,
    user: User,
    *,
    share_token: str | None = None,
) -> NativeAccess:
    if doc.owner_id == user.id:
        link_match = next((item for item in doc.link_shares if item.active), None)
        return NativeAccess(
            access_level="edit",
            can_view=True,
            can_edit=True,
            can_share=True,
            can_manage=True,
            matched_link=link_match,
        )

    direct_share = next((item for item in doc.user_shares if item.user_id == user.id), None)
    matched_link = next(
        (
            item
            for item in doc.link_shares
            if item.active and share_token and item.token == share_token
        ),
        None,
    )
    meeting_grant = db.scalar(
        select(DocMeetingAccess).where(
            DocMeetingAccess.doc_id == doc.id,
            DocMeetingAccess.user_id == user.id,
            DocMeetingAccess.revoked_at.is_(None),
            (DocMeetingAccess.expires_at.is_(None) | (DocMeetingAccess.expires_at > utcnow())),
        )
    )
    target_level, target_can_manage = target_access_level(db, doc, user)
    access_level = max_access_level(
        getattr(direct_share, "access_level", None),
        getattr(matched_link, "access_level", None),
        getattr(meeting_grant, "access_level", None),
        target_level,
    )
    return NativeAccess(
        access_level=access_level,
        can_view=access_level in TEAM_ACCESS_LEVEL_RANK,
        can_edit=access_level == "edit",
        can_share=target_can_manage,
        can_manage=target_can_manage,
        matched_link=matched_link,
    )


def doc_query():
    return select(NativeDoc).options(
        selectinload(NativeDoc.owner),
        selectinload(NativeDoc.pages).selectinload(NativeDocPage.created_by),
        selectinload(NativeDoc.user_shares).selectinload(NativeDocUserShare.user),
        selectinload(NativeDoc.link_shares),
        selectinload(NativeDoc.targets),
        selectinload(NativeDoc.collection),
    )


def load_native_doc_for_access(
    db: Session,
    doc_id: str,
) -> NativeDoc | None:
    current_workspace = get_current_workspace(db)
    query = doc_query().where(NativeDoc.id == doc_id)
    if current_workspace is not None:
        query = query.where(NativeDoc.workspace_id == current_workspace.id)
    return db.scalar(query)


def load_accessible_native_docs(db: Session, user: User) -> list[NativeDoc]:
    current_workspace = get_current_workspace(db)
    if current_workspace is None:
        return []
    docs = list(db.scalars(doc_query().where(NativeDoc.workspace_id == current_workspace.id)))
    return [doc for doc in docs if resolve_native_doc_access(db, doc, user).can_view]


def load_native_page(db: Session, page_id: str) -> NativeDocPage | None:
    return db.scalar(
        select(NativeDocPage)
        .options(selectinload(NativeDocPage.created_by), joinedload(NativeDocPage.doc))
        .where(NativeDocPage.id == page_id)
    )


def primary_target(doc: NativeDoc) -> NativeDocTarget | None:
    return select_primary_target(doc)


def validate_native_parent(
    doc: NativeDoc,
    parent_id: str | None,
    *,
    page_id: str | None = None,
) -> None:
    if parent_id is None:
        return
    active_pages = {page.id: page for page in doc.pages if page.trashed_at is None}
    parent = active_pages.get(parent_id)
    if parent is None:
        raise localized_http_exception(status_code=404, code="docs.parent_page_not_found")
    if page_id is not None and parent.id == page_id:
        raise localized_http_exception(status_code=409, code="docs.page_cannot_be_own_parent")

    ancestor = parent
    visited: set[str] = set()
    while ancestor is not None:
        if ancestor.id in visited:
            raise localized_http_exception(status_code=409, code="docs.page_parent_cycle")
        visited.add(ancestor.id)
        if page_id is not None and ancestor.parent_id == page_id:
            raise localized_http_exception(status_code=409, code="docs.page_parent_cycle")
        if ancestor.parent_id is None:
            break
        ancestor = active_pages.get(ancestor.parent_id)


def native_doc_from_item_or_404(
    db: Session,
    item_id: str,
    current_user: User,
    *,
    share_token: str | None,
) -> tuple[NativeDoc, NativeAccess]:
    doc = load_native_doc_for_access(db, normalize_doc_id(item_id))
    if doc is None:
        raise localized_http_exception(status_code=404, code="docs.doc_not_found")
    access = resolve_native_doc_access(db, doc, current_user, share_token=share_token)
    if not access.can_view or (doc.trashed_at is not None and not access.can_manage):
        raise localized_http_exception(status_code=404, code="docs.doc_not_found")
    return doc, access


def native_page_context_from_page_or_404(
    db: Session,
    *,
    page_id: str,
    user: User,
    share_token: str | None,
    require: NativePageRequirement,
) -> NativePageContext:
    page = load_native_page(db, normalize_page_id(page_id))
    if page is None or page.doc is None:
        raise localized_http_exception(status_code=404, code="docs.page_not_found")
    doc = load_native_doc_for_access(db, page.doc_id)
    if doc is None:
        raise localized_http_exception(status_code=404, code="docs.page_not_found")
    access = resolve_native_doc_access(db, doc, user, share_token=share_token)
    if require == "view":
        if not access.can_view or page.trashed_at is not None or doc.trashed_at is not None:
            raise localized_http_exception(status_code=403, code="docs.page_access_required")
    elif not access.can_edit or page.trashed_at is not None or doc.trashed_at is not None:
        raise localized_http_exception(status_code=403, code="docs.doc_edit_access_required")
    page.doc = doc
    return NativePageContext(page=page, doc=doc, access=access)
