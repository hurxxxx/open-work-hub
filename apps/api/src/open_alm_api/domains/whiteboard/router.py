from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session, get_session_factory
from open_alm_api.core.i18n import (
    LocalizedApiMessage,
    localized_http_exception,
    select_locale,
    translate_message,
)
from open_alm_api.core.settings import get_settings
from open_alm_api.domains.auth.access import (
    bind_current_workspace,
    resolve_workspace_role,
)
from open_alm_api.domains.auth.dependencies import (
    require_current_user,
    resolve_auth_context_from_token,
)
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.collaboration.yjs_runtime import (
    CollabConnectionLimitExceeded,
    FastAPIYjsWebsocket,
)
from open_alm_api.domains.whiteboard.collab import (
    WhiteboardCollabContext,
    WhiteboardCollabHub,
)
from open_alm_api.domains.whiteboard.app_catalog import WHITEBOARD_WORKSPACE_APP
from open_alm_api.domains.whiteboard.item_mutations import (
    WhiteboardItemUpdateCommand,
    update_whiteboard_item as update_whiteboard_item_command,
)
from open_alm_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardCollabDocument,
    WhiteboardTarget,
    WhiteboardLinkShare,
    WhiteboardUserShare,
    WhiteboardUserItemPref,
    empty_scene,
)
from open_alm_api.domains.whiteboard.access import (
    WhiteboardAccess,
    ensure_whiteboard_workspace_access as _ensure_whiteboard_workspace_access,
    load_whiteboard_for_share_token_or_404,
    load_whiteboard_for_user_or_404,
)
from open_alm_api.domains.whiteboard.hub import (
    ResolveWhiteboardSharedLinkResponse,
    WhiteboardDetail,
    WhiteboardHubQuery,
    WhiteboardHubResponse,
    WhiteboardHubView,
    _attach_context_slot,
    _delete_context_slot,
    _delete_primary_target,
    _find_context_slot,
    _get_or_create_pref,
    _get_pref_map,
    _is_singleton_context,
    _lookup_item,
    _require_context_write,
    _serialize_whiteboard_detail,
    _serialize_whiteboard_item,
    _upsert_primary_target,
    build_whiteboard_hub_response,
    resolve_whiteboard_hub_view,
)
from open_alm_api.domains.whiteboard.registry import (
    TargetRef,
    project_target_access,
)
from open_alm_api.domains.usage.service import (
    USAGE_EVENT_CONTENT_VIEW,
    record_usage_event,
)
from open_alm_api.domains.whiteboard.service import create_whiteboard_for_user
from open_alm_api.domains.whiteboard.sharing import (
    WhiteboardSharingResponse,
    delete_whiteboard_user_share as delete_whiteboard_user_share_command,
    disable_whiteboard_link_share as disable_whiteboard_link_share_command,
    get_whiteboard_sharing_response,
    upsert_whiteboard_link_share as upsert_whiteboard_link_share_command,
    upsert_whiteboard_user_share as upsert_whiteboard_user_share_command,
)
from open_alm_api.domains.whiteboard.scene_state import (
    apply_collab_snapshot,
    ensure_collab_session_state,
)


require_whiteboard_app_enabled = require_workspace_app_enabled(
    WHITEBOARD_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/whiteboard",
    tags=["whiteboard"],
    dependencies=[Depends(require_whiteboard_app_enabled)],
)
public_router = APIRouter(prefix="/whiteboard", tags=["whiteboard"])
ws_router = APIRouter(prefix="/whiteboard", tags=["whiteboard"])


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class WhiteboardTargetPayload(BaseModel):
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
    primary_target: WhiteboardTargetPayload | None = None


class UpdateWhiteboardRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    scene: dict[str, Any] | None = None


class UpdateWhiteboardTargetRequest(BaseModel):
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


class UpsertUserShareRequest(BaseModel):
    access_level: Literal["read", "edit"]


