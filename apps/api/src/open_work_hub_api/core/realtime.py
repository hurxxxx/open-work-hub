from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Mapping
from contextlib import suppress
from threading import Lock
from typing import Any
from uuid import uuid4

from redis import asyncio as redis_asyncio
from redis.asyncio.client import PubSub

from open_work_hub_api.core.realtime_relay import (
    build_realtime_event_envelope,
    decode_realtime_relay_payload,
    encode_realtime_relay_payload,
    realtime_channel_name,
)

logger = logging.getLogger(__name__)


RealtimeEvent = Mapping[str, Any]
APP_REALTIME_CHANNEL_PREFIX = "open-work-hub:app-realtime"


class TopicRealtimeHub:
    """Small in-process fanout hub for realtime events keyed by topic."""

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[RealtimeEvent]]] = defaultdict(set)
        self._lock = Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def startup(self) -> None:
        self._loop = asyncio.get_running_loop()

    async def shutdown(self) -> None:
        with self._lock:
            queues = [queue for user_queues in self._queues.values() for queue in user_queues]
            self._queues.clear()
        for queue in queues:
            queue.put_nowait({"type": "hub.shutdown", "data": {}})

    def subscribe(self, topic: str) -> asyncio.Queue[RealtimeEvent]:
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._queues[topic].add(queue)
        return queue

    def unsubscribe(self, topic: str, queue: asyncio.Queue[RealtimeEvent]) -> None:
        with self._lock:
            queues = self._queues.get(topic)
            if queues is None:
                return
            queues.discard(queue)
            if not queues:
                self._queues.pop(topic, None)

    def publish(self, topic: str, event: RealtimeEvent) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        loop.call_soon_threadsafe(self._publish_nowait, topic, dict(event))

    def _publish_nowait(self, topic: str, event: RealtimeEvent) -> None:
        with self._lock:
            queues = list(self._queues.get(topic, ()))
        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)


class UserRealtimeHub(TopicRealtimeHub):
    """Small in-process fanout hub for per-user realtime events."""


def realtime_user_topic(user_id: str) -> str:
    return f"user:{user_id}"


