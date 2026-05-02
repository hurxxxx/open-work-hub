from __future__ import annotations

import asyncio
import base64
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
import y_py as Y
from ypy_websocket.yroom import YRoom
from ypy_websocket.yutils import YMessageType

from aidoo_api.core.db import get_session_factory
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.collab import RedisCollabBus
from aidoo_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardCollabDocument,
    empty_scene,
)


logger = logging.getLogger(__name__)

COLLAB_RELAY_CHANNEL_PREFIX = "whiteboard-collab"
COLLAB_CLOSE_CODE_RELAY_UNAVAILABLE = 1013
REMOTE_UPDATE_HASH_CACHE_SIZE = 512


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def make_whiteboard_room_key(whiteboard_id: str) -> str:
    return f"whiteboard:{whiteboard_id}"


@dataclass(frozen=True)
class WhiteboardCollabContext:
    whiteboard_id: str
    room_key: str
    can_edit: bool
    scene: dict[str, Any]
    default_actor_user_id: str


@dataclass
class WhiteboardRoomRuntime:
    room_key: str
    whiteboard_id: str
    default_actor_user_id: str
    room: YRoom
    room_task: asyncio.Task[None]
    relay_task: asyncio.Task[None] | None = None
    relay_pubsub: object | None = None
    flush_task: asyncio.Task[None] | None = None
    flush_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_editor_user_id: str | None = None
    recent_remote_update_hashes: OrderedDict[str, None] = field(default_factory=OrderedDict)


def get_collab_document(
    db: Session,
    *,
    whiteboard_id: str,
) -> WhiteboardCollabDocument | None:
    return db.scalar(
        select(WhiteboardCollabDocument).where(
            WhiteboardCollabDocument.whiteboard_id == whiteboard_id,
        )
    )


def ensure_collab_document_state(
    db: Session,
    *,
    whiteboard: Whiteboard,
    reset_stale_yjs_state: bool = True,
) -> WhiteboardCollabDocument:
    room_key = make_whiteboard_room_key(whiteboard.id)
    collab = get_collab_document(db, whiteboard_id=whiteboard.id)
    snapshot_scene = whiteboard.scene or empty_scene()
    if collab is None:
        collab = WhiteboardCollabDocument(
            id=new_id(),
            room_key=room_key,
            whiteboard_id=whiteboard.id,
            snapshot_scene=snapshot_scene,
            last_snapshot_at=whiteboard.updated_at,
        )
        db.add(collab)
        db.flush()
        return collab

    if collab.snapshot_scene is None:
        collab.snapshot_scene = snapshot_scene
        collab.last_snapshot_at = whiteboard.updated_at
        db.add(collab)
        db.flush()
    elif reset_stale_yjs_state and collab.updated_at < whiteboard.updated_at:
        collab.yjs_state = None
        collab.snapshot_scene = snapshot_scene
        collab.last_snapshot_at = whiteboard.updated_at
        db.add(collab)
        db.flush()
    return collab


def update_collab_snapshot_record(
    db: Session,
    *,
    whiteboard: Whiteboard,
    snapshot_scene: dict[str, Any] | None,
    yjs_state: bytes | None,
) -> WhiteboardCollabDocument:
    collab = ensure_collab_document_state(
        db,
        whiteboard=whiteboard,
        reset_stale_yjs_state=False,
    )
    collab.snapshot_scene = snapshot_scene or empty_scene()
    collab.yjs_state = yjs_state
    collab.last_snapshot_at = _utcnow()
    db.add(collab)
    db.flush()
    return collab


def sync_collab_record_from_rest_patch(db: Session, *, whiteboard: Whiteboard) -> None:
    collab = get_collab_document(db, whiteboard_id=whiteboard.id)
    if collab is None:
        return
    collab.yjs_state = None
    collab.snapshot_scene = whiteboard.scene or empty_scene()
    collab.last_snapshot_at = _utcnow()
    db.add(collab)
    db.flush()


