from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, status
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.i18n import (
    LocalizedApiMessage,
    localized_http_exception,
    select_locale,
    translate_message,
)
from ai_do_api.core.realtime import (
    AppRealtimeHub,
    RealtimeEvent,
    realtime_user_topic,
)
from ai_do_api.domains.auth.dependencies import resolve_auth_context_from_token
from ai_do_api.domains.docs import realtime_protocol as docs_realtime_protocol
from ai_do_api.domains.notifications import realtime_event_types as notification_realtime_event_types
from ai_do_api.domains.notifications import service as notification_service
from ai_do_api.domains.realtime.docs_pages_subscription import (
    resolve_docs_pages_subscription,
)
from ai_do_api.domains.realtime import realtime_event_types


ws_router = APIRouter(prefix="/realtime", tags=["realtime"])
REALTIME_ACCESS_RECHECK_SECONDS = 60


@dataclass
class ActiveSubscription:
    topic: str
    queue: asyncio.Queue[RealtimeEvent]
    relay_task: asyncio.Task[None]
    client_payload: dict[str, Any] | None = None
    ref_count: int = 1


@ws_router.websocket("/ws")
async def app_realtime_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    token = await _resolve_ws_token(websocket)
    hub: AppRealtimeHub = websocket.app.state.app_realtime
    outbound: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=200)
    subscriptions: dict[str, ActiveSubscription] = {}
    try:
        user_id = await run_in_threadpool(_resolve_user_id_from_token, token)
    except HTTPException as exc:
        await _close_for_http_error(websocket, exc)
        return

    user_subscription = _subscribe_topic(hub, realtime_user_topic(user_id), outbound)
    try:
        initial_unread_count = await run_in_threadpool(_unread_count_for_user, user_id)
        await websocket.send_json(
            {"type": realtime_event_types.REALTIME_AUTH_OK, "data": {}}
        )
        await websocket.send_json(
            {
                "type": notification_realtime_event_types.NOTIFICATION_SNAPSHOT,
                "data": {"notification": None, "unread_count": initial_unread_count},
            }
        )
        sender_task = asyncio.create_task(_send_outbound_events(websocket, outbound))
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
    finally:
        _unsubscribe_topic(hub, user_subscription)
        for subscription in subscriptions.values():
            _unsubscribe_topic(hub, subscription)


async def _resolve_ws_token(websocket: WebSocket) -> str:
    query_token = websocket.query_params.get("token")
    if query_token:
        return query_token
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
    outbound: asyncio.Queue[RealtimeEvent],
) -> None:
    while True:
        try:
            event = await asyncio.wait_for(outbound.get(), timeout=25)
        except asyncio.TimeoutError:
            await websocket.send_json(
                {"type": realtime_event_types.REALTIME_KEEPALIVE, "data": {}}
            )
            continue
        if event.get("type") == "hub.shutdown":
            await websocket.close(code=1012)
            return
        await websocket.send_json(dict(event))


async def _receive_client_messages(
    websocket: WebSocket,
    *,
    hub: AppRealtimeHub,
    outbound: asyncio.Queue[RealtimeEvent],
    subscriptions: dict[str, ActiveSubscription],
    token: str,
    user_id: str,
) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        if message["type"] != "websocket.receive":
            continue
        raw_payload = message.get("text")
        if raw_payload is None:
            await _put_error(outbound, code="realtime.invalid_message", detail="Invalid realtime message.")
            continue
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            await _put_error(outbound, code="realtime.invalid_message", detail="Invalid realtime message.")
            continue
        if not isinstance(payload, dict):
            await _put_error(outbound, code="realtime.invalid_message", detail="Invalid realtime message.")
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
            await _put_error(outbound, code="realtime.unsupported_message", detail="Unsupported realtime message.")


