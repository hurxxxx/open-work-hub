from __future__ import annotations

import asyncio
import base64
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.core.db import get_db_session, get_session_factory
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import get_minio_client
from aidoo_api.domains.auth.access import (
    bind_current_workspace,
    get_current_workspace,
    resolve_workspace_role,
    resolve_workspaces,
)
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    resolve_auth_context_from_token,
)
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.collab import (
    DocsCollabHub,
    FastAPIYjsWebsocket,
    delete_collab_document,
    ensure_collab_document_state,
    persist_collab_snapshot_to_page,
    resolve_collab_page_context,
    sync_collab_record_from_rest_patch,
    update_collab_snapshot_record,
)
from aidoo_api.domains.docs.models import (
    DocMeetingAccess,
    DocsUserItemPref,
    NativeDoc,
    NativeDocContainer,
    NativeDocLinkShare,
    NativeDocPage,
    NativeDocUserShare,
)
from aidoo_api.domains.docs.rag_sync import enqueue_native_doc_rag_sync
from aidoo_api.domains.docs.registry import (
    ContainerRef,
    describe_source,
    project_container_access,
    resolve_container_label,
)
from aidoo_api.domains.media.router import cleanup_media_for_resource, sync_embedded_media
from aidoo_api.domains.rag.contracts import RagSyncOperation


router = APIRouter(prefix="/docs", tags=["docs"])
ws_router = APIRouter(prefix="/docs", tags=["docs"])

SOURCE_NATIVE_DOC = "native_doc"
PAGE_SOURCE_NATIVE_DOC = "native_doc_page"

TEAM_ACCESS_LEVEL_RANK = {
    "read": 10,
    "edit": 20,
}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _split_prefixed_id(value: str) -> tuple[str | None, str]:
    if "__" not in value:
        return None, value
    prefix, raw_id = value.split("__", 1)
    return prefix, raw_id


def _normalize_doc_id(value: str) -> str:
    prefix, raw_id = _split_prefixed_id(value)
    if prefix not in {None, SOURCE_NATIVE_DOC}:
        raise HTTPException(status_code=404, detail="Doc not found.")
    return raw_id


def _normalize_page_id(value: str) -> str:
    prefix, raw_id = _split_prefixed_id(value)
    if prefix not in {None, PAGE_SOURCE_NATIVE_DOC}:
        raise HTTPException(status_code=404, detail="Page not found.")
    return raw_id


def _share_token_allows_item_without_docs_access(item_id: str) -> bool:
    prefix, _raw_id = _split_prefixed_id(item_id)
    return prefix in {None, SOURCE_NATIVE_DOC}


def _share_token_allows_page_without_docs_access(page_id: str) -> bool:
    prefix, _raw_id = _split_prefixed_id(page_id)
    return prefix in {None, PAGE_SOURCE_NATIVE_DOC}


def _max_access_level(*levels: str | None) -> str | None:
    ranked = [level for level in levels if level in TEAM_ACCESS_LEVEL_RANK]
    if not ranked:
        return None
    return max(ranked, key=lambda item: TEAM_ACCESS_LEVEL_RANK[item])


def _require_workspace_slug(request: Request) -> str:
    workspace_slug = request.path_params.get("workspace_slug")
    if not workspace_slug:
        raise HTTPException(
            status_code=400,
            detail="Workspace-scoped collaboration routes require a workspace slug.",
        )
    return workspace_slug


def _decode_collab_yjs_state(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:  # pragma: no cover - defensive validation
        raise HTTPException(status_code=400, detail="Invalid yjs_state payload.") from exc


def _collab_ws_close_code_for_status(status_code: int) -> int:
    if status_code == 401:
        return 4401
    if status_code == 403:
        return 4403
    if status_code == 404:
        return 4404
    return 1011


async def _receive_collab_auth_frame(websocket: WebSocket) -> str:
    message = await websocket.receive()
    if message["type"] == "websocket.disconnect":
        raise HTTPException(status_code=401, detail="Authentication required.")
    payload = message.get("text")
    if payload is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=401, detail="Authentication required.") from exc
    token = parsed.get("token")
    if parsed.get("type") != "auth" or not isinstance(token, str) or not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return token


async def _resolve_collab_ws_token(websocket: WebSocket) -> str:
    query_token = websocket.query_params.get("token")
    if query_token:
        return query_token
    return await _receive_collab_auth_frame(websocket)


async def _close_websocket_for_http_error(websocket: WebSocket, exc: HTTPException) -> None:
    try:
        await websocket.close(
            code=_collab_ws_close_code_for_status(exc.status_code),
            reason=str(exc.detail),
        )
    except RuntimeError as close_error:
        if "after sending 'websocket.close'" in str(close_error):
            return
        raise


async def _monitor_collab_access(
    websocket: WebSocket,
    *,
    workspace_slug: str,
    page_ref: str,
    token: str,
) -> None:
    session_factory = get_session_factory()
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.collab_acl_recheck_seconds)
        db = session_factory()
        try:
            auth_context = resolve_auth_context_from_token(db, token, update_last_seen=False)
            context = resolve_collab_page_context(db, auth_context.user, workspace_slug, page_ref)
            if not context.can_edit:
                await websocket.close(code=4403, reason="Doc edit access required.")
                return
        except HTTPException as exc:
            await _close_websocket_for_http_error(websocket, exc)
            return
        finally:
            db.close()


