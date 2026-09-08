from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.ai.runtime.models import AgentInvocation, AgentRun, AgentTraceEvent
from open_work_hub_api.domains.auth.models import utcnow_naive

TERMINAL_RUN_STATUSES = ("completed", "failed", "cancelled", "abandoned")


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
        db.scalars(select(AgentInvocation).where(AgentInvocation.agent_run_id.in_(run_ids)))
    )
    for invocation in invocations:
        invocation.usage_json = None
        invocation.error = None
        db.add(invocation)

    trace_events = list(
        db.scalars(select(AgentTraceEvent).where(AgentTraceEvent.agent_run_id.in_(run_ids)))
    )
    for event in trace_events:
        event.payload_json = None
        db.add(event)

    return len(runs)


__all__ = ["TERMINAL_RUN_STATUSES", "scrub_completed_runtime_records"]
