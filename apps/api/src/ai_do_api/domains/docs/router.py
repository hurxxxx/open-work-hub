from __future__ import annotations

import asyncio
import base64
import json
import secrets
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session, get_session_factory
from ai_do_api.core.i18n import (
    DEFAULT_LOCALE,
    LocalizedApiMessage,
    localized_http_exception,
    translate_message,
)
from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import get_minio_client
from ai_do_api.domains.auth.access import (
    load_active_workspace_by_key,
    resolve_workspace_role,
    workspace_role_allows,
)
from ai_do_api.domains.auth.dependencies import (
    require_current_user,
    resolve_auth_context_from_token,
)
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from ai_do_api.domains.collaboration.yjs_runtime import (
    CollabConnectionLimitExceeded,
    FastAPIYjsWebsocket,
)
from ai_do_api.domains.docs import realtime_protocol
from ai_do_api.domains.docs import hub_projection
from ai_do_api.domains.docs import service as docs_service
from ai_do_api.domains.docs.app_catalog import DOCS_WORKSPACE_APP
from ai_do_api.domains.docs.access_context import (
    PAGE_SOURCE_NATIVE_DOC,
    SOURCE_NATIVE_DOC,
    NativeAccess,
    doc_query as _doc_query,
    ensure_docs_workspace_access as _ensure_docs_workspace_access,
    ensure_workspace_for_item_request as _ensure_workspace_for_item_request,
    ensure_workspace_for_page_request as _ensure_workspace_for_page_request,
    load_native_doc_for_access as _load_native_doc_for_access,
    load_native_page as _load_native_page,
    native_doc_from_item_or_404 as _native_doc_from_item_or_404,
    normalize_page_id as _normalize_page_id,
    primary_target as _primary_target,
    utcnow as _utcnow,
    workspace_for_doc as _workspace_for_doc,
)
from ai_do_api.domains.docs.collab import (
    DocsCollabHub,
    delete_collab_document,
    ensure_collab_document_state,
    persist_collab_snapshot_to_page,
    resolve_collab_page_context,
    sync_collab_record_from_rest_patch,
    update_collab_snapshot_record,
)
from ai_do_api.domains.docs.models import (
    DocsCollection,
    DocsUserItemPref,
    NativeDoc,
    NativeDocTarget,
    NativeDocLinkShare,
    NativeDocPage,
    NativeDocUserShare,
)
from ai_do_api.domains.docs.partitioning import ensure_native_doc_partition
from ai_do_api.domains.docs.page_mutations import (
    CreateNativePageCommand,
    DeleteNativePageCommand,
    UpdateNativePageCommand,
    create_native_page,
    delete_native_page,
    update_native_page,
)
from ai_do_api.domains.usage.service import (
    USAGE_EVENT_CONTENT_VIEW,
    record_usage_event,
)
from ai_do_api.domains.docs.rag_sync import enqueue_native_doc_rag_sync
from ai_do_api.domains.docs.registry import describe_source
from ai_do_api.domains.source_access.targets import (
    TargetRef,
    project_target_access,
    resolve_target_label,
)
from ai_do_api.domains.media.service import cleanup_media_for_resource
from ai_do_api.domains.pms import task_doc_links as pms_task_doc_links
from ai_do_api.domains.rag.contracts import RagSyncOperation
from ai_do_api.domains.rag.source_registry import RAG_SCOPE_OFFICIAL


require_docs_app_enabled = require_workspace_app_enabled(
    DOCS_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/docs",
    tags=["docs"],
    dependencies=[Depends(require_docs_app_enabled)],
)
public_router = APIRouter(prefix="/docs", tags=["docs"])
ws_router = APIRouter(prefix="/docs", tags=["docs"])
DocsDocType = Literal[
    "general",
    "meeting_notes",
    "project_brief",
    "spec",
    "policy",
    "guide",
    "memo",
]
DocsRagScope = Literal["official", "personal", "excluded"]
DocsContentFormat = Literal["block", "html"]
DocsHubContentFormat = Literal["block", "html", "mixed"]
DOC_TYPE_VALUES = {
    "general",
    "meeting_notes",
    "project_brief",
    "spec",
    "policy",
    "guide",
    "memo",
}
MAX_CONTENT_TEXT_CHARS = 2 * 1024 * 1024


def _require_workspace_slug(request: Request) -> str:
    workspace_slug = request.path_params.get("workspace_slug")
    if not workspace_slug:
        raise localized_http_exception(
            status_code=400,
            code="docs.workspace_slug_required",
        )
    return workspace_slug


def _require_docs_app_enabled_for_slug(db: Session, workspace_slug: str) -> Workspace:
    workspace = load_active_workspace_by_key(db, workspace_slug)
    if workspace is None:
        raise localized_http_exception(status_code=404, code="workspace.not_found")
    require_docs_app_enabled(db=db, current_workspace=workspace)
    return workspace