@dataclass
class NativeAccess:
    access_level: str | None
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool
    matched_link: NativeDocLinkShare | None


class DocsShareSummary(BaseModel):
    visibility: Literal["private", "shared"]
    user_share_count: int
    link_active: bool
    link_access_level: Literal["read", "edit"] | None = None


class DocsPrimaryContainer(BaseModel):
    app: str
    type: str
    id: str
    sort_order: int


class DocsHubItem(BaseModel):
    id: str
    source_app: str
    source_type: Literal["native_doc"] = SOURCE_NATIVE_DOC
    source_id: str
    source_kind: str
    source_ref: str | None = None
    generation_kind: str
    structure_kind: Literal["page_tree"] = "page_tree"
    location_label: str
    container_label: str
    primary_container: DocsPrimaryContainer | None = None
    source_badge: str
    source_deeplink: str | None = None
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
    source_type: Literal["native_doc_page"] = PAGE_SOURCE_NATIVE_DOC
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
    realtime_collab: bool = True


class DocsPageListResponse(BaseModel):
    items: list[DocsPageItem]


class DocsCollabSessionUser(BaseModel):
    id: str
    full_name: str


class DocsCollabSessionResponse(BaseModel):
    page_ref: str
    source_type: Literal["native_doc_page"] = PAGE_SOURCE_NATIVE_DOC
    source_page_id: str
    room_key: str
    ws_path: str
    can_edit: bool
    realtime_status: Literal["enabled", "degraded"] = "enabled"
    read_only_reason: Literal["relay_unavailable", "permission_revoked"] | None = None
    user: DocsCollabSessionUser
    snapshot_content_blocks: list[dict] | None = None
    yjs_state: str | None = None


class DocsCollabSnapshotRequest(BaseModel):
    content_blocks: list[dict] | None = None
    yjs_state: str | None = None


class DocsCollabSnapshotResponse(BaseModel):
    updated_at: datetime
    last_snapshot_at: datetime


class DocsHubQuery(BaseModel):
    view: Literal["all", "mine", "shared", "private", "meeting_notes", "recent", "archived"] = "all"
    q: str = ""
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = 1
    page_size: int = 50
    source_app: str | None = None
    source_kind: str | None = None
    container_app: str | None = None
    container_type: str | None = None
    container_id: str | None = None


class DocContainerPayload(BaseModel):
    app: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., min_length=1, max_length=64)
    id: str = Field(..., min_length=1, max_length=128)
    sort_order: int = 0


class CreateDocItemRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    first_page_title: str | None = Field(default=None, min_length=1, max_length=200)
    source_app: str = Field(default="docs", min_length=1, max_length=64)
    source_kind: str = Field(default="manual", min_length=1, max_length=64)
    source_ref: str | None = Field(default=None, max_length=128)
    generation_kind: str = Field(default="human", min_length=1, max_length=32)
    primary_container: DocContainerPayload | None = None


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


class FavoriteDocItem(BaseModel):
    id: str
    title: str
    source_type: Literal["native_doc"] = SOURCE_NATIVE_DOC


class RecentPageItem(BaseModel):
    page_id: str
    page_title: str
    doc_id: str
    doc_title: str
    source_type: Literal["native_doc"] = SOURCE_NATIVE_DOC
    location_label: str
    last_viewed_at: datetime


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


class UpdateDocContainerRequest(BaseModel):
    app: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., min_length=1, max_length=64)
    id: str = Field(..., min_length=1, max_length=128)
    sort_order: int = 0


def _workspace_for_doc(db: Session, doc: NativeDoc) -> Workspace:
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
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


def _ensure_docs_workspace_access(db: Session, user: User) -> Workspace:
    current_workspace = get_current_workspace(db)
    if current_workspace is None:
        for summary in resolve_workspaces(db, user):
            workspace = db.scalar(
                select(Workspace).where(
                    Workspace.id == summary["id"],
                    Workspace.active.is_(True),
                )
            )
            if workspace is None:
                continue
            current_workspace = workspace
            bind_current_workspace(db, current_workspace)
            break
        if current_workspace is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Docs requests require a workspace context.",
            )
    return current_workspace


def _serialize_native_share_summary(doc: NativeDoc) -> DocsShareSummary:
    active_link = next((item for item in doc.link_shares if item.active), None)
    user_share_count = len(doc.user_shares)
    primary_container = _primary_container(doc)
    is_container_shared = primary_container is not None
    is_meeting_note = doc.source_app == "meeting" and doc.source_kind == "meeting_notes"
    return DocsShareSummary(
        visibility="shared" if user_share_count > 0 or active_link is not None or is_container_shared or is_meeting_note else "private",
        user_share_count=user_share_count,
        link_active=active_link is not None,
        link_access_level=active_link.access_level if active_link is not None else None,
    )


def _primary_container(doc: NativeDoc) -> NativeDocContainer | None:
    active = list(doc.containers)
    if not active:
        return None
    active.sort(
        key=lambda item: (
            0 if item.is_primary else 1,
            item.sort_order,
            item.created_at,
        )
    )
    return active[0]


