from __future__ import annotations

from datetime import timedelta
import json
import logging
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.runtime.metrics import (
    record_shadow_write_failure,
    record_trace_event,
    record_trace_payload_truncated,
)
from aidoo_api.domains.ai.runtime.models import AgentInvocation, AgentRun, AgentTraceEvent
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.meeting.models import utcnow_naive


logger = logging.getLogger(__name__)

SENSITIVE_PAYLOAD_KEYS = {
    "api_key",
    "args",
    "arguments",
    "authorization",
    "completion",
    "content",
    "cookie",
    "headers",
    "messages",
    "password",
    "prompt",
    "provider_response",
    "raw",
    "raw_provider_payload",
    "raw_reasoning",
    "reasoning",
    "result",
    "output",
    "secret",
    "token",
    "tool_secret",
}
SAFE_PAYLOAD_KEYS = {
    "output_kind",
}
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[-._~+/=a-z0-9]+"),
    re.compile(r"(?i)\b(api[_-]?key|x-api-key|authorization)\s*[:=]\s*[^,\s;]+"),
    re.compile(r"(?i)\b(session|access|refresh|id)[_-]?token\s*[:=]\s*[^,\s;]+"),
    re.compile(r"(?i)\b(cookie|set-cookie)\s*[:=]\s*[^,\s;]+"),
)
TERMINAL_RUN_STATUSES = ("completed", "failed", "cancelled", "abandoned")
SINGLE_LOOP_FALLBACK_AGENT_ID = "single_loop.fallback"
GRAPH_EXECUTION_ADAPTER_AGENT_ID = "graph.adapter.node_runner"


