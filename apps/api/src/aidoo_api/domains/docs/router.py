from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.access import (
    bind_current_workspace,
    get_current_workspace,
    has_system_role,
    resolve_team_role,
    resolve_visible_features,
    resolve_workspaces,
    resolve_workspace_role,
    load_active_workspace_by_key,
    workspace_has_enabled_app,
)
from aidoo_api.domains.auth.dependencies import require_current_user
from aidoo_api.domains.auth.models import Team, TeamMember, User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.models import (
    DocsUserItemPref,
    NativeDoc,
    NativeDocLinkShare,
    NativeDocPage,
    NativeDocUserShare,
)
from aidoo_api.domains.media.router import sync_embedded_media
from aidoo_api.domains.pms.models import SpaceDoc, SpaceDocPage


router = APIRouter(prefix="/docs", tags=["docs"])

SOURCE_NATIVE_DOC = "native_doc"
SOURCE_PMS_SPACE_DOC = "pms_space_doc"

PAGE_SOURCE_NATIVE_DOC = "native_doc_page"
PAGE_SOURCE_PMS_SPACE_DOC = "pms_space_doc_page"

TEAM_ROLE_RANK = {
    "viewer": 10,
    "member": 20,
    "admin": 30,
    "owner": 40,
}
ACCESS_LEVEL_RANK = {
    "read": 10,
    "edit": 20,
}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_item_id(source_type: str, source_id: str) -> str:
    return f"{source_type}__{source_id}"


def _make_page_id(source_type: str, source_id: str) -> str:
    return f"{source_type}__{source_id}"


def _split_prefixed_id(value: str) -> tuple[str | None, str]:
    if "__" not in value:
        return None, value
    prefix, raw_id = value.split("__", 1)
    return prefix, raw_id


def _share_token_allows_item_without_docs_access(item_id: str) -> bool:
    prefix, _raw_id = _split_prefixed_id(item_id)
    return prefix == SOURCE_NATIVE_DOC


def _share_token_allows_page_without_docs_access(page_id: str) -> bool:
    prefix, _raw_id = _split_prefixed_id(page_id)
    return prefix == PAGE_SOURCE_NATIVE_DOC


def _max_access_level(*levels: str | None) -> str | None:
    ranked = [level for level in levels if level in ACCESS_LEVEL_RANK]
    if not ranked:
        return None
    return max(ranked, key=lambda item: ACCESS_LEVEL_RANK[item])


def _is_pms_super_admin(db: Session, user: User) -> bool:
    return has_system_role(db, user, "platform_admin")


def _team_role_allows(role: str | None, minimum: str) -> bool:
    current_rank = TEAM_ROLE_RANK.get(role or "", -1)
    minimum_rank = TEAM_ROLE_RANK.get(minimum, 999)
    return current_rank >= minimum_rank


def _ensure_docs_workspace_access(db: Session, user: User) -> None:
    current_workspace = get_current_workspace()
    if current_workspace is None:
        for summary in resolve_workspaces(db, user):
            if "docs" not in summary["enabled_apps"]:
                continue
            current_workspace = load_active_workspace_by_key(db, summary["slug"])
            if current_workspace is not None:
                bind_current_workspace(current_workspace)
                break
        if current_workspace is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Docs requests require a workspace context.",
            )
    if "nav.docs" not in resolve_visible_features(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feature access required: nav.docs",
        )
    if not workspace_has_enabled_app(db, current_workspace, "docs"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You need nav.docs. Ask a workspace admin to enable Docs.",
        )


def _load_active_pms_team(db: Session, team_id: str) -> Team | None:
    current_workspace = get_current_workspace()
    return db.scalar(
        select(Team)
        .options(joinedload(Team.workspace))
        .where(
            Team.id == team_id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
            Team.workspace_id == current_workspace.id if current_workspace is not None else True,
        )
    )


def _resolve_pms_team_role(db: Session, user: User, team_id: str) -> str | None:
    if _is_pms_super_admin(db, user):
        return "owner" if has_system_role(db, user, "platform_admin") else "admin"
    team = _load_active_pms_team(db, team_id)
    if team is None:
        return None
    return resolve_team_role(db, user, team)


def _accessible_pms_team_ids(db: Session, user: User) -> set[str]:
    current_workspace = get_current_workspace()
    if _is_pms_super_admin(db, user):
        return set(
            db.scalars(
                select(Team.id).where(
                    Team.active.is_(True),
                    Team.trashed_at.is_(None),
                    Team.workspace.has(Workspace.active.is_(True)),
                    Team.workspace_id == current_workspace.id if current_workspace is not None else True,
                )
            )
        )
    return set(
        db.scalars(
            select(TeamMember.team_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                TeamMember.user_id == user.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
                Team.workspace.has(Workspace.active.is_(True)),
                Team.workspace_id == current_workspace.id if current_workspace is not None else True,
            )
        )
    )


@dataclass
class NativeAccess:
    access_level: str | None
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool
    matched_link: NativeDocLinkShare | None