def _container_access_level(
    db: Session,
    doc: NativeDoc,
    user: User,
) -> tuple[str | None, bool]:
    workspace = _workspace_for_doc(db, doc)
    best_level: str | None = None
    can_manage = False
    for container in doc.containers:
        ref = ContainerRef(
            app=container.container_app,
            type=container.container_type,
            id=container.container_id,
        )
        projection = project_container_access(
            db=db,
            user=user,
            workspace=workspace,
            ref=ref,
        )
        if projection.can_manage:
            can_manage = True
        candidate = (
            "edit"
            if projection.can_edit or projection.can_manage
            else "read" if projection.can_view else None
        )
        best_level = _max_access_level(best_level, candidate)
    return best_level, can_manage


def _resolve_native_doc_access(
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
            (
                DocMeetingAccess.expires_at.is_(None)
                | (DocMeetingAccess.expires_at > _utcnow())
            ),
        )
    )
    container_access_level, container_can_manage = _container_access_level(db, doc, user)
    access_level = _max_access_level(
        getattr(direct_share, "access_level", None),
        getattr(matched_link, "access_level", None),
        getattr(meeting_grant, "access_level", None),
        container_access_level,
    )
    return NativeAccess(
        access_level=access_level,
        can_view=access_level in TEAM_ACCESS_LEVEL_RANK,
        can_edit=access_level == "edit",
        can_share=container_can_manage,
        can_manage=container_can_manage,
        matched_link=matched_link,
    )


def _doc_query() -> select[tuple[NativeDoc]]:
    return (
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages).selectinload(NativeDocPage.created_by),
            selectinload(NativeDoc.user_shares).selectinload(NativeDocUserShare.user),
            selectinload(NativeDoc.link_shares),
            selectinload(NativeDoc.containers),
        )
    )


def _load_accessible_native_docs(db: Session, user: User) -> list[NativeDoc]:
    current_workspace = get_current_workspace(db)
    if current_workspace is None:
        return []
    docs = list(
        db.scalars(
            _doc_query().where(NativeDoc.workspace_id == current_workspace.id)
        )
    )
    return [
        doc
        for doc in docs
        if _resolve_native_doc_access(db, doc, user).can_view
    ]


def _load_native_doc_for_access(
    db: Session,
    doc_id: str,
) -> NativeDoc | None:
    current_workspace = get_current_workspace(db)
    query = _doc_query().where(NativeDoc.id == doc_id)
    if current_workspace is not None:
        query = query.where(NativeDoc.workspace_id == current_workspace.id)
    return db.scalar(query)


def _load_native_page(db: Session, page_id: str) -> NativeDocPage | None:
    return db.scalar(
        select(NativeDocPage)
        .options(selectinload(NativeDocPage.created_by), joinedload(NativeDocPage.doc))
        .where(NativeDocPage.id == page_id)
    )


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
    source_doc_id: str,
) -> DocsUserItemPref:
    pref = db.scalar(
        select(DocsUserItemPref).where(
            DocsUserItemPref.user_id == user_id,
            DocsUserItemPref.source_type == SOURCE_NATIVE_DOC,
            DocsUserItemPref.source_doc_id == source_doc_id,
        )
    )
    if pref is not None:
        return pref
    pref = DocsUserItemPref(
        id=new_id(),
        user_id=user_id,
        source_type=SOURCE_NATIVE_DOC,
        source_doc_id=source_doc_id,
    )
    db.add(pref)
    db.flush()
    return pref


def _serialize_primary_container(container: NativeDocContainer | None) -> DocsPrimaryContainer | None:
    if container is None:
        return None
    return DocsPrimaryContainer(
        app=container.container_app,
        type=container.container_type,
        id=container.container_id,
        sort_order=container.sort_order,
    )


def _serialize_native_item(
    db: Session,
    doc: NativeDoc,
    access: NativeAccess,
    pref: DocsUserItemPref | None,
) -> DocsHubItem:
    workspace = _workspace_for_doc(db, doc)
    primary_container = _primary_container(doc)
    location_label = resolve_container_label(
        db=db,
        workspace=workspace,
        container=primary_container,
    )
    source = describe_source(
        workspace=workspace,
        doc=doc,
        primary_container=primary_container,
    )
    active_pages = [page for page in doc.pages if page.trashed_at is None]
    sharing_summary = _serialize_native_share_summary(doc)
    return DocsHubItem(
        id=doc.id,
        source_app=doc.source_app,
        source_id=doc.id,
        source_kind=doc.source_kind,
        source_ref=doc.source_ref,
        generation_kind=doc.generation_kind,
        location_label=location_label,
        container_label=location_label,
        primary_container=_serialize_primary_container(primary_container),
        source_badge=source.badge,
        source_deeplink=source.deep_link,
        title=doc.title,
        page_count=len(active_pages),
        created_by_id=doc.owner_id,
        created_by_name=getattr(doc.owner, "full_name", ""),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        trashed_at=doc.trashed_at,
        is_favorite=bool(pref and pref.is_favorite),
        is_private=sharing_summary.visibility == "private",
        last_viewed_at=pref.last_viewed_at if pref else None,
        can_view=access.can_view,
        can_edit=access.can_edit,
        can_share=access.can_share,
        can_manage=access.can_manage,
        sharing_summary=sharing_summary,
    )