def _persist_whiteboard_runtime_state_sync(
    session_factory: Any,
    *,
    whiteboard_id: str,
    yjs_state: bytes,
) -> None:
    db = session_factory()
    try:
        whiteboard = db.scalar(select(Whiteboard).where(Whiteboard.id == whiteboard_id))
        if whiteboard is None:
            return
        collab = ensure_collab_document_state(
            db,
            whiteboard=whiteboard,
            reset_stale_yjs_state=False,
        )
        collab.yjs_state = yjs_state
        db.add(collab)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class WhiteboardCollabBus(RedisCollabBus):
    @staticmethod
    def channel_name(room_key: str) -> str:
        return f"{COLLAB_RELAY_CHANNEL_PREFIX}:{room_key}"


class WhiteboardCollabHub:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = asyncio.Lock()
        self._rooms: dict[str, WhiteboardRoomRuntime] = {}
        self._session_factory = get_session_factory()
        self._instance_id = self._settings.instance_id or new_id()
        self._bus = WhiteboardCollabBus(
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

    async def get_room(
        self,
        context: WhiteboardCollabContext,
        yjs_state: bytes | None,
    ) -> WhiteboardRoomRuntime:
        async with self._lock:
            runtime = self._rooms.get(context.room_key)
            if runtime is not None:
                return runtime

            room = YRoom(ready=True, log=logger)
            room_task = asyncio.create_task(room.start())
            await room.started.wait()
            if yjs_state:
                Y.apply_update(room.ydoc, yjs_state)

            runtime = WhiteboardRoomRuntime(
                room_key=context.room_key,
                whiteboard_id=context.whiteboard_id,
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

    async def _run_room_relay_listener(self, runtime: WhiteboardRoomRuntime) -> None:
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

    async def _apply_remote_relay_message(
        self,
        runtime: WhiteboardRoomRuntime,
        raw_payload: object,
    ) -> None:
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
        runtime: WhiteboardRoomRuntime,
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

    def _schedule_flush(self, runtime: WhiteboardRoomRuntime) -> None:
        if runtime.flush_task is not None:
            runtime.flush_task.cancel()
        runtime.flush_task = asyncio.create_task(self._flush_after_delay(runtime))

    async def _flush_after_delay(self, runtime: WhiteboardRoomRuntime) -> None:
        try:
            await asyncio.sleep(self._settings.collab_snapshot_debounce_ms / 1000)
            await self._flush_runtime(runtime)
        except asyncio.CancelledError:
            return

    async def _flush_runtime(self, runtime: WhiteboardRoomRuntime) -> None:
        async with runtime.flush_lock:
            yjs_state = Y.encode_state_as_update(runtime.room.ydoc)
            try:
                await asyncio.to_thread(
                    _persist_whiteboard_runtime_state_sync,
                    self._session_factory,
                    whiteboard_id=runtime.whiteboard_id,
                    yjs_state=yjs_state,
                )
            except Exception as exc:
                logger.exception("Failed to persist whiteboard collaboration room %s: %s", runtime.room_key, exc)

    async def _handle_relay_failure(self, exc: Exception) -> None:
        if not self._bus.available:
            return
        logger.warning("Whiteboard collaboration relay failed: %s", exc)
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
    def _remember_remote_hash(runtime: WhiteboardRoomRuntime, update_hash: str) -> None:
        runtime.recent_remote_update_hashes[update_hash] = None
        runtime.recent_remote_update_hashes.move_to_end(update_hash)
        if len(runtime.recent_remote_update_hashes) > REMOTE_UPDATE_HASH_CACHE_SIZE:
            runtime.recent_remote_update_hashes.popitem(last=False)

    @staticmethod
    def _consume_remote_hash(runtime: WhiteboardRoomRuntime, update_hash: str) -> bool:
        if update_hash not in runtime.recent_remote_update_hashes:
            return False
        runtime.recent_remote_update_hashes.pop(update_hash, None)
        return True