def scrub_trace_payload(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in SAFE_PAYLOAD_KEYS:
                scrubbed[key] = scrub_trace_payload(item)
            elif any(marker in normalized_key for marker in SENSITIVE_PAYLOAD_KEYS):
                scrubbed[key] = "[redacted]"
            else:
                scrubbed[key] = scrub_trace_payload(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_trace_payload(item) for item in value]
    if isinstance(value, str):
        return _scrub_sensitive_string(value)
    return value


def _scrub_sensitive_string(value: str) -> str:
    scrubbed = value
    for pattern in SENSITIVE_VALUE_PATTERNS:
        scrubbed = pattern.sub("[redacted]", scrubbed)
    return scrubbed


def _payload_size_bytes(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def prepare_trace_payload(
    payload: dict[str, Any] | None,
    *,
    max_bytes: int | None = None,
) -> tuple[dict[str, Any], bool]:
    raw_payload = payload or {}
    limit = max_bytes if max_bytes is not None else get_settings().ai_runtime_trace_payload_max_bytes
    size_bytes = _payload_size_bytes(raw_payload)
    if size_bytes > limit:
        return (
            {
                "truncated": True,
                "original_size_bytes": size_bytes,
                "reason": "payload_too_large",
            },
            True,
        )
    return scrub_trace_payload(raw_payload), False


def append_trace_event(
    db: Session,
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    agent_invocation_id: str | None = None,
    run_seq: int = 0,
    invocation_seq: int = 0,
) -> AgentTraceEvent:
    prepared_payload, truncated = prepare_trace_payload(payload)
    db.scalar(
        select(AgentRun.id)
        .where(AgentRun.id == agent_run_id)
        .with_for_update()
    )
    current = db.scalar(
        select(func.max(AgentTraceEvent.event_seq)).where(
            AgentTraceEvent.agent_run_id == agent_run_id
        )
    )
    event = AgentTraceEvent(
        id=new_id(),
        agent_run_id=agent_run_id,
        agent_invocation_id=agent_invocation_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        run_seq=run_seq,
        invocation_seq=invocation_seq,
        event_seq=int(current if current is not None else -1) + 1,
        event_type=event_type,
        payload_json=prepared_payload,
    )
    db.add(event)
    db.flush()
    record_trace_event(event_type=event_type, result="ok")
    if truncated:
        record_trace_payload_truncated(event_type=event_type)
    return event


def append_graph_candidate_trace_events(
    db: Session,
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    runtime_metadata: dict[str, Any],
) -> None:
    graph_gate = runtime_metadata.get("graph_gate")
    if graph_gate != "eligible":
        return

    candidate_summary = runtime_metadata.get("graph_candidate_summary")
    if isinstance(candidate_summary, dict):
        generated_payload = {
            "runtime_profile": runtime_metadata.get("runtime_profile"),
            "graph_gate": graph_gate,
            "graph_candidate_summary": candidate_summary,
        }
        external_egress_summary = runtime_metadata.get("external_egress_summary")
        if external_egress_summary is not None:
            generated_payload["external_egress_summary"] = external_egress_summary
        append_trace_event(
            db,
            agent_run_id=agent_run_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            event_type="graph_candidate_generated",
            payload=generated_payload,
        )

    validated_payload = {
        "runtime_profile": runtime_metadata.get("runtime_profile"),
        "graph_gate": graph_gate,
        "graph_fallback_reason": runtime_metadata.get("graph_fallback_reason"),
        "graph_used": bool(runtime_metadata.get("graph_used")),
        "graph_validation_status": runtime_metadata.get("graph_validation_status"),
        "graph_validation_fallback_reason": runtime_metadata.get(
            "graph_validation_fallback_reason"
        ),
        "graph_registry_agent_count": int(
            runtime_metadata.get("graph_registry_agent_count") or 0
        ),
        "graph_write_agent_count": int(
            runtime_metadata.get("graph_write_agent_count") or 0
        ),
        "graph_candidate_summary": candidate_summary
        if isinstance(candidate_summary, dict)
        else None,
    }
    external_egress_summary = runtime_metadata.get("external_egress_summary")
    if external_egress_summary is not None:
        validated_payload["external_egress_summary"] = external_egress_summary
    append_trace_event(
        db,
        agent_run_id=agent_run_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        event_type="graph_candidate_validated",
        payload=validated_payload,
    )


def append_graph_schedule_trace_events(
    db: Session,
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    runtime_metadata: dict[str, Any],
    graph_invocations_by_seq: dict[int, AgentInvocation] | None = None,
) -> None:
    schedule_summary = runtime_metadata.get("graph_schedule_summary")
    if not isinstance(schedule_summary, dict):
        return

    if schedule_summary.get("state") != "planned":
        append_trace_event(
            db,
            agent_run_id=agent_run_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            event_type="graph_schedule_failed",
            payload={"graph_schedule_summary": schedule_summary},
        )
        return

    append_trace_event(
        db,
        agent_run_id=agent_run_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        event_type="graph_schedule_planned",
        payload={"graph_schedule_summary": schedule_summary},
    )
    steps = schedule_summary.get("steps")
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        try:
            invocation_seq = int(step.get("invocation_seq") or 0)
        except (TypeError, ValueError):
            continue
        graph_invocation = (graph_invocations_by_seq or {}).get(invocation_seq)
        append_trace_event(
            db,
            agent_run_id=agent_run_id,
            agent_invocation_id=graph_invocation.id if graph_invocation else None,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            invocation_seq=invocation_seq,
            event_type="graph_node_planned",
            payload={
                "invocation_seq": step.get("invocation_seq"),
                "agent_id": step.get("agent_id"),
                "state": step.get("state"),
                "depends_on_agent_ids": step.get("depends_on_agent_ids") or [],
            },
        )


def append_graph_execution_trace_events(
    db: Session,
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    runtime_metadata: dict[str, Any],
) -> None:
    execution_status = runtime_metadata.get("graph_execution_status")
    if not isinstance(execution_status, str) or execution_status == "not_applicable":
        return
    append_trace_event(
        db,
        agent_run_id=agent_run_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        event_type="graph_execution_gate_evaluated",
        payload={
            "graph_execution_status": execution_status,
            "graph_execution_fallback_reason": runtime_metadata.get(
                "graph_execution_fallback_reason"
            ),
            "graph_execution_fallback_policy": runtime_metadata.get(
                "graph_execution_fallback_policy"
            ),
            "graph_execution_adapter": runtime_metadata.get("graph_execution_adapter"),
            "graph_node_execution_summary": runtime_metadata.get(
                "graph_node_execution_summary"
            ),
        },
    )


def persist_graph_schedule_invocation_skeletons(
    db: Session,
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    runtime_metadata: dict[str, Any],
    status: str = "pending",
    purpose: str = "graph node planned",
) -> dict[int, AgentInvocation]:
    schedule_summary = runtime_metadata.get("graph_schedule_summary")
    if not isinstance(schedule_summary, dict) or schedule_summary.get("state") != "planned":
        return {}
    steps = schedule_summary.get("steps")
    if not isinstance(steps, list):
        return {}

    invocations_by_seq: dict[int, AgentInvocation] = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        agent_id = step.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            continue
        try:
            invocation_seq = int(step.get("invocation_seq") or 0)
        except (TypeError, ValueError):
            continue
        if invocation_seq in invocations_by_seq:
            continue
        invocation = AgentInvocation(
            id=new_id(),
            agent_run_id=agent_run_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            invocation_seq=invocation_seq,
            agent_id=agent_id,
            status=status,
            purpose=purpose,
        )
        db.add(invocation)
        invocations_by_seq[invocation_seq] = invocation
    db.flush()
    return invocations_by_seq


def _next_invocation_seq(db: Session, agent_run_id: str) -> int:
    current = db.scalar(
        select(func.max(AgentInvocation.invocation_seq)).where(
            AgentInvocation.agent_run_id == agent_run_id
        )
    )
    return int(current if current is not None else -1) + 1


def persist_single_loop_fallback_runtime_shadow(
    db: Session,
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    requested_by_user_id: str,
    runtime_metadata: dict[str, Any],
    finish_reason: str | None,
    response_status: str,
) -> None:
    if not get_settings().ai_runtime_shadow_write_enabled:
        return
    try:
        _persist_single_loop_fallback_runtime_shadow(
            db,
            agent_run_id=agent_run_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            requested_by_user_id=requested_by_user_id,
            runtime_metadata=runtime_metadata,
            finish_reason=finish_reason,
            response_status=response_status,
        )
        db.commit()
    except Exception:
        db.rollback()
        record_shadow_write_failure(operation="persist_single_loop_fallback_runtime_shadow")
        logger.exception(
            "ai_runtime.shadow_write_failed",
            extra={
                "agent_run_id": agent_run_id,
                "conversation_id": conversation_id,
                "workspace_id": workspace_id,
                "operation": "persist_single_loop_fallback_runtime_shadow",
            },
        )


def persist_graph_execution_runtime_shadow(
    db: Session,
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    requested_by_user_id: str,
    runtime_metadata: dict[str, Any],
    finish_reason: str | None,
    response_status: str,
) -> None:
    if not get_settings().ai_runtime_shadow_write_enabled:
        return
    try:
        _persist_graph_execution_runtime_shadow(
            db,
            agent_run_id=agent_run_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            requested_by_user_id=requested_by_user_id,
            runtime_metadata=runtime_metadata,
            finish_reason=finish_reason,
            response_status=response_status,
        )
        db.commit()
    except Exception:
        db.rollback()
        record_shadow_write_failure(operation="persist_graph_execution_runtime_shadow")
        logger.exception(
            "ai_runtime.shadow_write_failed",
            extra={
                "agent_run_id": agent_run_id,
                "conversation_id": conversation_id,
                "workspace_id": workspace_id,
                "operation": "persist_graph_execution_runtime_shadow",
            },
        )


def _persist_single_loop_fallback_runtime_shadow(
    db: Session,
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    requested_by_user_id: str,
    runtime_metadata: dict[str, Any],
    finish_reason: str | None,
    response_status: str,
) -> None:
    now = utcnow_naive()
    status = _terminal_runtime_status(
        finish_reason=finish_reason,
        response_status=response_status,
    )
    runtime_run = AgentRun(
        id=agent_run_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        requested_by_user_id=requested_by_user_id,
        status=status,
        runtime_profile=_runtime_profile_from_metadata(runtime_metadata),
        graph_enabled=runtime_metadata.get("graph_gate") == "eligible",
        model_profile_id=str(
            runtime_metadata.get("model") or runtime_metadata.get("chosen_model") or ""
        )
        or None,
        fallback_reason=runtime_metadata.get("graph_fallback_reason"),
        metadata_json={
            "source": "single_loop_fallback_shadow",
            "runtime_routing_reason_codes": runtime_metadata.get(
                "runtime_routing_reason_codes"
            ),
            "graph_gate": runtime_metadata.get("graph_gate"),
            "graph_fallback_reason": runtime_metadata.get("graph_fallback_reason"),
            "graph_used": bool(runtime_metadata.get("graph_used")),
            "graph_validation_status": runtime_metadata.get("graph_validation_status"),
            "graph_validation_fallback_reason": runtime_metadata.get(
                "graph_validation_fallback_reason"
            ),
            "graph_registry_agent_count": int(
                runtime_metadata.get("graph_registry_agent_count") or 0
            ),
            "graph_write_agent_count": int(
                runtime_metadata.get("graph_write_agent_count") or 0
            ),
            "graph_candidate_summary": runtime_metadata.get("graph_candidate_summary"),
            "graph_schedule_summary": runtime_metadata.get("graph_schedule_summary"),
            "external_egress_summary": runtime_metadata.get("external_egress_summary"),
            "graph_execution_status": runtime_metadata.get("graph_execution_status"),
            "graph_execution_fallback_reason": runtime_metadata.get(
                "graph_execution_fallback_reason"
            ),
            "graph_execution_fallback_policy": runtime_metadata.get(
                "graph_execution_fallback_policy"
            ),
            "graph_execution_adapter": runtime_metadata.get("graph_execution_adapter"),
            "graph_node_execution_summary": runtime_metadata.get(
                "graph_node_execution_summary"
            ),
        },
        created_at=now,
        updated_at=now,
    )
    db.add(runtime_run)
    db.flush()
    graph_invocations_by_seq = persist_graph_schedule_invocation_skeletons(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        runtime_metadata=runtime_metadata,
        status="abandoned",
        purpose="graph node planned; graph runtime fallback",
    )

    invocation = AgentInvocation(
        id=new_id(),
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        invocation_seq=_next_invocation_seq(db, runtime_run.id),
        agent_id=SINGLE_LOOP_FALLBACK_AGENT_ID,
        status=status,
        purpose="single-loop graph fallback",
    )
    db.add(invocation)
    db.flush()

    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        event_type="run_created",
        payload={
            "source": "single_loop_fallback_shadow",
            "runtime_profile": runtime_run.runtime_profile,
            "graph_gate": runtime_metadata.get("graph_gate"),
            "graph_fallback_reason": runtime_metadata.get("graph_fallback_reason"),
        },
    )
    append_graph_candidate_trace_events(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        runtime_metadata=runtime_metadata,
    )
    append_graph_schedule_trace_events(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        runtime_metadata=runtime_metadata,
        graph_invocations_by_seq=graph_invocations_by_seq,
    )
    append_graph_execution_trace_events(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        runtime_metadata=runtime_metadata,
    )
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        agent_invocation_id=invocation.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        invocation_seq=invocation.invocation_seq,
        event_type="invocation_started",
        payload={"agent_id": invocation.agent_id},
    )
    terminal_event = _terminal_trace_event_prefix(status)
    terminal_payload = {
        "agent_id": invocation.agent_id,
        "finish_reason": finish_reason,
        "response_status": response_status,
    }
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        agent_invocation_id=invocation.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        invocation_seq=invocation.invocation_seq,
        event_type=f"invocation_{terminal_event}",
        payload=terminal_payload,
    )
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        event_type=f"run_{terminal_event}",
        payload={
            "finish_reason": finish_reason,
            "response_status": response_status,
        },
    )


