from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from open_alm_api.core.settings import get_settings
from open_alm_api.domains.ai.runtime.metrics import record_shadow_write_failure
from open_alm_api.domains.ai.runtime.models import AgentInvocation, AgentRun
from open_alm_api.domains.ai.runtime.persistence import (
    append_graph_candidate_trace_events,
    append_graph_execution_trace_events,
    append_graph_schedule_trace_events,
    append_trace_event,
    persist_graph_schedule_invocation_skeletons,
)
from open_alm_api.domains.ai.runtime.runtime_shadow_projection import (
    runtime_profile_from_metadata,
    runtime_shadow_metadata_json,
)
from open_alm_api.domains.auth.models import utcnow_naive
from open_alm_api.domains.auth.security import new_id


logger = logging.getLogger(__name__)

SNAPSHOT_SCOPE_META_KEY = "scope"


def safe_runtime_shadow_write(
    db: Session,
    *,
    snapshot: Any,
    operation: Callable[..., None],
) -> None:
    if not get_settings().ai_runtime_shadow_write_enabled:
        return
    try:
        with db.begin_nested():
            operation(db, snapshot=snapshot)
    except Exception:
        operation_name = getattr(operation, "__name__", "anonymous")
        record_shadow_write_failure(operation=operation_name)
        logger.exception(
            "ai_runtime.shadow_write_failed",
            extra={
                "agent_run_id": snapshot.id,
                "conversation_id": snapshot.conversation_id,
                "workspace_id": snapshot.workspace_id,
                "operation": operation_name,
            },
        )


def persist_runtime_shadow_on_halt(
    db: Session,
    *,
    snapshot: Any,
) -> None:
    model_meta = dict(snapshot.model_meta or {})
    metadata_json = runtime_shadow_metadata_json(
        source="approval_snapshot_shadow",
        runtime_metadata=model_meta,
    )
    metadata_json.update(
        {
            "blocked_call_id": snapshot.blocked_call_id,
            SNAPSHOT_SCOPE_META_KEY: model_meta.get(SNAPSHOT_SCOPE_META_KEY),
        }
    )
    runtime_run = AgentRun(
        id=snapshot.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        requested_by_user_id=snapshot.requested_by_user_id,
        legacy_snapshot_id=snapshot.id,
        status="awaiting_approval",
        runtime_profile=runtime_profile_from_metadata(model_meta),
        graph_enabled=model_meta.get("graph_gate") == "eligible",
        model_profile_id=str(model_meta.get("model") or model_meta.get("chosen_model") or "")
        or None,
        metadata_json=metadata_json,
    )
    db.add(runtime_run)
    db.flush()
    graph_invocations_by_seq = persist_graph_schedule_invocation_skeletons(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        runtime_metadata=model_meta,
    )
    invocation = next(
        (
            graph_invocation
            for graph_invocation in graph_invocations_by_seq.values()
            if graph_invocation.agent_id == "approval.proposal_preview"
        ),
        None,
    )
    if invocation is None:
        invocation = AgentInvocation(
            id=new_id(),
            agent_run_id=runtime_run.id,
            workspace_id=snapshot.workspace_id,
            conversation_id=snapshot.conversation_id,
            invocation_seq=_next_runtime_invocation_seq(db, runtime_run.id),
            agent_id="approval.proposal_preview",
            status="awaiting_approval",
            purpose="approval required",
            input_ref=snapshot.blocked_call_id,
        )
    else:
        invocation.status = "awaiting_approval"
        invocation.purpose = "approval required"
        invocation.input_ref = snapshot.blocked_call_id
    db.add(invocation)
    db.flush()
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        event_type="run_created",
        payload={
            "source": "approval_snapshot_shadow",
            "legacy_snapshot_id": snapshot.id,
        },
    )
    append_graph_candidate_trace_events(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        runtime_metadata=model_meta,
    )
    append_graph_schedule_trace_events(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        runtime_metadata=model_meta,
        graph_invocations_by_seq=graph_invocations_by_seq,
    )
    append_graph_execution_trace_events(
        db,
        agent_run_id=runtime_run.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        runtime_metadata=model_meta,
    )
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        agent_invocation_id=invocation.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        invocation_seq=invocation.invocation_seq,
        event_type="invocation_started",
        payload={"agent_id": invocation.agent_id},
    )
    append_trace_event(
        db,
        agent_run_id=runtime_run.id,
        agent_invocation_id=invocation.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        invocation_seq=invocation.invocation_seq,
        event_type="approval_required",
        payload={
            "blocked_call_id": snapshot.blocked_call_id,
            "scope": model_meta.get(SNAPSHOT_SCOPE_META_KEY),
            "runtime_profile": runtime_run.runtime_profile,
            "runtime_routing_reason_codes": model_meta.get("runtime_routing_reason_codes"),
        },
    )


