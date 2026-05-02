from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.core.db import get_db_session, get_session_factory
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.auth.access import (
    bind_current_workspace,
    get_current_workspace,
    resolve_workspace_role,
    resolve_workspaces,
)
from aidoo_api.domains.auth.dependencies import require_current_user, resolve_auth_context_from_token
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.collab import FastAPIYjsWebsocket
from aidoo_api.domains.whiteboard.collab import (
    WhiteboardCollabContext,
    WhiteboardCollabHub,
    ensure_collab_document_state,
    sync_collab_record_from_rest_patch,
    update_collab_snapshot_record,
)
from aidoo_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardCollabDocument,
    WhiteboardContainer,
    WhiteboardLinkShare,
    WhiteboardUserShare,
    WhiteboardUserItemPref,
    empty_scene,
)
from aidoo_api.domains.whiteboard.registry import (
    ContainerRef,
    container_write_allowed,
    describe_source,
    project_container_access,
    resolve_container_label,
)
from aidoo_api.domains.whiteboard.service import create_whiteboard_for_user


router = APIRouter(prefix="/whiteboard", tags=["whiteboard"])
public_router = APIRouter(prefix="/whiteboard", tags=["whiteboard"])
ws_router = APIRouter(prefix="/whiteboard", tags=["whiteboard"])

TEAM_ACCESS_LEVEL_RANK = {
    "read": 10,
    "edit": 20,
}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _max_access_level(*levels: str | None) -> str | None:
    ranked = [level for level in levels if level in TEAM_ACCESS_LEVEL_RANK]
    if not ranked:
        return None
    return max(ranked, key=lambda item: TEAM_ACCESS_LEVEL_RANK[item])


@dataclass
class WhiteboardAccess:
    access_level: str | None
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool


class WhiteboardPrimaryContainer(BaseModel):
    app: str
    type: str
    id: str
    sort_order: int


class WhiteboardContainerItem(WhiteboardPrimaryContainer):
    is_primary: bool


class WhiteboardHubItem(BaseModel):
    id: str
    source_app: str
    source_type: Literal["whiteboard"] = "whiteboard"
    source_id: str
    source_kind: str
    source_ref: str | None = None
    generation_kind: str
    location_label: str
    container_label: str
    primary_container: WhiteboardPrimaryContainer | None = None
    containers: list[WhiteboardContainerItem] = Field(default_factory=list)
    source_badge: str
    source_deeplink: str | None = None
    title: str
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


class WhiteboardDetail(WhiteboardHubItem):
    scene: dict[str, Any]


class WhiteboardHubResponse(BaseModel):
    items: list[WhiteboardHubItem]
    total: int
    page: int
    page_size: int


class WhiteboardHubQuery(BaseModel):
    view: Literal["all", "mine", "recent", "favorites", "archived"] = "all"
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


class WhiteboardContainerPayload(BaseModel):
    app: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., min_length=1, max_length=64)
    id: str = Field(..., min_length=1, max_length=128)
    sort_order: int = 0


class CreateWhiteboardRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    scene: dict[str, Any] | None = None
    source_app: str = Field(default="whiteboard", min_length=1, max_length=64)
    source_kind: str = Field(default="manual", min_length=1, max_length=64)
    source_ref: str | None = Field(default=None, max_length=128)
    generation_kind: str = Field(default="human", min_length=1, max_length=32)
    primary_container: WhiteboardContainerPayload | None = None


class UpdateWhiteboardRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    scene: dict[str, Any] | None = None


class UpdateWhiteboardContainerRequest(BaseModel):
    app: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., min_length=1, max_length=64)
    id: str = Field(..., min_length=1, max_length=128)
    sort_order: int = 0


class ToggleFavoriteResponse(BaseModel):
    is_favorite: bool


class ShareableUserItem(BaseModel):
    id: str
    email: str
    full_name: str


class WhiteboardUserShareItem(BaseModel):
    user_id: str
    email: str
    full_name: str
    access_level: Literal["read", "edit"]


class WhiteboardLinkShareItem(BaseModel):
    token: str
    access_level: Literal["read", "edit"]
    active: bool
    share_path: str


class WhiteboardSharingResponse(BaseModel):
    whiteboard_id: str
    owner_id: str
    users: list[WhiteboardUserShareItem]
    link_share: WhiteboardLinkShareItem | None = None


class UpsertUserShareRequest(BaseModel):
    access_level: Literal["read", "edit"]


class UpsertLinkShareRequest(BaseModel):
    access_level: Literal["read", "edit"]
    active: bool = True
    regenerate_token: bool = False


class ResolveWhiteboardSharedLinkResponse(BaseModel):
    item: WhiteboardHubItem


class WhiteboardContextPayload(BaseModel):
    app: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., min_length=1, max_length=64)
    id: str = Field(..., min_length=1, max_length=128)


class WhiteboardContextSlotResponse(BaseModel):
    item: WhiteboardDetail | None = None


class CreateWhiteboardContextSlotRequest(WhiteboardContextPayload):
    title: str = Field(default="Untitled Whiteboard", min_length=1, max_length=200)


class AttachWhiteboardContextSlotRequest(WhiteboardContextPayload):
    whiteboard_id: str


class WhiteboardCollabSessionUser(BaseModel):
    id: str
    full_name: str


