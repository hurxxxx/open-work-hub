from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import json
import logging
from typing import Any

import y_py as Y
from ypy_websocket.yroom import YRoom
from ypy_websocket.yutils import YMessageType

from open_alm_api.core.db import get_session_factory
from open_alm_api.core.settings import get_settings
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.collaboration.yjs_runtime import (
    COLLAB_CLOSE_CODE_RELAY_UNAVAILABLE,
    CollabConnectionLimitExceeded,
    CollabBus,
    CollabRoomRuntime,
    RedisCollabBus,
    hash_bytes,
    release_yroom_thread_bound_state,
)
from open_alm_api.domains.whiteboard.scene_state import persist_runtime_yjs_state


logger = logging.getLogger(__name__)

COLLAB_RELAY_CHANNEL_PREFIX = "whiteboard-collab"


@dataclass(frozen=True)
class WhiteboardCollabContext:
    whiteboard_id: str
    room_key: str
    can_edit: bool
    scene: dict[str, Any]
    default_actor_user_id: str


class WhiteboardCollabHub:
    def __init__(
        self,
        *,
        instance_id: str | None = None,
        bus: CollabBus | None = None,
    ) -> None:
        self._settings = get_settings()
        self._lock = asyncio.Lock()
        self._rooms: dict[str, CollabRoomRuntime] = {}
        self._session_factory = get_session_factory()
        self._instance_id = instance_id or self._settings.instance_id or new_id()
        self._bus = bus
        if self._bus is None:
            self._bus = RedisCollabBus(
                self._settings.collab_redis_url,
                instance_id=self._instance_id,
                channel_prefix=COLLAB_RELAY_CHANNEL_PREFIX,
                operation_timeout_seconds=self._settings.collab_cleanup_timeout_seconds,
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
    ) -> CollabRoomRuntime:
        async with self._lock:
            runtime = self._rooms.get(context.room_key)
            if runtime is not None:
                return runtime

            room = YRoom(ready=True, log=logger)
            room_task = asyncio.create_task(room.start())
            await room.started.wait()
            if yjs_state:
                Y.apply_update(room.ydoc, yjs_state)

            runtime = CollabRoomRuntime(
                room_key=context.room_key,
                default_actor_user_id=context.default_actor_user_id,
                room=room,
                room_task=room_task,
                metadata={"whiteboard_id": context.whiteboard_id},
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

    async def acquire_connection_slot(
        self,
        runtime: CollabRoomRuntime,
        user_id: str,
    ) -> None:
        async with self._lock:
            if self._rooms.get(runtime.room_key) is not runtime:
                raise RuntimeError("Collaboration room is no longer active.")
            if runtime.active_connection_count >= self._settings.collab_max_room_clients:
                raise CollabConnectionLimitExceeded()
            user_count = runtime.active_user_connections.get(user_id, 0)
            if user_count >= self._settings.collab_max_user_room_connections:
                raise CollabConnectionLimitExceeded()
            runtime.active_connection_count += 1
            runtime.active_user_connections[user_id] = user_count + 1
            logger.info(
                "Whiteboard collaboration connection accepted: room_key=%s user_id=%s "
                "room_connections=%s user_room_connections=%s",
                runtime.room_key,
                user_id,
                runtime.active_connection_count,
                runtime.active_user_connections[user_id],
            )

    async def release_connection_slot(
        self,
        runtime: CollabRoomRuntime,
        user_id: str,
    ) -> None:
        async with self._lock:
            user_count = runtime.active_user_connections.get(user_id, 0)
            if user_count <= 1:
                runtime.active_user_connections.pop(user_id, None)
            else:
                runtime.active_user_connections[user_id] = user_count - 1
            runtime.active_connection_count = max(0, runtime.active_connection_count - 1)
            logger.info(
                "Whiteboard collaboration connection released: room_key=%s user_id=%s "
                "room_connections=%s user_room_connections=%s",
                runtime.room_key,
                user_id,
                runtime.active_connection_count,
                runtime.active_user_connections.get(user_id, 0),
            )

    async def cleanup_room(self, room_key: str) -> None:
        async with self._lock:
            runtime = self._rooms.get(room_key)
            if runtime is None or runtime.room.clients or runtime.active_connection_count:
                return
            self._rooms.pop(room_key, None)

        if runtime.flush_task is not None:
            runtime.flush_task.cancel()
            await self._run_cleanup_step(
                runtime,
                "flush task cancellation",
                asyncio.gather(runtime.flush_task, return_exceptions=True),
            )
        await self._run_cleanup_step(runtime, "flush", self._flush_runtime(runtime))
        if runtime.relay_task is not None:
            runtime.relay_task.cancel()
            await self._run_cleanup_step(
                runtime,
                "relay task cancellation",
                asyncio.gather(runtime.relay_task, return_exceptions=True),
            )
        if runtime.relay_pubsub is not None:
            await self._run_cleanup_step(
                runtime,
                "relay pubsub close",
                self._bus.close_pubsub(runtime.relay_pubsub, runtime.room_key),
            )
        self._stop_room(runtime)
        await self._run_cleanup_step(
            runtime,
            "room task stop",
            asyncio.gather(runtime.room_task, return_exceptions=True),
        )
        self._release_room_state(runtime)

    async def shutdown(self) -> None:
        async with self._lock:
            runtimes = list(self._rooms.values())
            self._rooms.clear()

        for runtime in runtimes:
            if runtime.flush_task is not None:
                runtime.flush_task.cancel()
                await self._run_cleanup_step(
                    runtime,
                    "flush task cancellation",
                    asyncio.gather(runtime.flush_task, return_exceptions=True),
                )
            await self._run_cleanup_step(runtime, "flush", self._flush_runtime(runtime))
            for client in list(runtime.room.clients):
                await client.close(code=1001, reason="Server shutdown.")
            if runtime.relay_task is not None:
                runtime.relay_task.cancel()
                await self._run_cleanup_step(
                    runtime,
                    "relay task cancellation",
                    asyncio.gather(runtime.relay_task, return_exceptions=True),
                )
            if runtime.relay_pubsub is not None:
                await self._run_cleanup_step(
                    runtime,
                    "relay pubsub close",
                    self._bus.close_pubsub(runtime.relay_pubsub, runtime.room_key),
                )
            self._stop_room(runtime)
            await self._run_cleanup_step(
                runtime,
                "room task stop",
                asyncio.gather(runtime.room_task, return_exceptions=True),
            )
            self._release_room_state(runtime)

        await self._bus.shutdown()

    async def _run_cleanup_step(
        self,
        runtime: CollabRoomRuntime,
        label: str,
        awaitable,
    ) -> None:
        try:
            await asyncio.wait_for(
                awaitable,
                timeout=self._settings.collab_cleanup_timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "Timed out during whiteboard collaboration cleanup: room_key=%s step=%s",
                runtime.room_key,
                label,
            )
        except Exception as exc:
            logger.warning(
                "Failed during whiteboard collaboration cleanup: room_key=%s step=%s error=%s",
                runtime.room_key,
                label,
                exc,
            )

    def _stop_room(self, runtime: CollabRoomRuntime) -> None:
        try:
            runtime.room.stop()
        except RuntimeError:
            return

    def _release_room_state(self, runtime: CollabRoomRuntime) -> None:
        try:
            release_yroom_thread_bound_state(runtime.room)
        except Exception as exc:
            logger.warning(
                "Failed to release whiteboard collaboration room state: room_key=%s error=%s",
                runtime.room_key,
                exc,
            )

    async def _run_room_relay_listener(self, runtime: CollabRoomRuntime) -> None:
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
        runtime: CollabRoomRuntime,
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
                update_hash = hash_bytes(data)
            runtime.remember_remote_update_hash(update_hash)
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
        update_hash = hash_bytes(update)
        should_publish = not runtime.consume_remote_update_hash(update_hash)
        self._schedule_flush(runtime)
        if should_publish and self._bus.available:
            asyncio.create_task(self._publish_update(runtime, update, update_hash))

    async def _publish_update(
        self,
        runtime: CollabRoomRuntime,
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

    def _schedule_flush(self, runtime: CollabRoomRuntime) -> None:
        if runtime.flush_task is not None:
            runtime.flush_task.cancel()
        runtime.flush_task = asyncio.create_task(self._flush_after_delay(runtime))

    async def _flush_after_delay(self, runtime: CollabRoomRuntime) -> None:
        try:
            await asyncio.sleep(self._settings.collab_snapshot_debounce_ms / 1000)
            await self._flush_runtime(runtime)
        except asyncio.CancelledError:
            return

    async def _flush_runtime(self, runtime: CollabRoomRuntime) -> None:
        async with runtime.flush_lock:
            yjs_state = bytes(Y.encode_state_as_update(runtime.room.ydoc))
            try:
                await asyncio.to_thread(
                    persist_runtime_yjs_state,
                    self._session_factory,
                    whiteboard_id=runtime.metadata["whiteboard_id"],
                    yjs_state=yjs_state,
                )
            except Exception as exc:
                logger.exception(
                    "Failed to persist whiteboard collaboration room %s: %s", runtime.room_key, exc
                )

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
