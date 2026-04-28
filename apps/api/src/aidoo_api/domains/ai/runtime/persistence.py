from __future__ import annotations

from datetime import timedelta
import json
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.runtime.metrics import (
    record_trace_event,
    record_trace_payload_truncated,
)
from aidoo_api.domains.ai.runtime.models import AgentInvocation, AgentRun, AgentTraceEvent
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.meeting.models import utcnow_naive


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
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[-._~+/=a-z0-9]+"),
    re.compile(r"(?i)\b(api[_-]?key|x-api-key|authorization)\s*[:=]\s*[^,\s;]+"),
    re.compile(r"(?i)\b(session|access|refresh|id)[_-]?token\s*[:=]\s*[^,\s;]+"),
    re.compile(r"(?i)\b(cookie|set-cookie)\s*[:=]\s*[^,\s;]+"),
)
TERMINAL_RUN_STATUSES = ("completed", "failed", "cancelled", "abandoned")


def scrub_trace_payload(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(marker in normalized_key for marker in SENSITIVE_PAYLOAD_KEYS):
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
    "append_trace_event",
    "prepare_trace_payload",
    "scrub_completed_runtime_records",
    "scrub_trace_payload",
]