def _resolve_native_doc_access(
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
    access_level = _max_access_level(
        getattr(direct_share, "access_level", None),
        getattr(matched_link, "access_level", None),
    )
    return NativeAccess(
        access_level=access_level,
        can_view=access_level in ACCESS_LEVEL_RANK,
        can_edit=access_level == "edit",
        can_share=False,
        can_manage=False,
        matched_link=matched_link,
    )


class DocsShareSummary(BaseModel):
    visibility: Literal["private", "shared"]
    user_share_count: int
    link_active: bool
    link_access_level: Literal["read", "edit"] | None = None


class DocsHubItem(BaseModel):
    id: str
    source_app: str
    source_type: str
    source_id: str
    structure_kind: Literal["page_tree"]
    location_label: str
    title: str
    page_count: int
    created_by_id: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
    is_favorite: bool
    is_private: bool
    last_viewed_at: datetime | None = None
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool
    sharing_summary: DocsShareSummary | None = None


class DocsHubResponse(BaseModel):
    items: list[DocsHubItem]
    total: int
    page: int
    page_size: int


class DocsPageItem(BaseModel):
    id: str
    doc_id: str
    source_type: str
    source_page_id: str
    parent_id: str | None = None
    title: str
    content_blocks: list[dict] | None = None
    sort_order: int
    created_by_id: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
    can_edit: bool


class DocsPageListResponse(BaseModel):
    items: list[DocsPageItem]


class FavoriteDocItem(BaseModel):
    id: str
    title: str
    source_type: str


class RecentPageItem(BaseModel):
    page_id: str
    page_title: str
    doc_id: str
    doc_title: str
    source_type: str
    location_label: str
    last_viewed_at: datetime


class CreateNativeDocRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    first_page_title: str | None = Field(default=None, min_length=1, max_length=200)


class UpdateDocItemRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class CreateDocPageRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    parent_id: str | None = None
    content_blocks: list[dict] | None = None
    sort_order: int | None = None


class UpdateDocPageRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: str | None = None
    content_blocks: list[dict] | None = None
    sort_order: int | None = None


class ToggleFavoriteResponse(BaseModel):
    is_favorite: bool


class RecordViewRequest(BaseModel):
    page_id: str | None = None


class ShareableUserItem(BaseModel):
    id: str
    email: str
    full_name: str


class NativeUserShareItem(BaseModel):
    user_id: str
    email: str
    full_name: str
    access_level: Literal["read", "edit"]


class NativeLinkShareItem(BaseModel):
    token: str
    access_level: Literal["read", "edit"]
    active: bool
    share_path: str


class NativeDocSharingResponse(BaseModel):
    doc_id: str
    owner_id: str
    users: list[NativeUserShareItem]
    link_share: NativeLinkShareItem | None = None


class UpsertUserShareRequest(BaseModel):
    access_level: Literal["read", "edit"]


class UpsertLinkShareRequest(BaseModel):
    access_level: Literal["read", "edit"]
    active: bool = True
    regenerate_token: bool = False


class ResolveSharedLinkResponse(BaseModel):
    item: DocsHubItem


def _get_pref_map(
    db: Session,
    user_id: str,
) -> dict[tuple[str, str], DocsUserItemPref]:
    rows = list(
        db.scalars(
            select(DocsUserItemPref).where(DocsUserItemPref.user_id == user_id)
        )
    )
    return {
        (row.source_type, row.source_doc_id): row
        for row in rows
    }


def _get_or_create_pref(
    db: Session,
    user_id: str,
    source_type: str,
    source_doc_id: str,
) -> DocsUserItemPref:
    pref = db.scalar(
        select(DocsUserItemPref).where(
            DocsUserItemPref.user_id == user_id,
            DocsUserItemPref.source_type == source_type,
            DocsUserItemPref.source_doc_id == source_doc_id,
        )
    )
    if pref is not None:
        return pref
    pref = DocsUserItemPref(
        id=new_id(),
        user_id=user_id,
        source_type=source_type,
        source_doc_id=source_doc_id,
    )
    db.add(pref)
    db.flush()
    return pref


def _serialize_native_share_summary(doc: NativeDoc) -> DocsShareSummary:
    active_link = next((item for item in doc.link_shares if item.active), None)
    user_share_count = len(doc.user_shares)
    return DocsShareSummary(
        visibility="private" if user_share_count == 0 and active_link is None else "shared",
        user_share_count=user_share_count,
        link_active=active_link is not None,
        link_access_level=active_link.access_level if active_link is not None else None,
    )


def _serialize_native_item(
    doc: NativeDoc,
    access: NativeAccess,
    pref: DocsUserItemPref | None,
) -> DocsHubItem:
    active_pages = [page for page in doc.pages if page.trashed_at is None]
    return DocsHubItem(
        id=_make_item_id(SOURCE_NATIVE_DOC, doc.id),
        source_app="docs",
        source_type=SOURCE_NATIVE_DOC,
        source_id=doc.id,
        structure_kind="page_tree",
        location_label="My Docs",
        title=doc.title,
        page_count=len(active_pages),
        created_by_id=doc.owner_id,
        created_by_name=getattr(doc.owner, "full_name", ""),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        trashed_at=doc.trashed_at,
        is_favorite=bool(pref and pref.is_favorite),
        is_private=_serialize_native_share_summary(doc).visibility == "private",
        last_viewed_at=pref.last_viewed_at if pref else None,
        can_view=access.can_view,
        can_edit=access.can_edit,
        can_share=access.can_share,
        can_manage=access.can_manage,
        sharing_summary=_serialize_native_share_summary(doc),
    )


def _serialize_space_doc_item(
    doc: SpaceDoc,
    *,
    location_label: str,
    role: str,
    pref: DocsUserItemPref | None,
) -> DocsHubItem:
    active_pages = [page for page in doc.pages if page.trashed_at is None]
    return DocsHubItem(
        id=_make_item_id(SOURCE_PMS_SPACE_DOC, doc.id),
        source_app="pms",
        source_type=SOURCE_PMS_SPACE_DOC,
        source_id=doc.id,
        structure_kind="page_tree",
        location_label=location_label,
        title=doc.title,
        page_count=len(active_pages),
        created_by_id=doc.created_by_id,
        created_by_name=getattr(doc.created_by, "full_name", ""),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        trashed_at=doc.trashed_at,
        is_favorite=bool(pref and pref.is_favorite),
        is_private=False,
        last_viewed_at=pref.last_viewed_at if pref else None,
        can_view=True,
        can_edit=_team_role_allows(role, "member"),
        can_share=False,
        can_manage=_team_role_allows(role, "admin"),
        sharing_summary=None,
    )


def _load_accessible_native_docs(db: Session, user: User) -> list[NativeDoc]:
    current_workspace = get_current_workspace()
    if current_workspace is None:
        return []
    docs = list(
        db.scalars(
            select(NativeDoc)
            .options(
                selectinload(NativeDoc.owner),
                selectinload(NativeDoc.pages).selectinload(NativeDocPage.created_by),
                selectinload(NativeDoc.user_shares).selectinload(NativeDocUserShare.user),
                selectinload(NativeDoc.link_shares),
            )
            .where(
                NativeDoc.owner_id == user.id,
                NativeDoc.workspace_id == current_workspace.id,
            )
        )
    )
    shared_docs = list(
        db.scalars(
            select(NativeDoc)
            .join(NativeDocUserShare, NativeDocUserShare.doc_id == NativeDoc.id)
            .options(
                selectinload(NativeDoc.owner),
                selectinload(NativeDoc.pages).selectinload(NativeDocPage.created_by),
                selectinload(NativeDoc.user_shares).selectinload(NativeDocUserShare.user),
                selectinload(NativeDoc.link_shares),
            )
            .where(
                NativeDocUserShare.user_id == user.id,
                NativeDoc.workspace_id == current_workspace.id,
            )
        )
    )
    by_id = {doc.id: doc for doc in docs}
    for doc in shared_docs:
        by_id.setdefault(doc.id, doc)
    return list(by_id.values())


def _load_native_doc_for_access(
    db: Session,
    doc_id: str,
) -> NativeDoc | None:
    current_workspace = get_current_workspace()
    query = (
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages).selectinload(NativeDocPage.created_by),
            selectinload(NativeDoc.user_shares).selectinload(NativeDocUserShare.user),
            selectinload(NativeDoc.link_shares),
        )
        .where(NativeDoc.id == doc_id)
    )
    if current_workspace is not None:
        query = query.where(NativeDoc.workspace_id == current_workspace.id)
    return db.scalar(query)


