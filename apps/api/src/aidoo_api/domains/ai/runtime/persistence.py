from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidoo_api.domains.ai.runtime.models import AgentRun, AgentTraceEvent
from aidoo_api.domains.auth.security import new_id


SENSITIVE_PAYLOAD_KEYS = {
    "api_key",
    "authorization",
    "password",
    "raw_provider_payload",
    "raw_reasoning",
    "reasoning",
    "secret",
    "token",
    "tool_secret",
}
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[-._~+/=a-z0-9]+"),
    re.compile(r"(?i)\b(api[_-]?key|x-api-key|authorization)\s*[:=]\s*[^,\s;]+"),
)


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
        payload_json=scrub_trace_payload(payload or {}),
    )
    db.add(event)
    db.flush()
    return event


__all__ = ["append_trace_event", "scrub_trace_payload"]
