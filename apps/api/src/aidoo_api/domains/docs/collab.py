from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import gc
import logging

from fastapi import HTTPException, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload
from uvicorn.protocols.utils import ClientDisconnected
import y_py as Y
from ypy_websocket.yroom import YRoom

from aidoo_api.domains.auth.access import (
    load_active_workspace_by_key,
    resolve_team_role,
    resolve_workspace_role,
    team_role_allows,
    workspace_role_allows,
)
from aidoo_api.domains.auth.models import Team, User
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.models import (
    DocMeetingAccess,
    DocsCollabDocument,
    NativeDoc,
    NativeDocPage,
    NativeDocUserShare,
)
from aidoo_api.domains.media.router import sync_embedded_media
from aidoo_api.domains.pms.models import SpaceDoc, SpaceDocPage


logger = logging.getLogger(__name__)

PAGE_SOURCE_NATIVE_DOC = "native_doc_page"
PAGE_SOURCE_PMS_SPACE_DOC = "pms_space_doc_page"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def make_page_ref(source_type: str, source_page_id: str) -> str:
    return f"{source_type}__{source_page_id}"


def split_page_ref(page_ref: str) -> tuple[str | None, str]:
    if "__" not in page_ref:
        return None, page_ref
    return tuple(page_ref.split("__", 1))  # type: ignore[return-value]


def make_room_key(source_type: str, source_page_id: str) -> str:
    return f"{source_type}:{source_page_id}"


@dataclass(frozen=True)
class CollabPageContext:
    page_ref: str
    source_type: str
    source_page_id: str
    room_key: str
    can_edit: bool
    content_blocks: list[dict] | None


def _load_native_page_for_collab(db: Session, page_id: str) -> NativeDocPage | None:
    return db.scalar(
        select(NativeDocPage)
        .options(
            selectinload(NativeDocPage.created_by),
            joinedload(NativeDocPage.doc)
            .selectinload(NativeDoc.user_shares)
            .selectinload(NativeDocUserShare.user),
        )
        .where(NativeDocPage.id == page_id)
    )


def _load_space_page_for_collab(db: Session, page_id: str) -> SpaceDocPage | None:
    return db.scalar(
        select(SpaceDocPage)
        .options(
            selectinload(SpaceDocPage.created_by),
            joinedload(SpaceDocPage.doc),
        )
        .where(SpaceDocPage.id == page_id)
    )


def _resolve_native_page_context(
    db: Session,
    user: User,
    workspace_slug: str,
    page_id: str,
) -> CollabPageContext:
    workspace = load_active_workspace_by_key(db, workspace_slug)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if not workspace_role_allows(resolve_workspace_role(db, user, workspace.id), "member"):
        raise HTTPException(status_code=403, detail="Workspace access required.")

    page = _load_native_page_for_collab(db, page_id)
    if page is None or page.doc is None or page.trashed_at is not None or page.doc.trashed_at is not None:
        raise HTTPException(status_code=404, detail="Page not found.")
    if page.doc.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Page not found.")

    if page.doc.owner_id == user.id:
        can_view = True
        can_edit = True
    else:
        direct_share = next((share for share in page.doc.user_shares if share.user_id == user.id), None)
        meeting_grant = db.scalar(
            select(DocMeetingAccess).where(
                DocMeetingAccess.doc_id == page.doc_id,
                DocMeetingAccess.user_id == user.id,
                DocMeetingAccess.revoked_at.is_(None),
                (
                    DocMeetingAccess.expires_at.is_(None)
                    | (DocMeetingAccess.expires_at > _utcnow())
                ),
            )
        )
        access_level = None
        for candidate in (getattr(direct_share, "access_level", None), getattr(meeting_grant, "access_level", None)):
            if candidate == "edit":
                access_level = "edit"
                break
            if access_level is None and candidate == "read":
                access_level = "read"
        can_view = access_level in {"read", "edit"}
        can_edit = access_level == "edit"

    if not can_view:
        raise HTTPException(status_code=404, detail="Page not found.")

    return CollabPageContext(
        page_ref=make_page_ref(PAGE_SOURCE_NATIVE_DOC, page.id),
        source_type=PAGE_SOURCE_NATIVE_DOC,
        source_page_id=page.id,
        room_key=make_room_key(PAGE_SOURCE_NATIVE_DOC, page.id),
        can_edit=can_edit,
        content_blocks=page.content_blocks,
    )