def _persist_graph_execution_runtime_shadow(
    db: Session,
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    requested_by_user_id: str,
    runtime_metadata: dict[str, Any],
    finish_reason: str | None,
    response_status: str,
) -> None:
    now = utcnow_naive()
    status = _terminal_runtime_status(
        finish_reason=finish_reason,
        response_status=response_status,
    )
    runtime_run = AgentRun(
        id=agent_run_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        requested_by_user_id=requested_by_user_id,
        status=status,
        runtime_profile=_runtime_profile_from_metadata(runtime_metadata),
        graph_enabled=runtime_metadata.get("graph_gate") == "eligible",
        model_profile_id=str(
            runtime_metadata.get("model") or runtime_metadata.get("chosen_model") or ""
        )
        or None,
        fallback_reason=runtime_metadata.get("graph_fallback_reason"),
        metadata_json={
            "source": "graph_execution_shadow",
            "runtime_routing_reason_codes": runtime_metadata.get(
                "runtime_routing_reason_codes"
            ),
            "graph_gate": runtime_metadata.get("graph_gate"),
            "graph_fallback_reason": runtime_metadata.get("graph_fallback_reason"),
            "graph_used": bool(runtime_metadata.get("graph_used")),
            "graph_validation_status": runtime_metadata.get("graph_validation_status"),
            "graph_validation_fallback_reason": runtime_metadata.get(
                "graph_validation_fallback_reason"
            ),
            "graph_registry_agent_count": int(
                runtime_metadata.get("graph_registry_agent_count") or 0
            ),
            "graph_write_agent_count": int(
                runtime_metadata.get("graph_write_agent_count") or 0
            ),
            "graph_candidate_summary": runtime_metadata.get("graph_candidate_summary"),
            "graph_schedule_summary": runtime_metadata.get("graph_schedule_summary"),
            "external_egress_summary": runtime_metadata.get("external_egress_summary"),
            "graph_execution_status": runtime_metadata.get("graph_execution_status"),
            "graph_execution_fallback_reason": runtime_metadata.get(
                "graph_execution_fallback_reason"
            ),
            "graph_execution_fallback_policy": runtime_metadata.get(
                "graph_execution_fallback_policy"
            ),
            "graph_execution_adapter": runtime_metadata.get("graph_execution_adapter"),
            "graph_node_execution_summary": runtime_metadata.get(
                "graph_node_execution_summary"
            ),
        },
        created_at=now,
        updated_at=now,
    )
    db.add(runtime_run)
    db.flush()
    graph_invocations_by_seq = persist_graph_schedule_invocation_skeletons(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        runtime_metadata=runtime_metadata,
        status=status,
        purpose="graph node covered by graph adapter",
    )
    node_status_by_agent_id = _graph_node_status_by_agent_id(runtime_metadata)
    for invocation in graph_invocations_by_seq.values():
        invocation.status = node_status_by_agent_id.get(invocation.agent_id, status)
        db.add(invocation)
    db.flush()

    adapter_invocation = AgentInvocation(
        id=new_id(),
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        invocation_seq=_next_invocation_seq(db, runtime_run.id),
        agent_id=GRAPH_EXECUTION_ADAPTER_AGENT_ID,
        status=status,
        purpose="graph-instructed single-loop adapter execution",
    )
    db.add(adapter_invocation)
    db.flush()

    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        event_type="run_created",
        payload={
            "source": "graph_execution_shadow",
            "runtime_profile": runtime_run.runtime_profile,
            "graph_gate": runtime_metadata.get("graph_gate"),
            "graph_execution_adapter": runtime_metadata.get("graph_execution_adapter"),
        },
    )
    append_graph_candidate_trace_events(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        runtime_metadata=runtime_metadata,
    )
    append_graph_schedule_trace_events(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        runtime_metadata=runtime_metadata,
        graph_invocations_by_seq=graph_invocations_by_seq,
    )
    append_graph_execution_trace_events(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        runtime_metadata=runtime_metadata,
    )
    terminal_event = _terminal_trace_event_prefix(status)
    for invocation_seq, invocation in sorted(graph_invocations_by_seq.items()):
        node_terminal_event = _terminal_trace_event_prefix(invocation.status)
        append_trace_event(
            db,
            agent_run_id=runtime_run.id,
            agent_invocation_id=invocation.id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            invocation_seq=invocation_seq,
            event_type="graph_node_started",
            payload={
                "agent_id": invocation.agent_id,
                "adapter": runtime_metadata.get("graph_execution_adapter"),
            },
        )
        append_trace_event(
            db,
            agent_run_id=runtime_run.id,
            agent_invocation_id=invocation.id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            invocation_seq=invocation_seq,
            event_type=f"graph_node_{node_terminal_event}",
            payload={
                "agent_id": invocation.agent_id,
                "adapter": runtime_metadata.get("graph_execution_adapter"),
                "finish_reason": finish_reason,
                "response_status": response_status,
            },
        )
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        agent_invocation_id=adapter_invocation.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        invocation_seq=adapter_invocation.invocation_seq,
        event_type="invocation_started",
        payload={
            "agent_id": adapter_invocation.agent_id,
            "adapter": runtime_metadata.get("graph_execution_adapter"),
        },
    )
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        agent_invocation_id=adapter_invocation.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        invocation_seq=adapter_invocation.invocation_seq,
        event_type=f"invocation_{terminal_event}",
        payload={
            "agent_id": adapter_invocation.agent_id,
            "finish_reason": finish_reason,
            "response_status": response_status,
        },
    )
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        event_type=f"run_{terminal_event}",
        payload={
            "finish_reason": finish_reason,
            "response_status": response_status,
        },
    )


