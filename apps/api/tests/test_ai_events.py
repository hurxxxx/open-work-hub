"""Envelope contract tests. These lock the Phase 2 wire format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from aidoo_api.domains.ai.events import (
    AgentEventEnvelope,
    ContentDeltaEvent,
    DoneEvent,
    EnvelopeEncoder,
    ErrorEvent,
    ReasoningDeltaEvent,
    ToolCallStartedEvent,
    envelope_schema,
    make_envelope,
    serialize_sse,
)


_ADAPTER: TypeAdapter = TypeAdapter(AgentEventEnvelope)
_SCHEMA_FIXTURE = (
    Path(__file__).parent / "fixtures" / "envelope_schema.json"
)


def test_discriminator_selects_content_delta() -> None:
    event = _ADAPTER.validate_python(
        {
            "seq": 0,
            "timestamp_ms": 1,
            "type": "content_delta",
            "data": {"text": "hi"},
        }
    )
    assert isinstance(event, ContentDeltaEvent)
    assert event.data.text == "hi"


def test_discriminator_selects_reasoning_delta() -> None:
    event = _ADAPTER.validate_python(
        {
            "seq": 1,
            "timestamp_ms": 2,
            "type": "reasoning_delta",
            "data": {"text": "think"},
        }
    )
    assert isinstance(event, ReasoningDeltaEvent)


def test_discriminator_selects_done_with_meta() -> None:
    event = _ADAPTER.validate_python(
        {
            "seq": 5,
            "timestamp_ms": 3,
            "type": "done",
            "data": {
                "finish_reason": "stop",
                "audit_id": None,
                "meta": {
                    "policy": "external",
                    "chosen_pool": "local",
                    "forced_local": True,
                    "pii_hits": ["email"],
                    "provider": "mlx-lm",
                },
            },
        }
    )
    assert isinstance(event, DoneEvent)
    assert event.data.finish_reason == "stop"
    assert event.data.meta is not None
    assert event.data.meta.pii_hits == ["email"]


def test_discriminator_selects_error() -> None:
    event = _ADAPTER.validate_python(
        {
            "seq": 0,
            "timestamp_ms": 0,
            "type": "error",
            "data": {
                "code": "provider_error",
                "message": "down",
                "retryable": False,
            },
        }
    )
    assert isinstance(event, ErrorEvent)


def test_reserved_types_parse_even_though_unused() -> None:
    event = _ADAPTER.validate_python(
        {
            "seq": 0,
            "timestamp_ms": 0,
            "type": "tool_call_started",
            "data": {"call_id": "c1", "name": "pms.search_issues"},
        }
    )
    assert isinstance(event, ToolCallStartedEvent)


def test_roundtrip_preserves_fields_for_all_published_types() -> None:
    published = [
        make_envelope("content_delta", 0, {"text": "a"}),
        make_envelope("reasoning_delta", 1, {"text": "b"}),
        make_envelope(
            "usage",
            2,
            {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        ),
        make_envelope(
            "done",
            3,
            {"finish_reason": "stop", "audit_id": None, "meta": None},
        ),
        make_envelope(
            "error",
            4,
            {"code": "provider_error", "message": "x", "retryable": False},
        ),
    ]
    for event in published:
        blob = event.model_dump_json()
        reparsed = _ADAPTER.validate_python(json.loads(blob))
        assert reparsed == event


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


def test_seq_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        ContentDeltaEvent(seq=-1, timestamp_ms=0, data={"text": "x"})


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


def test_usage_event_allows_partial_counts() -> None:
    event = make_envelope("usage", 0, {"total_tokens": 99})
    framed = serialize_sse(event)
    payload = json.loads(framed["data"])
    assert payload["data"] == {"total_tokens": 99}


def test_envelope_schema_snapshot_matches() -> None:
    """Guards against accidental wire-format changes.

    If this fails after an intentional change, regenerate with:
        python -c "from aidoo_api.domains.ai.events import envelope_schema; \
import json, pathlib; \
pathlib.Path('apps/api/tests/fixtures/envelope_schema.json').write_text( \
json.dumps(envelope_schema(), indent=2, sort_keys=True) + chr(10))"
    """
    assert _SCHEMA_FIXTURE.exists(), (
        "fixture missing; regenerate — see docstring for command"
    )
    current = json.dumps(envelope_schema(), indent=2, sort_keys=True) + "\n"
    expected = _SCHEMA_FIXTURE.read_text(encoding="utf-8")
    assert current == expected, (
        "envelope schema changed; review the diff and regenerate the fixture "
        "if the change is intentional"
    )
