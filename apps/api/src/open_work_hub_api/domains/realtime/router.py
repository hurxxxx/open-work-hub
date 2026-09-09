from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, status
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.i18n import (
    LocalizedApiMessage,
    localized_http_exception,
    select_locale,
    translate_message,
)
from open_work_hub_api.core.realtime import (
    AppRealtimeHub,
    RealtimeEvent,
    realtime_user_topic,
)
from open_work_hub_api.domains.auth.dependencies import resolve_auth_context_from_token
from open_work_hub_api.domains.notifications import (
    realtime_event_types as notification_realtime_event_types,
)
from open_work_hub_api.domains.notifications import service as notification_service
from open_work_hub_api.domains.realtime import realtime_event_types
from open_work_hub_api.domains.realtime.resource_subscriptions import (
    ResourceSubscription,
    authorize_resource_event,
    requested_resource_subscription,
    resolve_resource_subscription,
)
from open_work_hub_api.domains.realtime.user_events import authorize_user_event

ws_router = APIRouter(prefix="/realtime", tags=["realtime"])
REALTIME_ACCESS_RECHECK_SECONDS = 60
SubscriptionId = tuple[str, str, str | None]


@dataclass
class ActiveSubscription:
    topic: str
    queue: asyncio.Queue[RealtimeEvent]
    relay_task: asyncio.Task[None] | None = None
    client_payload: dict[str, Any] | None = None
    resource: ResourceSubscription | None = None
    ref_count: int = 1
    active: bool = True


@dataclass(frozen=True)
class OutboundEvent:
    event: RealtimeEvent
    subscription: ActiveSubscription | None = None