def _decode_collab_yjs_state(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:  # pragma: no cover - defensive validation
        raise localized_http_exception(status_code=400, code="docs.invalid_yjs_state") from exc


def _collab_ws_close_code_for_status(status_code: int) -> int:
    if status_code == 401:
        return 4401
    if status_code == 403:
        return 4403
    if status_code == 404:
        return 4404
    return 1011


def _collab_ws_reason_for_http_error(exc: HTTPException) -> str:
    if isinstance(exc.detail, LocalizedApiMessage):
        return translate_message(exc.detail, DEFAULT_LOCALE)
    return str(exc.detail)


async def _receive_collab_auth_frame(websocket: WebSocket) -> str:
    message = await websocket.receive()
    if message["type"] == "websocket.disconnect":
        raise localized_http_exception(status_code=401, code="auth.required")
    payload = message.get("text")
    if payload is None:
        raise localized_http_exception(status_code=401, code="auth.required")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise localized_http_exception(status_code=401, code="auth.required") from exc
    token = parsed.get("token")
    if parsed.get("type") != "auth" or not isinstance(token, str) or not token:
        raise localized_http_exception(status_code=401, code="auth.required")
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
            reason=_collab_ws_reason_for_http_error(exc),
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
            _require_docs_app_enabled_for_slug(db, workspace_slug)
            context = resolve_collab_page_context(db, auth_context.user, workspace_slug, page_ref)
            if not context.can_edit:
                await websocket.close(
                    code=4403,
                    reason=translate_message(
                        LocalizedApiMessage(code="docs.doc_edit_access_required"),
                        DEFAULT_LOCALE,
                    ),
                )
                return
        except HTTPException as exc:
            await _close_websocket_for_http_error(websocket, exc)
            return
        finally:
            db.close()


class DocsShareSummary(BaseModel):
    visibility: Literal["private", "shared"]
    user_share_count: int
    link_active: bool
    link_access_level: Literal["read", "edit"] | None = None


class DocsCollectionSummary(BaseModel):
    id: str
    name: str
    scope: Literal["workspace", "private"]


class DocsCollectionItem(DocsCollectionSummary):
    workspace_id: str
    owner_id: str | None = None
    sort_order: int
    doc_count: int = 0
    created_at: datetime
    updated_at: datetime


class DocsCollectionListResponse(BaseModel):
    items: list[DocsCollectionItem]


class CreateDocsCollectionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=140)
    scope: Literal["workspace", "private"] = "workspace"
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Collection name is required.")
        return stripped


class UpdateDocsCollectionRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=140)
    sort_order: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Collection name is required.")
        return stripped


class DocsPrimaryTarget(BaseModel):
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
    rag_scope: DocsRagScope = RAG_SCOPE_OFFICIAL
    doc_type: DocsDocType = "general"
    content_format: DocsHubContentFormat = "block"
    structure_kind: Literal["page_tree"] = "page_tree"
    location_label: str
    target_label: str
    collection: DocsCollectionSummary | None = None
    primary_target: DocsPrimaryTarget | None = None
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
    content_text: str | None = None
    content_format: DocsContentFormat = "block"
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


class DocTargetPayload(BaseModel):
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
    rag_scope: DocsRagScope = RAG_SCOPE_OFFICIAL
    doc_type: DocsDocType = "general"
    content_format: DocsContentFormat = "block"
    first_page_content_text: str | None = Field(default=None, max_length=MAX_CONTENT_TEXT_CHARS)
    collection_id: str | None = None
    primary_target: DocTargetPayload | None = None


class UpdateDocItemRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    doc_type: DocsDocType = Field(default=None)
    rag_scope: DocsRagScope | None = None
    collection_id: str | None = None


class CreateDocPageRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    parent_id: str | None = None
    content_format: DocsContentFormat = "block"
    content_blocks: list[dict] | None = None
    content_text: str | None = Field(default=None, max_length=MAX_CONTENT_TEXT_CHARS)
    sort_order: int | None = None


class UpdateDocPageRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: str | None = None
    content_blocks: list[dict] | None = None
    content_text: str | None = Field(default=None, max_length=MAX_CONTENT_TEXT_CHARS)
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


class RelatedPmsTaskAttachRequest(BaseModel):
    task_id: str


class RelatedPmsTaskItem(BaseModel):
    id: str
    doc_id: str
    task_id: str
    task_reference: str
    task_title: str
    task_status: str
    task_status_label: str
    task_priority: str
    task_list_id: str
    task_list_name: str
    created_by_id: str
    created_at: datetime


class RelatedPmsTasksResponse(BaseModel):
    items: list[RelatedPmsTaskItem]


class UpsertUserShareRequest(BaseModel):
    access_level: Literal["read", "edit"]


class UpsertLinkShareRequest(BaseModel):
    access_level: Literal["read", "edit"]
    active: bool = True
    regenerate_token: bool = False


class ResolveSharedLinkResponse(BaseModel):
    item: DocsHubItem


class UpdateDocTargetRequest(BaseModel):
    app: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., min_length=1, max_length=64)
    id: str = Field(..., min_length=1, max_length=128)
    sort_order: int = 0


def _default_doc_type_for_source(source_app: str, source_kind: str) -> DocsDocType:
    if source_app == "meeting" or source_kind == "meeting_notes":
        return "meeting_notes"
    return "general"


