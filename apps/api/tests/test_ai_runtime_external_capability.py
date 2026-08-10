from __future__ import annotations


from ai_do_api.domains.ai.runtime.external_capability import (
    decide_external_capability_request,
)
from ai_do_api.domains.ai.runtime.external_egress import ExternalEgressDecision


def test_external_capability_request_decision_handles_ready_and_sanitized_empty() -> None:
    allowed = ExternalEgressDecision(
        capability="search",
        requested_provider="openai",
        provider="openai",
        allow_external=True,
        reason="allowed",
    )

    ready = decide_external_capability_request(
        egress_decision=allowed,
        expected_capability="search",
        sanitized_payload="  public query  ",
    )
    empty = decide_external_capability_request(
        egress_decision=allowed,
        expected_capability="search",
        sanitized_payload=" \n ",
    )

    assert ready.status == "ready"
    assert ready.provider == "openai"
    assert ready.disabled_reason is None
    assert ready.egress_reason == "allowed"
    assert ready.sanitized_payload == "public query"
    assert empty.status == "disabled"
    assert empty.disabled_reason == "sanitized_empty"
    assert empty.sanitized_payload == ""


def _dict_result(**kwargs: object) -> dict[str, object]:
    return kwargs