@ws_router.websocket("/ws")
async def app_realtime_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    hub: AppRealtimeHub = websocket.app.state.app_realtime
    outbound: asyncio.Queue[OutboundEvent] = asyncio.Queue(maxsize=200)
    subscriptions: dict[SubscriptionId, ActiveSubscription] = {}
    try:
        token = await _resolve_ws_token(websocket)
        user_id = await run_in_threadpool(_resolve_user_id_from_token, token)
    except HTTPException as exc:
        await _close_for_http_error(websocket, exc)
        return

    user_subscription = _subscribe_topic(hub, realtime_user_topic(user_id), outbound)
    try:
        initial_unread_count = await run_in_threadpool(_unread_count_for_user, user_id)
        await _ensure_current_session(token=token, user_id=user_id)
        await websocket.send_json({"type": realtime_event_types.REALTIME_AUTH_OK, "data": {}})
        await websocket.send_json(
            {
                "type": notification_realtime_event_types.NOTIFICATION_SNAPSHOT,
                "data": {"notification": None, "unread_count": initial_unread_count},
            }
        )
        sender_task = asyncio.create_task(
            _send_outbound_events(
                websocket,
                outbound,
                hub=hub,
                subscriptions=subscriptions,
                token=token,
                user_id=user_id,
            )
        )
        receiver_task = asyncio.create_task(
            _receive_client_messages(
                websocket,
                hub=hub,
                outbound=outbound,
                subscriptions=subscriptions,
                token=token,
                user_id=user_id,
            )
        )
        monitor_task = asyncio.create_task(
            _monitor_realtime_access(
                websocket,
                token=token,
                user_id=user_id,
                subscriptions=subscriptions,
                outbound=outbound,
            )
        )
        done, pending = await asyncio.wait(
            {sender_task, receiver_task, monitor_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except WebSocketDisconnect:
                pass
            except RuntimeError:
                pass
    except HTTPException as exc:
        await _close_for_http_error(websocket, exc)
    finally:
        _unsubscribe_topic(hub, user_subscription)
        for subscription in subscriptions.values():
            _unsubscribe_topic(hub, subscription)


async def _resolve_ws_token(websocket: WebSocket) -> str:
    if "token" in websocket.query_params:
        raise localized_http_exception(status_code=401, code="auth.required")
    message = await websocket.receive()
    if message["type"] == "websocket.disconnect":
        raise localized_http_exception(status_code=401, code="auth.required")
    if message["type"] != "websocket.receive":
        raise localized_http_exception(status_code=401, code="auth.required")
    payload = message.get("text")
    if payload is None:
        raise localized_http_exception(status_code=401, code="auth.required")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise localized_http_exception(status_code=401, code="auth.required") from exc
    if not isinstance(parsed, dict):
        raise localized_http_exception(status_code=401, code="auth.required")
    token = parsed.get("token")
    if (
        parsed.get("type") == realtime_event_types.REALTIME_AUTH
        and isinstance(token, str)
        and token
    ):
        return token
    raise localized_http_exception(status_code=401, code="auth.required")


async def _send_outbound_events(
    websocket: WebSocket,
    outbound: asyncio.Queue[OutboundEvent],
    *,
    hub: AppRealtimeHub,
    subscriptions: dict[SubscriptionId, ActiveSubscription],
    token: str,
    user_id: str,
) -> None:
    while True:
        try:
            pending = await asyncio.wait_for(outbound.get(), timeout=25)
        except asyncio.TimeoutError:
            pending = OutboundEvent({"type": realtime_event_types.REALTIME_KEEPALIVE, "data": {}})
        subscription = pending.subscription
        if subscription is not None and not subscription.active:
            continue
        if pending.event.get("type") == "hub.shutdown":
            await websocket.close(code=1012)
            return
        try:
            await _ensure_current_session(token=token, user_id=user_id)
            event = pending.event
            if subscription is not None and subscription.resource is not None:
                assert subscription.client_payload is not None
                authorized = await run_in_threadpool(
                    authorize_resource_event,
                    subscription.resource,
                    subscription.client_payload,
                    event,
                    token=token,
                    user_id=user_id,
                )
                # An unsubscribe may have completed during the database check.
                if not subscription.active:
                    continue
                event = authorized.event
                if authorized.revoke:
                    _remove_subscription(hub, subscriptions, subscription)
                if event is None:
                    continue
            elif subscription is not None:
                event = await run_in_threadpool(
                    authorize_user_event, event, token=token, user_id=user_id
                )
                if event is None or not subscription.active:
                    continue
            await websocket.send_json(dict(event))
        except HTTPException as exc:
            await _close_for_http_error(websocket, exc)
            return


async def _receive_client_messages(
    websocket: WebSocket,
    *,
    hub: AppRealtimeHub,
    outbound: asyncio.Queue[OutboundEvent],
    subscriptions: dict[SubscriptionId, ActiveSubscription],
    token: str,
    user_id: str,
) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        if message["type"] != "websocket.receive":
            continue
        try:
            await _ensure_current_session(token=token, user_id=user_id)
        except HTTPException as exc:
            await _close_for_http_error(websocket, exc)
            return
        raw_payload = message.get("text")
        if raw_payload is None:
            await _put_error(
                outbound, code="realtime.invalid_message", detail="Invalid realtime message."
            )
            continue
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            await _put_error(
                outbound, code="realtime.invalid_message", detail="Invalid realtime message."
            )
            continue
        if not isinstance(payload, dict):
            await _put_error(
                outbound, code="realtime.invalid_message", detail="Invalid realtime message."
            )
            continue

        message_type = payload.get("type")
        if message_type == realtime_event_types.REALTIME_SUBSCRIBE:
            await _handle_subscribe(
                payload,
                hub=hub,
                outbound=outbound,
                subscriptions=subscriptions,
                token=token,
                user_id=user_id,
            )
        elif message_type == realtime_event_types.REALTIME_UNSUBSCRIBE:
            _handle_unsubscribe(payload, hub=hub, subscriptions=subscriptions)
        else:
            await _put_error(
                outbound,
                code="realtime.unsupported_message",
                detail="Unsupported realtime message.",
            )


async def _handle_subscribe(
    payload: dict[str, Any],
    *,
    hub: AppRealtimeHub,
    outbound: asyncio.Queue[OutboundEvent],
    subscriptions: dict[SubscriptionId, ActiveSubscription],
    token: str,
    user_id: str,
) -> None:
    try:
        requested = requested_resource_subscription(payload)
    except HTTPException:
        await _put_error(
            outbound, code="realtime.unsupported_subscription", detail="Unsupported subscription."
        )
        return

    try:
        resolved = await run_in_threadpool(
            resolve_resource_subscription,
            payload,
            token=token,
            user_id=user_id,
        )
    except HTTPException as exc:
        # The initial HTTP read may have raced an ACL change before subscription.
        # Echo only the requested ID, never any source existence or metadata.
        await outbound.put(OutboundEvent(requested.access_changed_event()))
        await _put_http_error(outbound, exc)
        return

    subscription_id = _subscription_id(requested.topic, requested.key, payload.get("share_token"))
    existing = subscriptions.get(subscription_id)
    if existing is not None:
        existing.ref_count += 1
        existing.client_payload = dict(payload)
        if resolved.snapshot is not None:
            await outbound.put(OutboundEvent(resolved.snapshot, existing))
        else:
            await outbound.put(OutboundEvent(resolved.access_changed_event(), existing))
        return

    subscription = _subscribe_topic(
        hub,
        resolved.channel,
        outbound,
        client_payload=dict(payload),
        resource=resolved,
    )
    subscriptions[subscription_id] = subscription
    if resolved.snapshot is not None:
        await outbound.put(OutboundEvent(resolved.snapshot, subscription))
    else:
        await outbound.put(OutboundEvent(resolved.access_changed_event(), subscription))


def _handle_unsubscribe(
    payload: dict[str, Any],
    *,
    hub: AppRealtimeHub,
    subscriptions: dict[SubscriptionId, ActiveSubscription],
) -> None:
    topic_name = payload.get("topic")
    key = payload.get("key")
    if not isinstance(topic_name, str) or not isinstance(key, str):
        return
    share_token = payload.get("share_token")
    if share_token is not None and (not isinstance(share_token, str) or not share_token):
        return
    subscription = subscriptions.pop(
        _subscription_id(topic_name, key, payload.get("share_token")), None
    )
    if subscription is not None:
        subscription.ref_count -= 1
        if subscription.ref_count > 0:
            subscriptions[_subscription_id(topic_name, key, payload.get("share_token"))] = (
                subscription
            )
            return
        _unsubscribe_topic(hub, subscription)


def _subscribe_topic(
    hub: AppRealtimeHub,
    topic: str,
    outbound: asyncio.Queue[OutboundEvent],
    *,
    client_payload: dict[str, Any] | None = None,
    resource: ResourceSubscription | None = None,
) -> ActiveSubscription:
    queue = hub.subscribe(topic)
    subscription = ActiveSubscription(
        topic=topic, queue=queue, client_payload=client_payload, resource=resource
    )
    subscription.relay_task = asyncio.create_task(_relay_events(subscription, outbound))
    return subscription


def _unsubscribe_topic(hub: AppRealtimeHub, subscription: ActiveSubscription) -> None:
    subscription.active = False
    if subscription.relay_task is not None:
        subscription.relay_task.cancel()
    hub.unsubscribe(subscription.topic, subscription.queue)


def _remove_subscription(
    hub: AppRealtimeHub,
    subscriptions: dict[SubscriptionId, ActiveSubscription],
    subscription: ActiveSubscription,
) -> None:
    if subscription.resource is not None:
        subscription_id = _subscription_id(
            subscription.resource.topic,
            subscription.resource.key,
            (subscription.client_payload or {}).get("share_token"),
        )
        if subscriptions.get(subscription_id) is subscription:
            subscriptions.pop(subscription_id)
    _unsubscribe_topic(hub, subscription)


async def _relay_events(
    subscription: ActiveSubscription,
    outbound: asyncio.Queue[OutboundEvent],
) -> None:
    while True:
        event = await subscription.queue.get()
        if outbound.full():
            try:
                outbound.get_nowait()
            except asyncio.QueueEmpty:
                pass
        outbound.put_nowait(OutboundEvent(event, subscription))


def _resolve_user_id_from_token(token: str, *, update_last_seen: bool = True) -> str:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        auth_context = resolve_auth_context_from_token(
            db,
            token,
            update_last_seen=update_last_seen,
        )
        return auth_context.user.id
    finally:
        db.close()


def _unread_count_for_user(user_id: str) -> int:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        return notification_service.unread_count(db, user_id)
    finally:
        db.close()


async def _ensure_current_session(*, token: str, user_id: str) -> None:
    resolved_user_id = await run_in_threadpool(
        _resolve_user_id_from_token, token, update_last_seen=False
    )
    if resolved_user_id != user_id:
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED, code="auth.required"
        )


async def _monitor_realtime_access(
    websocket: WebSocket,
    *,
    token: str,
    user_id: str,
    subscriptions: dict[SubscriptionId, ActiveSubscription],
    outbound: asyncio.Queue[OutboundEvent],
) -> None:
    while True:
        await asyncio.sleep(REALTIME_ACCESS_RECHECK_SECONDS)
        try:
            await _ensure_current_session(token=token, user_id=user_id)
            for subscription in list(subscriptions.values()):
                if subscription.client_payload is None or subscription.resource is None:
                    continue
                try:
                    await run_in_threadpool(
                        resolve_resource_subscription,
                        subscription.client_payload,
                        token=token,
                        user_id=user_id,
                    )
                except HTTPException as exc:
                    if exc.status_code == 401:
                        raise
                    await outbound.put(
                        OutboundEvent(subscription.resource.access_changed_event(), subscription)
                    )
        except HTTPException as exc:
            await _close_for_http_error(websocket, exc)
            return


def _subscription_id(topic: str, key: str, share_token: str | None = None) -> SubscriptionId:
    return topic, key, share_token


async def _put_error(
    outbound: asyncio.Queue[OutboundEvent],
    *,
    code: str,
    detail: str,
) -> None:
    await outbound.put(
        OutboundEvent(
            {
                "type": "realtime.error",
                "data": {
                    "code": code,
                    "detail": detail,
                },
            }
        )
    )


async def _put_http_error(outbound: asyncio.Queue[OutboundEvent], exc: HTTPException) -> None:
    detail = (
        translate_message(exc.detail, "ko-KR")
        if isinstance(exc.detail, LocalizedApiMessage)
        else str(exc.detail)
    )
    await _put_error(
        outbound,
        code=exc.detail.code if isinstance(exc.detail, LocalizedApiMessage) else "realtime.error",
        detail=detail,
    )


async def _close_for_http_error(websocket: WebSocket, exc: HTTPException) -> None:
    locale = select_locale(
        explicit_locale=websocket.headers.get("x-open-work-hub-locale"),
        accept_language=websocket.headers.get("accept-language"),
    )
    reason = (
        translate_message(exc.detail, locale)
        if isinstance(exc.detail, LocalizedApiMessage)
        else str(exc.detail)
    )
    await websocket.close(code=1008, reason=reason[:120])