def _serialize_native_page(
    page: NativeDocPage,
    *,
    can_edit: bool,
) -> DocsPageItem:
    return DocsPageItem(
        id=page.id,
        doc_id=page.doc_id,
        source_page_id=page.id,
        parent_id=page.parent_id,
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


def _native_doc_from_item_or_404(
    db: Session,
    item_id: str,
    current_user: User,
    *,
    share_token: str | None,
) -> tuple[NativeDoc, NativeAccess]:
    doc = _load_native_doc_for_access(db, _normalize_doc_id(item_id))
    if doc is None:
        raise HTTPException(status_code=404, detail="Doc not found.")
    access = _resolve_native_doc_access(db, doc, current_user, share_token=share_token)
    if not access.can_view or (doc.trashed_at is not None and not access.can_manage):
        raise HTTPException(status_code=404, detail="Doc not found.")
    return doc, access


def _lookup_item(
    db: Session,
    item_id: str,
    current_user: User,
    *,
    share_token: str | None = None,
) -> DocsHubItem:
    doc, access = _native_doc_from_item_or_404(
        db,
        item_id,
        current_user,
        share_token=share_token,
    )
    pref_map = _get_pref_map(db, current_user.id)
    return _serialize_native_item(
        db,
        doc,
        access,
        pref_map.get((SOURCE_NATIVE_DOC, doc.id)),
    )


def _filter_docs(
    docs: list[DocsHubItem],
    *,
    current_user_id: str,
    query: DocsHubQuery,
) -> list[DocsHubItem]:
    filtered = docs
    if query.view == "mine":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.created_by_id == current_user_id
        ]
    elif query.view == "shared":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.created_by_id != current_user_id
        ]
    elif query.view == "private":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None
            and item.created_by_id == current_user_id
            and item.is_private
        ]
    elif query.view == "meeting_notes":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None
            and item.source_app == "meeting"
            and item.source_kind == "meeting_notes"
        ]
    elif query.view == "recent":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.last_viewed_at is not None
        ]
    elif query.view == "archived":
        filtered = [item for item in filtered if item.trashed_at is not None]
    else:
        filtered = [item for item in filtered if item.trashed_at is None]

    if query.source_app:
        filtered = [item for item in filtered if item.source_app == query.source_app]
    if query.source_kind:
        filtered = [item for item in filtered if item.source_kind == query.source_kind]
    if query.container_app:
        filtered = [
            item
            for item in filtered
            if item.primary_container is not None and item.primary_container.app == query.container_app
        ]
    if query.container_type:
        filtered = [
            item
            for item in filtered
            if item.primary_container is not None and item.primary_container.type == query.container_type
        ]
    if query.container_id:
        filtered = [
            item
            for item in filtered
            if item.primary_container is not None and item.primary_container.id == query.container_id
        ]

    search = query.q.strip().lower()
    if search:
        filtered = [
            item
            for item in filtered
            if search in item.title.lower()
            or search in item.location_label.lower()
            or search in item.source_badge.lower()
        ]
    return filtered


def _sort_docs(
    docs: list[DocsHubItem],
    *,
    sort_by: str,
    sort_dir: Literal["asc", "desc"],
) -> list[DocsHubItem]:
    reverse = sort_dir != "asc"

    def sort_key(item: DocsHubItem):
        if sort_by == "title":
            return item.title.lower()
        if sort_by == "created_at":
            return item.created_at
        if sort_by == "last_viewed_at":
            return item.last_viewed_at or datetime.min
        if sort_by == "container_sort_order":
            return item.primary_container.sort_order if item.primary_container is not None else 0
        return item.updated_at

    return sorted(docs, key=sort_key, reverse=reverse)


def _container_write_allowed(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: ContainerRef,
) -> bool:
    if ref.app == "docs" and ref.type == "workspace_sidebar" and ref.id == workspace.id:
        return True
    projection = project_container_access(
        db=db,
        user=user,
        workspace=workspace,
        ref=ref,
    )
    return projection.can_edit or projection.can_manage


def _upsert_primary_container(
    db: Session,
    *,
    doc: NativeDoc,
    payload: UpdateDocContainerRequest,
    current_user: User,
) -> NativeDocContainer:
    workspace = _workspace_for_doc(db, doc)
    ref = ContainerRef(app=payload.app, type=payload.type, id=payload.id)
    if not _container_write_allowed(
        db=db,
        user=current_user,
        workspace=workspace,
        ref=ref,
    ):
        raise HTTPException(status_code=403, detail="Container edit access required.")

    for container in doc.containers:
        container.is_primary = False
        db.add(container)

    existing = next(
        (
            container
            for container in doc.containers
            if container.container_app == payload.app
            and container.container_type == payload.type
            and container.container_id == payload.id
        ),
        None,
    )
    if existing is None:
        existing = NativeDocContainer(
            id=new_id(),
            doc_id=doc.id,
            container_app=payload.app,
            container_type=payload.type,
            container_id=payload.id,
            is_primary=True,
            sort_order=payload.sort_order,
        )
        db.add(existing)
        doc.containers.append(existing)
    else:
        existing.is_primary = True
        existing.sort_order = payload.sort_order
        db.add(existing)
    db.flush()
    return existing


def _delete_primary_container(db: Session, doc: NativeDoc) -> None:
    for container in list(doc.containers):
        if container.is_primary:
            db.delete(container)


