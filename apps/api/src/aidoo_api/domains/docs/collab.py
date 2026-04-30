from __future__ import annotations

import asyncio
import base64
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import logging

from fastapi import HTTPException, WebSocket
from redis import asyncio as redis_asyncio
from redis.asyncio.client import PubSub
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload, selectinload
from starlette.websockets import WebSocketDisconnect, WebSocketState
from uvicorn.protocols.utils import ClientDisconnected
import y_py as Y
from ypy_websocket.yroom import YRoom
from ypy_websocket.yutils import YMessageType

from aidoo_api.core.db import get_session_factory
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.auth.access import (
    load_active_workspace_by_key,
    resolve_workspace_role,
    workspace_role_allows,
)
from aidoo_api.domains.auth.models import User
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.collab_codec import blocks_to_yjs_state, yjs_state_to_blocks
from aidoo_api.domains.docs.models import (
    DocMeetingAccess,
    DocsCollabDocument,
    NativeDoc,
    NativeDocPage,
    NativeDocUserShare,
)
from aidoo_api.domains.docs.registry import ContainerRef, project_container_access
from aidoo_api.domains.media.service import sync_embedded_media
from aidoo_api.domains.search.hooks import enqueue_doc_search_index


logger = logging.getLogger(__name__)

PAGE_SOURCE_NATIVE_DOC = "native_doc_page"

COLLAB_RELAY_CHANNEL_PREFIX = "docs-collab"
COLLAB_CLOSE_CODE_RELAY_UNAVAILABLE = 1013
REMOTE_UPDATE_HASH_CACHE_SIZE = 512


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
    default_actor_user_id: str


@dataclass
class RoomRuntime:
    room_key: str
    source_type: str
    source_page_id: str
    default_actor_user_id: str
    room: YRoom
    room_task: asyncio.Task[None]
    relay_task: asyncio.Task[None] | None = None
    relay_pubsub: PubSub | None = None
    flush_task: asyncio.Task[None] | None = None
    flush_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_editor_user_id: str | None = None
    recent_remote_update_hashes: OrderedDict[str, None] = field(default_factory=OrderedDict)


class RedisCollabBus:
    def __init__(self, redis_url: str, *, instance_id: str) -> None:
        self._redis_url = redis_url
        self.instance_id = instance_id
        self._redis: redis_asyncio.Redis | None = None
        self._available = False
        self._failure_reason: str | None = None

    @property
    def available(self) -> bool:
        return self._available

    @property
    def failure_reason(self) -> str | None:
        return self._failure_reason

    async def startup(self) -> None:
        self._redis = redis_asyncio.from_url(self._redis_url)
        try:
            await self._redis.ping()
            self._available = True
            self._failure_reason = None
        except Exception as exc:
            logger.warning("Docs collaboration relay is unavailable: %s", exc)
            self._available = False
            self._failure_reason = "relay_unavailable"

    async def shutdown(self) -> None:
        self._available = False
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def create_pubsub(self, room_key: str) -> PubSub:
        if not self._available or self._redis is None:
            raise RuntimeError("Collaboration relay is unavailable.")
        channel = self.channel_name(room_key)
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(channel)
        return pubsub

    async def publish(self, room_key: str, payload: dict[str, object]) -> None:
        if not self._available or self._redis is None:
            raise RuntimeError("Collaboration relay is unavailable.")
        await self._redis.publish(
            self.channel_name(room_key),
            json.dumps(payload).encode("utf-8"),
        )

    def mark_failed(self, *, reason: str = "relay_unavailable") -> None:
        self._available = False
        self._failure_reason = reason

    @staticmethod
    def channel_name(room_key: str) -> str:
        return f"{COLLAB_RELAY_CHANNEL_PREFIX}:{room_key}"


