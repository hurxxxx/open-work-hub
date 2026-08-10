from __future__ import annotations

import datetime as dt
import json

import pytest

from ai_do_api.core.realtime_relay import (
    RealtimeRelayPayload,
    build_realtime_event_envelope,
    decode_realtime_relay_payload,
    encode_realtime_relay_payload,
    realtime_channel_name,
)


def test_build_realtime_event_envelope_adds_metadata_without_mutating_source() -> None:
    event = {"type": "probe.event"}

    envelope = build_realtime_event_envelope(
        event,
        "user:user-1",
        now_ms=12345,
        event_id_factory=lambda: "event-1",
    )

    assert envelope == {
        "type": "probe.event",
        "data": {},
        "event_id": "event-1",
        "topic": "user:user-1",
        "published_at_ms": 12345,
    }
    assert event == {"type": "probe.event"}


def test_build_realtime_event_envelope_preserves_existing_metadata() -> None:
    event = {
        "type": "probe.event",
        "data": {"value": 1},
        "event_id": "existing-event",
        "topic": "existing-topic",
        "published_at_ms": 67890,
    }

    envelope = build_realtime_event_envelope(
        event,
        "user:user-1",
        now_ms=12345,
        event_id_factory=lambda: "new-event",
    )

    assert envelope == event


def test_encode_realtime_relay_payload_serializes_wire_payload_as_utf8_bytes() -> None:
    encoded = encode_realtime_relay_payload(
        "user:user-1",
        {"type": "probe.event", "data": {"when": dt.date(2026, 5, 31), "text": "plain"}},
        "publisher-1",
    )

    assert isinstance(encoded, bytes)
    assert json.loads(encoded.decode("utf-8")) == {
        "instance_id": "publisher-1",
        "topic": "user:user-1",
        "event": {"type": "probe.event", "data": {"when": "2026-05-31", "text": "plain"}},
    }


def test_decode_realtime_relay_payload_accepts_remote_relay_payload() -> None:
    raw_payload = encode_realtime_relay_payload(
        "user:user-1",
        {"type": "probe.event", "data": {"value": 1}},
        "publisher-1",
    )

    assert decode_realtime_relay_payload(raw_payload, "publisher-2") == RealtimeRelayPayload(
        topic="user:user-1",
        event={"type": "probe.event", "data": {"value": 1}},
    )


def test_decode_realtime_relay_payload_accepts_bytearray_payload() -> None:
    raw_payload = bytearray(
        encode_realtime_relay_payload(
            "user:user-1",
            {"type": "probe.event", "data": {"value": 1}},
            "publisher-1",
        )
    )

    assert decode_realtime_relay_payload(raw_payload, "publisher-2") == RealtimeRelayPayload(
        topic="user:user-1",
        event={"type": "probe.event", "data": {"value": 1}},
    )


def test_decode_realtime_relay_payload_ignores_self_published_relay() -> None:
    raw_payload = encode_realtime_relay_payload(
        "user:user-1",
        {"type": "probe.event", "data": {}},
        "publisher-1",
    )

    assert decode_realtime_relay_payload(raw_payload, "publisher-1") is None


@pytest.mark.parametrize(
    "raw_payload",
    [
        None,
        "not-bytes",
        b"not-json",
        b"\xff",
        b"[]",
        b'{"event": {}}',
        b'{"topic": "user:user-1"}',
        b'{"topic": 42, "event": {}}',
        b'{"topic": "user:user-1", "event": []}',
    ],
)
def test_decode_realtime_relay_payload_ignores_malformed_or_incomplete_payloads(
    raw_payload: object,
) -> None:
    assert decode_realtime_relay_payload(raw_payload, "publisher-1") is None


def test_realtime_channel_name_joins_prefix_and_topic() -> None:
    assert realtime_channel_name("ai-do:app-realtime", "user:user-1") == (
        "ai-do:app-realtime:user:user-1"
    )