def _clone_page_tree(
    db: Session,
    *,
    source_doc: NativeDoc,
    destination_doc_id: str,
    actor_user_id: str,
) -> None:
    by_parent: dict[str | None, list[NativeDocPage]] = {}
    for page in source_doc.pages:
        if page.trashed_at is not None:
            continue
        by_parent.setdefault(page.parent_id, []).append(page)
    for bucket in by_parent.values():
        bucket.sort(key=lambda page: (page.sort_order, page.created_at))

    def clone_subtree(parent_id: str | None, destination_parent_id: str | None) -> None:
        for page in by_parent.get(parent_id, []):
            cloned = NativeDocPage(
                id=new_id(),
                doc_id=destination_doc_id,
                parent_id=destination_parent_id,
                title=page.title,
                content_blocks=page.content_blocks,
                sort_order=page.sort_order,
                created_by_id=actor_user_id,
            )
            db.add(cloned)
            db.flush()
            sync_collab_record_from_rest_patch(
                db,
                source_type=PAGE_SOURCE_NATIVE_DOC,
                source_page_id=cloned.id,
                snapshot_content_blocks=cloned.content_blocks,
            )
            clone_subtree(page.id, cloned.id)

    clone_subtree(None, None)


def list_hub_internal(
    db: Session,
    *,
    user: User,
    query: DocsHubQuery,
) -> DocsHubResponse:
    _ensure_docs_workspace_access(db, user)
    pref_map = _get_pref_map(db, user.id)
    docs = [
        _serialize_native_item(
            db,
            doc,
            _resolve_native_doc_access(db, doc, user),
            pref_map.get((SOURCE_NATIVE_DOC, doc.id)),
        )
        for doc in _load_accessible_native_docs(db, user)
    ]
    docs = _filter_docs(docs, current_user_id=user.id, query=query)
    docs = _sort_docs(docs, sort_by=query.sort_by, sort_dir=query.sort_dir)
    total = len(docs)
    start = (query.page - 1) * query.page_size
    end = start + query.page_size
    return DocsHubResponse(
        items=docs[start:end],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


def get_item_internal(
    db: Session,
    *,
    user: User,
    item_id: str,
    share_token: str | None,
) -> DocsHubItem:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, user)
    return _lookup_item(db, item_id, user, share_token=share_token)


def list_pages_internal(
    db: Session,
    *,
    user: User,
    item_id: str,
    share_token: str | None,
) -> DocsPageListResponse:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, user)
    doc, access = _native_doc_from_item_or_404(db, item_id, user, share_token=share_token)
    pages = [
        _serialize_native_page(page, can_edit=access.can_edit)
        for page in sorted(
            [page for page in doc.pages if page.trashed_at is None],
            key=lambda page: (
                "" if page.parent_id is None else page.parent_id,
                page.sort_order,
                page.created_at,
            ),
        )
    ]
    return DocsPageListResponse(items=pages)