def _load_native_page_for_collab(db: Session, page_id: str) -> NativeDocPage | None:
    return db.scalar(
        select(NativeDocPage)
        .options(
            selectinload(NativeDocPage.created_by),
            joinedload(NativeDocPage.doc)
            .selectinload(NativeDoc.containers),
            joinedload(NativeDocPage.doc)
            .selectinload(NativeDoc.user_shares)
            .selectinload(NativeDocUserShare.user),
        )
        .where(NativeDocPage.id == page_id)
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
        container_access_level = None
        for container in page.doc.containers:
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
            candidate = (
                "edit"
                if projection.can_edit or projection.can_manage
                else "read" if projection.can_view else None
            )
            if candidate == "edit":
                container_access_level = "edit"
                break
            if container_access_level is None and candidate == "read":
                container_access_level = "read"
        access_level = None
        for candidate in (
            getattr(direct_share, "access_level", None),
            getattr(meeting_grant, "access_level", None),
            container_access_level,
        ):
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
        default_actor_user_id=page.created_by_id,
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
    """Get-or-create the collab document row for a page.

    Two concurrent calls (e.g. two meeting-notes sessions opened at the same
    instant) both missed the cache and raced to ``INSERT``, producing
    ``UniqueViolation`` on ``uq_docs_collab_documents_room_key``. Use a
    Postgres upsert (``INSERT ... ON CONFLICT DO NOTHING``) so the racing
    insert is absorbed silently; whichever transaction wins owns the row
    and the other re-queries it after the conflict.
    """
    existing = get_collab_document(
        db,
        source_type=source_type,
        source_page_id=source_page_id,
    )
    if existing is not None:
        if existing.room_key != room_key:
            existing.room_key = room_key
        if existing.snapshot_content_blocks is None and snapshot_content_blocks is not None:
            existing.snapshot_content_blocks = snapshot_content_blocks
        db.add(existing)
        db.flush()
        return existing

    stmt = (
        pg_insert(DocsCollabDocument)
        .values(
            id=new_id(),
            room_key=room_key,
            source_type=source_type,
            source_page_id=source_page_id,
            snapshot_content_blocks=snapshot_content_blocks,
        )
        .on_conflict_do_nothing(
            index_elements=[DocsCollabDocument.room_key],
        )
    )
    db.execute(stmt)
    db.flush()

    # Re-fetch the canonical row. With DO NOTHING we cannot rely on RETURNING,
    # so we always read back the state the winning transaction left us.
    collab = get_collab_document(
        db,
        source_type=source_type,
        source_page_id=source_page_id,
    )
    if collab is None:
        # Extremely unlikely but not impossible if a concurrent delete raced
        # between our upsert and re-read. Fall back to a hard insert and let
        # any error propagate.
        raise RuntimeError(
            "Collab document disappeared immediately after upsert. "
            f"source_type={source_type} source_page_id={source_page_id}"
        )
    if collab.snapshot_content_blocks is None and snapshot_content_blocks is not None:
        collab.snapshot_content_blocks = snapshot_content_blocks
        db.add(collab)
        db.flush()
    return collab


def ensure_collab_document_state(
    db: Session,
    *,
    source_type: str,
    source_page_id: str,
    room_key: str,
    snapshot_content_blocks: list[dict] | None,
) -> DocsCollabDocument:
    collab = ensure_collab_document(
        db,
        source_type=source_type,
        source_page_id=source_page_id,
        room_key=room_key,
        snapshot_content_blocks=snapshot_content_blocks,
    )
    if collab.yjs_state is None and snapshot_content_blocks is not None:
        collab.yjs_state = blocks_to_yjs_state(snapshot_content_blocks)
        collab.snapshot_content_blocks = snapshot_content_blocks
        collab.last_snapshot_at = collab.last_snapshot_at or _utcnow()
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
        yjs_state=blocks_to_yjs_state(snapshot_content_blocks),
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
        enqueue_doc_search_index(db, doc=page.doc, operation="upsert")
        return

    raise HTTPException(status_code=404, detail="Page not found.")


def materialize_collab_room_state(
    db: Session,
    *,
    source_type: str,
    source_page_id: str,
    room_key: str,
    yjs_state: bytes,
    actor_user_id: str,
    fallback_actor_user_id: str,
) -> DocsCollabDocument:
    content_blocks = yjs_state_to_blocks(yjs_state)
    actor = db.scalar(select(User).where(User.id == actor_user_id))
    if actor is None:
        actor = db.scalar(select(User).where(User.id == fallback_actor_user_id))
    if actor is None:
        raise HTTPException(status_code=404, detail="Collaboration actor not found.")

    persist_collab_snapshot_to_page(
        db,
        current_user=actor,
        source_type=source_type,
        source_page_id=source_page_id,
        content_blocks=content_blocks,
    )
    return update_collab_snapshot_record(
        db,
        source_type=source_type,
        source_page_id=source_page_id,
        room_key=room_key,
        snapshot_content_blocks=content_blocks,
        yjs_state=yjs_state,
    )


class FastAPIYjsWebsocket:
    def __init__(
        self,
        websocket: WebSocket,
        path: str,
        room_runtime: RoomRuntime,
        user_id: str,
    ):
        self._websocket = websocket
        self._path = path
        self._room_runtime = room_runtime
        self._user_id = user_id

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
        if payload and payload[0] == YMessageType.SYNC:
            self._room_runtime.last_editor_user_id = self._user_id
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
        self._settings = get_settings()
        self._lock = asyncio.Lock()
        self._rooms: dict[str, RoomRuntime] = {}
        self._session_factory = get_session_factory()
        self._instance_id = self._settings.instance_id or new_id()
        self._bus = RedisCollabBus(
            self._settings.collab_redis_url,
            instance_id=self._instance_id,
        )

    @property
    def relay_available(self) -> bool:
        return self._bus.available

    @property
    def relay_read_only_reason(self) -> str | None:
        return self._bus.failure_reason

    async def startup(self) -> None:
        await self._bus.startup()

    async def get_room(self, context: CollabPageContext, yjs_state: bytes | None) -> RoomRuntime:
        async with self._lock:
            runtime = self._rooms.get(context.room_key)
            if runtime is not None:
                return runtime

            room = YRoom(ready=True, log=logger)
            room_task = asyncio.create_task(room.start())
            await room.started.wait()
            if yjs_state:
                Y.apply_update(room.ydoc, yjs_state)

            runtime = RoomRuntime(
                room_key=context.room_key,
                source_type=context.source_type,
                source_page_id=context.source_page_id,
                default_actor_user_id=context.default_actor_user_id,
                room=room,
                room_task=room_task,
            )
            room.on_message = lambda message, room_key=context.room_key: self._handle_room_message(
                room_key,
                message,
            )
            room.ydoc.observe_after_transaction(
                lambda event, room_key=context.room_key: self._handle_room_update(
                    room_key,
                    event.get_update(),
                )
            )
            if self._bus.available:
                runtime.relay_pubsub = await self._bus.create_pubsub(context.room_key)
                runtime.relay_task = asyncio.create_task(self._run_room_relay_listener(runtime))
            self._rooms[context.room_key] = runtime
            return runtime

    async def cleanup_room(self, room_key: str) -> None:
        async with self._lock:
            runtime = self._rooms.get(room_key)
            if runtime is None or runtime.room.clients:
                return
            self._rooms.pop(room_key, None)

        if runtime.flush_task is not None:
            runtime.flush_task.cancel()
            await asyncio.gather(runtime.flush_task, return_exceptions=True)
        await self._flush_runtime(runtime)
        if runtime.relay_task is not None:
            runtime.relay_task.cancel()
            await asyncio.gather(runtime.relay_task, return_exceptions=True)
        if runtime.relay_pubsub is not None:
            await runtime.relay_pubsub.unsubscribe(self._bus.channel_name(runtime.room_key))
            await runtime.relay_pubsub.aclose()
        runtime.room.stop()
        await asyncio.gather(runtime.room_task, return_exceptions=True)

    async def shutdown(self) -> None:
        async with self._lock:
            runtimes = list(self._rooms.values())
            self._rooms.clear()

        for runtime in runtimes:
            if runtime.flush_task is not None:
                runtime.flush_task.cancel()
                await asyncio.gather(runtime.flush_task, return_exceptions=True)
            await self._flush_runtime(runtime)
            for client in list(runtime.room.clients):
                await client.close(code=1001, reason="Server shutdown.")
            if runtime.relay_task is not None:
                runtime.relay_task.cancel()
                await asyncio.gather(runtime.relay_task, return_exceptions=True)
            if runtime.relay_pubsub is not None:
                await runtime.relay_pubsub.unsubscribe(self._bus.channel_name(runtime.room_key))
                await runtime.relay_pubsub.aclose()
            runtime.room.stop()
            await asyncio.gather(runtime.room_task, return_exceptions=True)

        await self._bus.shutdown()

    async def _run_room_relay_listener(self, runtime: RoomRuntime) -> None:
        assert runtime.relay_pubsub is not None
        try:
            while True:
                message = await runtime.relay_pubsub.get_message(timeout=1.0)
                if message is None:
                    await asyncio.sleep(0.05)
                    continue
                await self._apply_remote_relay_message(runtime, message["data"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._handle_relay_failure(exc)

    async def _apply_remote_relay_message(self, runtime: RoomRuntime, raw_payload: object) -> None:
        if not isinstance(raw_payload, (bytes, bytearray)):
            return
        payload = json.loads(raw_payload.decode("utf-8"))
        if payload.get("instance_id") == self._instance_id:
            return
        if payload.get("room_key") != runtime.room_key:
            return

        encoded_data = payload.get("data")
        if not isinstance(encoded_data, str):
            return
        data = base64.b64decode(encoded_data.encode("ascii"))

        if payload.get("type") == "yjs_update":
            update_hash = payload.get("hash")
            if not isinstance(update_hash, str):
                update_hash = _hash_bytes(data)
            self._remember_remote_hash(runtime, update_hash)
            actor_user_id = payload.get("actor_user_id")
            if isinstance(actor_user_id, str) and actor_user_id:
                runtime.last_editor_user_id = actor_user_id
            Y.apply_update(runtime.room.ydoc, data)
            return

        if payload.get("type") == "awareness":
            for client in list(runtime.room.clients):
                await client.send(data)

    def _handle_room_message(self, room_key: str, message: bytes) -> bool:
        if not message or not self._bus.available:
            return False
        if message[0] == YMessageType.AWARENESS:
            asyncio.create_task(self._publish_awareness(room_key, message))
        return False

    def _handle_room_update(self, room_key: str, update: bytes) -> None:
        runtime = self._rooms.get(room_key)
        if runtime is None:
            return
        update_hash = _hash_bytes(update)
        should_publish = not self._consume_remote_hash(runtime, update_hash)
        self._schedule_flush(runtime)
        if should_publish and self._bus.available:
            asyncio.create_task(self._publish_update(runtime, update, update_hash))

    async def _publish_update(
        self,
        runtime: RoomRuntime,
        update: bytes,
        update_hash: str,
    ) -> None:
        try:
            await self._bus.publish(
                runtime.room_key,
                {
                    "instance_id": self._instance_id,
                    "room_key": runtime.room_key,
                    "type": "yjs_update",
                    "hash": update_hash,
                    "actor_user_id": runtime.last_editor_user_id,
                    "data": base64.b64encode(update).decode("ascii"),
                },
            )
        except Exception as exc:
            await self._handle_relay_failure(exc)

    async def _publish_awareness(self, room_key: str, message: bytes) -> None:
        try:
            await self._bus.publish(
                room_key,
                {
                    "instance_id": self._instance_id,
                    "room_key": room_key,
                    "type": "awareness",
                    "data": base64.b64encode(message).decode("ascii"),
                },
            )
        except Exception as exc:
            await self._handle_relay_failure(exc)

    def _schedule_flush(self, runtime: RoomRuntime) -> None:
        if runtime.flush_task is not None:
            runtime.flush_task.cancel()
        runtime.flush_task = asyncio.create_task(self._flush_after_delay(runtime))

    async def _flush_after_delay(self, runtime: RoomRuntime) -> None:
        try:
            await asyncio.sleep(self._settings.collab_snapshot_debounce_ms / 1000)
            await self._flush_runtime(runtime)
        except asyncio.CancelledError:
            return

    async def _flush_runtime(self, runtime: RoomRuntime) -> None:
        async with runtime.flush_lock:
            yjs_state = Y.encode_state_as_update(runtime.room.ydoc)
            actor_user_id = runtime.last_editor_user_id or runtime.default_actor_user_id
            try:
                await asyncio.to_thread(
                    self._persist_runtime_state_sync,
                    source_type=runtime.source_type,
                    source_page_id=runtime.source_page_id,
                    room_key=runtime.room_key,
                    fallback_actor_user_id=runtime.default_actor_user_id,
                    yjs_state=yjs_state,
                    actor_user_id=actor_user_id,
                )
            except Exception as exc:
                logger.exception("Failed to persist docs collaboration room %s: %s", runtime.room_key, exc)

    def _persist_runtime_state_sync(
        self,
        *,
        source_type: str,
        source_page_id: str,
        room_key: str,
        fallback_actor_user_id: str,
        yjs_state: bytes,
        actor_user_id: str,
    ) -> None:
        db = self._session_factory()
        try:
            materialize_collab_room_state(
                db,
                source_type=source_type,
                source_page_id=source_page_id,
                room_key=room_key,
                yjs_state=yjs_state,
                actor_user_id=actor_user_id,
                fallback_actor_user_id=fallback_actor_user_id,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def _handle_relay_failure(self, exc: Exception) -> None:
        if not self._bus.available:
            return
        logger.warning("Docs collaboration relay failed: %s", exc)
        self._bus.mark_failed()
        async with self._lock:
            runtimes = list(self._rooms.values())
        for runtime in runtimes:
            for client in list(runtime.room.clients):
                await client.close(
                    code=COLLAB_CLOSE_CODE_RELAY_UNAVAILABLE,
                    reason="Collaboration relay unavailable.",
                )

    @staticmethod
    def _remember_remote_hash(runtime: RoomRuntime, update_hash: str) -> None:
        runtime.recent_remote_update_hashes[update_hash] = None
        runtime.recent_remote_update_hashes.move_to_end(update_hash)
        if len(runtime.recent_remote_update_hashes) > REMOTE_UPDATE_HASH_CACHE_SIZE:
            runtime.recent_remote_update_hashes.popitem(last=False)

    @staticmethod
    def _consume_remote_hash(runtime: RoomRuntime, update_hash: str) -> bool:
        if update_hash not in runtime.recent_remote_update_hashes:
            return False
        runtime.recent_remote_update_hashes.pop(update_hash, None)
        return True