class WhiteboardCollabSessionResponse(BaseModel):
    whiteboard_id: str
    room_key: str
    ws_path: str
    can_edit: bool
    realtime_status: Literal["enabled", "degraded"] = "enabled"
    read_only_reason: Literal["relay_unavailable", "permission_revoked"] | None = None
    user: WhiteboardCollabSessionUser
    snapshot_scene: dict[str, Any] | None = None
    yjs_state: str | None = None


class WhiteboardCollabSnapshotRequest(BaseModel):
    scene: dict[str, Any] | None = None
    yjs_state: str | None = None


class WhiteboardCollabSnapshotResponse(BaseModel):
    updated_at: datetime
    last_snapshot_at: datetime


def _require_workspace_slug(request: Request) -> str:
    workspace_slug = request.path_params.get("workspace_slug")
    if not workspace_slug:
        raise HTTPException(
            status_code=400,
            detail="Workspace-scoped collaboration routes require a workspace slug.",
        )
    return workspace_slug


def _bind_workspace_slug_for_collab(db: Session, user: User, workspace_slug: str) -> Workspace:
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.key == workspace_slug,
            Workspace.active.is_(True),
        )
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if resolve_workspace_role(db, user, workspace.id) is None:
        raise HTTPException(status_code=403, detail="Workspace access required.")
    bind_current_workspace(db, workspace)
    return workspace


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


def _resolve_whiteboard_collab_context(
    db: Session,
    user: User,
    item_id: str,
) -> WhiteboardCollabContext:
    _ensure_whiteboard_workspace_access(db, user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, user)
    collab = ensure_collab_document_state(db, whiteboard=whiteboard)
    return WhiteboardCollabContext(
        whiteboard_id=whiteboard.id,
        room_key=collab.room_key,
        can_edit=access.can_edit,
        scene=whiteboard.scene or empty_scene(),
        default_actor_user_id=whiteboard.owner_id,
    )


async def _monitor_whiteboard_collab_access(
    websocket: WebSocket,
    *,
    workspace_slug: str,
    item_id: str,
    token: str,
) -> None:
    session_factory = get_session_factory()
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.collab_acl_recheck_seconds)
        db = session_factory()
        try:
            auth_context = resolve_auth_context_from_token(db, token, update_last_seen=False)
            _bind_workspace_slug_for_collab(db, auth_context.user, workspace_slug)
            context = _resolve_whiteboard_collab_context(db, auth_context.user, item_id)
            if not context.can_edit:
                await websocket.close(code=4403, reason="Whiteboard edit access required.")
                return
        except HTTPException as exc:
            await _close_websocket_for_http_error(websocket, exc)
            return
        finally:
            db.close()


def _ensure_whiteboard_workspace_access(db: Session, user: User) -> Workspace:
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
            detail="Whiteboard requests require a workspace context.",
        )
    return current_workspace


def _workspace_for_whiteboard(db: Session, whiteboard: Whiteboard) -> Workspace:
    current_workspace = get_current_workspace(db)
    if current_workspace is not None and current_workspace.id == whiteboard.workspace_id:
        return current_workspace
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == whiteboard.workspace_id,
            Workspace.active.is_(True),
        )
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


def _primary_container(whiteboard: Whiteboard) -> WhiteboardContainer | None:
    active = list(whiteboard.containers)
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


def _serialize_primary_container(
    container: WhiteboardContainer | None,
) -> WhiteboardPrimaryContainer | None:
    if container is None:
        return None
    return WhiteboardPrimaryContainer(
        app=container.container_app,
        type=container.container_type,
        id=container.container_id,
        sort_order=container.sort_order,
    )


def _serialize_container(container: WhiteboardContainer) -> WhiteboardContainerItem:
    return WhiteboardContainerItem(
        app=container.container_app,
        type=container.container_type,
        id=container.container_id,
        sort_order=container.sort_order,
        is_primary=container.is_primary,
    )