class AppRealtimeHub(TopicRealtimeHub):
    """App event fanout backed by Redis Pub/Sub for cross-process delivery.

    Redis Pub/Sub is intentionally treated as at-most-once live invalidation.
    Consumers must refetch canonical state from HTTP APIs after reconnect.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        instance_id: str,
        channel_prefix: str = APP_REALTIME_CHANNEL_PREFIX,
    ) -> None:
        super().__init__()
        self._redis_url = redis_url
        self._instance_id = instance_id
        self._publisher_id = f"{instance_id}:{uuid4().hex}"
        self._channel_prefix = channel_prefix
        self._redis: redis_asyncio.Redis | None = None
        self._pubsub: PubSub | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._connect_lock = asyncio.Lock()
        self._stopping = False
        self._redis_available = False

    @property
    def redis_available(self) -> bool:
        return self._redis_available

    async def startup(self) -> None:
        await super().startup()
        self._stopping = False
        await self._connect_redis()
        if not self._redis_available:
            self._schedule_reconnect()

    async def shutdown(self) -> None:
        self._stopping = True
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            await asyncio.gather(self._reconnect_task, return_exceptions=True)
            self._reconnect_task = None
        await self._close_redis()
        self._redis_available = False
        await super().shutdown()

    def publish(self, topic: str, event: RealtimeEvent) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        envelope = self._event_envelope(topic, event)
        loop.call_soon_threadsafe(self._publish_nowait, topic, envelope)
        loop.call_soon_threadsafe(self._schedule_redis_publish, topic, envelope)

    def publish_user(self, user_id: str, event: RealtimeEvent) -> None:
        self.publish(realtime_user_topic(user_id), event)

    def _event_envelope(self, topic: str, event: RealtimeEvent) -> dict[str, Any]:
        return build_realtime_event_envelope(
            event,
            topic,
            now_ms=int(time.time() * 1000),
            event_id_factory=lambda: uuid4().hex,
        )

    def _schedule_redis_publish(self, topic: str, event: dict[str, Any]) -> None:
        if not self._redis_available or self._redis is None:
            return
        asyncio.create_task(self._publish_to_redis(topic, event))

    async def _publish_to_redis(self, topic: str, event: dict[str, Any]) -> None:
        if not self._redis_available or self._redis is None:
            return
        try:
            await self._redis.publish(
                self._channel_name(topic),
                encode_realtime_relay_payload(topic, event, self._publisher_id),
            )
        except Exception as exc:  # pragma: no cover - depends on local infra
            self._mark_redis_unavailable("publish failed", exc)

    async def _run_redis_listener(self) -> None:
        assert self._pubsub is not None
        try:
            while True:
                message = await self._pubsub.get_message(timeout=1.0)
                if message is None:
                    await asyncio.sleep(0.05)
                    continue
                self._handle_redis_message(message.get("data"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - depends on local infra
            self._mark_redis_unavailable("listener failed", exc)

    def _handle_redis_message(self, raw_payload: object) -> None:
        payload = decode_realtime_relay_payload(raw_payload, self._publisher_id)
        if payload is None:
            return
        self._publish_nowait(payload.topic, payload.event)

    def _channel_name(self, topic: str) -> str:
        return realtime_channel_name(self._channel_prefix, topic)

    async def _connect_redis(self) -> None:
        async with self._connect_lock:
            await self._close_redis()
            if self._stopping:
                return
            redis = redis_asyncio.from_url(self._redis_url)
            pubsub: PubSub | None = None
            try:
                await redis.ping()
                pubsub = redis.pubsub(ignore_subscribe_messages=True)
                await pubsub.psubscribe(realtime_channel_name(self._channel_prefix, "*"))
            except Exception as exc:  # pragma: no cover - depends on local infra
                logger.warning("App realtime Redis relay is unavailable: %s", exc)
                self._redis_available = False
                if pubsub is not None:
                    with suppress(Exception):
                        await pubsub.aclose()
                with suppress(Exception):
                    await redis.aclose()
                return
            self._redis = redis
            self._pubsub = pubsub
            self._listener_task = asyncio.create_task(self._run_redis_listener())
            self._redis_available = True

    async def _close_redis(self) -> None:
        listener_task = self._listener_task
        if listener_task is not None and listener_task is not asyncio.current_task():
            listener_task.cancel()
            await asyncio.gather(listener_task, return_exceptions=True)
        self._listener_task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.punsubscribe(realtime_channel_name(self._channel_prefix, "*"))
                await self._pubsub.aclose()
            except Exception as exc:  # pragma: no cover - defensive shutdown
                logger.debug("App realtime Redis pubsub close failed: %s", exc)
            self._pubsub = None
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception as exc:  # pragma: no cover - defensive shutdown
                logger.debug("App realtime Redis close failed: %s", exc)
            self._redis = None
        self._redis_available = False

    def _mark_redis_unavailable(self, context: str, exc: Exception) -> None:
        if self._redis_available:
            logger.warning("App realtime Redis relay %s: %s", context, exc)
        self._redis_available = False
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._stopping:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._run_reconnect_loop())

    async def _run_reconnect_loop(self) -> None:
        delay_seconds = 0.5
        try:
            while not self._stopping:
                await asyncio.sleep(delay_seconds)
                await self._connect_redis()
                if self._redis_available:
                    return
                delay_seconds = min(delay_seconds * 2, 5)
        except asyncio.CancelledError:
            raise


class InProcessAppRealtimeHub(AppRealtimeHub):
    """App realtime hub that keeps the production event envelope without Redis."""

    def __init__(self, *, instance_id: str) -> None:
        super().__init__("redis://in-process.invalid/0", instance_id=instance_id)

    @property
    def redis_available(self) -> bool:
        # This Adapter is intentionally usable as the available realtime runtime in
        # Docker-free tests. Production always uses ``AppRealtimeHub``.
        return True

    async def startup(self) -> None:
        await TopicRealtimeHub.startup(self)

    async def shutdown(self) -> None:
        await TopicRealtimeHub.shutdown(self)