def _load_native_page(
    db: Session,
    page_id: str,
) -> NativeDocPage | None:
    return db.scalar(
        select(NativeDocPage)
        .options(selectinload(NativeDocPage.created_by), joinedload(NativeDocPage.doc))
        .where(NativeDocPage.id == page_id)
    )


def _collect_native_page_subtree(
    pages: list[NativeDocPage],
    root_page_id: str,
) -> list[NativeDocPage]:
    by_parent: dict[str | None, list[NativeDocPage]] = {}
    by_id = {page.id: page for page in pages}
    for page in pages:
        by_parent.setdefault(page.parent_id, []).append(page)
    root = by_id.get(root_page_id)
    if root is None:
        return []
    result: list[NativeDocPage] = []
    stack = [root]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current.id in seen:
            continue
        seen.add(current.id)
        result.append(current)
        stack.extend(by_parent.get(current.id, []))
    return result


def _validate_native_parent(
    doc: NativeDoc,
    parent_id: str | None,
    *,
    page_id: str | None = None,
) -> None:
    if parent_id is None:
        return
    active_pages = {
        page.id: page
        for page in doc.pages
        if page.trashed_at is None
    }
    parent = active_pages.get(parent_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent page not found.")
    if page_id is not None and parent.id == page_id:
        raise HTTPException(status_code=409, detail="Page cannot be its own parent.")

    ancestor = parent
    visited: set[str] = set()
    while ancestor is not None:
        if ancestor.id in visited:
            raise HTTPException(status_code=409, detail="Page parent relationship cannot contain a cycle.")
        visited.add(ancestor.id)
        if page_id is not None and ancestor.parent_id == page_id:
            raise HTTPException(status_code=409, detail="Page parent relationship cannot contain a cycle.")
        if ancestor.parent_id is None:
            break
        ancestor = active_pages.get(ancestor.parent_id)


def _load_accessible_space_docs(
    db: Session,
    user: User,
) -> list[SpaceDoc]:
    team_ids = _accessible_pms_team_ids(db, user)
    if not team_ids:
        return []
    return list(
        db.scalars(
            select(SpaceDoc)
            .options(
                selectinload(SpaceDoc.created_by),
                selectinload(SpaceDoc.pages).selectinload(SpaceDocPage.created_by),
            )
            .where(SpaceDoc.team_id.in_(team_ids))
        )
    )


def _load_space_doc_with_pages(db: Session, doc_id: str) -> SpaceDoc | None:
    return db.scalar(
        select(SpaceDoc)
        .options(
            selectinload(SpaceDoc.created_by),
            selectinload(SpaceDoc.pages).selectinload(SpaceDocPage.created_by),
        )
        .where(SpaceDoc.id == doc_id)
    )


def _load_space_doc_page_with_doc(db: Session, page_id: str) -> SpaceDocPage | None:
    return db.scalar(
        select(SpaceDocPage)
        .options(
            selectinload(SpaceDocPage.created_by),
            joinedload(SpaceDocPage.doc).selectinload(SpaceDoc.pages),
        )
        .where(SpaceDocPage.id == page_id)
    )


def _validate_space_doc_parent(
    doc: SpaceDoc,
    parent_id: str | None,
    *,
    page_id: str | None = None,
) -> None:
    if parent_id is None:
        return
    active_pages = {
        page.id: page
        for page in doc.pages
        if page.trashed_at is None
    }
    parent = active_pages.get(parent_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent page not found.")
    if page_id is not None and parent.id == page_id:
        raise HTTPException(status_code=409, detail="Page cannot be its own parent.")
    if parent.space_doc_id != doc.id:
        raise HTTPException(status_code=409, detail="Parent page must belong to the same document collection.")
    ancestor = parent
    visited: set[str] = set()
    while ancestor is not None:
        if ancestor.id in visited:
            raise HTTPException(status_code=409, detail="Page parent relationship cannot contain a cycle.")
        visited.add(ancestor.id)
        if page_id is not None and ancestor.parent_id == page_id:
            raise HTTPException(status_code=409, detail="Page parent relationship cannot contain a cycle.")
        if ancestor.parent_id is None:
            break
        ancestor = active_pages.get(ancestor.parent_id)


def _collect_space_page_subtree(
    pages: list[SpaceDocPage],
    root_page_id: str,
) -> list[SpaceDocPage]:
    by_parent: dict[str | None, list[SpaceDocPage]] = {}
    by_id = {page.id: page for page in pages}
    for page in pages:
        by_parent.setdefault(page.parent_id, []).append(page)
    root = by_id.get(root_page_id)
    if root is None:
        return []
    result: list[SpaceDocPage] = []
    stack = [root]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current.id in seen:
            continue
        seen.add(current.id)
        result.append(current)
        stack.extend(by_parent.get(current.id, []))
    return result


def _serialize_native_page(
    doc: NativeDoc,
    page: NativeDocPage,
    *,
    can_edit: bool,
) -> DocsPageItem:
    return DocsPageItem(
        id=_make_page_id(PAGE_SOURCE_NATIVE_DOC, page.id),
        doc_id=_make_item_id(SOURCE_NATIVE_DOC, doc.id),
        source_type=PAGE_SOURCE_NATIVE_DOC,
        source_page_id=page.id,
        parent_id=_make_page_id(PAGE_SOURCE_NATIVE_DOC, page.parent_id) if page.parent_id else None,
        title=page.title,
        content_blocks=page.content_blocks,
        sort_order=page.sort_order,
        created_by_id=page.created_by_id,
        created_by_name=getattr(page.created_by, "full_name", ""),
        created_at=page.created_at,
        updated_at=page.updated_at,
        trashed_at=page.trashed_at,
        can_edit=can_edit,
    )


def _serialize_space_page(
    doc: SpaceDoc,
    page: SpaceDocPage,
    *,
    can_edit: bool,
) -> DocsPageItem:
    return DocsPageItem(
        id=_make_page_id(PAGE_SOURCE_PMS_SPACE_DOC, page.id),
        doc_id=_make_item_id(SOURCE_PMS_SPACE_DOC, doc.id),
        source_type=PAGE_SOURCE_PMS_SPACE_DOC,
        source_page_id=page.id,
        parent_id=_make_page_id(PAGE_SOURCE_PMS_SPACE_DOC, page.parent_id) if page.parent_id else None,
        title=page.title,
        content_blocks=page.content_blocks,
        sort_order=page.sort_order,
        created_by_id=page.created_by_id,
        created_by_name=getattr(page.created_by, "full_name", ""),
        created_at=page.created_at,
        updated_at=page.updated_at,
        trashed_at=page.trashed_at,
        can_edit=can_edit,
    )


def _space_location_label(db: Session, team_id: str) -> str:
    team = _load_active_pms_team(db, team_id)
    return f"PMS / {team.name}" if team is not None else "PMS"


def _native_doc_from_item_or_404(
    db: Session,
    item_id: str,
    current_user: User,
    *,
    share_token: str | None,
) -> tuple[NativeDoc, NativeAccess]:
    prefix, raw_id = _split_prefixed_id(item_id)
    if prefix not in {None, SOURCE_NATIVE_DOC}:
        raise HTTPException(status_code=404, detail="Doc not found.")
    doc = _load_native_doc_for_access(db, raw_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Doc not found.")
    access = _resolve_native_doc_access(doc, current_user, share_token=share_token)
    if not access.can_view or doc.trashed_at is not None and not access.can_manage:
        raise HTTPException(status_code=404, detail="Doc not found.")
    return doc, access


def _space_doc_from_item_or_404(
    db: Session,
    item_id: str,
    current_user: User,
) -> tuple[SpaceDoc, str]:
    prefix, raw_id = _split_prefixed_id(item_id)
    if prefix not in {None, SOURCE_PMS_SPACE_DOC}:
        raise HTTPException(status_code=404, detail="Doc not found.")
    doc = _load_space_doc_with_pages(db, raw_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Doc not found.")
    role = _resolve_pms_team_role(db, current_user, doc.team_id)
    if role is None or doc.trashed_at is not None and not _team_role_allows(role, "admin"):
        raise HTTPException(status_code=404, detail="Doc not found.")
    return doc, role


def _lookup_item(
    db: Session,
    item_id: str,
    current_user: User,
    *,
    share_token: str | None = None,
) -> DocsHubItem:
    prefix, raw_id = _split_prefixed_id(item_id)
    pref_map = _get_pref_map(db, current_user.id)

    if prefix in {SOURCE_NATIVE_DOC, None}:
        doc = _load_native_doc_for_access(db, raw_id)
        if doc is not None:
            access = _resolve_native_doc_access(doc, current_user, share_token=share_token)
            if access.can_view and (doc.trashed_at is None or access.can_manage):
                return _serialize_native_item(
                    doc,
                    access,
                    pref_map.get((SOURCE_NATIVE_DOC, doc.id)),
                )

    if share_token is not None and prefix in {SOURCE_NATIVE_DOC, None}:
        raise HTTPException(status_code=404, detail="Doc not found.")

    if prefix in {SOURCE_PMS_SPACE_DOC, None}:
        doc = _load_space_doc_with_pages(db, raw_id)
        if doc is not None:
            role = _resolve_pms_team_role(db, current_user, doc.team_id)
            if role is not None and (doc.trashed_at is None or _team_role_allows(role, "admin")):
                return _serialize_space_doc_item(
                    doc,
                    location_label=_space_location_label(db, doc.team_id),
                    role=role,
                    pref=pref_map.get((SOURCE_PMS_SPACE_DOC, doc.id)),
                )

    raise HTTPException(status_code=404, detail="Doc not found.")


def _filter_docs_by_category(
    docs: list[DocsHubItem],
    *,
    current_user_id: str,
    category: str,
    q: str,
) -> list[DocsHubItem]:
    filtered = docs
    if category == "my":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.created_by_id == current_user_id
        ]
    elif category == "shared":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.created_by_id != current_user_id
        ]
    elif category == "private":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None
            and item.source_type == SOURCE_NATIVE_DOC
            and item.is_private
            and item.created_by_id == current_user_id
        ]
    elif category == "recent":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.last_viewed_at is not None
        ]
    elif category == "archived":
        filtered = [item for item in filtered if item.trashed_at is not None]
    else:
        filtered = [item for item in filtered if item.trashed_at is None]

    query = q.strip().lower()
    if query:
        filtered = [
            item
            for item in filtered
            if query in item.title.lower() or query in item.location_label.lower()
        ]
    return filtered


