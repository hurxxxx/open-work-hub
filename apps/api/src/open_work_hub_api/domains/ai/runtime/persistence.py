from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.runtime.graph_schedule_summary import (
    graph_schedule_is_planned,
    ordered_graph_schedule_steps,
)
from open_work_hub_api.domains.ai.runtime.metrics import (
    record_shadow_write_failure,
    record_trace_event,
    record_trace_payload_truncated,
)
from open_work_hub_api.domains.ai.runtime.models import AgentInvocation, AgentRun, AgentTraceEvent
from open_work_hub_api.domains.ai.runtime.retention import scrub_completed_runtime_records
from open_work_hub_api.domains.ai.runtime.runtime_shadow_projection import (
    RuntimeShadowContext,
    build_runtime_shadow_context,
    graph_node_status_by_agent_id,
    runtime_profile_from_metadata,
    runtime_shadow_metadata_json,
    terminal_trace_event_prefix,
)
from open_work_hub_api.domains.ai.runtime.trace_payload import (
    prepare_trace_payload,
    scrub_trace_payload,
)
from open_work_hub_api.domains.ai.runtime.trace_projection import (
    graph_candidate_trace_payloads,
    graph_execution_gate_payload,
    graph_execution_run_created_payload,
    graph_node_planned_payload,
    invocation_started_payload,
    single_loop_run_created_payload,
    terminal_invocation_payload,
    terminal_run_payload,
)
from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.auth.security import new_id

logger = logging.getLogger(__name__)

SINGLE_LOOP_FALLBACK_AGENT_ID = "single_loop.fallback"
GRAPH_EXECUTION_ADAPTER_AGENT_ID = "graph.adapter.node_runner"
_ADAPTER_NOT_PROVIDED = object()


def append_trace_event(
    db: Session,
    *,
    agent_run_id: str,
    conversation_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    agent_invocation_id: str | None = None,
    run_seq: int = 0,
    invocation_seq: int = 0,
) -> AgentTraceEvent:
    prepared_payload, truncated = prepare_trace_payload(payload)
    db.scalar(select(AgentRun.id).where(AgentRun.id == agent_run_id).with_for_update())
    current = db.scalar(
        select(func.max(AgentTraceEvent.event_seq)).where(
            AgentTraceEvent.agent_run_id == agent_run_id
        )
    )
    event = AgentTraceEvent(
        id=new_id(),
        agent_run_id=agent_run_id,
        agent_invocation_id=agent_invocation_id,
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
    conversation_id: str,
    runtime_metadata: dict[str, Any],
) -> None:
    for event_type, payload in graph_candidate_trace_payloads(runtime_metadata):
        append_trace_event(
            db,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            event_type=event_type,
            payload=payload,
        )


def append_graph_schedule_trace_events(
    db: Session,
    *,
    agent_run_id: str,
    conversation_id: str,
    runtime_metadata: dict[str, Any],
    graph_invocations_by_seq: dict[int, AgentInvocation] | None = None,
) -> None:
    schedule_summary = runtime_metadata.get("graph_schedule_summary")
    if not isinstance(schedule_summary, dict):
        return

    if not graph_schedule_is_planned(schedule_summary):
        append_trace_event(
            db,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            event_type="graph_schedule_failed",
            payload={"graph_schedule_summary": schedule_summary},
        )
        return

    append_trace_event(
        db,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        event_type="graph_schedule_planned",
        payload={"graph_schedule_summary": schedule_summary},
    )
    for step in ordered_graph_schedule_steps(schedule_summary):
        invocation_seq = int(step["invocation_seq"])
        graph_invocation = (graph_invocations_by_seq or {}).get(invocation_seq)
        append_trace_event(
            db,
            agent_run_id=agent_run_id,
            agent_invocation_id=graph_invocation.id if graph_invocation else None,
            conversation_id=conversation_id,
            invocation_seq=invocation_seq,
            event_type="graph_node_planned",
            payload=graph_node_planned_payload(step),
        )


