from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


RealtimeEvent = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RealtimeRelayPayload:
    topic: str
    event: dict[str, Any]


def build_realtime_event_envelope(
    event: RealtimeEvent,
    topic: str,
    now_ms: int,
    event_id_factory: Callable[[], str],
) -> dict[str, Any]:
    envelope = dict(event)
    envelope.setdefault("data", {})
    if "event_id" not in envelope:
        envelope["event_id"] = event_id_factory()
    envelope.setdefault("topic", topic)
    envelope.setdefault("published_at_ms", now_ms)
    return envelope


def encode_realtime_relay_payload(
    topic: str,
    event: RealtimeEvent,
    publisher_id: str,
) -> bytes:
    payload = {
        "instance_id": publisher_id,
        "topic": topic,
        "event": dict(event),
    }
    return json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")


def decode_realtime_relay_payload(
    raw_payload: object,
    self_publisher_id: str,
) -> RealtimeRelayPayload | None:
    if not isinstance(raw_payload, (bytes, bytearray)):
        return None
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("instance_id") == self_publisher_id:
        return None
    topic = payload.get("topic")
    event = payload.get("event")
    if not isinstance(topic, str) or not isinstance(event, dict):
        return None
    return RealtimeRelayPayload(topic=topic, event=event)


def realtime_channel_name(prefix: str, topic: str) -> str:
    return f"{prefix}:{topic}"
