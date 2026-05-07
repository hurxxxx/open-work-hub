"""Audit helpers for LLM requests.

Intentionally minimal: one function, one payload shape. The raw prompt/content
is **never** stored — only identity + decision + counters + error summary.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_do_api.core.telemetry import current_trace_id
from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.auth.access import record_audit_log


ACTION_LLM_CALL = "llm_call"
ACTION_LLM_TOOL_CALL = "llm_tool_call"
ACTION_LLM_TOOL_APPROVAL_RESOLVED = "llm_tool_approval_resolved"
ENTITY_KIND_LLM_TASK = "llm_task"
ENTITY_KIND_TOOL_CALL = "ai_tool"
ENTITY_KIND_TOOL_APPROVAL = "ai_tool_approval"
logger = logging.getLogger(__name__)


def log_llm_call(
    *,
    source: str,
    actor_user_id: str | None,
    principal_kind: str,
    principal_id: str | None,
    workspace_id: str,
    task_kind: str,
    policy: str | None,
    chosen_pool: str,
    decision_reason: str | None,
    forced_local: bool,
    pii_hits: list[str] | None,
    model: str,
    status: str,
    latency_ms: int,
    usage: dict[str, int] | None = None,
    max_tokens: int | None = None,
    finish_reason: str | None = None,
    error: str | None = None,
    entity_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
) -> None:
    """Record a single LLM request to the audit log.

    ``status`` is one of ``ok``, ``error``, ``blocked_by_pii``, or
    ``cancelled`` (streaming: consumer closed the generator). ``usage`` is
    expected to carry the fixed shape
    ``{prompt_tokens, completion_tokens, total_tokens}``; individual fields
    may be missing when the provider did not report them.
    """
    payload: dict[str, Any] = {
        "source": source,
        "actor_user_id": actor_user_id,
        "principal_kind": principal_kind,
        "principal_id": principal_id,
        "workspace_id": workspace_id,
        "task_kind": task_kind,
        "policy": policy,
        "chosen_pool": chosen_pool,
        "decision_reason": decision_reason,
        "forced_local": forced_local,
        "pii_hits": list(pii_hits or []),
        "model": model,
        "status": status,
        "latency_ms": latency_ms,
        "usage": dict(usage) if usage else None,
        "max_tokens": max_tokens,
        "finish_reason": finish_reason,
        "trace_id": current_trace_id(),
    }
    if error:
        payload["error"] = error
    if agent_run_id:
        payload["agent_run_id"] = agent_run_id
    if conversation_id:
        payload["conversation_id"] = conversation_id

    summary = (
        f"llm_call source={source} pool={chosen_pool} task_kind={task_kind} "
        f"status={status}"
    )

    _persist_audit_event(
        action=ACTION_LLM_CALL,
        entity_kind=ENTITY_KIND_LLM_TASK,
        entity_id=entity_id,
        summary=summary,
        actor_user_id=actor_user_id,
        payload=payload,
    )


def log_llm_tool_call(
    *,
    source: str,
    actor_user_id: str | None,
    principal_kind: str,
    principal_id: str | None,
    workspace_id: str,
    tool_name: str,
    args_summary: str,
    status: str,
    resource_ids: list[str] | None,
    latency_ms: int,
    call_id: str | None = None,
    approval_id: str | None = None,
    error: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "source": source,
        "actor_user_id": actor_user_id,
        "principal_kind": principal_kind,
        "principal_id": principal_id,
        "workspace_id": workspace_id,
        "tool_name": tool_name,
        "args_summary": args_summary,
        "status": status,
        "resource_ids": list(resource_ids or []),
        "latency_ms": latency_ms,
        "call_id": call_id,
        "approval_id": approval_id,
        "trace_id": current_trace_id(),
    }
    if error:
        payload["error"] = error
    if agent_run_id:
        payload["agent_run_id"] = agent_run_id
    if conversation_id:
        payload["conversation_id"] = conversation_id

    summary = (
        f"llm_tool_call source={source} tool={tool_name} status={status}"
    )

    _persist_audit_event(
        action=ACTION_LLM_TOOL_CALL,
        entity_kind=ENTITY_KIND_TOOL_CALL,
        entity_id=call_id,
        summary=summary,
        actor_user_id=actor_user_id,
        payload=payload,
    )


def log_llm_tool_approval_resolved(
    *,
    actor_user_id: str | None,
    workspace_id: str,
    approval_id: str,
    tool_name: str,
    decision: str,
    resolver_user_id: str | None,
    elapsed_since_request_ms: int,
) -> None:
    payload: dict[str, Any] = {
        "workspace_id": workspace_id,
        "approval_id": approval_id,
        "tool_name": tool_name,
        "decision": decision,
        "resolver_user_id": resolver_user_id,
        "elapsed_since_request_ms": elapsed_since_request_ms,
    }
    summary = (
        "llm_tool_approval_resolved "
        f"tool={tool_name} decision={decision} approval_id={approval_id}"
    )
    _persist_audit_event(
        action=ACTION_LLM_TOOL_APPROVAL_RESOLVED,
        entity_kind=ENTITY_KIND_TOOL_APPROVAL,
        entity_id=approval_id,
        summary=summary,
        actor_user_id=actor_user_id,
        payload=payload,
    )


def _persist_audit_event(
    *,
    action: str,
    entity_kind: str,
    entity_id: str | None,
    summary: str,
    actor_user_id: str | None,
    payload: dict[str, Any],
) -> None:

    audit_db = get_session_factory()()
    try:
        record_audit_log(
            audit_db,
            action=action,
            entity_kind=entity_kind,
            entity_id=entity_id,
            summary=summary,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        audit_db.commit()
    except Exception:
        audit_db.rollback()
        logger.warning("Failed to persist AI audit log", exc_info=True)
    finally:
        audit_db.close()
