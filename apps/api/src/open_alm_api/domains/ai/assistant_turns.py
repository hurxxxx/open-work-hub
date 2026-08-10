"""Assistant-turn accumulation and artifact serialization helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from open_alm_api.domains.ai.artifact_parser import ArtifactStreamParser
from open_alm_api.domains.ai.artifact_stream_envelopes import (
    emit_content_through_parser,
    flush_parser,
    parser_events_to_envelopes,
    serialize_agent_event_through_artifacts,
)
from open_alm_api.domains.ai.events import EnvelopeEncoder, serialize_sse
from open_alm_api.domains.ai.runtime.routing_metadata import (
    runtime_persisted_meta_from_done_meta,
)
from open_alm_api.domains.ai.tool_call_event_projection import iter_tool_call_events
from open_alm_api.domains.ai.tool_runtime import ToolCallExecution


SYNC_FINISH_REASONS = {"stop", "length", "cancelled", "error"}
EMPTY_LENGTH_RESPONSE_MESSAGE = (
    "응답이 토큰 한도에 도달해 중간에서 잘렸습니다. 질문 범위를 줄이거나 이어서 요청하세요."
)
EMPTY_CANCELLED_RESPONSE_MESSAGE = "응답이 중단되었습니다."
EMPTY_ERROR_RESPONSE_MESSAGE = "응답 중 오류가 발생했습니다."


class SyncAssistantResponse(Protocol):
    model: str
    content: str
    finish_reason: str | None
    provider: str
    policy: str | None
    chosen_pool: str | None
    decision_reason: str | None
    forced_local: bool
    pii_hits: Iterable[str]
    canonical_model: str


@dataclass(frozen=True)
class AssistantTurnRecord:
    content: str
    meta: dict[str, Any] | None


@dataclass
class AssistantTurnBuffer:
    """Accumulates streamed envelopes so we can persist a final assistant turn.

    Observes the already-serialized ``{event, data}`` dicts as they flow
    through the publisher. Tool call state is threaded across three event types
    (``tool_call_started`` -> ``tool_call_args_delta`` -> ``tool_result``) into
    one record per ``call_id`` so a reloaded turn can render the same cards the
    live UI did. Artifacts are threaded the same way so reload can re-open the
    side panel with the original body.
    """

    content: str = ""
    reasoning: str = ""
    tool_call_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_call_order: list[str] = field(default_factory=list)
    artifact_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifact_order: list[str] = field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    done_meta: dict[str, Any] | None = None
    finish_reason: str | None = None
    response_status: str = "done"
    cancelled: bool = False
    # Captured from ``error`` envelopes so a stream that fails before any
    # content_delta still persists with the failure text the live UI showed.
    error_message: str | None = None

    def _touch_tool_call(self, call_id: str) -> dict[str, Any]:
        # Mirrors the frontend ToolCallBuffer shape so a reloaded turn renders
        # the same tool card: `result` is a nested object with its own status
        # + preview + error, not top-level fields.
        if call_id not in self.tool_call_records:
            self.tool_call_order.append(call_id)
            self.tool_call_records[call_id] = {
                "call_id": call_id,
                "name": None,
                "args_preview": None,
                "argsBuffer": "",
                "status": "running",
                "result": None,
                "startedAtMs": None,
                "completedAtMs": None,
            }
        return self.tool_call_records[call_id]

    def _touch_artifact(self, artifact_id: str) -> dict[str, Any]:
        # Persisted artifact shape mirrors the client's ArtifactEntry. The
        # language hint is only set for code artifacts.
        if artifact_id not in self.artifact_records:
            self.artifact_order.append(artifact_id)
            self.artifact_records[artifact_id] = {
                "id": artifact_id,
                "type": "document",
                "title": None,
                "language": None,
                "content": "",
                "status": "open",
            }
        return self.artifact_records[artifact_id]

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return [self.tool_call_records[call_id] for call_id in self.tool_call_order]

    @property
    def artifacts(self) -> list[dict[str, Any]]:
        return [self.artifact_records[artifact_id] for artifact_id in self.artifact_order]

    def observe(self, event_dict: dict[str, str]) -> None:
        # serialize_sse serialises the full envelope `{seq, timestamp_ms,
        # type, data: {...}}` into the SSE `data` field, so the interesting
        # payload we want to inspect sits at `envelope["data"]`.
        try:
            envelope = json.loads(event_dict.get("data", ""))
        except (ValueError, TypeError):
            return
        event_type = event_dict.get("event")
        payload = envelope.get("data") or {}
        timestamp_ms = envelope.get("timestamp_ms")
        if event_type == "content_delta":
            self.content += payload.get("text", "")
        elif event_type == "reasoning_delta":
            self.reasoning += payload.get("text", "")
        elif event_type == "tool_call_started":
            call_id = payload.get("call_id")
            if call_id:
                record = self._touch_tool_call(call_id)
                record["name"] = payload.get("name") or record["name"]
                record["args_preview"] = payload.get("args_preview") or record["args_preview"]
                if record["startedAtMs"] is None:
                    record["startedAtMs"] = timestamp_ms
        elif event_type == "tool_call_args_delta":
            call_id = payload.get("call_id")
            if call_id:
                record = self._touch_tool_call(call_id)
                record["argsBuffer"] += payload.get("delta", "")
        elif event_type == "tool_result":
            call_id = payload.get("call_id")
            if call_id:
                record = self._touch_tool_call(call_id)
                status = payload.get("status") or record["status"]
                record["status"] = status
                record["result"] = {
                    "status": status,
                    "preview": payload.get("result_preview"),
                    "error": payload.get("error"),
                }
                record["completedAtMs"] = timestamp_ms
        elif event_type == "approval_required":
            self.pending_approvals.append(payload)
        elif event_type == "artifact_started":
            artifact_id = payload.get("artifact_id")
            if artifact_id:
                record = self._touch_artifact(artifact_id)
                record["type"] = payload.get("artifact_type") or record["type"]
                record["title"] = payload.get("title") or record["title"]
                language = payload.get("language")
                if language:
                    record["language"] = language
        elif event_type == "artifact_delta":
            artifact_id = payload.get("artifact_id")
            if artifact_id:
                record = self._touch_artifact(artifact_id)
                record["content"] += payload.get("delta", "")
        elif event_type == "artifact_completed":
            artifact_id = payload.get("artifact_id")
            if artifact_id:
                record = self._touch_artifact(artifact_id)
                record["status"] = "closed"
        elif event_type == "error":
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                self.error_message = message
        elif event_type == "done":
            self.done_meta = payload.get("meta") or {}
            self.finish_reason = payload.get("finish_reason")
            if self.finish_reason == "error":
                self.response_status = "error"


def build_assistant_turn_record(
    buffer: AssistantTurnBuffer,
    *,
    fallback_meta: dict[str, Any] | None = None,
) -> AssistantTurnRecord | None:
    """Build the assistant turn payload that conversation persistence writes.

    The stream publisher owns when to write; this module owns what gets written
    from the accumulated event buffer. Empty successful streams are ignored, but
    terminal failures, cancellations, length stops, and artifact-only responses
    still produce a reloadable assistant turn.
    """

    response_status = "cancelled" if buffer.cancelled else buffer.response_status
    has_body = bool(
        buffer.content
        or buffer.reasoning
        or buffer.tool_calls
        or buffer.pending_approvals
        or buffer.artifacts
    )
    is_terminal_failure = response_status in {"cancelled", "error"} or (
        buffer.finish_reason in {"cancelled", "error", "length"}
    )
    if not has_body and not is_terminal_failure:
        return None

    persisted_content = buffer.content
    if not persisted_content and buffer.error_message:
        persisted_content = buffer.error_message
    if not persisted_content and not has_body:
        if buffer.finish_reason == "length":
            persisted_content = EMPTY_LENGTH_RESPONSE_MESSAGE
        elif response_status == "cancelled":
            persisted_content = EMPTY_CANCELLED_RESPONSE_MESSAGE
        elif response_status == "error":
            persisted_content = EMPTY_ERROR_RESPONSE_MESSAGE

    done_meta = buffer.done_meta or fallback_meta or {}
    reasoning_status = response_status if buffer.reasoning and response_status != "done" else None

    meta: dict[str, Any] = {
        "reasoning": buffer.reasoning or None,
        "reasoning_status": reasoning_status,
        "policy": done_meta.get("policy"),
        "chosen_pool": done_meta.get("chosen_pool"),
        "decision_reason": done_meta.get("decision_reason"),
        "forced_local": done_meta.get("forced_local"),
        "pii_hits": done_meta.get("pii_hits") or [],
        "provider": done_meta.get("provider"),
        "finish_reason": buffer.finish_reason,
        "response_status": response_status,
        "tool_calls": buffer.tool_calls,
        "pending_approvals": buffer.pending_approvals,
        "artifacts": buffer.artifacts,
    }
    meta.update(runtime_persisted_meta_from_done_meta(done_meta))
    meta = {key: value for key, value in meta.items() if value not in (None, [], "")}
    return AssistantTurnRecord(content=persisted_content, meta=meta or None)


def assistant_buffer_from_sync_response(
    response: SyncAssistantResponse,
    *,
    parse_artifacts: bool = True,
    tool_execution: ToolCallExecution | None = None,
    server_owned_artifact_types: frozenset[str] = frozenset(),
) -> AssistantTurnBuffer:
    buffer = AssistantTurnBuffer(
        done_meta={
            "policy": response.policy,
            "chosen_pool": response.chosen_pool,
            "decision_reason": response.decision_reason,
            "forced_local": response.forced_local,
            "pii_hits": list(response.pii_hits),
            "model": response.model,
            "chosen_model": response.model,
            "canonical_model": response.canonical_model,
            "provider": response.provider,
        },
        finish_reason=(
            response.finish_reason if response.finish_reason in SYNC_FINISH_REASONS else None
        ),
        response_status="error" if response.finish_reason == "error" else "done",
    )
    if not parse_artifacts:
        # Tool-command responses go straight into ``content`` without
        # re-parsing. When the underlying ToolCallExecution is available,
        # synthesize the same tool-call metadata the streaming transport records.
        if tool_execution is not None:
            encoder = EnvelopeEncoder()
            for event in iter_tool_call_events(encoder=encoder, execution=tool_execution):
                buffer.observe(serialize_sse(event))
        buffer.content = response.content or ""
        return buffer

    parser = ArtifactStreamParser(
        server_owned_artifact_types=server_owned_artifact_types
    )
    encoder = EnvelopeEncoder()
    for event in emit_content_through_parser(
        response.content or "",
        parser=parser,
        encoder=encoder,
    ):
        buffer.observe(event)
    for event in flush_parser(parser, encoder=encoder):
        buffer.observe(event)
    return buffer


__all__ = [
    "AssistantTurnRecord",
    "AssistantTurnBuffer",
    "EMPTY_CANCELLED_RESPONSE_MESSAGE",
    "EMPTY_ERROR_RESPONSE_MESSAGE",
    "EMPTY_LENGTH_RESPONSE_MESSAGE",
    "SYNC_FINISH_REASONS",
    "SyncAssistantResponse",
    "assistant_buffer_from_sync_response",
    "build_assistant_turn_record",
    "emit_content_through_parser",
    "flush_parser",
    "parser_events_to_envelopes",
    "serialize_agent_event_through_artifacts",
]