def _sort_docs(
    docs: list[DocsHubItem],
    *,
    sort_by: str,
    sort_dir: str,
) -> list[DocsHubItem]:
    reverse = sort_dir != "asc"

    def sort_key(item: DocsHubItem):
        if sort_by == "title":
            return item.title.lower()
        if sort_by == "created_at":
            return item.created_at
        if sort_by == "last_viewed_at":
            return item.last_viewed_at or datetime.min
        return item.updated_at

    return sorted(docs, key=sort_key, reverse=reverse)


@router.get("/hub", response_model=DocsHubResponse)
def list_docs_hub(
    category: str = Query(default="all"),
    q: str = Query(default=""),
    sort_by: str = Query(default="updated_at"),
    sort_dir: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubResponse:
    _ensure_docs_workspace_access(db, current_user)

    pref_map = _get_pref_map(db, current_user.id)

    native_items = [
        _serialize_native_item(
            doc,
            _resolve_native_doc_access(doc, current_user),
            pref_map.get((SOURCE_NATIVE_DOC, doc.id)),
        )
        for doc in _load_accessible_native_docs(db, current_user)
        if _resolve_native_doc_access(doc, current_user).can_view
    ]

    space_items: list[DocsHubItem] = []
    for doc in _load_accessible_space_docs(db, current_user):
        role = _resolve_pms_team_role(db, current_user, doc.team_id)
        if role is None:
            continue
        space_items.append(
            _serialize_space_doc_item(
                doc,
                location_label=_space_location_label(db, doc.team_id),
                role=role,
                pref=pref_map.get((SOURCE_PMS_SPACE_DOC, doc.id)),
            )
        )

    docs = _filter_docs_by_category(
        [*native_items, *space_items],
        current_user_id=current_user.id,
        category=category,
        q=q,
    )
    docs = _sort_docs(docs, sort_by=sort_by, sort_dir=sort_dir)
    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size
    return DocsHubResponse(
        items=docs[start:end],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/native-docs", response_model=DocsHubItem, status_code=status.HTTP_201_CREATED)
def create_native_doc(
    payload: CreateNativeDocRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    _ensure_docs_workspace_access(db, current_user)
    current_workspace = get_current_workspace()
    if current_workspace is None:
        raise HTTPException(status_code=403, detail="Docs requests require a workspace context.")

    doc = NativeDoc(
        id=new_id(),
        workspace_id=current_workspace.id,
        owner_id=current_user.id,
        title=payload.title.strip(),
    )
    db.add(doc)
    page = NativeDocPage(
        id=new_id(),
        doc_id=doc.id,
        parent_id=None,
        title=(payload.first_page_title or payload.title).strip(),
        content_blocks=[],
        sort_order=0,
        created_by_id=current_user.id,
    )
    db.add(page)
    db.commit()
    doc = _load_native_doc_for_access(db, doc.id)
    assert doc is not None
    return _serialize_native_item(
        doc,
        _resolve_native_doc_access(doc, current_user),
        _get_pref_map(db, current_user.id).get((SOURCE_NATIVE_DOC, doc.id)),
    )


@router.get("/items/{item_id}", response_model=DocsHubItem)
def get_doc_item(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, current_user)
    return _lookup_item(db, item_id, current_user, share_token=share_token)


@router.patch("/items/{item_id}", response_model=DocsHubItem)
def update_doc_item(
    item_id: str,
    payload: UpdateDocItemRequest,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, current_user)

    item = _lookup_item(db, item_id, current_user, share_token=share_token)
    if not item.can_manage:
        raise HTTPException(status_code=403, detail="Doc manage access required.")

    if payload.title is None:
        return item

    if item.source_type == SOURCE_NATIVE_DOC:
        doc, _access = _native_doc_from_item_or_404(
            db,
            item_id,
            current_user,
            share_token=share_token,
        )
        doc.title = payload.title.strip()
        db.add(doc)
        db.commit()
        return _lookup_item(db, item_id, current_user, share_token=share_token)

    if item.source_type == SOURCE_PMS_SPACE_DOC:
        doc, _role = _space_doc_from_item_or_404(db, item_id, current_user)
        doc.title = payload.title.strip()
        db.add(doc)
        db.commit()
        return _lookup_item(db, item_id, current_user)

    raise HTTPException(status_code=404, detail="Doc not found.")


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc_item(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, current_user)
    item = _lookup_item(db, item_id, current_user, share_token=share_token)
    if not item.can_manage:
        raise HTTPException(status_code=403, detail="Doc manage access required.")

    if item.source_type == SOURCE_NATIVE_DOC:
        doc, _access = _native_doc_from_item_or_404(
            db,
            item_id,
            current_user,
            share_token=share_token,
        )
        deleted_at = _utcnow()
        doc.trashed_at = deleted_at
        for page in doc.pages:
            if page.trashed_at is None:
                page.trashed_at = deleted_at
                db.add(page)
        db.add(doc)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if item.source_type == SOURCE_PMS_SPACE_DOC:
        doc, _role = _space_doc_from_item_or_404(db, item_id, current_user)
        deleted_at = _utcnow()
        doc.trashed_at = deleted_at
        for page in doc.pages:
            if page.trashed_at is None:
                page.trashed_at = deleted_at
                db.add(page)
        db.add(doc)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404, detail="Doc not found.")


@router.post(
    "/items/{item_id}/duplicate",
    response_model=DocsHubItem,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_doc_item(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    """Duplicate any doc the user can view into a new private native doc owned by them."""
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, current_user)

    item = _lookup_item(db, item_id, current_user, share_token=share_token)
    if not item.can_view:
        raise HTTPException(status_code=403, detail="Doc view access required.")

    # Collect non-trashed source pages, regardless of source type.
    if item.source_type == SOURCE_NATIVE_DOC:
        source_doc, _access = _native_doc_from_item_or_404(
            db, item_id, current_user, share_token=share_token,
        )
        source_title = source_doc.title
        source_pages = [page for page in source_doc.pages if page.trashed_at is None]
    elif item.source_type == SOURCE_PMS_SPACE_DOC:
        source_doc, _role = _space_doc_from_item_or_404(db, item_id, current_user)
        source_title = source_doc.title
        source_pages = [page for page in source_doc.pages if page.trashed_at is None]
    else:
        raise HTTPException(status_code=404, detail="Doc not found.")

    # Create the new native doc shell.
    current_workspace = get_current_workspace()
    if current_workspace is None:
        raise HTTPException(status_code=403, detail="Docs requests require a workspace context.")
    new_doc = NativeDoc(
        id=new_id(),
        workspace_id=current_workspace.id,
        owner_id=current_user.id,
        title=f"{source_title} (copy)"[:200],
    )
    db.add(new_doc)

    # Clone pages preserving parent/child hierarchy via id mapping.
    sorted_pages = sorted(
        source_pages,
        key=lambda page: (
            "" if page.parent_id is None else page.parent_id,
            page.sort_order,
            page.created_at,
        ),
    )
    id_map: dict[str, str] = {}
    cloned_pages: list[tuple[NativeDocPage, list[dict] | None]] = []
    for source_page in sorted_pages:
        new_page_id = new_id()
        id_map[source_page.id] = new_page_id
        new_parent_id = id_map.get(source_page.parent_id) if source_page.parent_id else None
        content_blocks = source_page.content_blocks or []
        new_page = NativeDocPage(
            id=new_page_id,
            doc_id=new_doc.id,
            parent_id=new_parent_id,
            title=source_page.title,
            content_blocks=content_blocks,
            sort_order=source_page.sort_order,
            created_by_id=current_user.id,
        )
        db.add(new_page)
        cloned_pages.append((new_page, content_blocks))

    # Always include at least one page so the new doc opens to something.
    if not cloned_pages:
        empty_page = NativeDocPage(
            id=new_id(),
            doc_id=new_doc.id,
            parent_id=None,
            title=source_title,
            content_blocks=[],
            sort_order=0,
            created_by_id=current_user.id,
        )
        db.add(empty_page)

    db.commit()

    # Re-link any embedded media to the cloned pages.
    for new_page, content_blocks in cloned_pages:
        if content_blocks:
            sync_embedded_media(db, content_blocks, "docs_native_page", new_page.id, current_user)

    new_doc = _load_native_doc_for_access(db, new_doc.id)
    assert new_doc is not None
    return _serialize_native_item(
        new_doc,
        _resolve_native_doc_access(new_doc, current_user),
        _get_pref_map(db, current_user.id).get((SOURCE_NATIVE_DOC, new_doc.id)),
    )


@router.get("/items/{item_id}/pages", response_model=DocsPageListResponse)
def list_doc_pages(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageListResponse:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, current_user)
    item = _lookup_item(db, item_id, current_user, share_token=share_token)
    if item.source_type == SOURCE_NATIVE_DOC:
        doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)
        items = [
            _serialize_native_page(doc, page, can_edit=access.can_edit)
            for page in sorted(
                [page for page in doc.pages if page.trashed_at is None],
                key=lambda page: (
                    "" if page.parent_id is None else page.parent_id,
                    page.sort_order,
                    page.created_at,
                ),
            )
        ]
        return DocsPageListResponse(items=items)

    if item.source_type == SOURCE_PMS_SPACE_DOC:
        doc, role = _space_doc_from_item_or_404(db, item_id, current_user)
        items = [
            _serialize_space_page(doc, page, can_edit=_team_role_allows(role, "member"))
            for page in sorted(
                [page for page in doc.pages if page.trashed_at is None],
                key=lambda page: (
                    "" if page.parent_id is None else page.parent_id,
                    page.sort_order,
                    page.created_at,
                ),
            )
        ]
        return DocsPageListResponse(items=items)

    raise HTTPException(status_code=404, detail="Doc not found.")


@router.post("/items/{item_id}/pages", response_model=DocsPageItem, status_code=status.HTTP_201_CREATED)
def create_doc_page(
    item_id: str,
    payload: CreateDocPageRequest,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, current_user)
    item = _lookup_item(db, item_id, current_user, share_token=share_token)
    if not item.can_edit:
        raise HTTPException(status_code=403, detail="Doc edit access required.")

    if item.source_type == SOURCE_NATIVE_DOC:
        doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)
        parent_id = payload.parent_id
        if parent_id:
            parent_prefix, parent_raw_id = _split_prefixed_id(parent_id)
            if parent_prefix not in {None, PAGE_SOURCE_NATIVE_DOC}:
                raise HTTPException(status_code=400, detail="Parent page must belong to the same document.")
            parent_id = parent_raw_id
        _validate_native_parent(doc, parent_id)
        sibling_count = len([
            page
            for page in doc.pages
            if page.trashed_at is None and page.parent_id == parent_id
        ])
        page = NativeDocPage(
            id=new_id(),
            doc_id=doc.id,
            parent_id=parent_id,
            title=payload.title.strip(),
            content_blocks=payload.content_blocks,
            sort_order=payload.sort_order if payload.sort_order is not None else sibling_count,
            created_by_id=current_user.id,
        )
        db.add(page)
        db.flush()
        if payload.content_blocks is not None:
            sync_embedded_media(db, payload.content_blocks, "docs_native_page", page.id, current_user)
        db.commit()
        page = _load_native_page(db, page.id)
        assert page is not None
        doc = _load_native_doc_for_access(db, doc.id)
        assert doc is not None
        return _serialize_native_page(doc, page, can_edit=access.can_edit)

    doc, role = _space_doc_from_item_or_404(db, item_id, current_user)
    parent_id = payload.parent_id
    if parent_id:
        parent_prefix, parent_raw_id = _split_prefixed_id(parent_id)
        if parent_prefix not in {None, PAGE_SOURCE_PMS_SPACE_DOC}:
            raise HTTPException(status_code=400, detail="Parent page must belong to the same document.")
        parent_id = parent_raw_id
    _validate_space_doc_parent(doc, parent_id)
    sibling_count = len([
        page
        for page in doc.pages
        if page.trashed_at is None and page.parent_id == parent_id
    ])
    page = SpaceDocPage(
        id=new_id(),
        team_id=doc.team_id,
        space_doc_id=doc.id,
        parent_id=parent_id,
        title=payload.title.strip(),
        content_blocks=payload.content_blocks,
        sort_order=payload.sort_order if payload.sort_order is not None else sibling_count,
        created_by_id=current_user.id,
    )
    db.add(page)
    db.flush()
    if payload.content_blocks is not None:
        sync_embedded_media(db, payload.content_blocks, "space_doc_page", page.id, current_user)
    db.commit()
    page = _load_space_doc_page_with_doc(db, page.id)
    assert page is not None and page.doc is not None
    return _serialize_space_page(page.doc, page, can_edit=_team_role_allows(role, "member"))


@router.patch("/pages/{page_id}", response_model=DocsPageItem)
def update_doc_page(
    page_id: str,
    payload: UpdateDocPageRequest,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    prefix, raw_id = _split_prefixed_id(page_id)
    if share_token is None or not _share_token_allows_page_without_docs_access(page_id):
        _ensure_docs_workspace_access(db, current_user)

    if prefix in {PAGE_SOURCE_NATIVE_DOC, None}:
        page = _load_native_page(db, raw_id)
        if page is not None:
            doc = _load_native_doc_for_access(db, page.doc_id)
            assert doc is not None
            access = _resolve_native_doc_access(doc, current_user, share_token=share_token)
            if not access.can_edit or page.trashed_at is not None or doc.trashed_at is not None:
                raise HTTPException(status_code=403, detail="Doc edit access required.")
            if "parent_id" in payload.model_fields_set:
                next_parent_id = payload.parent_id
                if next_parent_id:
                    parent_prefix, parent_raw_id = _split_prefixed_id(next_parent_id)
                    if parent_prefix not in {None, PAGE_SOURCE_NATIVE_DOC}:
                        raise HTTPException(status_code=400, detail="Parent page must belong to the same document.")
                    next_parent_id = parent_raw_id
                _validate_native_parent(doc, next_parent_id, page_id=page.id)
                page.parent_id = next_parent_id
            if payload.title is not None:
                page.title = payload.title.strip()
            if "content_blocks" in payload.model_fields_set:
                page.content_blocks = payload.content_blocks
                sync_embedded_media(db, payload.content_blocks, "docs_native_page", page.id, current_user)
            if payload.sort_order is not None:
                page.sort_order = payload.sort_order
            db.add(page)
            db.commit()
            page = _load_native_page(db, page.id)
            assert page is not None
            doc = _load_native_doc_for_access(db, page.doc_id)
            assert doc is not None
            return _serialize_native_page(doc, page, can_edit=access.can_edit)

    if prefix in {PAGE_SOURCE_PMS_SPACE_DOC, None}:
        page = _load_space_doc_page_with_doc(db, raw_id)
        if page is not None and page.doc is not None:
            role = _resolve_pms_team_role(db, current_user, page.doc.team_id)
            if role is None or not _team_role_allows(role, "member") or page.trashed_at is not None or page.doc.trashed_at is not None:
                raise HTTPException(status_code=403, detail="Doc edit access required.")
            if "parent_id" in payload.model_fields_set:
                next_parent_id = payload.parent_id
                if next_parent_id:
                    parent_prefix, parent_raw_id = _split_prefixed_id(next_parent_id)
                    if parent_prefix not in {None, PAGE_SOURCE_PMS_SPACE_DOC}:
                        raise HTTPException(status_code=400, detail="Parent page must belong to the same document.")
                    next_parent_id = parent_raw_id
                _validate_space_doc_parent(page.doc, next_parent_id, page_id=page.id)
                page.parent_id = next_parent_id
            if payload.title is not None:
                page.title = payload.title.strip()
            if "content_blocks" in payload.model_fields_set:
                page.content_blocks = payload.content_blocks
                sync_embedded_media(db, payload.content_blocks, "space_doc_page", page.id, current_user)
            if payload.sort_order is not None:
                page.sort_order = payload.sort_order
            db.add(page)
            db.commit()
            page = _load_space_doc_page_with_doc(db, page.id)
            assert page is not None and page.doc is not None
            return _serialize_space_page(page.doc, page, can_edit=True)

    raise HTTPException(status_code=404, detail="Page not found.")


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc_page(
    page_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    prefix, raw_id = _split_prefixed_id(page_id)
    if share_token is None or not _share_token_allows_page_without_docs_access(page_id):
        _ensure_docs_workspace_access(db, current_user)

    if prefix in {PAGE_SOURCE_NATIVE_DOC, None}:
        page = _load_native_page(db, raw_id)
        if page is not None:
            doc = _load_native_doc_for_access(db, page.doc_id)
            assert doc is not None
            access = _resolve_native_doc_access(doc, current_user, share_token=share_token)
            if not access.can_edit or page.trashed_at is not None or doc.trashed_at is not None:
                raise HTTPException(status_code=403, detail="Doc edit access required.")
            deleted_at = _utcnow()
            for node in _collect_native_page_subtree([item for item in doc.pages if item.trashed_at is None], page.id):
                node.trashed_at = deleted_at
                db.add(node)
            db.commit()
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    if prefix in {PAGE_SOURCE_PMS_SPACE_DOC, None}:
        page = _load_space_doc_page_with_doc(db, raw_id)
        if page is not None and page.doc is not None:
            role = _resolve_pms_team_role(db, current_user, page.doc.team_id)
            if role is None or not _team_role_allows(role, "member") or page.trashed_at is not None or page.doc.trashed_at is not None:
                raise HTTPException(status_code=403, detail="Doc edit access required.")
            deleted_at = _utcnow()
            for node in _collect_space_page_subtree([item for item in page.doc.pages if item.trashed_at is None], page.id):
                node.trashed_at = deleted_at
                db.add(node)
            db.commit()
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404, detail="Page not found.")


@router.patch("/items/{item_id}/favorite", response_model=ToggleFavoriteResponse)
def toggle_doc_favorite(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ToggleFavoriteResponse:
    _ensure_docs_workspace_access(db, current_user)
    item = _lookup_item(db, item_id, current_user)
    pref = _get_or_create_pref(db, current_user.id, item.source_type, item.source_id)
    pref.is_favorite = not pref.is_favorite
    db.add(pref)
    db.commit()
    return ToggleFavoriteResponse(is_favorite=pref.is_favorite)


@router.post("/items/{item_id}/view")
def record_doc_view(
    item_id: str,
    payload: RecordViewRequest,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> dict[str, bool]:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, current_user)
    item = _lookup_item(db, item_id, current_user, share_token=share_token)
    pref = _get_or_create_pref(db, current_user.id, item.source_type, item.source_id)
    pref.last_viewed_at = _utcnow()
    page_title = item.title
    page_source_id = item.source_id
    if payload.page_id:
        page_prefix, page_raw_id = _split_prefixed_id(payload.page_id)
        if item.source_type == SOURCE_NATIVE_DOC and page_prefix in {None, PAGE_SOURCE_NATIVE_DOC}:
            page = next(
                (
                    current_page
                    for current_page in _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)[0].pages
                    if current_page.id == page_raw_id and current_page.trashed_at is None
                ),
                None,
            )
            if page is not None:
                page_title = page.title
                page_source_id = page.id
        elif item.source_type == SOURCE_PMS_SPACE_DOC and page_prefix in {None, PAGE_SOURCE_PMS_SPACE_DOC}:
            page = next(
                (
                    current_page
                    for current_page in _space_doc_from_item_or_404(db, item_id, current_user)[0].pages
                    if current_page.id == page_raw_id and current_page.trashed_at is None
                ),
                None,
            )
            if page is not None:
                page_title = page.title
                page_source_id = page.id
    pref.last_viewed_page_source_id = page_source_id
    pref.last_viewed_page_title = page_title
    db.add(pref)
    db.commit()
    return {"ok": True}


@router.get("/favorites", response_model=list[FavoriteDocItem])
def list_favorite_docs(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[FavoriteDocItem]:
    _ensure_docs_workspace_access(db, current_user)
    items: list[DocsHubItem] = []
    for pref in db.scalars(
        select(DocsUserItemPref).where(
            DocsUserItemPref.user_id == current_user.id,
            DocsUserItemPref.is_favorite.is_(True),
        )
    ):
        try:
            item = _lookup_item(
                db,
                _make_item_id(pref.source_type, pref.source_doc_id),
                current_user,
            )
        except HTTPException:
            continue
        if item.trashed_at is None and item.is_favorite:
            items.append(item)
    items = _sort_docs(items, sort_by="updated_at", sort_dir="desc")
    return [
        FavoriteDocItem(id=item.id, title=item.title, source_type=item.source_type)
        for item in items
    ]


@router.get("/recent-pages", response_model=list[RecentPageItem])
def list_recent_pages(
    limit: int = Query(default=10, ge=1, le=20),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[RecentPageItem]:
    _ensure_docs_workspace_access(db, current_user)
    prefs = list(
        db.scalars(
            select(DocsUserItemPref)
            .where(
                DocsUserItemPref.user_id == current_user.id,
                DocsUserItemPref.last_viewed_at.is_not(None),
            )
            .order_by(DocsUserItemPref.last_viewed_at.desc())
        )
    )
    items: list[RecentPageItem] = []
    for pref in prefs:
        try:
            doc = _lookup_item(
                db,
                _make_item_id(pref.source_type, pref.source_doc_id),
                current_user,
            )
        except HTTPException:
            continue
        if doc.trashed_at is not None:
            continue
        page_source_id = pref.last_viewed_page_source_id or pref.source_doc_id
        if pref.source_type == SOURCE_NATIVE_DOC:
            page_id = _make_page_id(PAGE_SOURCE_NATIVE_DOC, page_source_id)
        elif pref.source_type == SOURCE_PMS_SPACE_DOC:
            page_id = _make_page_id(PAGE_SOURCE_PMS_SPACE_DOC, page_source_id)
        else:
            continue
        items.append(
            RecentPageItem(
                page_id=page_id,
                page_title=pref.last_viewed_page_title or doc.title,
                doc_id=doc.id,
                doc_title=doc.title,
                source_type=doc.source_type,
                location_label=doc.location_label,
                last_viewed_at=pref.last_viewed_at or doc.updated_at,
            )
        )
        if len(items) >= limit:
            break
    return items


@router.get("/shareable-users", response_model=list[ShareableUserItem])
def list_shareable_users(
    q: str = Query(default=""),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[ShareableUserItem]:
    _ensure_docs_workspace_access(db, current_user)
    current_workspace = get_current_workspace()
    if current_workspace is None:
        raise HTTPException(status_code=403, detail="Docs requests require a workspace context.")
    query = select(User).where(User.status == "active").order_by(User.full_name.asc(), User.email.asc())
    search = q.strip()
    if search:
        query = query.where(
            (User.full_name.ilike(f"%{search}%")) | (User.email.ilike(f"%{search}%"))
        )
    users = list(db.scalars(query.limit(30)))
    return [
        ShareableUserItem(id=user.id, email=user.email, full_name=user.full_name)
        for user in users
        if user.id != current_user.id
        and resolve_workspace_role(db, user, current_workspace.id) is not None
    ]


def _serialize_sharing_response(doc: NativeDoc) -> NativeDocSharingResponse:
    link_share = next((item for item in doc.link_shares if item.active), None)
    return NativeDocSharingResponse(
        doc_id=_make_item_id(SOURCE_NATIVE_DOC, doc.id),
        owner_id=doc.owner_id,
        users=[
            NativeUserShareItem(
                user_id=item.user_id,
                email=item.user.email,
                full_name=item.user.full_name,
                access_level=item.access_level,
            )
            for item in sorted(doc.user_shares, key=lambda row: (row.user.full_name.lower(), row.user.email.lower()))
        ],
        link_share=(
            NativeLinkShareItem(
                token=link_share.token,
                access_level=link_share.access_level,
                active=link_share.active,
                share_path=f"/docs/shared/{link_share.token}",
            )
            if link_share is not None
            else None
        ),
    )


def _load_native_doc_for_owner_or_403(
    db: Session,
    item_id: str,
    current_user: User,
) -> NativeDoc:
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=None)
    if not access.can_share:
        raise HTTPException(status_code=403, detail="Doc share access required.")
    return doc


@router.get("/items/{item_id}/sharing", response_model=NativeDocSharingResponse)
def get_native_doc_sharing(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NativeDocSharingResponse:
    _ensure_docs_workspace_access(db, current_user)
    doc = _load_native_doc_for_owner_or_403(db, item_id, current_user)
    return _serialize_sharing_response(doc)


@router.put("/items/{item_id}/sharing/users/{user_id}", response_model=NativeDocSharingResponse)
def upsert_native_doc_user_share(
    item_id: str,
    user_id: str,
    payload: UpsertUserShareRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NativeDocSharingResponse:
    _ensure_docs_workspace_access(db, current_user)
    doc = _load_native_doc_for_owner_or_403(db, item_id, current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=409, detail="Owner already has full access.")
    target_user = db.scalar(select(User).where(User.id == user_id, User.status == "active"))
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if resolve_workspace_role(db, target_user, doc.workspace_id) is None:
        raise HTTPException(
            status_code=409,
            detail="Shared users must be members of the same workspace.",
        )
    share = next((item for item in doc.user_shares if item.user_id == user_id), None)
    if share is None:
        share = NativeDocUserShare(
            id=new_id(),
            doc_id=doc.id,
            user_id=user_id,
            access_level=payload.access_level,
            created_by_id=current_user.id,
        )
        db.add(share)
    else:
        share.access_level = payload.access_level
        db.add(share)
    db.commit()
    doc = _load_native_doc_for_access(db, doc.id)
    assert doc is not None
    return _serialize_sharing_response(doc)


@router.delete("/items/{item_id}/sharing/users/{user_id}", response_model=NativeDocSharingResponse)
def delete_native_doc_user_share(
    item_id: str,
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NativeDocSharingResponse:
    _ensure_docs_workspace_access(db, current_user)
    doc = _load_native_doc_for_owner_or_403(db, item_id, current_user)
    share = next((item for item in doc.user_shares if item.user_id == user_id), None)
    if share is not None:
        db.delete(share)
        db.commit()
    doc = _load_native_doc_for_access(db, doc.id)
    assert doc is not None
    return _serialize_sharing_response(doc)


@router.put("/items/{item_id}/sharing/link", response_model=NativeDocSharingResponse)
def upsert_native_doc_link_share(
    item_id: str,
    payload: UpsertLinkShareRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NativeDocSharingResponse:
    _ensure_docs_workspace_access(db, current_user)
    doc = _load_native_doc_for_owner_or_403(db, item_id, current_user)
    link_share = next(iter(doc.link_shares), None)
    if link_share is None:
        link_share = NativeDocLinkShare(
            id=new_id(),
            doc_id=doc.id,
            token=secrets.token_urlsafe(24),
            access_level=payload.access_level,
            active=payload.active,
            created_by_id=current_user.id,
        )
        db.add(link_share)
    else:
        if payload.regenerate_token or not link_share.token:
            link_share.token = secrets.token_urlsafe(24)
        link_share.access_level = payload.access_level
        link_share.active = payload.active
        db.add(link_share)
    db.commit()
    doc = _load_native_doc_for_access(db, doc.id)
    assert doc is not None
    return _serialize_sharing_response(doc)


@router.delete("/items/{item_id}/sharing/link", response_model=NativeDocSharingResponse)
def disable_native_doc_link_share(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NativeDocSharingResponse:
    _ensure_docs_workspace_access(db, current_user)
    doc = _load_native_doc_for_owner_or_403(db, item_id, current_user)
    link_share = next(iter(doc.link_shares), None)
    if link_share is not None:
        link_share.active = False
        db.add(link_share)
        db.commit()
    doc = _load_native_doc_for_access(db, doc.id)
    assert doc is not None
    return _serialize_sharing_response(doc)


@router.get("/shared-links/{share_token}", response_model=ResolveSharedLinkResponse)
def resolve_shared_link(
    share_token: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ResolveSharedLinkResponse:
    doc = db.scalar(
        select(NativeDoc)
        .join(NativeDocLinkShare, NativeDocLinkShare.doc_id == NativeDoc.id)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages).selectinload(NativeDocPage.created_by),
            selectinload(NativeDoc.user_shares).selectinload(NativeDocUserShare.user),
            selectinload(NativeDoc.link_shares),
        )
        .where(
            NativeDocLinkShare.token == share_token,
            NativeDocLinkShare.active.is_(True),
            NativeDoc.trashed_at.is_(None),
        )
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Shared document not found.")
    access = _resolve_native_doc_access(doc, current_user, share_token=share_token)
    if not access.can_view:
        raise HTTPException(status_code=403, detail="Shared document access required.")
    pref = _get_pref_map(db, current_user.id).get((SOURCE_NATIVE_DOC, doc.id))
    return ResolveSharedLinkResponse(
        item=_serialize_native_item(doc, access, pref)
    )