def mark_runtime_shadow_completed(
    db: Session,
    *,
    snapshot: Any,
) -> None:
    now = utcnow_naive()
    runtime_run = db.get(AgentRun, snapshot.id)
    if runtime_run is None:
        return
    runtime_run.status = "completed"
    runtime_run.updated_at = now
    db.add(runtime_run)
    db.execute(
        update(AgentInvocation)
        .where(
            AgentInvocation.agent_run_id == snapshot.id,
            AgentInvocation.status.in_(("pending", "running", "awaiting_approval", "resumed")),
        )
        .values(status="completed", updated_at=now)
    )
    append_trace_event(
        db,
        agent_run_id=snapshot.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        event_type="run_completed",
        payload={"legacy_snapshot_id": snapshot.id},
    )


def mark_runtime_shadow_abandoned(
    db: Session,
    *,
    snapshot: Any,
    cause: str,
) -> None:
    now = utcnow_naive()
    runtime_run = db.get(AgentRun, snapshot.id)
    if runtime_run is None:
        return
    runtime_run.status = "abandoned"
    runtime_run.updated_at = now
    db.add(runtime_run)
    db.execute(
        update(AgentInvocation)
        .where(
            AgentInvocation.agent_run_id == snapshot.id,
            AgentInvocation.status.in_(("pending", "running", "awaiting_approval", "resumed")),
        )
        .values(status="abandoned", updated_at=now)
    )
    append_trace_event(
        db,
        agent_run_id=snapshot.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        event_type="run_abandoned",
        payload={"legacy_snapshot_id": snapshot.id, "cause": cause},
    )


def mark_runtime_shadow_awaiting_approval(
    db: Session,
    *,
    snapshot: Any,
) -> None:
    now = utcnow_naive()
    runtime_run = db.get(AgentRun, snapshot.id)
    if runtime_run is None:
        return
    runtime_run.status = "awaiting_approval"
    runtime_run.updated_at = now
    db.add(runtime_run)
    invocation = db.scalar(
        select(AgentInvocation)
        .where(
            AgentInvocation.agent_run_id == snapshot.id,
            AgentInvocation.status == "resumed",
        )
        .order_by(AgentInvocation.invocation_seq.desc())
        .limit(1)
    )
    if invocation is not None:
        invocation.status = "awaiting_approval"
        invocation.updated_at = now
        db.add(invocation)
    append_trace_event(
        db,
        agent_run_id=snapshot.id,
        agent_invocation_id=invocation.id if invocation is not None else None,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        invocation_seq=invocation.invocation_seq if invocation is not None else 0,
        event_type="approval_resume_rewound",
        payload={
            "blocked_call_id": snapshot.blocked_call_id,
            "legacy_snapshot_id": snapshot.id,
        },
    )


def mark_runtime_shadow_resumed(
    db: Session,
    *,
    snapshot: Any,
) -> None:
    now = utcnow_naive()
    runtime_run = db.get(AgentRun, snapshot.id)
    if runtime_run is None:
        return
    runtime_run.status = "running"
    runtime_run.updated_at = now
    db.add(runtime_run)
    db.execute(
        update(AgentInvocation)
        .where(
            AgentInvocation.agent_run_id == snapshot.id,
            AgentInvocation.status == "awaiting_approval",
        )
        .values(status="resumed", updated_at=now)
    )
    invocation = AgentInvocation(
        id=new_id(),
        agent_run_id=snapshot.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        invocation_seq=_next_runtime_invocation_seq(db, snapshot.id),
        agent_id="approval.proposal_preview",
        status="resumed",
        purpose="approval resumed",
        input_ref=snapshot.blocked_call_id,
    )
    db.add(invocation)
    db.flush()
    append_trace_event(
        db,
        agent_run_id=snapshot.id,
        agent_invocation_id=invocation.id,
        workspace_id=snapshot.workspace_id,
        conversation_id=snapshot.conversation_id,
        invocation_seq=invocation.invocation_seq,
        event_type="approval_resumed",
        payload={
            "blocked_call_id": snapshot.blocked_call_id,
            "legacy_snapshot_id": snapshot.id,
        },
    )


def _next_runtime_invocation_seq(db: Session, agent_run_id: str) -> int:
    current = db.scalar(
        select(func.max(AgentInvocation.invocation_seq)).where(
            AgentInvocation.agent_run_id == agent_run_id
        )
    )
    return int(current if current is not None else -1) + 1
