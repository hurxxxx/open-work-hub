"""Runtime run inspection response projection."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ai_do_api.domains.ai.runtime.trace_payload import scrub_trace_payload


class RuntimeInvocationResponse(BaseModel):
    id: str
    invocation_seq: int
    agent_id: str
    status: str
    purpose: str
    input_ref: str | None = None
    output_ref: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class RuntimeTraceEventResponse(BaseModel):
    id: str
    invocation_id: str | None = None
    run_seq: int
    invocation_seq: int
    event_seq: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class RuntimeRunInspectionResponse(BaseModel):
    id: str
    workspace_id: str
    conversation_id: str
    requested_by_user_id: str
    legacy_snapshot_id: str | None = None
    status: str
    runtime_profile: str
    graph_enabled: bool
    model_profile_id: str | None = None
    fallback_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    invocations: list[RuntimeInvocationResponse]
    trace_events: list[RuntimeTraceEventResponse]


def runtime_run_inspection_response(
    runtime_run: Any,
    *,
    invocations: Iterable[Any],
    trace_events: Iterable[Any],
) -> RuntimeRunInspectionResponse:
    return RuntimeRunInspectionResponse(
        id=runtime_run.id,
        workspace_id=runtime_run.workspace_id,
        conversation_id=runtime_run.conversation_id,
        requested_by_user_id=runtime_run.requested_by_user_id,
        legacy_snapshot_id=runtime_run.legacy_snapshot_id,
        status=runtime_run.status,
        runtime_profile=runtime_run.runtime_profile,
        graph_enabled=runtime_run.graph_enabled,
        model_profile_id=runtime_run.model_profile_id,
        fallback_reason=runtime_run.fallback_reason,
        created_at=runtime_run.created_at,
        updated_at=runtime_run.updated_at,
        invocations=[
            RuntimeInvocationResponse(
                id=invocation.id,
                invocation_seq=invocation.invocation_seq,
                agent_id=invocation.agent_id,
                status=invocation.status,
                purpose=invocation.purpose,
                input_ref=_scrub_runtime_inspection_value(invocation.input_ref),
                output_ref=_scrub_runtime_inspection_value(invocation.output_ref),
                error=_scrub_runtime_inspection_value(invocation.error),
                created_at=invocation.created_at,
                updated_at=invocation.updated_at,
            )
            for invocation in invocations
        ],
        trace_events=[
            RuntimeTraceEventResponse(
                id=event.id,
                invocation_id=event.agent_invocation_id,
                run_seq=event.run_seq,
                invocation_seq=event.invocation_seq,
                event_seq=event.event_seq,
                event_type=event.event_type,
                payload=scrub_trace_payload(event.payload_json or {}),
                created_at=event.created_at,
            )
            for event in trace_events
        ],
    )


def _scrub_runtime_inspection_value(value: str | None) -> str | None:
    if value is None:
        return None
    scrubbed = scrub_trace_payload({"value": value}).get("value")
    return scrubbed if isinstance(scrubbed, str) else "[redacted]"


__all__ = [
    "RuntimeInvocationResponse",
    "RuntimeRunInspectionResponse",
    "RuntimeTraceEventResponse",
    "runtime_run_inspection_response",
]