def append_graph_execution_trace_events(
    db: Session,
    *,
    agent_run_id: str,
    conversation_id: str,
    runtime_metadata: dict[str, Any],
) -> None:
    execution_status = runtime_metadata.get("graph_execution_status")
    if not isinstance(execution_status, str) or execution_status == "not_applicable":
        return
    append_trace_event(
        db,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        event_type="graph_execution_gate_evaluated",
        payload=graph_execution_gate_payload(runtime_metadata),
    )


def persist_graph_schedule_invocation_skeletons(
    db: Session,
    *,
    agent_run_id: str,
    conversation_id: str,
    runtime_metadata: dict[str, Any],
    status: str = "pending",
    purpose: str = "graph node planned",
) -> dict[int, AgentInvocation]:
    schedule_summary = runtime_metadata.get("graph_schedule_summary")
    if not graph_schedule_is_planned(schedule_summary):
        return {}

    invocations_by_seq: dict[int, AgentInvocation] = {}
    for step in ordered_graph_schedule_steps(schedule_summary):
        agent_id = step["agent_id"]
        invocation_seq = int(step["invocation_seq"])
        if invocation_seq in invocations_by_seq:
            continue
        invocation = AgentInvocation(
            id=new_id(),
            agent_run_id=agent_run_id,
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


def _create_runtime_shadow_run(
    db: Session,
    *,
    context: RuntimeShadowContext,
    source: str,
) -> AgentRun:
    now = utcnow_naive()
    runtime_metadata = context.runtime_metadata
    runtime_run = AgentRun(
        id=context.agent_run_id,
        conversation_id=context.conversation_id,
        requested_by_user_id=context.requested_by_user_id,
        status=context.status,
        runtime_profile=runtime_profile_from_metadata(runtime_metadata),
        graph_enabled=runtime_metadata.get("graph_gate") == "eligible",
        model_profile_id=str(
            runtime_metadata.get("model") or runtime_metadata.get("chosen_model") or ""
        )
        or None,
        fallback_reason=runtime_metadata.get("graph_fallback_reason"),
        metadata_json=runtime_shadow_metadata_json(
            source=source,
            runtime_metadata=runtime_metadata,
        ),
        created_at=now,
        updated_at=now,
    )
    db.add(runtime_run)
    db.flush()
    return runtime_run


def _create_runtime_shadow_invocation(
    db: Session,
    *,
    context: RuntimeShadowContext,
    runtime_run: AgentRun,
    agent_id: str,
    status: str,
    purpose: str,
) -> AgentInvocation:
    invocation = AgentInvocation(
        id=new_id(),
        agent_run_id=runtime_run.id,
        conversation_id=context.conversation_id,
        invocation_seq=_next_invocation_seq(db, runtime_run.id),
        agent_id=agent_id,
        status=status,
        purpose=purpose,
    )
    db.add(invocation)
    db.flush()
    return invocation


def _append_common_graph_shadow_trace_events(
    db: Session,
    *,
    context: RuntimeShadowContext,
    runtime_run: AgentRun,
    graph_invocations_by_seq: dict[int, AgentInvocation],
) -> None:
    append_graph_candidate_trace_events(
        db,
        agent_run_id=runtime_run.id,
        conversation_id=context.conversation_id,
        runtime_metadata=context.runtime_metadata,
    )
    append_graph_schedule_trace_events(
        db,
        agent_run_id=runtime_run.id,
        conversation_id=context.conversation_id,
        runtime_metadata=context.runtime_metadata,
        graph_invocations_by_seq=graph_invocations_by_seq,
    )
    append_graph_execution_trace_events(
        db,
        agent_run_id=runtime_run.id,
        conversation_id=context.conversation_id,
        runtime_metadata=context.runtime_metadata,
    )


def _runtime_invocation_started_payload(
    *,
    agent_id: str,
    adapter: Any = _ADAPTER_NOT_PROVIDED,
) -> dict[str, Any]:
    if adapter is _ADAPTER_NOT_PROVIDED:
        return invocation_started_payload(agent_id=agent_id)
    return invocation_started_payload(agent_id=agent_id, adapter=adapter)


def _runtime_terminal_invocation_payload(
    *,
    agent_id: str,
    finish_reason: str | None,
    response_status: str,
    adapter: Any = _ADAPTER_NOT_PROVIDED,
) -> dict[str, Any]:
    if adapter is _ADAPTER_NOT_PROVIDED:
        return terminal_invocation_payload(
            agent_id=agent_id,
            finish_reason=finish_reason,
            response_status=response_status,
        )
    return terminal_invocation_payload(
        agent_id=agent_id,
        adapter=adapter,
        finish_reason=finish_reason,
        response_status=response_status,
    )


def _append_invocation_started_trace_event(
    db: Session,
    *,
    context: RuntimeShadowContext,
    runtime_run: AgentRun,
    invocation: AgentInvocation,
    event_type: str = "invocation_started",
    invocation_seq: int | None = None,
    adapter: Any = _ADAPTER_NOT_PROVIDED,
) -> None:
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        agent_invocation_id=invocation.id,
        conversation_id=context.conversation_id,
        invocation_seq=(invocation.invocation_seq if invocation_seq is None else invocation_seq),
        event_type=event_type,
        payload=_runtime_invocation_started_payload(
            agent_id=invocation.agent_id,
            adapter=adapter,
        ),
    )