def _serialize_collection_item(
    collection: DocsCollection,
    *,
    doc_count: int = 0,
) -> DocsCollectionItem:
    return DocsCollectionItem(
        id=collection.id,
        workspace_id=collection.workspace_id,
        scope=collection.scope,  # type: ignore[arg-type]
        owner_id=collection.owner_id,
        name=collection.name,
        sort_order=collection.sort_order,
        doc_count=doc_count,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _collection_query_for_user(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    scope: str | None = None,
) -> list[DocsCollection]:
    query = select(DocsCollection).where(DocsCollection.workspace_id == workspace.id)
    if scope is not None:
        query = query.where(DocsCollection.scope == scope)
    if scope == "private":
        query = query.where(DocsCollection.owner_id == user.id)
    elif scope == "workspace":
        query = query.where(DocsCollection.scope == "workspace")
    else:
        query = query.where(
            (DocsCollection.scope == "workspace")
            | ((DocsCollection.scope == "private") & (DocsCollection.owner_id == user.id))
        )
    return list(
        db.scalars(
            query.order_by(
                DocsCollection.scope,
                DocsCollection.sort_order,
                DocsCollection.name,
                DocsCollection.created_at,
            )
        )
    )


def _collection_doc_scope(
    db: Session,
    *,
    doc: NativeDoc,
    user: User,
) -> str | None:
    workspace = _workspace_for_doc(db, doc)
    primary_target = _primary_target(doc)
    if (
        primary_target is not None
        and primary_target.target_app == "docs"
        and primary_target.target_type == "workspace_sidebar"
        and primary_target.target_id == workspace.id
    ):
        return "workspace"
    if primary_target is None and doc.owner_id == user.id:
        return "private"
    return None


def _load_collection_for_doc_scope(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    collection_id: str | None,
    expected_scope: str | None,
) -> DocsCollection | None:
    if collection_id is None:
        return None
    collection = db.scalar(
        select(DocsCollection).where(
            DocsCollection.id == collection_id,
            DocsCollection.workspace_id == workspace.id,
        )
    )
    if collection is None:
        raise localized_http_exception(status_code=404, code="docs.collection_not_found")
    if expected_scope is None or collection.scope != expected_scope:
        raise localized_http_exception(status_code=400, code="docs.collection_scope_mismatch")
    if collection.scope == "private" and collection.owner_id != user.id:
        raise localized_http_exception(status_code=403, code="docs.collection_access_required")
    if collection.scope == "workspace" and resolve_workspace_role(db, user, workspace.id) is None:
        raise localized_http_exception(status_code=403, code="docs.collection_access_required")
    return collection


def _load_collection_for_doc(
    db: Session,
    *,
    doc: NativeDoc,
    user: User,
    collection_id: str | None,
) -> DocsCollection | None:
    return _load_collection_for_doc_scope(
        db,
        workspace=_workspace_for_doc(db, doc),
        user=user,
        collection_id=collection_id,
        expected_scope=_collection_doc_scope(db, doc=doc, user=user),
    )


def _ensure_doc_collection_still_valid(db: Session, *, doc: NativeDoc, user: User) -> None:
    if doc.collection_id is None:
        return
    try:
        _load_collection_for_doc(db, doc=doc, user=user, collection_id=doc.collection_id)
    except HTTPException:
        doc.collection_id = None
        db.add(doc)


def _get_pref_map(
    db: Session,
    user_id: str,
) -> dict[tuple[str, str], DocsUserItemPref]:
    rows = list(db.scalars(select(DocsUserItemPref).where(DocsUserItemPref.user_id == user_id)))
    return {(row.source_type, row.source_doc_id): row for row in rows}


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


def _serialize_native_item(
    db: Session,
    doc: NativeDoc,
    user: User,
    access: NativeAccess,
    pref: DocsUserItemPref | None,
) -> DocsHubItem:
    workspace = _workspace_for_doc(db, doc)
    primary_target = _primary_target(doc)
    location_label = resolve_target_label(
        db=db,
        workspace=workspace,
        target=primary_target,
    )
    source = describe_source(
        workspace=workspace,
        doc=doc,
        primary_target=primary_target,
    )
    return DocsHubItem.model_validate(
        hub_projection.serialize_native_hub_item(
            doc=doc,
            user=user,
            access=access,
            pref=pref,
            location_label=location_label,
            source_badge=source.badge,
            source_deeplink=source.deep_link,
            primary_target=primary_target,
            include_rag_scope=True,
        )
    )


def _serialize_native_page(
    page: NativeDocPage,
    *,
    can_edit: bool,
) -> DocsPageItem:
    return DocsPageItem.model_validate(
        hub_projection.serialize_native_page(page, can_edit=can_edit)
    )


def _serialize_visible_related_pms_task_links(
    db: Session,
    *,
    user: User,
    doc_id: str,
) -> RelatedPmsTasksResponse:
    return RelatedPmsTasksResponse(
        items=pms_task_doc_links.visible_related_pms_task_items(
            db,
            user=user,
            doc_id=doc_id,
        )
    )


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
        current_user,
        access,
        pref_map.get((SOURCE_NATIVE_DOC, doc.id)),
    )


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
        if sort_by == "target_sort_order":
            return item.primary_target.sort_order if item.primary_target is not None else 0
        return item.updated_at

    return sorted(docs, key=sort_key, reverse=reverse)


def _target_write_allowed(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: TargetRef,
) -> bool:
    if ref.app == "docs" and ref.type == "workspace_sidebar" and ref.id == workspace.id:
        return True
    projection = project_target_access(
        db=db,
        user=user,
        workspace=workspace,
        ref=ref,
    )
    return projection.can_edit or projection.can_manage