def _container_access_level(
    db: Session,
    whiteboard: Whiteboard,
    user: User,
) -> tuple[str | None, bool]:
    workspace = _workspace_for_whiteboard(db, whiteboard)
    best_level: str | None = None
    can_manage = False
    for container in whiteboard.containers:
        projection = project_container_access(
            db=db,
            user=user,
            workspace=workspace,
            ref=ContainerRef(
                app=container.container_app,
                type=container.container_type,
                id=container.container_id,
            ),
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


def _resolve_whiteboard_access(
    db: Session,
    whiteboard: Whiteboard,
    user: User,
    share_token: str | None = None,
) -> WhiteboardAccess:
    if whiteboard.owner_id == user.id:
        return WhiteboardAccess(
            access_level="edit",
            can_view=True,
            can_edit=True,
            can_share=True,
            can_manage=True,
        )
    direct_share = next((item for item in whiteboard.user_shares if item.user_id == user.id), None)
    matched_link = (
        next(
            (
                item
                for item in whiteboard.link_shares
                if item.active and item.token == share_token
            ),
            None,
        )
        if share_token
        else None
    )
    container_access_level, container_can_manage = _container_access_level(db, whiteboard, user)
    access_level = _max_access_level(
        getattr(direct_share, "access_level", None),
        getattr(matched_link, "access_level", None),
        container_access_level,
    )
    return WhiteboardAccess(
        access_level=access_level,
        can_view=access_level in TEAM_ACCESS_LEVEL_RANK,
        can_edit=access_level == "edit",
        can_share=container_can_manage,
        can_manage=container_can_manage,
    )


def _whiteboard_query() -> select[tuple[Whiteboard]]:
    return (
        select(Whiteboard)
        .options(
            selectinload(Whiteboard.owner),
            selectinload(Whiteboard.containers),
            selectinload(Whiteboard.user_shares).selectinload(WhiteboardUserShare.user),
            selectinload(Whiteboard.link_shares),
        )
    )


def _load_accessible_whiteboards(db: Session, user: User) -> list[Whiteboard]:
    current_workspace = get_current_workspace(db)
    if current_workspace is None:
        return []
    whiteboards = list(
        db.scalars(
            _whiteboard_query().where(Whiteboard.workspace_id == current_workspace.id)
        )
    )
    return [
        whiteboard
        for whiteboard in whiteboards
        if _resolve_whiteboard_access(db, whiteboard, user).can_view
    ]


def _load_whiteboard_for_access(db: Session, whiteboard_id: str) -> Whiteboard | None:
    current_workspace = get_current_workspace(db)
    query = _whiteboard_query().where(Whiteboard.id == whiteboard_id)
    if current_workspace is not None:
        query = query.where(Whiteboard.workspace_id == current_workspace.id)
    return db.scalar(query)


def _get_pref_map(db: Session, user_id: str) -> dict[str, WhiteboardUserItemPref]:
    rows = list(
        db.scalars(
            select(WhiteboardUserItemPref).where(WhiteboardUserItemPref.user_id == user_id)
        )
    )
    return {row.whiteboard_id: row for row in rows}


def _get_or_create_pref(
    db: Session,
    user_id: str,
    whiteboard_id: str,
) -> WhiteboardUserItemPref:
    pref = db.scalar(
        select(WhiteboardUserItemPref).where(
            WhiteboardUserItemPref.user_id == user_id,
            WhiteboardUserItemPref.whiteboard_id == whiteboard_id,
        )
    )
    if pref is not None:
        return pref
    pref = WhiteboardUserItemPref(
        id=new_id(),
        user_id=user_id,
        whiteboard_id=whiteboard_id,
    )
    db.add(pref)
    db.flush()
    return pref


def _serialize_whiteboard_item(
    db: Session,
    whiteboard: Whiteboard,
    access: WhiteboardAccess,
    pref: WhiteboardUserItemPref | None,
) -> WhiteboardHubItem:
    workspace = _workspace_for_whiteboard(db, whiteboard)
    primary_container = _primary_container(whiteboard)
    containers = sorted(
        whiteboard.containers,
        key=lambda item: (
            0 if item.is_primary else 1,
            item.container_app,
            item.container_type,
            item.sort_order,
            item.created_at,
        ),
    )
    location_label = resolve_container_label(
        db=db,
        workspace=workspace,
        container=primary_container,
    )
    source_badge, source_deeplink = describe_source(
        workspace=workspace,
        whiteboard=whiteboard,
        primary_container=primary_container,
    )
    return WhiteboardHubItem(
        id=whiteboard.id,
        source_app=whiteboard.source_app,
        source_id=whiteboard.id,
        source_kind=whiteboard.source_kind,
        source_ref=whiteboard.source_ref,
        generation_kind=whiteboard.generation_kind,
        location_label=location_label,
        container_label=location_label,
        primary_container=_serialize_primary_container(primary_container),
        containers=[_serialize_container(container) for container in containers],
        source_badge=source_badge,
        source_deeplink=source_deeplink,
        title=whiteboard.title,
        created_by_id=whiteboard.owner_id,
        created_by_name=getattr(whiteboard.owner, "full_name", ""),
        created_at=whiteboard.created_at,
        updated_at=whiteboard.updated_at,
        trashed_at=whiteboard.trashed_at,
        is_favorite=bool(pref and pref.is_favorite),
        is_private=primary_container is None,
        last_viewed_at=pref.last_viewed_at if pref else None,
        can_view=access.can_view,
        can_edit=access.can_edit,
        can_share=access.can_share,
        can_manage=access.can_manage,
    )


def _serialize_whiteboard_detail(
    db: Session,
    whiteboard: Whiteboard,
    access: WhiteboardAccess,
    pref: WhiteboardUserItemPref | None,
) -> WhiteboardDetail:
    item = _serialize_whiteboard_item(db, whiteboard, access, pref)
    return WhiteboardDetail(
        **item.model_dump(),
        scene=whiteboard.scene or empty_scene(),
    )


def _whiteboard_from_item_or_404(
    db: Session,
    item_id: str,
    current_user: User,
    share_token: str | None = None,
) -> tuple[Whiteboard, WhiteboardAccess]:
    whiteboard = _load_whiteboard_for_access(db, item_id)
    if whiteboard is None:
        raise HTTPException(status_code=404, detail="Whiteboard not found.")
    access = _resolve_whiteboard_access(db, whiteboard, current_user, share_token=share_token)
    if not access.can_view or (whiteboard.trashed_at is not None and not access.can_manage):
        raise HTTPException(status_code=404, detail="Whiteboard not found.")
    return whiteboard, access


def _whiteboard_from_share_token_or_404(
    db: Session,
    share_token: str,
    current_user: User,
) -> tuple[Whiteboard, WhiteboardAccess]:
    whiteboard = db.scalar(
        _whiteboard_query()
        .join(WhiteboardLinkShare, WhiteboardLinkShare.whiteboard_id == Whiteboard.id)
        .where(
            WhiteboardLinkShare.token == share_token,
            WhiteboardLinkShare.active.is_(True),
        )
    )
    if whiteboard is None or whiteboard.trashed_at is not None:
        raise HTTPException(status_code=404, detail="Shared link not found.")
    access = _resolve_whiteboard_access(db, whiteboard, current_user, share_token=share_token)
    if not access.can_view:
        raise HTTPException(status_code=404, detail="Shared link not found.")
    return whiteboard, access


def _lookup_item(
    db: Session,
    item_id: str,
    current_user: User,
    share_token: str | None = None,
) -> WhiteboardDetail:
    whiteboard, access = _whiteboard_from_item_or_404(
        db,
        item_id,
        current_user,
        share_token=share_token,
    )
    return _serialize_whiteboard_detail(
        db,
        whiteboard,
        access,
        _get_pref_map(db, current_user.id).get(whiteboard.id),
    )


def _filter_whiteboards(
    whiteboards: list[WhiteboardHubItem],
    *,
    current_user_id: str,
    query: WhiteboardHubQuery,
) -> list[WhiteboardHubItem]:
    filtered = whiteboards
    if query.view == "mine":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.created_by_id == current_user_id
        ]
    elif query.view == "recent":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.last_viewed_at is not None
        ]
    elif query.view == "favorites":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.is_favorite
        ]
    elif query.view == "archived":
        filtered = [item for item in filtered if item.trashed_at is not None]
    else:
        filtered = [item for item in filtered if item.trashed_at is None]

    def container_matches(item: WhiteboardHubItem) -> bool:
        if not (query.container_app or query.container_type or query.container_id):
            return True
        return any(
            (query.container_app is None or container.app == query.container_app)
            and (query.container_type is None or container.type == query.container_type)
            and (query.container_id is None or container.id == query.container_id)
            for container in item.containers
        )

    if query.source_app:
        filtered = [item for item in filtered if item.source_app == query.source_app]
    if query.source_kind:
        filtered = [item for item in filtered if item.source_kind == query.source_kind]
    filtered = [item for item in filtered if container_matches(item)]

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


