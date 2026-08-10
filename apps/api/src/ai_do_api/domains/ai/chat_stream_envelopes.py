"""Projection from normalized chat stream chunks to serialized SSE envelopes."""

from __future__ import annotations

from typing import Any

from ai_do_api.core.llm import LlmPoolConfig, PolicyDecision
from ai_do_api.core.llm_adapters import StreamChunk
from ai_do_api.domains.ai.events import EnvelopeEncoder, make_envelope, serialize_sse
from ai_do_api.domains.ai.runtime.routing import RuntimeRoutingDecision
from ai_do_api.domains.ai.runtime.routing_metadata import runtime_routing_done_meta


def chunk_to_envelope(
    chunk: StreamChunk,
    *,
    encoder: EnvelopeEncoder,
    reasoning_gate: bool,
    decision: PolicyDecision | None,
    config: LlmPoolConfig | None,
    model: str | None,
    runtime_routing: RuntimeRoutingDecision | None = None,
    agent_run_id: str | None = None,
) -> dict[str, str] | None:
    # Content chunks are routed through the artifact parser in the publisher
    # loop, not this projection.
    if chunk.kind == "content":
        return None
    if chunk.kind == "reasoning" and chunk.text and reasoning_gate:
        return serialize_sse(
            make_envelope(
                "reasoning_delta",
                encoder.next_seq(),
                {"text": chunk.text},
            )
        )
    if chunk.kind == "usage" and chunk.usage:
        return serialize_sse(make_envelope("usage", encoder.next_seq(), chunk.usage))
    if chunk.kind == "tool_call_start" and chunk.tool_call_id and chunk.tool_name:
        return serialize_sse(
            make_envelope(
                "tool_call_started",
                encoder.next_seq(),
                {"call_id": chunk.tool_call_id, "name": chunk.tool_name},
            )
        )
    if chunk.kind == "tool_call_args" and chunk.tool_call_id and chunk.args_delta:
        return serialize_sse(
            make_envelope(
                "tool_call_args_delta",
                encoder.next_seq(),
                {"call_id": chunk.tool_call_id, "delta": chunk.args_delta},
            )
        )
    if chunk.kind == "done":
        return serialize_sse(
            make_envelope(
                "done",
                encoder.next_seq(),
                {
                    "finish_reason": chunk.finish_reason or "stop",
                    "audit_id": None,
                    "meta": build_done_meta(
                        decision,
                        config,
                        model=model,
                        runtime_routing=runtime_routing,
                        agent_run_id=agent_run_id,
                    ),
                },
            )
        )
    return None


def build_done_meta(
    decision: PolicyDecision | None,
    config: LlmPoolConfig | None,
    *,
    model: str | None,
    runtime_routing: RuntimeRoutingDecision | None = None,
    agent_run_id: str | None = None,
) -> dict[str, Any] | None:
    if decision is None or config is None:
        return None
    meta = {
        "policy": decision.policy,
        "chosen_pool": decision.chosen_pool,
        "decision_reason": decision.reason,
        "forced_local": decision.forced_local,
        "pii_hits": list(decision.pii_hits),
        "model": model or config.default_model,
        "chosen_model": model or config.default_model,
        "canonical_model": config.canonical_model,
        "provider": config.provider,
        "agent_run_id": agent_run_id,
    }
    if runtime_routing is not None:
        meta.update(runtime_routing_done_meta(runtime_routing))
    return meta


__all__ = [
    "build_done_meta",
    "chunk_to_envelope",
]
