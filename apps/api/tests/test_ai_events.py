"""Envelope contract tests for the current streaming wire format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from open_work_hub_api.domains.ai.events import (
    AgentEventEnvelope,
    EnvelopeEncoder,
    make_envelope,
    serialize_sse,
)


_ADAPTER: TypeAdapter = TypeAdapter(AgentEventEnvelope)
_SCHEMA_FIXTURE = (
    Path(__file__).parent / "fixtures" / "envelope_schema.json"
)


def test_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(
            {
                "seq": 0,
                "timestamp_ms": 0,
                "type": "garbage",
                "data": {},
            }
        )


def test_make_envelope_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        make_envelope("garbage", 0, {})


def test_seq_is_monotone_via_encoder() -> None:
    encoder = EnvelopeEncoder()
    assert [encoder.next_seq() for _ in range(4)] == [0, 1, 2, 3]


def test_serialize_sse_shape() -> None:
    event = make_envelope("content_delta", 0, {"text": "hi"})
    framed = serialize_sse(event)
    assert framed["event"] == "content_delta"
    payload = json.loads(framed["data"])
    assert payload["type"] == "content_delta"
    assert payload["seq"] == 0
    assert payload["data"] == {"text": "hi"}


def test_done_meta_defaults_excluded_when_none_via_serialize_sse() -> None:
    event = make_envelope(
        "done",
        0,
        {"finish_reason": "stop", "audit_id": None, "meta": None},
    )
    framed = serialize_sse(event)
    payload = json.loads(framed["data"])
    # exclude_none=True drops the None fields in data
    assert "audit_id" not in payload["data"]
    assert "meta" not in payload["data"]
    assert payload["data"] == {"finish_reason": "stop"}