def _sort_whiteboards(
    whiteboards: list[WhiteboardHubItem],
    *,
    sort_by: str,
    sort_dir: Literal["asc", "desc"],
) -> list[WhiteboardHubItem]:
    reverse = sort_dir != "asc"

    def sort_key(item: WhiteboardHubItem):
        if sort_by == "title":
            return item.title.lower()
        if sort_by == "created_at":
            return item.created_at
        if sort_by == "last_viewed_at":
            return item.last_viewed_at or datetime.min
        if sort_by == "container_sort_order":
            return item.containers[0].sort_order if item.containers else 0
        return item.updated_at

    return sorted(whiteboards, key=sort_key, reverse=reverse)


def _upsert_primary_container(
    db: Session,
    *,
    whiteboard: Whiteboard,
    payload: UpdateWhiteboardContainerRequest,
    current_user: User,
) -> WhiteboardContainer:
    workspace = _workspace_for_whiteboard(db, whiteboard)
    ref = ContainerRef(app=payload.app, type=payload.type, id=payload.id)
    if not container_write_allowed(
        db=db,
        user=current_user,
        workspace=workspace,
        ref=ref,
    ):
        raise HTTPException(status_code=403, detail="Container edit access required.")
    if _is_singleton_context(ref):
        _delete_context_slot(db, ref=ref, except_whiteboard_id=whiteboard.id)

    for container in whiteboard.containers:
        container.is_primary = False
        db.add(container)

    existing = next(
        (
            container
            for container in whiteboard.containers
            if container.container_app == payload.app
            and container.container_type == payload.type
            and container.container_id == payload.id
        ),
        None,
    )
    if existing is None:
        existing = WhiteboardContainer(
            id=new_id(),
            whiteboard_id=whiteboard.id,
            container_app=payload.app,
            container_type=payload.type,
            container_id=payload.id,
            is_primary=True,
            sort_order=payload.sort_order,
            created_by_id=current_user.id,
        )
        db.add(existing)
        whiteboard.containers.append(existing)
    else:
        existing.is_primary = True
        existing.sort_order = payload.sort_order
        db.add(existing)
    db.flush()
    return existing


def _delete_primary_container(db: Session, whiteboard: Whiteboard) -> None:
    for container in list(whiteboard.containers):
        if container.is_primary:
            db.delete(container)


def _is_singleton_context(ref: ContainerRef) -> bool:
    return (
        (ref.app == "meeting" and ref.type == "meeting")
        or (ref.app == "pms" and ref.type == "task_list")
    )


def _require_context_write(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    ref: ContainerRef,
) -> None:
    if not container_write_allowed(db=db, user=user, workspace=workspace, ref=ref):
        raise HTTPException(status_code=403, detail="Container edit access required.")


def _find_context_slot(db: Session, ref: ContainerRef) -> WhiteboardContainer | None:
    return db.scalar(
        select(WhiteboardContainer)
        .options(selectinload(WhiteboardContainer.whiteboard))
        .where(
            WhiteboardContainer.container_app == ref.app,
            WhiteboardContainer.container_type == ref.type,
            WhiteboardContainer.container_id == ref.id,
        )
        .order_by(WhiteboardContainer.created_at.asc())
    )


