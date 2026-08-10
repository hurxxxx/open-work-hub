from __future__ import annotations

from ai_do_api.domains.ai.runtime.trace_payload import (
    prepare_trace_payload,
    scrub_trace_payload,
)


def test_trace_payload_scrub_redacts_sensitive_keys_and_values() -> None:
    payload = scrub_trace_payload(
        {
            "prompt": "must-not-leak",
            "messages": [{"role": "user", "content": "must-not-leak"}],
            "arguments": {"summary": "must-not-leak"},
            "args": {"nested": "must-not-leak"},
            "result": "must-not-leak",
            "output": "must-not-leak",
            "content": "must-not-leak",
            "provider_response": {"text": "must-not-leak"},
            "safe": "Authorization: Bearer must-not-leak",
            "result_refs": ["safe-ref"],
        }
    )

    assert payload == {
        "prompt": "[redacted]",
        "messages": "[redacted]",
        "arguments": "[redacted]",
        "args": "[redacted]",
        "result": "[redacted]",
        "output": "[redacted]",
        "content": "[redacted]",
        "provider_response": "[redacted]",
        "safe": "[redacted]",
        "result_refs": ["safe-ref"],
    }


def test_prepare_trace_payload_replaces_oversized_payload_before_scrub() -> None:
    payload, truncated = prepare_trace_payload(
        {"prompt": "must-not-leak", "safe": "x" * 128},
        max_bytes=32,
    )

    assert truncated is True
    assert payload["truncated"] is True
    assert payload["reason"] == "payload_too_large"
    assert payload["original_size_bytes"] > 32
    assert "must-not-leak" not in str(payload)


def test_prepare_trace_payload_scrubs_payload_within_limit() -> None:
    payload, truncated = prepare_trace_payload(
        {
            "token": "must-not-leak",
            "result_refs": ["mock://result"],
        },
        max_bytes=512,
    )

    assert truncated is False
    assert payload == {
        "token": "[redacted]",
        "result_refs": ["mock://result"],
    }