def _terminal_runtime_status(*, finish_reason: str | None, response_status: str) -> str:
    if response_status == "cancelled" or finish_reason == "cancelled":
        return "cancelled"
    if response_status == "error" or finish_reason == "error":
        return "failed"
    return "completed"


def _terminal_trace_event_prefix(status: str) -> str:
    if status == "failed":
        return "failed"
    if status == "cancelled":
        return "cancelled"
    return "completed"


def _runtime_profile_from_metadata(runtime_metadata: dict[str, Any]) -> str:
    runtime_profile = runtime_metadata.get("runtime_profile")
    if runtime_profile in {"interactive_read", "grounded_report", "long_doc", "high_risk_action"}:
        return str(runtime_profile)
    return "interactive_read"


def _graph_node_status_by_agent_id(runtime_metadata: dict[str, Any]) -> dict[str, str]:
    summary = runtime_metadata.get("graph_node_execution_summary")
    if not isinstance(summary, dict):
        return {}
    nodes = summary.get("nodes")
    if not isinstance(nodes, list):
        return {}
    statuses: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        agent_id = node.get("agent_id")
        raw_status = node.get("status")
        if not isinstance(agent_id, str) or not agent_id:
            continue
        if raw_status in {"completed", "failed", "cancelled"}:
            statuses[agent_id] = raw_status
    return statuses


