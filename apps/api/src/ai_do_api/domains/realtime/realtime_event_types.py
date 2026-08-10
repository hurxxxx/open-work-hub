from __future__ import annotations

from collections.abc import Mapping
from typing import Any


REALTIME_AUTH = "auth"
REALTIME_SUBSCRIBE = "subscribe"
REALTIME_UNSUBSCRIBE = "unsubscribe"

REALTIME_AUTH_OK = "realtime.auth.ok"
REALTIME_KEEPALIVE = "realtime.keepalive"

REALTIME_CLIENT_EVENT_TYPES = frozenset(
    {
        REALTIME_AUTH,
        REALTIME_SUBSCRIBE,
        REALTIME_UNSUBSCRIBE,
    }
)

REALTIME_SERVER_EVENT_TYPES = frozenset(
    {
        REALTIME_AUTH_OK,
        REALTIME_KEEPALIVE,
    }
)


def build_realtime_event(
    event_type: str,
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {"type": event_type, "data": {} if data is None else dict(data)}


def is_realtime_client_event_type(event_type: str) -> bool:
    return event_type in REALTIME_CLIENT_EVENT_TYPES


def is_realtime_server_event_type(event_type: str) -> bool:
    return event_type in REALTIME_SERVER_EVENT_TYPES