def _append_terminal_invocation_trace_event(
    db: Session,
    *,
    context: RuntimeShadowContext,
    runtime_run: AgentRun,
    invocation: AgentInvocation,
    event_type_prefix: str = "invocation",
    terminal_event: str | None = None,
    invocation_seq: int | None = None,
    adapter: Any = _ADAPTER_NOT_PROVIDED,
) -> None:
    event_suffix = terminal_event or context.terminal_event
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        agent_invocation_id=invocation.id,
        conversation_id=context.conversation_id,
        invocation_seq=(invocation.invocation_seq if invocation_seq is None else invocation_seq),
        event_type=f"{event_type_prefix}_{event_suffix}",
        payload=_runtime_terminal_invocation_payload(
            agent_id=invocation.agent_id,
            adapter=adapter,
            finish_reason=context.finish_reason,
            response_status=context.response_status,
        ),
    )


def _append_terminal_run_trace_event(
    db: Session,
    *,
    context: RuntimeShadowContext,
    runtime_run: AgentRun,
) -> None:
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        conversation_id=context.conversation_id,
        event_type=f"run_{context.terminal_event}",
        payload=terminal_run_payload(
            finish_reason=context.finish_reason,
            response_status=context.response_status,
        ),
    )


def _append_terminal_invocation_and_run_trace_events(
    db: Session,
    *,
    context: RuntimeShadowContext,
    runtime_run: AgentRun,
    invocation: AgentInvocation,
    start_adapter: Any = _ADAPTER_NOT_PROVIDED,
    terminal_adapter: Any = _ADAPTER_NOT_PROVIDED,
) -> None:
    _append_invocation_started_trace_event(
        db,
        context=context,
        runtime_run=runtime_run,
        invocation=invocation,
        adapter=start_adapter,
    )
    _append_terminal_invocation_trace_event(
        db,
        context=context,
        runtime_run=runtime_run,
        invocation=invocation,
        adapter=terminal_adapter,
    )
    _append_terminal_run_trace_event(
        db,
        context=context,
        runtime_run=runtime_run,
    )


def persist_single_loop_fallback_runtime_shadow(
    db: Session,
    *,
    agent_run_id: str,
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
                "operation": "persist_single_loop_fallback_runtime_shadow",
            },
        )


def persist_graph_execution_runtime_shadow(
    db: Session,
    *,
    agent_run_id: str,
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
                "operation": "persist_graph_execution_runtime_shadow",
            },
        )