def _resolve_space_page_context(
    db: Session,
    user: User,
    workspace_slug: str,
    page_id: str,
) -> CollabPageContext:
    workspace = load_active_workspace_by_key(db, workspace_slug)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if not workspace_role_allows(resolve_workspace_role(db, user, workspace.id), "member"):
        raise HTTPException(status_code=403, detail="Workspace access required.")

    page = _load_space_page_for_collab(db, page_id)
    if page is None or page.doc is None or page.trashed_at is not None or page.doc.trashed_at is not None:
        raise HTTPException(status_code=404, detail="Page not found.")

    team = db.scalar(
        select(Team).where(
            Team.id == page.team_id,
            Team.workspace_id == workspace.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
        )
    )
    if team is None:
        raise HTTPException(status_code=404, detail="Page not found.")

    role = resolve_team_role(db, user, team)
    if not team_role_allows(role, "viewer"):
        raise HTTPException(status_code=404, detail="Page not found.")

    return CollabPageContext(
        page_ref=make_page_ref(PAGE_SOURCE_PMS_SPACE_DOC, page.id),
        source_type=PAGE_SOURCE_PMS_SPACE_DOC,
        source_page_id=page.id,
        room_key=make_room_key(PAGE_SOURCE_PMS_SPACE_DOC, page.id),
        can_edit=team_role_allows(role, "member"),
        content_blocks=page.content_blocks,
    )


def resolve_collab_page_context(
    db: Session,
    user: User,
    workspace_slug: str,
    page_ref: str,
) -> CollabPageContext:
    source_type, source_page_id = split_page_ref(page_ref)
    if source_type == PAGE_SOURCE_NATIVE_DOC:
        return _resolve_native_page_context(db, user, workspace_slug, source_page_id)
    if source_type == PAGE_SOURCE_PMS_SPACE_DOC:
        return _resolve_space_page_context(db, user, workspace_slug, source_page_id)
    raise HTTPException(status_code=404, detail="Page not found.")


def get_collab_document(
    db: Session,
    *,
    source_type: str,
    source_page_id: str,
) -> DocsCollabDocument | None:
    return db.scalar(
        select(DocsCollabDocument).where(
            DocsCollabDocument.source_type == source_type,
            DocsCollabDocument.source_page_id == source_page_id,
        )
    )


def ensure_collab_document(
    db: Session,
    *,
    source_type: str,
    source_page_id: str,
    room_key: str,
    snapshot_content_blocks: list[dict] | None,
) -> DocsCollabDocument:
    existing = get_collab_document(
        db,
        source_type=source_type,
        source_page_id=source_page_id,
    )
    if existing is not None:
        if existing.snapshot_content_blocks is None and snapshot_content_blocks is not None:
            existing.snapshot_content_blocks = snapshot_content_blocks
            db.add(existing)
        return existing

    collab = DocsCollabDocument(
        id=new_id(),
        room_key=room_key,
        source_type=source_type,
        source_page_id=source_page_id,
        snapshot_content_blocks=snapshot_content_blocks,
    )
    db.add(collab)
    db.flush()
    return collab


def update_collab_snapshot_record(
    db: Session,
    *,
    source_type: str,
    source_page_id: str,
    room_key: str,
    snapshot_content_blocks: list[dict] | None,
    yjs_state: bytes | None,
) -> DocsCollabDocument:
    collab = ensure_collab_document(
        db,
        source_type=source_type,
        source_page_id=source_page_id,
        room_key=room_key,
        snapshot_content_blocks=snapshot_content_blocks,
    )
    collab.snapshot_content_blocks = snapshot_content_blocks
    collab.yjs_state = yjs_state
    collab.last_snapshot_at = _utcnow()
    db.add(collab)
    db.flush()
    return collab


def sync_collab_record_from_rest_patch(
    db: Session,
    *,
    source_type: str,
    source_page_id: str,
    snapshot_content_blocks: list[dict] | None,
) -> None:
    update_collab_snapshot_record(
        db,
        source_type=source_type,
        source_page_id=source_page_id,
        room_key=make_room_key(source_type, source_page_id),
        snapshot_content_blocks=snapshot_content_blocks,
        yjs_state=None,
    )


def delete_collab_document(
    db: Session,
    *,
    source_type: str,
    source_page_id: str,
) -> None:
    db.execute(
        delete(DocsCollabDocument).where(
            DocsCollabDocument.source_type == source_type,
            DocsCollabDocument.source_page_id == source_page_id,
        )
    )