def _upsert_primary_target(
    db: Session,
    *,
    doc: NativeDoc,
    payload: UpdateDocTargetRequest,
    current_user: User,
) -> NativeDocTarget:
    workspace = _workspace_for_doc(db, doc)
    ref = TargetRef(app=payload.app, type=payload.type, id=payload.id)
    if not _target_write_allowed(
        db=db,
        user=current_user,
        workspace=workspace,
        ref=ref,
    ):
        raise localized_http_exception(status_code=403, code="docs.target_edit_access_required")

    for target in doc.targets:
        target.is_primary = False
        db.add(target)

    existing = next(
        (
            target
            for target in doc.targets
            if target.target_app == payload.app
            and target.target_type == payload.type
            and target.target_id == payload.id
        ),
        None,
    )
    if existing is None:
        existing = NativeDocTarget(
            id=new_id(),
            doc_id=doc.id,
            target_app=payload.app,
            target_type=payload.type,
            target_id=payload.id,
            is_primary=True,
            sort_order=payload.sort_order,
        )
        db.add(existing)
        doc.targets.append(existing)
    else:
        existing.is_primary = True
        existing.sort_order = payload.sort_order
        db.add(existing)
    _ensure_doc_collection_still_valid(db, doc=doc, user=current_user)
    db.flush()
    return existing


def _delete_primary_target(db: Session, doc: NativeDoc, *, current_user: User) -> None:
    for target in list(doc.targets):
        if target.is_primary:
            doc.targets.remove(target)
            db.delete(target)
    db.flush()
    _ensure_doc_collection_still_valid(db, doc=doc, user=current_user)


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
                content_format=page.content_format,
                content_blocks=page.content_blocks,
                content_text=page.content_text,
                sort_order=page.sort_order,
                created_by_id=actor_user_id,
            )
            db.add(cloned)
            db.flush()
            if page.content_format == "block":
                sync_collab_record_from_rest_patch(
                    db,
                    source_type=PAGE_SOURCE_NATIVE_DOC,
                    source_page_id=cloned.id,
                    snapshot_content_blocks=cloned.content_blocks,
                )
            clone_subtree(page.id, cloned.id)

    clone_subtree(None, None)


def _publish_doc_pages_event(
    request: Request,
    *,
    doc_id: str,
    action: Literal["created", "updated", "deleted"],
    actor_user_id: str,
    page: NativeDocPage | None = None,
    page_id: str | None = None,
) -> None:
    payload = {
        "doc_id": doc_id,
        "action": action,
        "page_id": page.id if page is not None else page_id,
        "parent_id": page.parent_id if page is not None else None,
        "actor_user_id": actor_user_id,
    }
    request.app.state.app_realtime.publish(
        realtime_protocol.docs_pages_topic(doc_id),
        {
            "type": realtime_protocol.DOCS_PAGES_CHANGED,
            "data": payload,
        },
    )