class UpsertLinkShareRequest(BaseModel):
    access_level: Literal["read", "edit"]
    active: bool = True
    regenerate_token: bool = False


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
        raise localized_http_exception(
            status_code=400,
            code="whiteboard.workspace_slug_required",
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
        raise localized_http_exception(status_code=404, code="workspace.not_found")
    if resolve_workspace_role(db, user, workspace.id) is None:
        raise localized_http_exception(status_code=403, code="workspace.access_required")
    require_whiteboard_app_enabled(db=db, current_workspace=workspace)
    bind_current_workspace(db, workspace)
    return workspace


def _whiteboard_from_item_or_404(
    db: Session,
    item_id: str,
    current_user: User,
    share_token: str | None = None,
) -> tuple[Whiteboard, WhiteboardAccess]:
    context = load_whiteboard_for_user_or_404(
        db,
        item_id,
        current_user,
        share_token=share_token,
    )
    return context.whiteboard, context.access


def _whiteboard_from_share_token_or_404(
    db: Session,
    share_token: str,
    current_user: User,
) -> tuple[Whiteboard, WhiteboardAccess]:
    context = load_whiteboard_for_share_token_or_404(db, share_token, current_user)
    return context.whiteboard, context.access


def _decode_collab_yjs_state(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:  # pragma: no cover - defensive validation
        raise localized_http_exception(
            status_code=400,
            code="whiteboard.invalid_yjs_state",
        ) from exc


def _collab_ws_close_code_for_status(status_code: int) -> int:
    if status_code == 401:
        return 4401
    if status_code == 403:
        return 4403
    if status_code == 404:
        return 4404
    return 1011


def _websocket_locale(websocket: WebSocket) -> str:
    return select_locale(
        explicit_locale=websocket.headers.get("x-open-alm-locale"),
        accept_language=websocket.headers.get("accept-language"),
    )


def _websocket_message(websocket: WebSocket, code: str) -> str:
    return translate_message(LocalizedApiMessage(code=code), _websocket_locale(websocket))


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
    reason = (
        translate_message(exc.detail, _websocket_locale(websocket))
        if isinstance(exc.detail, LocalizedApiMessage)
        else str(exc.detail)
    )
    try:
        await websocket.close(
            code=_collab_ws_close_code_for_status(exc.status_code),
            reason=reason,
        )
    except RuntimeError as close_error:
        if "after sending 'websocket.close'" in str(close_error):
            return
        raise


def _ensure_whiteboard_collab_context(
    db: Session,
    user: User,
    item_id: str,
) -> tuple[WhiteboardCollabContext, WhiteboardCollabDocument]:
    _ensure_whiteboard_workspace_access(db, user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, user)
    scene_state = ensure_collab_session_state(db, whiteboard=whiteboard)
    assert scene_state.collab is not None
    context = WhiteboardCollabContext(
        whiteboard_id=whiteboard.id,
        room_key=scene_state.collab.room_key,
        can_edit=access.can_edit,
        scene=whiteboard.scene or empty_scene(),
        default_actor_user_id=whiteboard.owner_id,
    )
    return context, scene_state.collab


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
            _whiteboard, access = _whiteboard_from_item_or_404(db, item_id, auth_context.user)
            if not access.can_edit:
                await websocket.close(
                    code=4403,
                    reason=_websocket_message(
                        websocket,
                        "whiteboard.edit_access_required",
                    ),
                )
                return
        except HTTPException as exc:
            await _close_websocket_for_http_error(websocket, exc)
            return
        finally:
            db.close()


@router.get("/hub", response_model=WhiteboardHubResponse)
def list_whiteboard_hub(
    view: WhiteboardHubView | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str = Query(default=""),
    sort_by: str = Query(default="updated_at"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    source_app: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    space_id: str | None = Query(default=None),
    target_app: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardHubResponse:
    query = WhiteboardHubQuery(
        view=resolve_whiteboard_hub_view(view=view, category=category),
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
        source_app=source_app,
        source_kind=source_kind,
        space_id=space_id,
        target_app=target_app,
        target_type=target_type,
        target_id=target_id,
    )
    return build_whiteboard_hub_response(db, current_user=current_user, query=query)


@router.get("/contexts/slot", response_model=WhiteboardContextSlotResponse)
def get_whiteboard_context_slot(
    app: str = Query(..., min_length=1, max_length=64),
    type: str = Query(..., min_length=1, max_length=64),
    id: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardContextSlotResponse:
    workspace = _ensure_whiteboard_workspace_access(db, current_user)
    ref = TargetRef(app=app, type=type, id=id)
    projection = project_target_access(db=db, user=current_user, workspace=workspace, ref=ref)
    if not projection.can_view:
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.target_access_required",
        )
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
    ref = TargetRef(app=payload.app, type=payload.type, id=payload.id)
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
        primary_target=(ref.app, ref.type, ref.id, 0),
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
    ref = TargetRef(app=payload.app, type=payload.type, id=payload.id)
    _require_context_write(db, workspace=workspace, user=current_user, ref=ref)
    whiteboard, _access = _whiteboard_from_item_or_404(db, payload.whiteboard_id, current_user)
    if _is_singleton_context(ref):
        _delete_context_slot(db, ref=ref, except_whiteboard_id=whiteboard.id)
    _attach_context_slot(
        db,
        whiteboard=whiteboard,
        ref=ref,
        current_user=current_user,
        is_primary=len(whiteboard.targets) == 0,
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
    ref = TargetRef(app=app, type=type, id=id)
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
    target_payload = payload.primary_target
    target_ref = (
        TargetRef(
            app=target_payload.app,
            type=target_payload.type,
            id=target_payload.id,
        )
        if target_payload is not None
        else None
    )
    if target_ref is not None:
        _require_context_write(db, workspace=workspace, user=current_user, ref=target_ref)
        if _is_singleton_context(target_ref):
            _delete_context_slot(db, ref=target_ref)

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
        primary_target=(
            (
                target_ref.app,
                target_ref.type,
                target_ref.id,
                target_payload.sort_order,
            )
            if target_payload is not None and target_ref is not None
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
    update_whiteboard_item_command(
        db,
        WhiteboardItemUpdateCommand(
            whiteboard=whiteboard,
            access=access,
            title=payload.title,
            scene=payload.scene,
            update_scene="scene" in payload.model_fields_set,
        ),
    )
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
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.manage_access_required",
        )
    whiteboard.trashed_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items/{item_id}/restore", response_model=WhiteboardDetail)
def restore_whiteboard_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_manage:
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.manage_access_required",
        )
    if whiteboard.trashed_at is not None:
        whiteboard.trashed_at = None
        whiteboard.updated_at = _utcnow()
        db.add(whiteboard)
        db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.delete("/items/{item_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_whiteboard_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_manage:
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.manage_access_required",
        )
    if whiteboard.trashed_at is None:
        raise localized_http_exception(
            status_code=409,
            code="whiteboard.archive_before_permanent_delete",
        )

    db.execute(
        delete(WhiteboardCollabDocument).where(
            WhiteboardCollabDocument.whiteboard_id == whiteboard.id
        )
    )
    db.execute(
        delete(WhiteboardUserItemPref).where(WhiteboardUserItemPref.whiteboard_id == whiteboard.id)
    )
    db.execute(
        delete(WhiteboardUserShare).where(WhiteboardUserShare.whiteboard_id == whiteboard.id)
    )
    db.execute(
        delete(WhiteboardLinkShare).where(WhiteboardLinkShare.whiteboard_id == whiteboard.id)
    )
    db.execute(delete(WhiteboardTarget).where(WhiteboardTarget.whiteboard_id == whiteboard.id))
    db.execute(
        delete(Whiteboard)
        .where(Whiteboard.id == whiteboard.id)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/items/{item_id}/target", response_model=WhiteboardDetail)
def update_whiteboard_target(
    item_id: str,
    payload: UpdateWhiteboardTargetRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_edit:
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.edit_access_required",
        )
    _upsert_primary_target(db, whiteboard=whiteboard, payload=payload, current_user=current_user)
    whiteboard.updated_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.delete("/items/{item_id}/target", response_model=WhiteboardDetail)
def delete_whiteboard_target(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_edit:
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.edit_access_required",
        )
    _delete_primary_target(db, whiteboard)
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


@router.get("/items/{item_id}/sharing", response_model=WhiteboardSharingResponse)
def get_whiteboard_sharing(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    return get_whiteboard_sharing_response(db, item_id=item_id, current_user=current_user)


@router.put("/items/{item_id}/sharing/users/{user_id}", response_model=WhiteboardSharingResponse)
def upsert_whiteboard_user_share(
    item_id: str,
    user_id: str,
    payload: UpsertUserShareRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    return upsert_whiteboard_user_share_command(
        db,
        item_id=item_id,
        user_id=user_id,
        access_level=payload.access_level,
        current_user=current_user,
    )


@router.delete("/items/{item_id}/sharing/users/{user_id}", response_model=WhiteboardSharingResponse)
def delete_whiteboard_user_share(
    item_id: str,
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    return delete_whiteboard_user_share_command(
        db,
        item_id=item_id,
        user_id=user_id,
        current_user=current_user,
    )


@router.put("/items/{item_id}/sharing/link", response_model=WhiteboardSharingResponse)
def upsert_whiteboard_link_share(
    item_id: str,
    payload: UpsertLinkShareRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    return upsert_whiteboard_link_share_command(
        db,
        item_id=item_id,
        access_level=payload.access_level,
        active=payload.active,
        regenerate_token=payload.regenerate_token,
        current_user=current_user,
    )


@router.delete("/items/{item_id}/sharing/link", response_model=WhiteboardSharingResponse)
def disable_whiteboard_link_share(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardSharingResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    return disable_whiteboard_link_share_command(
        db,
        item_id=item_id,
        current_user=current_user,
    )


@router.get("/collab/items/{item_id}/session", response_model=WhiteboardCollabSessionResponse)
def get_whiteboard_collab_session(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardCollabSessionResponse:
    _require_workspace_slug(request)
    context, collab = _ensure_whiteboard_collab_context(db, current_user, item_id)
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
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.edit_access_required",
        )

    scene = payload.scene or empty_scene()
    yjs_state = _decode_collab_yjs_state(payload.yjs_state)
    scene_state = apply_collab_snapshot(
        db,
        whiteboard=whiteboard,
        scene=scene,
        yjs_state=yjs_state,
    )
    assert scene_state.collab is not None
    collab = scene_state.collab
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
    yjs_websocket: FastAPIYjsWebsocket | None = None
    runtime = None
    auth_user_id: str | None = None
    slot_acquired = False
    hub: WhiteboardCollabHub = websocket.app.state.whiteboard_collab

    try:
        token = await _resolve_collab_ws_token(websocket)
        workspace_slug = websocket.path_params.get("workspace_slug")
        if not workspace_slug:
            raise localized_http_exception(
                status_code=400,
                code="whiteboard.workspace_slug_required",
            )

        session_factory = get_session_factory()
        db = session_factory()
        collab_yjs_state: bytes | None = None
        try:
            auth_context = resolve_auth_context_from_token(db, token)
            auth_user_id = auth_context.user.id
            _bind_workspace_slug_for_collab(db, auth_context.user, workspace_slug)
            context, collab = _ensure_whiteboard_collab_context(db, auth_context.user, item_id)
            if not context.can_edit:
                raise localized_http_exception(
                    status_code=403,
                    code="whiteboard.edit_access_required",
                )
            db.commit()
            collab_yjs_state = collab.yjs_state
        finally:
            db.close()

        if context is None:
            raise localized_http_exception(status_code=404, code="whiteboard.not_found")

        room_key = context.room_key
        if room_name and room_name != room_key:
            raise localized_http_exception(status_code=404, code="whiteboard.room_not_found")
        if not hub.relay_available:
            await websocket.close(
                code=1013,
                reason=_websocket_message(
                    websocket,
                    "whiteboard.collab_relay_unavailable",
                ),
            )
            return

        runtime = await hub.get_room(context, collab_yjs_state)
        try:
            await hub.acquire_connection_slot(runtime, auth_user_id)
            slot_acquired = True
        except CollabConnectionLimitExceeded as exc:
            await websocket.close(code=exc.close_code, reason=exc.reason)
            return
        monitor_task = asyncio.create_task(
            _monitor_whiteboard_collab_access(
                websocket,
                workspace_slug=workspace_slug,
                item_id=item_id,
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


@public_router.get(
    "/shared-links/{share_token}", response_model=ResolveWhiteboardSharedLinkResponse
)
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
    update_whiteboard_item_command(
        db,
        WhiteboardItemUpdateCommand(
            whiteboard=whiteboard,
            access=access,
            title=payload.title,
            scene=payload.scene,
            update_scene="scene" in payload.model_fields_set,
        ),
    )
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
    record_usage_event(
        db,
        actor_user_id=current_user.id,
        workspace_id=whiteboard.workspace_id,
        app_id="whiteboard",
        event_type=USAGE_EVENT_CONTENT_VIEW,
        content_kind="whiteboard",
        content_id=whiteboard.id,
        content_title=whiteboard.title,
        source="whiteboard.item.view",
    )
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