def _delete_context_slot(
    db: Session,
    *,
    ref: ContainerRef,
    except_whiteboard_id: str | None = None,
) -> None:
    containers = list(
        db.scalars(
            select(WhiteboardContainer).where(
                WhiteboardContainer.container_app == ref.app,
                WhiteboardContainer.container_type == ref.type,
                WhiteboardContainer.container_id == ref.id,
            )
        )
    )
    deleted = False
    for container in containers:
        if except_whiteboard_id is not None and container.whiteboard_id == except_whiteboard_id:
            continue
        db.delete(container)
        deleted = True
    if deleted:
        db.flush()


def _attach_context_slot(
    db: Session,
    *,
    whiteboard: Whiteboard,
    ref: ContainerRef,
    current_user: User,
    is_primary: bool,
) -> WhiteboardContainer:
    existing = next(
        (
            container
            for container in whiteboard.containers
            if container.container_app == ref.app
            and container.container_type == ref.type
            and container.container_id == ref.id
        ),
        None,
    )
    if existing is None:
        existing = WhiteboardContainer(
            id=new_id(),
            whiteboard_id=whiteboard.id,
            container_app=ref.app,
            container_type=ref.type,
            container_id=ref.id,
            is_primary=is_primary,
            sort_order=0,
            created_by_id=current_user.id,
        )
        db.add(existing)
        whiteboard.containers.append(existing)
    else:
        existing.is_primary = existing.is_primary or is_primary
        existing.created_by_id = existing.created_by_id or current_user.id
        db.add(existing)
    db.flush()
    return existing