def _persist_single_loop_fallback_runtime_shadow(
    db: Session,
    *,
    agent_run_id: str,
    conversation_id: str,
    requested_by_user_id: str,
    runtime_metadata: dict[str, Any],
    finish_reason: str | None,
    response_status: str,
) -> None:
    context = build_runtime_shadow_context(
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        requested_by_user_id=requested_by_user_id,
        runtime_metadata=runtime_metadata,
        finish_reason=finish_reason,
        response_status=response_status,
    )
    runtime_run = _create_runtime_shadow_run(
        db,
        context=context,
        source="single_loop_fallback_shadow",
    )
    graph_invocations_by_seq = persist_graph_schedule_invocation_skeletons(
        db,
        agent_run_id=runtime_run.id,
        conversation_id=context.conversation_id,
        runtime_metadata=context.runtime_metadata,
        status="abandoned",
        purpose="graph node planned; graph runtime fallback",
    )

    invocation = _create_runtime_shadow_invocation(
        db,
        context=context,
        runtime_run=runtime_run,
        agent_id=SINGLE_LOOP_FALLBACK_AGENT_ID,
        status=context.status,
        purpose="single-loop graph fallback",
    )

    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        conversation_id=context.conversation_id,
        event_type="run_created",
        payload=single_loop_run_created_payload(
            runtime_profile=runtime_run.runtime_profile,
            runtime_metadata=context.runtime_metadata,
        ),
    )
    _append_common_graph_shadow_trace_events(
        db,
        context=context,
        runtime_run=runtime_run,
        graph_invocations_by_seq=graph_invocations_by_seq,
    )
    _append_terminal_invocation_and_run_trace_events(
        db,
        context=context,
        runtime_run=runtime_run,
        invocation=invocation,
    )


def _persist_graph_execution_runtime_shadow(
    db: Session,
    *,
    agent_run_id: str,
    conversation_id: str,
    requested_by_user_id: str,
    runtime_metadata: dict[str, Any],
    finish_reason: str | None,
    response_status: str,
) -> None:
    context = build_runtime_shadow_context(
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        requested_by_user_id=requested_by_user_id,
        runtime_metadata=runtime_metadata,
        finish_reason=finish_reason,
        response_status=response_status,
    )
    runtime_run = _create_runtime_shadow_run(
        db,
        context=context,
        source="graph_execution_shadow",
    )
    graph_invocations_by_seq = persist_graph_schedule_invocation_skeletons(
        db,
        agent_run_id=runtime_run.id,
        conversation_id=context.conversation_id,
        runtime_metadata=context.runtime_metadata,
        status=context.status,
        purpose="graph node covered by graph adapter",
    )
    node_status_by_agent_id = graph_node_status_by_agent_id(context.runtime_metadata)
    for invocation in graph_invocations_by_seq.values():
        invocation.status = node_status_by_agent_id.get(
            invocation.agent_id,
            context.status,
        )
        db.add(invocation)
    db.flush()

    adapter_invocation = _create_runtime_shadow_invocation(
        db,
        context=context,
        runtime_run=runtime_run,
        agent_id=GRAPH_EXECUTION_ADAPTER_AGENT_ID,
        status=context.status,
        purpose="graph-instructed single-loop adapter execution",
    )

    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        conversation_id=context.conversation_id,
        event_type="run_created",
        payload=graph_execution_run_created_payload(
            runtime_profile=runtime_run.runtime_profile,
            runtime_metadata=context.runtime_metadata,
        ),
    )
    _append_common_graph_shadow_trace_events(
        db,
        context=context,
        runtime_run=runtime_run,
        graph_invocations_by_seq=graph_invocations_by_seq,
    )
    graph_execution_adapter = context.runtime_metadata.get("graph_execution_adapter")
    for invocation_seq, invocation in sorted(graph_invocations_by_seq.items()):
        node_terminal_event = terminal_trace_event_prefix(invocation.status)
        _append_invocation_started_trace_event(
            db,
            context=context,
            runtime_run=runtime_run,
            invocation=invocation,
            invocation_seq=invocation_seq,
            event_type="graph_node_started",
            adapter=graph_execution_adapter,
        )
        _append_terminal_invocation_trace_event(
            db,
            context=context,
            runtime_run=runtime_run,
            invocation=invocation,
            invocation_seq=invocation_seq,
            event_type_prefix="graph_node",
            terminal_event=node_terminal_event,
            adapter=graph_execution_adapter,
        )
    _append_terminal_invocation_and_run_trace_events(
        db,
        context=context,
        runtime_run=runtime_run,
        invocation=adapter_invocation,
        start_adapter=graph_execution_adapter,
    )


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