def persist_collab_snapshot_to_page(
    db: Session,
    *,
    current_user: User,
    source_type: str,
    source_page_id: str,
    content_blocks: list[dict] | None,
) -> None:
    if source_type == PAGE_SOURCE_NATIVE_DOC:
        page = _load_native_page_for_collab(db, source_page_id)
        if page is None or page.doc is None or page.trashed_at is not None or page.doc.trashed_at is not None:
            raise HTTPException(status_code=404, detail="Page not found.")
        page.content_blocks = content_blocks
        sync_embedded_media(db, content_blocks, "docs_native_page", page.id, current_user)
        db.add(page)
        db.flush()
        return

    if source_type == PAGE_SOURCE_PMS_SPACE_DOC:
        page = _load_space_page_for_collab(db, source_page_id)
        if page is None or page.doc is None or page.trashed_at is not None or page.doc.trashed_at is not None:
            raise HTTPException(status_code=404, detail="Page not found.")
        page.content_blocks = content_blocks
        sync_embedded_media(db, content_blocks, "space_doc_page", page.id, current_user)
        db.add(page)
        db.flush()
        return

    raise HTTPException(status_code=404, detail="Page not found.")


class FastAPIYjsWebsocket:
    def __init__(self, websocket: WebSocket, path: str):
        self._websocket = websocket
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self.recv()
        except Exception as exc:  # pragma: no cover - ypy-websocket expects StopAsyncIteration
            raise StopAsyncIteration() from exc

    async def recv(self) -> bytes:
        message = await self._websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise RuntimeError("WebSocket disconnected.")
        payload = message.get("bytes")
        if payload is None:
            raise RuntimeError("Unexpected non-binary WebSocket frame.")
        return payload

    async def send(self, message: bytes) -> None:
        if not self._is_connected():
            return
        try:
            await self._websocket.send_bytes(message)
        except (ClientDisconnected, WebSocketDisconnect, RuntimeError) as exc:
            if self._is_closed_send_error(exc):
                return
            raise

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        if not self._is_connected():
            return
        try:
            await self._websocket.close(code=code, reason=reason)
        except (ClientDisconnected, WebSocketDisconnect, RuntimeError) as exc:
            if self._is_closed_send_error(exc):
                return
            raise

    def _is_connected(self) -> bool:
        return (
            self._websocket.client_state == WebSocketState.CONNECTED
            and self._websocket.application_state == WebSocketState.CONNECTED
        )

    @staticmethod
    def _is_closed_send_error(exc: Exception) -> bool:
        if isinstance(exc, (ClientDisconnected, WebSocketDisconnect)):
            return True
        message = str(exc)
        return (
            "after sending 'websocket.close'" in message
            or "Cannot call \"send\" once a close message has been sent." in message
            or "no close frame received or sent" in message
        )


class DocsCollabHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._rooms: dict[str, YRoom] = {}
        self._room_tasks: dict[str, asyncio.Task[None]] = {}

    async def get_room(self, room_key: str, yjs_state: bytes | None) -> YRoom:
        async with self._lock:
            room = self._rooms.get(room_key)
            if room is not None:
                return room

            room = YRoom(ready=True, log=logger)
            room_task = asyncio.create_task(room.start())
            await room.started.wait()
            if yjs_state:
                Y.apply_update(room.ydoc, yjs_state)
            self._rooms[room_key] = room
            self._room_tasks[room_key] = room_task
            return room

    async def cleanup_room(self, room_key: str) -> None:
        async with self._lock:
            room = self._rooms.get(room_key)
            if room is None or room.clients:
                return
            room_task = self._room_tasks.pop(room_key, None)
            room.stop()
            self._rooms.pop(room_key, None)
            if room_task is not None:
                await asyncio.gather(room_task, return_exceptions=True)
            # y_py documents must be collected on the same thread they were created on.
            gc.collect()

    async def shutdown(self) -> None:
        async with self._lock:
            room_tasks = list(self._room_tasks.values())
            for room in self._rooms.values():
                for client in list(room.clients):
                    await client.close(code=1001, reason="Server shutdown.")
                room.stop()
            self._rooms.clear()
            self._room_tasks.clear()
            if room_tasks:
                await asyncio.gather(*room_tasks, return_exceptions=True)
            gc.collect()