def read_page_internal(
    db: Session,
    *,
    user: User,
    page_id: str,
    share_token: str | None,
) -> DocsPageItem:
    if share_token is None or not _share_token_allows_page_without_docs_access(page_id):
        _ensure_docs_workspace_access(db, user)
    page = _load_native_page(db, _normalize_page_id(page_id))
    if page is None or page.doc is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    doc = _load_native_doc_for_access(db, page.doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    access = _resolve_native_doc_access(db, doc, user, share_token=share_token)
    if not access.can_view or page.trashed_at is not None or doc.trashed_at is not None:
        raise HTTPException(status_code=403, detail="Page access required.")
    return _serialize_native_page(page, can_edit=access.can_edit)


@router.get("/hub", response_model=DocsHubResponse)
def list_docs_hub(
    view: Literal["all", "mine", "shared", "private", "meeting_notes", "recent", "archived"] | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str = Query(default=""),
    sort_by: str = Query(default="updated_at"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    source_app: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    container_app: str | None = Query(default=None),
    container_type: str | None = Query(default=None),
    container_id: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubResponse:
    resolved_view = view or {
        "all": "all",
        "my": "mine",
        "shared": "shared",
        "private": "private",
        "recent": "recent",
        "archived": "archived",
        "notes": "meeting_notes",
        "meeting_notes": "meeting_notes",
    }.get(category or "all", "all")
    query = DocsHubQuery(
        view=resolved_view,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
        source_app=source_app,
        source_kind=source_kind,
        container_app=container_app,
        container_type=container_type,
        container_id=container_id,
    )
    return list_hub_internal(db, user=current_user, query=query)


@router.post("/items", response_model=DocsHubItem, status_code=status.HTTP_201_CREATED)
def create_doc_item(
    payload: CreateDocItemRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    workspace = _ensure_docs_workspace_access(db, current_user)
    container_payload = payload.primary_container
    if container_payload is not None and not _container_write_allowed(
        db=db,
        user=current_user,
        workspace=workspace,
        ref=ContainerRef(app=container_payload.app, type=container_payload.type, id=container_payload.id),
    ):
        raise HTTPException(status_code=403, detail="Container edit access required.")

    doc = NativeDoc(
        id=new_id(),
        workspace_id=workspace.id,
        owner_id=current_user.id,
        title=payload.title.strip(),
        source_app=payload.source_app,
        source_kind=payload.source_kind,
        source_ref=payload.source_ref,
        generation_kind=payload.generation_kind,
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
    db.flush()
    if container_payload is not None:
        _upsert_primary_container(
            db,
            doc=doc,
            payload=UpdateDocContainerRequest.model_validate(container_payload.model_dump()),
            current_user=current_user,
        )
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()
    return _lookup_item(db, doc.id, current_user)


@router.get("/items/{item_id}", response_model=DocsHubItem)
def get_doc_item(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    return get_item_internal(
        db,
        user=current_user,
        item_id=item_id,
        share_token=share_token,
    )


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
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)
    if not access.can_manage:
        raise HTTPException(status_code=403, detail="Doc manage access required.")
    if payload.title is not None:
        doc.title = payload.title.strip()
        db.add(doc)
        enqueue_native_doc_rag_sync(
            db,
            doc=doc,
            operation=RagSyncOperation.UPSERT,
        )
        db.commit()
    return _lookup_item(db, doc.id, current_user, share_token=share_token)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc_item(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, current_user)
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)
    if not access.can_manage:
        raise HTTPException(status_code=403, detail="Doc manage access required.")

    deleted_at = _utcnow()
    doc.trashed_at = deleted_at
    media_keys: list[str] = []
    for page in doc.pages:
        if page.trashed_at is None:
            page.trashed_at = deleted_at
            db.add(page)
            delete_collab_document(
                db,
                source_type=PAGE_SOURCE_NATIVE_DOC,
                source_page_id=page.id,
            )
            media_keys.extend(cleanup_media_for_resource(db, "docs_native_page", page.id))
    db.add(doc)
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.DELETE,
    )
    db.commit()

    if media_keys:
        settings = get_settings()
        client = get_minio_client()
        for key in media_keys:
            try:
                client.remove_object(settings.minio_bucket, key)
            except Exception:
                pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items/{item_id}/duplicate", response_model=DocsHubItem, status_code=status.HTTP_201_CREATED)
def duplicate_doc_item(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, current_user)
    source_doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)
    if not access.can_view:
        raise HTTPException(status_code=403, detail="Doc access required.")

    duplicate = NativeDoc(
        id=new_id(),
        workspace_id=source_doc.workspace_id,
        owner_id=current_user.id,
        title=f"{source_doc.title} Copy",
        source_app=source_doc.source_app,
        source_kind=source_doc.source_kind,
        source_ref=source_doc.source_ref,
        generation_kind=source_doc.generation_kind,
    )
    db.add(duplicate)
    db.flush()
    for container in source_doc.containers:
        db.add(
            NativeDocContainer(
                id=new_id(),
                doc_id=duplicate.id,
                container_app=container.container_app,
                container_type=container.container_type,
                container_id=container.container_id,
                is_primary=container.is_primary,
                sort_order=container.sort_order,
            )
        )
    _clone_page_tree(
        db,
        source_doc=source_doc,
        destination_doc_id=duplicate.id,
        actor_user_id=current_user.id,
    )
    enqueue_native_doc_rag_sync(
        db,
        doc=duplicate,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()
    return _lookup_item(db, duplicate.id, current_user)


@router.get("/items/{item_id}/pages", response_model=DocsPageListResponse)
def list_doc_pages(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageListResponse:
    return list_pages_internal(
        db,
        user=current_user,
        item_id=item_id,
        share_token=share_token,
    )


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
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Doc edit access required.")

    parent_id = _normalize_page_id(payload.parent_id) if payload.parent_id else None
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
        sync_collab_record_from_rest_patch(
            db,
            source_type=PAGE_SOURCE_NATIVE_DOC,
            source_page_id=page.id,
            snapshot_content_blocks=payload.content_blocks,
        )
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()
    page = _load_native_page(db, page.id)
    assert page is not None
    return _serialize_native_page(page, can_edit=access.can_edit)


@router.get("/pages/{page_id}", response_model=DocsPageItem)
def get_doc_page(
    page_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    return read_page_internal(
        db,
        user=current_user,
        page_id=page_id,
        share_token=share_token,
    )


@router.patch("/pages/{page_id}", response_model=DocsPageItem)
def update_doc_page(
    page_id: str,
    payload: UpdateDocPageRequest,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    if share_token is None or not _share_token_allows_page_without_docs_access(page_id):
        _ensure_docs_workspace_access(db, current_user)
    page = _load_native_page(db, _normalize_page_id(page_id))
    if page is None or page.doc is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    doc = _load_native_doc_for_access(db, page.doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    access = _resolve_native_doc_access(db, doc, current_user, share_token=share_token)
    if not access.can_edit or page.trashed_at is not None or doc.trashed_at is not None:
        raise HTTPException(status_code=403, detail="Doc edit access required.")

    if "parent_id" in payload.model_fields_set:
        next_parent_id = _normalize_page_id(payload.parent_id) if payload.parent_id else None
        _validate_native_parent(doc, next_parent_id, page_id=page.id)
        page.parent_id = next_parent_id
    if payload.title is not None:
        page.title = payload.title.strip()
    if "content_blocks" in payload.model_fields_set:
        page.content_blocks = payload.content_blocks
        sync_embedded_media(db, payload.content_blocks, "docs_native_page", page.id, current_user)
        sync_collab_record_from_rest_patch(
            db,
            source_type=PAGE_SOURCE_NATIVE_DOC,
            source_page_id=page.id,
            snapshot_content_blocks=payload.content_blocks,
        )
    if payload.sort_order is not None:
        page.sort_order = payload.sort_order
    db.add(page)
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()
    page = _load_native_page(db, page.id)
    assert page is not None
    return _serialize_native_page(page, can_edit=access.can_edit)


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc_page(
    page_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    if share_token is None or not _share_token_allows_page_without_docs_access(page_id):
        _ensure_docs_workspace_access(db, current_user)
    page = _load_native_page(db, _normalize_page_id(page_id))
    if page is None or page.doc is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    doc = _load_native_doc_for_access(db, page.doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    access = _resolve_native_doc_access(db, doc, current_user, share_token=share_token)
    if not access.can_edit or page.trashed_at is not None or doc.trashed_at is not None:
        raise HTTPException(status_code=403, detail="Doc edit access required.")

    deleted_at = _utcnow()
    media_keys: list[str] = []
    for node in _collect_native_page_subtree([item for item in doc.pages if item.trashed_at is None], page.id):
        node.trashed_at = deleted_at
        db.add(node)
        delete_collab_document(
            db,
            source_type=PAGE_SOURCE_NATIVE_DOC,
            source_page_id=node.id,
        )
        media_keys.extend(cleanup_media_for_resource(db, "docs_native_page", node.id))
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()
    if media_keys:
        settings = get_settings()
        client = get_minio_client()
        for key in media_keys:
            try:
                client.remove_object(settings.minio_bucket, key)
            except Exception:
                pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/items/{item_id}/container", response_model=DocsHubItem)
def update_doc_container(
    item_id: str,
    payload: UpdateDocContainerRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    _ensure_docs_workspace_access(db, current_user)
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=None)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Doc edit access required.")
    _upsert_primary_container(db, doc=doc, payload=payload, current_user=current_user)
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.VISIBILITY_UPDATE,
    )
    db.commit()
    return _lookup_item(db, doc.id, current_user)


@router.delete("/items/{item_id}/container", response_model=DocsHubItem)
def delete_doc_container(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    _ensure_docs_workspace_access(db, current_user)
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=None)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Doc edit access required.")
    _delete_primary_container(db, doc)
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.VISIBILITY_UPDATE,
    )
    db.commit()
    return _lookup_item(db, doc.id, current_user)


@router.patch("/items/{item_id}/favorite", response_model=ToggleFavoriteResponse)
def toggle_doc_favorite(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ToggleFavoriteResponse:
    _ensure_docs_workspace_access(db, current_user)
    item = _lookup_item(db, item_id, current_user)
    pref = _get_or_create_pref(db, current_user.id, item.source_id)
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
    pref = _get_or_create_pref(db, current_user.id, item.source_id)
    pref.last_viewed_at = _utcnow()
    page_title = item.title
    page_source_id = item.source_id
    if payload.page_id:
        raw_page_id = _normalize_page_id(payload.page_id)
        page = next(
            (
                current_page
                for current_page in _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)[0].pages
                if current_page.id == raw_page_id and current_page.trashed_at is None
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
            DocsUserItemPref.source_type == SOURCE_NATIVE_DOC,
            DocsUserItemPref.is_favorite.is_(True),
        )
    ):
        try:
            item = _lookup_item(db, pref.source_doc_id, current_user)
        except HTTPException:
            continue
        if item.trashed_at is None and item.is_favorite:
            items.append(item)
    items = _sort_docs(items, sort_by="updated_at", sort_dir="desc")
    return [
        FavoriteDocItem(id=item.id, title=item.title)
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
                DocsUserItemPref.source_type == SOURCE_NATIVE_DOC,
                DocsUserItemPref.last_viewed_at.is_not(None),
            )
            .order_by(DocsUserItemPref.last_viewed_at.desc())
        )
    )
    items: list[RecentPageItem] = []
    for pref in prefs:
        try:
            doc = _lookup_item(db, pref.source_doc_id, current_user)
        except HTTPException:
            continue
        if doc.trashed_at is not None:
            continue
        items.append(
            RecentPageItem(
                page_id=pref.last_viewed_page_source_id or pref.source_doc_id,
                page_title=pref.last_viewed_page_title or doc.title,
                doc_id=doc.id,
                doc_title=doc.title,
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
    current_workspace = _ensure_docs_workspace_access(db, current_user)
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
        doc_id=doc.id,
        owner_id=doc.owner_id,
        users=[
            NativeUserShareItem(
                user_id=item.user_id,
                email=item.user.email,
                full_name=item.user.full_name,
                access_level=item.access_level,
            )
            for item in sorted(
                doc.user_shares,
                key=lambda row: (row.user.full_name.lower(), row.user.email.lower()),
            )
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


def _load_native_doc_for_share_or_403(
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
    doc = _load_native_doc_for_share_or_403(db, item_id, current_user)
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
    doc = _load_native_doc_for_share_or_403(db, item_id, current_user)
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
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.VISIBILITY_UPDATE,
    )
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
    doc = _load_native_doc_for_share_or_403(db, item_id, current_user)
    share = next((item for item in doc.user_shares if item.user_id == user_id), None)
    if share is not None:
        db.delete(share)
        enqueue_native_doc_rag_sync(
            db,
            doc=doc,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
        )
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
    doc = _load_native_doc_for_share_or_403(db, item_id, current_user)
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
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.VISIBILITY_UPDATE,
    )
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
    doc = _load_native_doc_for_share_or_403(db, item_id, current_user)
    link_share = next(iter(doc.link_shares), None)
    if link_share is not None:
        link_share.active = False
        db.add(link_share)
        enqueue_native_doc_rag_sync(
            db,
            doc=doc,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
        )
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
        _doc_query()
        .join(NativeDocLinkShare, NativeDocLinkShare.doc_id == NativeDoc.id)
        .where(
            NativeDocLinkShare.token == share_token,
            NativeDocLinkShare.active.is_(True),
        )
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Shared link not found.")
    item = _lookup_item(db, doc.id, current_user, share_token=share_token)
    return ResolveSharedLinkResponse(item=item)


@router.get("/collab/pages/{page_ref}/session", response_model=DocsCollabSessionResponse)
def get_docs_collab_session(
    page_ref: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsCollabSessionResponse:
    workspace_slug = _require_workspace_slug(request)
    context = resolve_collab_page_context(db, current_user, workspace_slug, page_ref)
    collab = ensure_collab_document_state(
        db,
        source_type=context.source_type,
        source_page_id=context.source_page_id,
        room_key=context.room_key,
        snapshot_content_blocks=context.content_blocks,
    )
    db.commit()
    ws_path = request.url.path.removesuffix("/session") + "/ws"
    hub: DocsCollabHub = request.app.state.docs_collab
    return DocsCollabSessionResponse(
        page_ref=context.page_ref,
        source_page_id=context.source_page_id,
        room_key=collab.room_key,
        ws_path=ws_path,
        can_edit=context.can_edit,
        realtime_status="enabled" if hub.relay_available else "degraded",
        read_only_reason=None if hub.relay_available else "relay_unavailable",
        user=DocsCollabSessionUser(id=current_user.id, full_name=current_user.full_name),
        snapshot_content_blocks=collab.snapshot_content_blocks,
        yjs_state=(
            base64.b64encode(collab.yjs_state).decode("ascii")
            if collab.yjs_state is not None
            else None
        ),
    )


@router.put("/collab/pages/{page_ref}/snapshot", response_model=DocsCollabSnapshotResponse)
def save_docs_collab_snapshot(
    page_ref: str,
    payload: DocsCollabSnapshotRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsCollabSnapshotResponse:
    workspace_slug = _require_workspace_slug(request)
    context = resolve_collab_page_context(db, current_user, workspace_slug, page_ref)
    if not context.can_edit:
        raise HTTPException(status_code=403, detail="Doc edit access required.")

    yjs_state = _decode_collab_yjs_state(payload.yjs_state)
    persist_collab_snapshot_to_page(
        db,
        current_user=current_user,
        source_type=context.source_type,
        source_page_id=context.source_page_id,
        content_blocks=payload.content_blocks,
    )
    collab = update_collab_snapshot_record(
        db,
        source_type=context.source_type,
        source_page_id=context.source_page_id,
        room_key=context.room_key,
        snapshot_content_blocks=payload.content_blocks,
        yjs_state=yjs_state,
    )
    db.commit()
    snapshot_at = collab.last_snapshot_at or _utcnow()
    return DocsCollabSnapshotResponse(
        updated_at=snapshot_at,
        last_snapshot_at=snapshot_at,
    )


@ws_router.websocket("/collab/pages/{page_ref}/ws")
@ws_router.websocket("/collab/pages/{page_ref}/ws/{room_name}")
async def docs_collab_websocket(
    websocket: WebSocket,
    page_ref: str,
    room_name: str | None = None,
) -> None:
    await websocket.accept()

    monitor_task: asyncio.Task[None] | None = None
    room_key: str | None = None
    hub: DocsCollabHub = websocket.app.state.docs_collab

    try:
        token = await _resolve_collab_ws_token(websocket)
        workspace_slug = websocket.path_params.get("workspace_slug")
        if not workspace_slug:
            raise HTTPException(
                status_code=400,
                detail="Workspace-scoped collaboration routes require a workspace slug.",
            )

        session_factory = get_session_factory()
        db = session_factory()
        collab_yjs_state: bytes | None = None
        auth_user_id: str | None = None
        try:
            auth_context = resolve_auth_context_from_token(db, token)
            auth_user_id = auth_context.user.id
            context = resolve_collab_page_context(db, auth_context.user, workspace_slug, page_ref)
            if not context.can_edit:
                raise HTTPException(status_code=403, detail="Doc edit access required.")
            collab = ensure_collab_document_state(
                db,
                source_type=context.source_type,
                source_page_id=context.source_page_id,
                room_key=context.room_key,
                snapshot_content_blocks=context.content_blocks,
            )
            db.commit()
            collab_yjs_state = collab.yjs_state
        finally:
            db.close()

        room_key = context.room_key
        if room_name and room_name != room_key:
            raise HTTPException(status_code=404, detail="Room not found.")
        if not hub.relay_available:
            await websocket.close(code=1013, reason="Collaboration relay unavailable.")
            return

        runtime = await hub.get_room(context, collab_yjs_state)
        monitor_task = asyncio.create_task(
            _monitor_collab_access(
                websocket,
                workspace_slug=workspace_slug,
                page_ref=page_ref,
                token=token,
            )
        )
        await runtime.room.serve(
            FastAPIYjsWebsocket(
                websocket,
                room_key,
                runtime,
                auth_user_id,
            )
        )
    except HTTPException as exc:
        await _close_websocket_for_http_error(websocket, exc)
    finally:
        if monitor_task is not None:
            monitor_task.cancel()
            await asyncio.gather(monitor_task, return_exceptions=True)
        if room_key is not None:
            await hub.cleanup_room(room_key)