def scrub_completed_runtime_records(db: Session, *, older_than_days: int = 90) -> int:
    threshold = utcnow_naive() - timedelta(days=older_than_days)
    runs = list(
        db.scalars(
            select(AgentRun).where(
                AgentRun.status.in_(TERMINAL_RUN_STATUSES),
                AgentRun.updated_at < threshold,
            )
        )
    )
    run_ids = [run.id for run in runs]
    if not run_ids:
        return 0

    for run in runs:
        run.metadata_json = None
        db.add(run)

    invocations = list(
        db.scalars(
            select(AgentInvocation).where(AgentInvocation.agent_run_id.in_(run_ids))
        )
    )
    for invocation in invocations:
        invocation.usage_json = None
        invocation.error = None
        db.add(invocation)

    trace_events = list(
        db.scalars(
            select(AgentTraceEvent).where(AgentTraceEvent.agent_run_id.in_(run_ids))
        )
    )
    for event in trace_events:
        event.payload_json = None
        db.add(event)

    return len(runs)


__all__ = [
    "append_graph_candidate_trace_events",
    "append_graph_execution_trace_events",
    "append_graph_schedule_trace_events",
    "append_trace_event",
    "persist_graph_execution_runtime_shadow",
    "persist_graph_schedule_invocation_skeletons",
    "persist_single_loop_fallback_runtime_shadow",
    "prepare_trace_payload",
    "scrub_completed_runtime_records",
    "scrub_trace_payload",
]