@router.get("/collections", response_model=DocsCollectionListResponse)
def list_doc_collections(
    scope: Literal["workspace", "private"] | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsCollectionListResponse:
    workspace = _ensure_docs_workspace_access(db, current_user)
    collections = _collection_query_for_user(
        db,
        workspace=workspace,
        user=current_user,
        scope=scope,
    )
    collection_ids = [collection.id for collection in collections]
    doc_counts: dict[str, int] = {}
    if collection_ids:
        for collection_id, count in db.execute(
            select(NativeDoc.collection_id, func.count())
            .where(
                NativeDoc.collection_id.in_(collection_ids),
                NativeDoc.trashed_at.is_(None),
            )
            .group_by(NativeDoc.collection_id)
        ):
            if collection_id is not None:
                doc_counts[collection_id] = int(count)
    return DocsCollectionListResponse(
        items=[
            _serialize_collection_item(
                collection,
                doc_count=doc_counts.get(collection.id, 0),
            )
            for collection in collections
        ]
    )


@router.post("/collections", response_model=DocsCollectionItem, status_code=status.HTTP_201_CREATED)
def create_doc_collection(
    payload: CreateDocsCollectionRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsCollectionItem:
    workspace = _ensure_docs_workspace_access(db, current_user)
    role = resolve_workspace_role(db, current_user, workspace.id)
    if payload.scope == "workspace" and not workspace_role_allows(role, "admin"):
        raise localized_http_exception(
            status_code=403, code="docs.collection_manage_access_required"
        )
    collection = DocsCollection(
        id=new_id(),
        workspace_id=workspace.id,
        scope=payload.scope,
        owner_id=current_user.id if payload.scope == "private" else None,
        name=payload.name,
        sort_order=payload.sort_order,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return _serialize_collection_item(collection, doc_count=0)


@router.patch("/collections/{collection_id}", response_model=DocsCollectionItem)
def update_doc_collection(
    collection_id: str,
    payload: UpdateDocsCollectionRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsCollectionItem:
    workspace = _ensure_docs_workspace_access(db, current_user)
    collection = db.scalar(
        select(DocsCollection).where(
            DocsCollection.id == collection_id,
            DocsCollection.workspace_id == workspace.id,
        )
    )
    if collection is None:
        raise localized_http_exception(status_code=404, code="docs.collection_not_found")
    if collection.scope == "private" and collection.owner_id != current_user.id:
        raise localized_http_exception(
            status_code=403, code="docs.collection_manage_access_required"
        )
    if collection.scope == "workspace" and not workspace_role_allows(
        resolve_workspace_role(db, current_user, workspace.id),
        "admin",
    ):
        raise localized_http_exception(
            status_code=403, code="docs.collection_manage_access_required"
        )
    if payload.name is not None:
        collection.name = payload.name
    if payload.sort_order is not None:
        collection.sort_order = payload.sort_order
    collection.updated_at = _utcnow()
    db.commit()
    db.refresh(collection)
    doc_count = (
        db.scalar(
            select(func.count())
            .select_from(NativeDoc)
            .where(NativeDoc.collection_id == collection.id, NativeDoc.trashed_at.is_(None))
        )
        or 0
    )
    return _serialize_collection_item(collection, doc_count=int(doc_count))


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc_collection(
    collection_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    workspace = _ensure_docs_workspace_access(db, current_user)
    collection = db.scalar(
        select(DocsCollection).where(
            DocsCollection.id == collection_id,
            DocsCollection.workspace_id == workspace.id,
        )
    )
    if collection is None:
        raise localized_http_exception(status_code=404, code="docs.collection_not_found")
    if collection.scope == "private" and collection.owner_id != current_user.id:
        raise localized_http_exception(
            status_code=403, code="docs.collection_manage_access_required"
        )
    if collection.scope == "workspace" and not workspace_role_allows(
        resolve_workspace_role(db, current_user, workspace.id),
        "admin",
    ):
        raise localized_http_exception(
            status_code=403, code="docs.collection_manage_access_required"
        )
    for doc in db.scalars(select(NativeDoc).where(NativeDoc.collection_id == collection.id)):
        doc.collection_id = None
        db.add(doc)
    db.delete(collection)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/hub", response_model=DocsHubResponse)
def list_docs_hub(
    view: Literal["all", "mine", "shared", "private", "meeting_notes", "recent", "archived"]
    | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str = Query(default=""),
    sort_by: str = Query(default="updated_at"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    source_app: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    collection_id: str | None = Query(default=None),
    doc_type: DocsDocType | None = Query(default=None),
    space_id: str | None = Query(default=None),
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
    return DocsHubResponse.model_validate(
        docs_service.list_hub(
            db,
            user=current_user,
            view=resolved_view,
            q=q,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
            source_app=source_app,
            source_kind=source_kind,
            collection_id=collection_id,
            doc_type=doc_type,
            space_id=space_id,
        )
    )


@router.post("/items", response_model=DocsHubItem, status_code=status.HTTP_201_CREATED)
def create_doc_item(
    payload: CreateDocItemRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    workspace = _ensure_docs_workspace_access(db, current_user)
    if payload.content_format == "block" and payload.first_page_content_text is not None:
        raise localized_http_exception(status_code=400, code="docs.content_format_mismatch")
    target_payload = payload.primary_target
    if target_payload is not None and not _target_write_allowed(
        db=db,
        user=current_user,
        workspace=workspace,
        ref=TargetRef(app=target_payload.app, type=target_payload.type, id=target_payload.id),
    ):
        raise localized_http_exception(status_code=403, code="docs.target_edit_access_required")

    doc_type = (
        payload.doc_type
        if "doc_type" in payload.model_fields_set
        else _default_doc_type_for_source(payload.source_app, payload.source_kind)
    )
    doc = NativeDoc(
        id=new_id(),
        workspace_id=workspace.id,
        owner_id=current_user.id,
        title=payload.title.strip(),
        doc_type=doc_type,
        source_app=payload.source_app,
        source_kind=payload.source_kind,
        source_ref=payload.source_ref,
        generation_kind=payload.generation_kind,
        rag_scope=payload.rag_scope,
    )
    ensure_native_doc_partition(db, doc=doc)
    db.add(doc)
    page = NativeDocPage(
        id=new_id(),
        doc_id=doc.id,
        parent_id=None,
        title=(payload.first_page_title or payload.title).strip(),
        content_format=payload.content_format,
        content_blocks=[] if payload.content_format == "block" else None,
        content_text=payload.first_page_content_text if payload.content_format != "block" else None,
        sort_order=0,
        created_by_id=current_user.id,
    )
    db.add(page)
    db.flush()
    if target_payload is not None:
        _upsert_primary_target(
            db,
            doc=doc,
            payload=UpdateDocTargetRequest.model_validate(target_payload.model_dump()),
            current_user=current_user,
        )
    if payload.collection_id is not None:
        collection = _load_collection_for_doc(
            db,
            doc=doc,
            user=current_user,
            collection_id=payload.collection_id,
        )
        doc.collection_id = collection.id if collection is not None else None
        db.add(doc)
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
    return DocsHubItem.model_validate(
        docs_service.get_item(
            db,
            user=current_user,
            item_id=item_id,
            share_token=share_token,
        )
    )


@router.get("/items/{item_id}/pms-tasks", response_model=RelatedPmsTasksResponse)
def list_doc_pms_tasks(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RelatedPmsTasksResponse:
    _ensure_docs_workspace_access(db, current_user)
    doc, _access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=None)
    return _serialize_visible_related_pms_task_links(db, user=current_user, doc_id=doc.id)


@router.post(
    "/items/{item_id}/pms-tasks",
    response_model=RelatedPmsTasksResponse,
    status_code=status.HTTP_201_CREATED,
)
def attach_doc_pms_task(
    item_id: str,
    payload: RelatedPmsTaskAttachRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RelatedPmsTasksResponse:
    _ensure_docs_workspace_access(db, current_user)
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=None)
    if not access.can_edit:
        raise localized_http_exception(status_code=403, code="docs.doc_edit_access_required")
    pms_task_doc_links.attach_task_to_doc(
        db,
        user=current_user,
        doc=doc,
        task_id=payload.task_id,
    )
    return _serialize_visible_related_pms_task_links(db, user=current_user, doc_id=doc.id)


@router.delete("/items/{item_id}/pms-tasks/{task_id}", response_model=RelatedPmsTasksResponse)
def detach_doc_pms_task(
    item_id: str,
    task_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RelatedPmsTasksResponse:
    _ensure_docs_workspace_access(db, current_user)
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=None)
    if not access.can_edit:
        raise localized_http_exception(status_code=403, code="docs.doc_edit_access_required")
    pms_task_doc_links.detach_task_from_doc(
        db,
        user=current_user,
        doc=doc,
        task_id=task_id,
    )
    return _serialize_visible_related_pms_task_links(db, user=current_user, doc_id=doc.id)


@router.patch("/items/{item_id}", response_model=DocsHubItem)
def update_doc_item(
    item_id: str,
    payload: UpdateDocItemRequest,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    _ensure_workspace_for_item_request(db, current_user, item_id=item_id, share_token=share_token)
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)
    if not access.can_manage:
        raise localized_http_exception(status_code=403, code="docs.doc_manage_access_required")
    changed = False
    if payload.title is not None:
        doc.title = payload.title.strip()
        changed = True
    if "doc_type" in payload.model_fields_set and payload.doc_type is not None:
        doc.doc_type = payload.doc_type
        changed = True
    if "rag_scope" in payload.model_fields_set and payload.rag_scope is not None:
        doc.rag_scope = payload.rag_scope
        changed = True
    if "collection_id" in payload.model_fields_set:
        collection = _load_collection_for_doc(
            db,
            doc=doc,
            user=current_user,
            collection_id=payload.collection_id,
        )
        doc.collection_id = collection.id if collection is not None else None
        changed = True
    if changed:
        db.add(doc)
        enqueue_native_doc_rag_sync(db, doc=doc, operation=RagSyncOperation.UPSERT)
        db.commit()
    return _lookup_item(db, doc.id, current_user, share_token=share_token)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc_item(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _ensure_workspace_for_item_request(db, current_user, item_id=item_id, share_token=share_token)
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=share_token)
    if not access.can_manage:
        raise localized_http_exception(status_code=403, code="docs.doc_manage_access_required")

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


@router.post(
    "/items/{item_id}/duplicate", response_model=DocsHubItem, status_code=status.HTTP_201_CREATED
)
def duplicate_doc_item(
    item_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    _ensure_workspace_for_item_request(db, current_user, item_id=item_id, share_token=share_token)
    source_doc, access = _native_doc_from_item_or_404(
        db, item_id, current_user, share_token=share_token
    )
    if not access.can_view:
        raise localized_http_exception(status_code=403, code="docs.doc_access_required")

    duplicate = NativeDoc(
        id=new_id(),
        workspace_id=source_doc.workspace_id,
        owner_id=current_user.id,
        title=f"{source_doc.title} Copy",
        doc_type=source_doc.doc_type if source_doc.doc_type in DOC_TYPE_VALUES else "general",
        source_app=source_doc.source_app,
        source_kind=source_doc.source_kind,
        source_ref=source_doc.source_ref,
        generation_kind=source_doc.generation_kind,
        rag_scope=source_doc.rag_scope,
    )
    ensure_native_doc_partition(db, doc=duplicate)
    db.add(duplicate)
    db.flush()
    for target in source_doc.targets:
        db.add(
            NativeDocTarget(
                id=new_id(),
                doc_id=duplicate.id,
                target_app=target.target_app,
                target_type=target.target_type,
                target_id=target.target_id,
                is_primary=target.is_primary,
                sort_order=target.sort_order,
            )
        )
    if source_doc.collection is not None:
        if (
            source_doc.collection.scope == "workspace"
            and resolve_workspace_role(db, current_user, source_doc.workspace_id) is not None
        ):
            duplicate.collection_id = source_doc.collection_id
        elif source_doc.collection.scope == "private" and source_doc.owner_id == current_user.id:
            duplicate.collection_id = source_doc.collection_id
        db.add(duplicate)
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
    return DocsPageListResponse.model_validate(
        docs_service.list_pages(
            db,
            user=current_user,
            item_id=item_id,
            share_token=share_token,
        )
    )


@router.post(
    "/items/{item_id}/pages", response_model=DocsPageItem, status_code=status.HTTP_201_CREATED
)
def create_doc_page(
    item_id: str,
    payload: CreateDocPageRequest,
    request: Request,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    _ensure_workspace_for_item_request(db, current_user, item_id=item_id, share_token=share_token)
    result = create_native_page(
        db,
        user=current_user,
        share_token=share_token,
        command=CreateNativePageCommand(
            item_id=item_id,
            title=payload.title,
            parent_id=payload.parent_id,
            content_format=payload.content_format,
            content_blocks=payload.content_blocks,
            content_blocks_present="content_blocks" in payload.model_fields_set,
            content_text=payload.content_text,
            content_text_present="content_text" in payload.model_fields_set,
            sort_order=payload.sort_order,
        ),
    )
    if result.created:
        page = _load_native_page(db, result.page_id)
        assert page is not None
        _publish_doc_pages_event(
            request,
            doc_id=result.doc_id,
            action="created",
            actor_user_id=current_user.id,
            page=page,
        )
    return DocsPageItem.model_validate(result.page)


@router.get("/pages/{page_id}", response_model=DocsPageItem)
def get_doc_page(
    page_id: str,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    return DocsPageItem.model_validate(
        docs_service.read_page(
            db,
            user=current_user,
            page_id=page_id,
            share_token=share_token,
        )
    )


@router.patch("/pages/{page_id}", response_model=DocsPageItem)
def update_doc_page(
    page_id: str,
    payload: UpdateDocPageRequest,
    request: Request,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    _ensure_workspace_for_page_request(db, current_user, page_id=page_id, share_token=share_token)
    result = update_native_page(
        db,
        user=current_user,
        command=UpdateNativePageCommand(
            page_id=page_id,
            parent_id=payload.parent_id,
            parent_id_present="parent_id" in payload.model_fields_set,
            title=payload.title,
            content_blocks=payload.content_blocks,
            content_blocks_present="content_blocks" in payload.model_fields_set,
            content_text=payload.content_text,
            content_text_present="content_text" in payload.model_fields_set,
            sort_order=payload.sort_order,
        ),
        share_token=share_token,
    )
    if result.metadata_changed:
        page = _load_native_page(db, result.page_id)
        assert page is not None
        _publish_doc_pages_event(
            request,
            doc_id=result.doc_id,
            action="updated",
            actor_user_id=current_user.id,
            page=page,
        )
    return DocsPageItem.model_validate(result.page)


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc_page(
    page_id: str,
    request: Request,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _ensure_workspace_for_page_request(db, current_user, page_id=page_id, share_token=share_token)
    result = delete_native_page(
        db,
        user=current_user,
        command=DeleteNativePageCommand(page_id=page_id),
        share_token=share_token,
    )
    _publish_doc_pages_event(
        request,
        doc_id=result.doc_id,
        action="deleted",
        actor_user_id=current_user.id,
        page_id=result.page_id,
    )
    if result.media_keys:
        settings = get_settings()
        client = get_minio_client()
        for key in result.media_keys:
            try:
                client.remove_object(settings.minio_bucket, key)
            except Exception:
                pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/items/{item_id}/target", response_model=DocsHubItem)
def update_doc_target(
    item_id: str,
    payload: UpdateDocTargetRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    _ensure_docs_workspace_access(db, current_user)
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=None)
    if not access.can_edit:
        raise localized_http_exception(status_code=403, code="docs.doc_edit_access_required")
    _upsert_primary_target(db, doc=doc, payload=payload, current_user=current_user)
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()
    return _lookup_item(db, doc.id, current_user)


@router.delete("/items/{item_id}/target", response_model=DocsHubItem)
def delete_doc_target(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    _ensure_docs_workspace_access(db, current_user)
    doc, access = _native_doc_from_item_or_404(db, item_id, current_user, share_token=None)
    if not access.can_edit:
        raise localized_http_exception(status_code=403, code="docs.doc_edit_access_required")
    _delete_primary_target(db, doc, current_user=current_user)
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
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


@public_router.get("/items/{item_id}", response_model=DocsHubItem)
def get_shared_doc_item(
    item_id: str,
    share_token: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    return DocsHubItem.model_validate(
        docs_service.get_item(
            db,
            user=current_user,
            item_id=item_id,
            share_token=share_token,
        )
    )


@public_router.patch("/items/{item_id}", response_model=DocsHubItem)
def update_shared_doc_item(
    item_id: str,
    payload: UpdateDocItemRequest,
    share_token: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    return update_doc_item(item_id, payload, share_token, db, current_user)


@public_router.post(
    "/items/{item_id}/duplicate", response_model=DocsHubItem, status_code=status.HTTP_201_CREATED
)
def duplicate_shared_doc_item(
    item_id: str,
    share_token: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsHubItem:
    return duplicate_doc_item(item_id, share_token, db, current_user)


@public_router.get("/items/{item_id}/pages", response_model=DocsPageListResponse)
def list_shared_doc_pages(
    item_id: str,
    share_token: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageListResponse:
    return DocsPageListResponse.model_validate(
        docs_service.list_pages(
            db,
            user=current_user,
            item_id=item_id,
            share_token=share_token,
        )
    )


@public_router.post(
    "/items/{item_id}/pages", response_model=DocsPageItem, status_code=status.HTTP_201_CREATED
)
def create_shared_doc_page(
    item_id: str,
    payload: CreateDocPageRequest,
    request: Request,
    share_token: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    return create_doc_page(item_id, payload, request, share_token, db, current_user)


@public_router.get("/pages/{page_id}", response_model=DocsPageItem)
def get_shared_doc_page(
    page_id: str,
    share_token: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    return DocsPageItem.model_validate(
        docs_service.read_page(
            db,
            user=current_user,
            page_id=page_id,
            share_token=share_token,
        )
    )


@public_router.patch("/pages/{page_id}", response_model=DocsPageItem)
def update_shared_doc_page(
    page_id: str,
    payload: UpdateDocPageRequest,
    request: Request,
    share_token: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocsPageItem:
    return update_doc_page(page_id, payload, request, share_token, db, current_user)


@public_router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shared_doc_page(
    page_id: str,
    request: Request,
    share_token: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    return delete_doc_page(page_id, request, share_token, db, current_user)


@public_router.post("/items/{item_id}/view")
def record_shared_doc_view(
    item_id: str,
    payload: RecordViewRequest,
    share_token: str = Query(..., min_length=1),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> dict[str, bool]:
    return record_doc_view(item_id, payload, share_token, db, current_user)


@router.post("/items/{item_id}/view")
def record_doc_view(
    item_id: str,
    payload: RecordViewRequest,
    share_token: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> dict[str, bool]:
    _ensure_workspace_for_item_request(db, current_user, item_id=item_id, share_token=share_token)
    doc, _access = _native_doc_from_item_or_404(
        db,
        item_id,
        current_user,
        share_token=share_token,
    )
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
                for current_page in doc.pages
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
    record_usage_event(
        db,
        actor_user_id=current_user.id,
        workspace_id=doc.workspace_id,
        app_id="docs",
        event_type=USAGE_EVENT_CONTENT_VIEW,
        content_kind="doc",
        content_id=doc.id,
        content_title=item.title,
        source="docs.item.view",
        metadata={"doc_type": doc.doc_type, "page_viewed": bool(payload.page_id)},
    )
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
    return [FavoriteDocItem(id=item.id, title=item.title) for item in items]


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
    query = (
        select(User).where(User.status == "active").order_by(User.full_name.asc(), User.email.asc())
    )
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
        raise localized_http_exception(status_code=403, code="docs.doc_share_access_required")
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
        raise localized_http_exception(status_code=409, code="docs.owner_already_has_full_access")
    target_user = db.scalar(select(User).where(User.id == user_id, User.status == "active"))
    if target_user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    if resolve_workspace_role(db, target_user, doc.workspace_id) is None:
        raise localized_http_exception(
            status_code=409,
            code="docs.shared_users_workspace_required",
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


@public_router.get("/shared-links/{share_token}", response_model=ResolveSharedLinkResponse)
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
        raise localized_http_exception(status_code=404, code="docs.shared_link_not_found")
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
        raise localized_http_exception(status_code=403, code="docs.doc_edit_access_required")

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
    runtime = None
    yjs_websocket: FastAPIYjsWebsocket | None = None
    auth_user_id: str | None = None
    slot_acquired = False
    hub: DocsCollabHub = websocket.app.state.docs_collab

    try:
        token = await _resolve_collab_ws_token(websocket)
        workspace_slug = websocket.path_params.get("workspace_slug")
        if not workspace_slug:
            raise localized_http_exception(
                status_code=400,
                code="docs.workspace_slug_required",
            )

        session_factory = get_session_factory()
        db = session_factory()
        collab_yjs_state: bytes | None = None
        try:
            auth_context = resolve_auth_context_from_token(db, token)
            auth_user_id = auth_context.user.id
            _require_docs_app_enabled_for_slug(db, workspace_slug)
            context = resolve_collab_page_context(db, auth_context.user, workspace_slug, page_ref)
            if not context.can_edit:
                raise localized_http_exception(
                    status_code=403, code="docs.doc_edit_access_required"
                )
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
            raise localized_http_exception(status_code=404, code="docs.room_not_found")
        if not hub.relay_available:
            await websocket.close(code=1013, reason="Collaboration relay unavailable.")
            return

        runtime = await hub.get_room(context, collab_yjs_state)
        try:
            await hub.acquire_connection_slot(runtime, auth_user_id)
            slot_acquired = True
        except CollabConnectionLimitExceeded as exc:
            await websocket.close(code=exc.close_code, reason=exc.reason)
            return
        monitor_task = asyncio.create_task(
            _monitor_collab_access(
                websocket,
                workspace_slug=workspace_slug,
                page_ref=page_ref,
                token=token,
            )
        )
        yjs_websocket = FastAPIYjsWebsocket(
            websocket,
            room_key,
            runtime,
            auth_user_id,
        )
        await runtime.room.serve(yjs_websocket)
    except HTTPException as exc:
        await _close_websocket_for_http_error(websocket, exc)
    finally:
        if yjs_websocket is not None:
            yjs_websocket.detach_room_runtime()
        if monitor_task is not None:
            monitor_task.cancel()
            await asyncio.gather(monitor_task, return_exceptions=True)
        if slot_acquired and runtime is not None and auth_user_id is not None:
            await hub.release_connection_slot(runtime, auth_user_id)
        if room_key is not None:
            await hub.cleanup_room(room_key)
        runtime = None