@router.get("/hub", response_model=WhiteboardHubResponse)
def list_whiteboard_hub(
    view: Literal["all", "mine", "recent", "favorites", "archived"] | None = Query(default=None),
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
) -> WhiteboardHubResponse:
    resolved_view = view or {
        "all": "all",
        "my": "mine",
        "mine": "mine",
        "recent": "recent",
        "favorite": "favorites",
        "favorites": "favorites",
        "archived": "archived",
    }.get(category or "all", "all")
    query = WhiteboardHubQuery(
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
    _ensure_whiteboard_workspace_access(db, current_user)
    pref_map = _get_pref_map(db, current_user.id)
    whiteboards = [
        _serialize_whiteboard_item(
            db,
            whiteboard,
            _resolve_whiteboard_access(db, whiteboard, current_user),
            pref_map.get(whiteboard.id),
        )
        for whiteboard in _load_accessible_whiteboards(db, current_user)
    ]
    whiteboards = _filter_whiteboards(whiteboards, current_user_id=current_user.id, query=query)
    whiteboards = _sort_whiteboards(whiteboards, sort_by=query.sort_by, sort_dir=query.sort_dir)
    total = len(whiteboards)
    start = (query.page - 1) * query.page_size
    end = start + query.page_size
    return WhiteboardHubResponse(
        items=whiteboards[start:end],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


@router.get("/contexts/slot", response_model=WhiteboardContextSlotResponse)
def get_whiteboard_context_slot(
    app: str = Query(..., min_length=1, max_length=64),
    type: str = Query(..., min_length=1, max_length=64),
    id: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardContextSlotResponse:
    workspace = _ensure_whiteboard_workspace_access(db, current_user)
    ref = ContainerRef(app=app, type=type, id=id)
    projection = project_container_access(db=db, user=current_user, workspace=workspace, ref=ref)
    if not projection.can_view:
        raise HTTPException(status_code=403, detail="Container access required.")
    slot = _find_context_slot(db, ref)
    if slot is None:
        return WhiteboardContextSlotResponse(item=None)
    return WhiteboardContextSlotResponse(item=_lookup_item(db, slot.whiteboard_id, current_user))


@router.post("/contexts/slot", response_model=WhiteboardDetail, status_code=status.HTTP_201_CREATED)
def create_whiteboard_context_slot(
    payload: CreateWhiteboardContextSlotRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    workspace = _ensure_whiteboard_workspace_access(db, current_user)
    ref = ContainerRef(app=payload.app, type=payload.type, id=payload.id)
    _require_context_write(db, workspace=workspace, user=current_user, ref=ref)
    if _is_singleton_context(ref):
        _delete_context_slot(db, ref=ref)
    whiteboard = create_whiteboard_for_user(
        db,
        workspace_id=workspace.id,
        owner_id=current_user.id,
        title=payload.title,
        source_app=payload.app,
        source_kind="manual",
        source_ref=payload.id,
        primary_container=(ref.app, ref.type, ref.id, 0),
    )
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.put("/contexts/slot", response_model=WhiteboardDetail)
def attach_whiteboard_context_slot(
    payload: AttachWhiteboardContextSlotRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    workspace = _ensure_whiteboard_workspace_access(db, current_user)
    ref = ContainerRef(app=payload.app, type=payload.type, id=payload.id)
    _require_context_write(db, workspace=workspace, user=current_user, ref=ref)
    whiteboard, _access = _whiteboard_from_item_or_404(db, payload.whiteboard_id, current_user)
    if _is_singleton_context(ref):
        _delete_context_slot(db, ref=ref, except_whiteboard_id=whiteboard.id)
    _attach_context_slot(
        db,
        whiteboard=whiteboard,
        ref=ref,
        current_user=current_user,
        is_primary=len(whiteboard.containers) == 0,
    )
    whiteboard.updated_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.delete("/contexts/slot", status_code=status.HTTP_204_NO_CONTENT)
def detach_whiteboard_context_slot(
    app: str = Query(..., min_length=1, max_length=64),
    type: str = Query(..., min_length=1, max_length=64),
    id: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    workspace = _ensure_whiteboard_workspace_access(db, current_user)
    ref = ContainerRef(app=app, type=type, id=id)
    _require_context_write(db, workspace=workspace, user=current_user, ref=ref)
    _delete_context_slot(db, ref=ref)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items", response_model=WhiteboardDetail, status_code=status.HTTP_201_CREATED)
def create_whiteboard_item(
    payload: CreateWhiteboardRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    workspace = _ensure_whiteboard_workspace_access(db, current_user)
    container_payload = payload.primary_container
    container_ref = (
        ContainerRef(
            app=container_payload.app,
            type=container_payload.type,
            id=container_payload.id,
        )
        if container_payload is not None
        else None
    )
    if container_ref is not None:
        _require_context_write(db, workspace=workspace, user=current_user, ref=container_ref)
        if _is_singleton_context(container_ref):
            _delete_context_slot(db, ref=container_ref)

    whiteboard = create_whiteboard_for_user(
        db,
        workspace_id=workspace.id,
        owner_id=current_user.id,
        title=payload.title,
        scene=payload.scene,
        source_app=payload.source_app,
        source_kind=payload.source_kind,
        source_ref=payload.source_ref,
        generation_kind=payload.generation_kind,
        primary_container=(
            (
                container_ref.app,
                container_ref.type,
                container_ref.id,
                container_payload.sort_order,
            )
            if container_payload is not None and container_ref is not None
            else None
        ),
    )
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.get("/items/{item_id}", response_model=WhiteboardDetail)
def get_whiteboard_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    return _lookup_item(db, item_id, current_user)


@router.patch("/items/{item_id}", response_model=WhiteboardDetail)
def update_whiteboard_item(
    item_id: str,
    payload: UpdateWhiteboardRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Whiteboard edit access required.")
    if payload.title is not None:
        if not access.can_manage:
            raise HTTPException(status_code=403, detail="Whiteboard manage access required.")
        whiteboard.title = payload.title.strip()
    if "scene" in payload.model_fields_set:
        whiteboard.scene = payload.scene or empty_scene()
    whiteboard.updated_at = _utcnow()
    if "scene" in payload.model_fields_set:
        sync_collab_record_from_rest_patch(db, whiteboard=whiteboard)
    db.add(whiteboard)
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_whiteboard_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_manage:
        raise HTTPException(status_code=403, detail="Whiteboard manage access required.")
    whiteboard.trashed_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/items/{item_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_whiteboard_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_manage:
        raise HTTPException(status_code=403, detail="Whiteboard manage access required.")
    if whiteboard.trashed_at is None:
        raise HTTPException(status_code=409, detail="Archive the whiteboard before permanent deletion.")

    db.execute(delete(WhiteboardCollabDocument).where(WhiteboardCollabDocument.whiteboard_id == whiteboard.id))
    db.execute(delete(WhiteboardUserItemPref).where(WhiteboardUserItemPref.whiteboard_id == whiteboard.id))
    db.execute(delete(WhiteboardUserShare).where(WhiteboardUserShare.whiteboard_id == whiteboard.id))
    db.execute(delete(WhiteboardLinkShare).where(WhiteboardLinkShare.whiteboard_id == whiteboard.id))
    db.execute(delete(WhiteboardContainer).where(WhiteboardContainer.whiteboard_id == whiteboard.id))
    db.execute(delete(Whiteboard).where(Whiteboard.id == whiteboard.id).execution_options(synchronize_session=False))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/items/{item_id}/container", response_model=WhiteboardDetail)
def update_whiteboard_container(
    item_id: str,
    payload: UpdateWhiteboardContainerRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Whiteboard edit access required.")
    _upsert_primary_container(db, whiteboard=whiteboard, payload=payload, current_user=current_user)
    whiteboard.updated_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.delete("/items/{item_id}/container", response_model=WhiteboardDetail)
def delete_whiteboard_container(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Whiteboard edit access required.")
    _delete_primary_container(db, whiteboard)
    whiteboard.updated_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.get("/shareable-users", response_model=list[ShareableUserItem])
def list_whiteboard_shareable_users(
    q: str = Query(default=""),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[ShareableUserItem]:
    current_workspace = _ensure_whiteboard_workspace_access(db, current_user)
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


def _serialize_sharing_response(whiteboard: Whiteboard) -> WhiteboardSharingResponse:
    link_share = next((item for item in whiteboard.link_shares if item.active), None)
    return WhiteboardSharingResponse(
        whiteboard_id=whiteboard.id,
        owner_id=whiteboard.owner_id,
        users=[
            WhiteboardUserShareItem(
                user_id=item.user_id,
                email=item.user.email,
                full_name=item.user.full_name,
                access_level=item.access_level,  # type: ignore[arg-type]
            )
            for item in sorted(
                whiteboard.user_shares,
                key=lambda row: (row.user.full_name.lower(), row.user.email.lower()),
            )
        ],
        link_share=(
            WhiteboardLinkShareItem(
                token=link_share.token,
                access_level=link_share.access_level,  # type: ignore[arg-type]
                active=link_share.active,
                share_path=f"/whiteboard/shared/{link_share.token}",
            )
            if link_share is not None
            else None
        ),
    )


def _load_whiteboard_for_share_or_403(
    db: Session,
    item_id: str,
    current_user: User,
) -> Whiteboard:
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_share:
        raise HTTPException(status_code=403, detail="Whiteboard share access required.")
    return whiteboard


@router.get("/items/{item_id}/sharing", response_model=WhiteboardSharingResponse)
def get_whiteboard_sharing(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard = _load_whiteboard_for_share_or_403(db, item_id, current_user)
    return _serialize_sharing_response(whiteboard)


@router.put("/items/{item_id}/sharing/users/{user_id}", response_model=WhiteboardSharingResponse)
def upsert_whiteboard_user_share(
    item_id: str,
    user_id: str,
    payload: UpsertUserShareRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard = _load_whiteboard_for_share_or_403(db, item_id, current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=409, detail="Owner already has full access.")
    target_user = db.scalar(select(User).where(User.id == user_id, User.status == "active"))
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if resolve_workspace_role(db, target_user, whiteboard.workspace_id) is None:
        raise HTTPException(
            status_code=409,
            detail="Shared users must be members of the same workspace.",
        )
    share = next((item for item in whiteboard.user_shares if item.user_id == user_id), None)
    if share is None:
        share = WhiteboardUserShare(
            id=new_id(),
            whiteboard_id=whiteboard.id,
            user_id=user_id,
            access_level=payload.access_level,
            created_by_id=current_user.id,
        )
        db.add(share)
    else:
        share.access_level = payload.access_level
        db.add(share)
    db.commit()
    whiteboard = _load_whiteboard_for_access(db, whiteboard.id)
    assert whiteboard is not None
    return _serialize_sharing_response(whiteboard)


@router.delete("/items/{item_id}/sharing/users/{user_id}", response_model=WhiteboardSharingResponse)
def delete_whiteboard_user_share(
    item_id: str,
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard = _load_whiteboard_for_share_or_403(db, item_id, current_user)
    share = next((item for item in whiteboard.user_shares if item.user_id == user_id), None)
    if share is not None:
        db.delete(share)
        db.commit()
    whiteboard = _load_whiteboard_for_access(db, whiteboard.id)
    assert whiteboard is not None
    return _serialize_sharing_response(whiteboard)


@router.put("/items/{item_id}/sharing/link", response_model=WhiteboardSharingResponse)
def upsert_whiteboard_link_share(
    item_id: str,
    payload: UpsertLinkShareRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard = _load_whiteboard_for_share_or_403(db, item_id, current_user)
    link_share = next(iter(whiteboard.link_shares), None)
    if link_share is None:
        link_share = WhiteboardLinkShare(
            id=new_id(),
            whiteboard_id=whiteboard.id,
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
    whiteboard = _load_whiteboard_for_access(db, whiteboard.id)
    assert whiteboard is not None
    return _serialize_sharing_response(whiteboard)


@router.delete("/items/{item_id}/sharing/link", response_model=WhiteboardSharingResponse)
def disable_whiteboard_link_share(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard = _load_whiteboard_for_share_or_403(db, item_id, current_user)
    link_share = next(iter(whiteboard.link_shares), None)
    if link_share is not None:
        link_share.active = False
        db.add(link_share)
        db.commit()
    whiteboard = _load_whiteboard_for_access(db, whiteboard.id)
    assert whiteboard is not None
    return _serialize_sharing_response(whiteboard)


@router.get("/collab/items/{item_id}/session", response_model=WhiteboardCollabSessionResponse)
def get_whiteboard_collab_session(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardCollabSessionResponse:
    _require_workspace_slug(request)
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    collab = ensure_collab_document_state(db, whiteboard=whiteboard)
    context = WhiteboardCollabContext(
        whiteboard_id=whiteboard.id,
        room_key=collab.room_key,
        can_edit=access.can_edit,
        scene=whiteboard.scene or empty_scene(),
        default_actor_user_id=whiteboard.owner_id,
    )
    db.commit()
    ws_path = request.url.path.removesuffix("/session") + "/ws"
    hub: WhiteboardCollabHub = request.app.state.whiteboard_collab
    return WhiteboardCollabSessionResponse(
        whiteboard_id=context.whiteboard_id,
        room_key=collab.room_key,
        ws_path=ws_path,
        can_edit=context.can_edit,
        realtime_status="enabled" if hub.relay_available else "degraded",
        read_only_reason=None if hub.relay_available else "relay_unavailable",
        user=WhiteboardCollabSessionUser(id=current_user.id, full_name=current_user.full_name),
        snapshot_scene=collab.snapshot_scene or context.scene,
        yjs_state=(
            base64.b64encode(collab.yjs_state).decode("ascii")
            if collab.yjs_state is not None
            else None
        ),
    )


@router.put("/collab/items/{item_id}/snapshot", response_model=WhiteboardCollabSnapshotResponse)
def save_whiteboard_collab_snapshot(
    item_id: str,
    payload: WhiteboardCollabSnapshotRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardCollabSnapshotResponse:
    _require_workspace_slug(request)
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Whiteboard edit access required.")

    scene = payload.scene or empty_scene()
    whiteboard.scene = scene
    whiteboard.updated_at = _utcnow()
    db.add(whiteboard)
    collab = update_collab_snapshot_record(
        db,
        whiteboard=whiteboard,
        snapshot_scene=scene,
        yjs_state=_decode_collab_yjs_state(payload.yjs_state),
    )
    db.commit()
    snapshot_at = collab.last_snapshot_at or _utcnow()
    return WhiteboardCollabSnapshotResponse(
        updated_at=whiteboard.updated_at,
        last_snapshot_at=snapshot_at,
    )


@ws_router.websocket("/collab/items/{item_id}/ws")
@ws_router.websocket("/collab/items/{item_id}/ws/{room_name}")
async def whiteboard_collab_websocket(
    websocket: WebSocket,
    item_id: str,
    room_name: str | None = None,
) -> None:
    await websocket.accept()

    monitor_task: asyncio.Task[None] | None = None
    room_key: str | None = None
    context: WhiteboardCollabContext | None = None
    hub: WhiteboardCollabHub = websocket.app.state.whiteboard_collab

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
            _bind_workspace_slug_for_collab(db, auth_context.user, workspace_slug)
            context = _resolve_whiteboard_collab_context(db, auth_context.user, item_id)
            if not context.can_edit:
                raise HTTPException(status_code=403, detail="Whiteboard edit access required.")
            whiteboard = _load_whiteboard_for_access(db, context.whiteboard_id)
            if whiteboard is None:
                raise HTTPException(status_code=404, detail="Whiteboard not found.")
            collab = ensure_collab_document_state(db, whiteboard=whiteboard)
            db.commit()
            collab_yjs_state = collab.yjs_state
        finally:
            db.close()

        if context is None:
            raise HTTPException(status_code=404, detail="Whiteboard not found.")

        room_key = context.room_key
        if room_name and room_name != room_key:
            raise HTTPException(status_code=404, detail="Room not found.")
        if not hub.relay_available:
            await websocket.close(code=1013, reason="Collaboration relay unavailable.")
            return

        runtime = await hub.get_room(context, collab_yjs_state)
        monitor_task = asyncio.create_task(
            _monitor_whiteboard_collab_access(
                websocket,
                workspace_slug=workspace_slug,
                item_id=item_id,
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


@public_router.get("/shared-links/{share_token}", response_model=ResolveWhiteboardSharedLinkResponse)
def resolve_whiteboard_shared_link(
    share_token: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ResolveWhiteboardSharedLinkResponse:
    whiteboard, access = _whiteboard_from_share_token_or_404(db, share_token, current_user)
    item = _serialize_whiteboard_item(
        db,
        whiteboard,
        access,
        _get_pref_map(db, current_user.id).get(whiteboard.id),
    )
    return ResolveWhiteboardSharedLinkResponse(item=item)


@public_router.get("/shared-links/{share_token}/item", response_model=WhiteboardDetail)
def get_shared_whiteboard_item(
    share_token: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    whiteboard, access = _whiteboard_from_share_token_or_404(db, share_token, current_user)
    return _serialize_whiteboard_detail(
        db,
        whiteboard,
        access,
        _get_pref_map(db, current_user.id).get(whiteboard.id),
    )


@public_router.patch("/shared-links/{share_token}/item", response_model=WhiteboardDetail)
def update_shared_whiteboard_item(
    share_token: str,
    payload: UpdateWhiteboardRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    whiteboard, access = _whiteboard_from_share_token_or_404(db, share_token, current_user)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Whiteboard edit access required.")
    if payload.title is not None:
        if not access.can_manage:
            raise HTTPException(status_code=403, detail="Whiteboard manage access required.")
        whiteboard.title = payload.title.strip()
    if "scene" in payload.model_fields_set:
        whiteboard.scene = payload.scene or empty_scene()
    whiteboard.updated_at = _utcnow()
    if "scene" in payload.model_fields_set:
        sync_collab_record_from_rest_patch(db, whiteboard=whiteboard)
    db.add(whiteboard)
    db.commit()
    return _serialize_whiteboard_detail(
        db,
        whiteboard,
        access,
        _get_pref_map(db, current_user.id).get(whiteboard.id),
    )


@public_router.post("/shared-links/{share_token}/view", status_code=status.HTTP_204_NO_CONTENT)
def record_shared_whiteboard_view(
    share_token: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    whiteboard, _access = _whiteboard_from_share_token_or_404(db, share_token, current_user)
    pref = _get_or_create_pref(db, current_user.id, whiteboard.id)
    pref.last_viewed_at = _utcnow()
    db.add(pref)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/items/{item_id}/favorite", response_model=ToggleFavoriteResponse)
def toggle_whiteboard_favorite(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ToggleFavoriteResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, _access = _whiteboard_from_item_or_404(db, item_id, current_user)
    pref = _get_or_create_pref(db, current_user.id, whiteboard.id)
    pref.is_favorite = not pref.is_favorite
    db.add(pref)
    db.commit()
    return ToggleFavoriteResponse(is_favorite=pref.is_favorite)


@router.post("/items/{item_id}/view", status_code=status.HTTP_204_NO_CONTENT)
def record_whiteboard_view(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, _access = _whiteboard_from_item_or_404(db, item_id, current_user)
    pref = _get_or_create_pref(db, current_user.id, whiteboard.id)
    pref.last_viewed_at = _utcnow()
    db.add(pref)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