async def _handle_subscribe(
    payload: dict[str, Any],
    *,
    hub: AppRealtimeHub,
    outbound: asyncio.Queue[RealtimeEvent],
    subscriptions: dict[str, ActiveSubscription],
    token: str,
    user_id: str,
) -> None:
    topic_name = payload.get("topic")
    key = payload.get("key")
    if (
        topic_name != docs_realtime_protocol.DOCS_PAGES_TOPIC
        or not isinstance(key, str)
        or not key
    ):
        await _put_error(outbound, code="realtime.unsupported_subscription", detail="Unsupported subscription.")
        return

    subscription_id = _subscription_id(topic_name, key)
    existing = subscriptions.get(subscription_id)
    if existing is not None:
        try:
            resolved = await run_in_threadpool(
                resolve_docs_pages_subscription,
                payload,
                token=token,
                user_id=user_id,
            )
        except HTTPException as exc:
            await _put_http_error(outbound, exc)
            return
        existing.ref_count += 1
        existing.client_payload = dict(payload)
        await _put_docs_pages_snapshot(outbound, resolved.doc_id, resolved.updated_at)
        return

    try:
        resolved = await run_in_threadpool(
            resolve_docs_pages_subscription,
            payload,
            token=token,
            user_id=user_id,
        )
    except HTTPException as exc:
        await _put_http_error(outbound, exc)
        return

    subscription = _subscribe_topic(
        hub,
        docs_realtime_protocol.docs_pages_topic(resolved.doc_id),
        outbound,
        client_payload=dict(payload),
    )
    subscriptions[subscription_id] = subscription
    await _put_docs_pages_snapshot(outbound, resolved.doc_id, resolved.updated_at)


def _handle_unsubscribe(
    payload: dict[str, Any],
    *,
    hub: AppRealtimeHub,
    subscriptions: dict[str, ActiveSubscription],
) -> None:
    topic_name = payload.get("topic")
    key = payload.get("key")
    if not isinstance(topic_name, str) or not isinstance(key, str):
        return
    subscription = subscriptions.pop(_subscription_id(topic_name, key), None)
    if subscription is not None:
        subscription.ref_count -= 1
        if subscription.ref_count > 0:
            subscriptions[_subscription_id(topic_name, key)] = subscription
            return
        _unsubscribe_topic(hub, subscription)


def _subscribe_topic(
    hub: AppRealtimeHub,
    topic: str,
    outbound: asyncio.Queue[RealtimeEvent],
    *,
    client_payload: dict[str, Any] | None = None,
) -> ActiveSubscription:
    queue = hub.subscribe(topic)
    relay_task = asyncio.create_task(_relay_events(queue, outbound))
    return ActiveSubscription(topic=topic, queue=queue, relay_task=relay_task, client_payload=client_payload)


def _unsubscribe_topic(hub: AppRealtimeHub, subscription: ActiveSubscription) -> None:
    subscription.relay_task.cancel()
    hub.unsubscribe(subscription.topic, subscription.queue)


async def _relay_events(
    source: asyncio.Queue[RealtimeEvent],
    outbound: asyncio.Queue[RealtimeEvent],
) -> None:
    while True:
        event = await source.get()
        if outbound.full():
            try:
                outbound.get_nowait()
            except asyncio.QueueEmpty:
                pass
        outbound.put_nowait(event)


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


async def _monitor_realtime_access(
    websocket: WebSocket,
    *,
    token: str,
    user_id: str,
    subscriptions: dict[str, ActiveSubscription],
) -> None:
    while True:
        await asyncio.sleep(REALTIME_ACCESS_RECHECK_SECONDS)
        try:
            resolved_user_id = await run_in_threadpool(
                _resolve_user_id_from_token,
                token,
                update_last_seen=False,
            )
            if resolved_user_id != user_id:
                raise localized_http_exception(status_code=status.HTTP_401_UNAUTHORIZED, code="auth.required")
            for subscription in list(subscriptions.values()):
                if subscription.client_payload is None:
                    continue
                await run_in_threadpool(
                    resolve_docs_pages_subscription,
                    subscription.client_payload,
                    token=token,
                    user_id=user_id,
                )
        except HTTPException as exc:
            await _close_for_http_error(websocket, exc)
            return


async def _put_docs_pages_snapshot(
    outbound: asyncio.Queue[RealtimeEvent],
    doc_id: str,
    updated_at: datetime | None,
) -> None:
    await outbound.put(
        {
            "type": docs_realtime_protocol.DOCS_PAGES_SNAPSHOT,
            "data": {
                "doc_id": doc_id,
                "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at,
            },
        }
    )


def _subscription_id(topic: str, key: str) -> str:
    return f"{topic}:{key}"


async def _put_error(
    outbound: asyncio.Queue[RealtimeEvent],
    *,
    code: str,
    detail: str,
) -> None:
    await outbound.put(
        {
            "type": "realtime.error",
            "data": {
                "code": code,
                "detail": detail,
            },
        }
    )


async def _put_http_error(outbound: asyncio.Queue[RealtimeEvent], exc: HTTPException) -> None:
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
        explicit_locale=websocket.headers.get("x-ai-do-locale"),
        accept_language=websocket.headers.get("accept-language"),
    )
    reason = translate_message(exc.detail, locale) if isinstance(exc.detail, LocalizedApiMessage) else str(exc.detail)
    await websocket.close(code=1008, reason=reason[:120])
