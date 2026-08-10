"""Audit helpers for LLM requests.

Full raw prompt/content is not stored. AI security detections may additionally
write detector-specific value/count statistics to a dedicated monitoring table.
"""

from __future__ import annotations

import logging
from typing import Any

from open_work_hub_api.core.telemetry import current_trace_id
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.ai.security_detected_values import (
    record_ai_security_detected_values,
)
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.ai.interactions import record_ai_interaction


ACTION_LLM_CALL = "llm_call"
ACTION_AI_EXTERNAL_CALL = "ai_external_call"
ACTION_LLM_TOOL_CALL = "llm_tool_call"
ACTION_LLM_TOOL_APPROVAL_RESOLVED = "llm_tool_approval_resolved"
ENTITY_KIND_AI_EXTERNAL_CAPABILITY = "ai_external_capability"
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
    app_id: str,
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
    context_strategy: str | None = None,
    estimated_input_tokens: int | None = None,
    sensitivity_labels: list[str] | None = None,
    blocked_entity_types: list[str] | None = None,
    content_origin: str | None = None,
    source_kinds: list[str] | None = None,
    ai_security_policy_effect: str | None = None,
    ai_security_policy_rule_id: str | None = None,
    ai_security_policy_reason: str | None = None,
    ai_security_policy_audit_only: bool = False,
    custom_block_term_count: int = 0,
    external_transfer_exception_id: str | None = None,
    external_transfer_exception_name: str | None = None,
    external_transfer_exception_reason: str | None = None,
    external_transfer_exception_blockers: list[str] | None = None,
    ai_security_pipeline_exemption_id: str | None = None,
    ai_security_pipeline_exemption_name: str | None = None,
    ai_security_pipeline_exemption_reason: str | None = None,
    mask_applied: bool = False,
    masked_entity_types: list[str] | None = None,
    masked_text_count: int = 0,
    privacy_filter_status: str | None = None,
    privacy_filter_used: bool = False,
    finish_reason: str | None = None,
    error: str | None = None,
    entity_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    detected_values: list[dict[str, object]] | None = None,
    workload_id: str | None = None,
) -> None:
    """Record a single LLM request to the audit log.

    ``status`` is one of ``ok``, ``error``, ``blocked_by_pii``, or
    ``cancelled`` (streaming: consumer closed the generator). ``usage`` is
    expected to carry the fixed shape
    ``{prompt_tokens, completion_tokens, total_tokens}``; individual fields
    may be missing when the provider did not report them.
    """
    payload = _with_trace_and_optional_fields(
        {
            **_identity_payload(
                source=source,
                actor_user_id=actor_user_id,
                principal_kind=principal_kind,
                principal_id=principal_id,
                workspace_id=workspace_id,
            ),
            "task_kind": task_kind,
            "workload_id": workload_id,
            "app_id": app_id,
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
            "context_strategy": context_strategy,
            "estimated_input_tokens": estimated_input_tokens,
            "sensitivity_labels": list(sensitivity_labels or []),
            "blocked_entity_types": list(blocked_entity_types or []),
            "content_origin": content_origin,
            "source_kinds": list(source_kinds or []),
            "ai_security_policy_effect": ai_security_policy_effect,
            "ai_security_policy_rule_id": ai_security_policy_rule_id,
            "ai_security_policy_reason": ai_security_policy_reason,
            "ai_security_policy_audit_only": ai_security_policy_audit_only,
            "custom_block_term_count": custom_block_term_count,
            "external_transfer_exception_id": external_transfer_exception_id,
            "external_transfer_exception_name": external_transfer_exception_name,
            "external_transfer_exception_reason": external_transfer_exception_reason,
            "external_transfer_exception_blockers": list(
                external_transfer_exception_blockers or []
            ),
            "ai_security_pipeline_exemption_id": ai_security_pipeline_exemption_id,
            "ai_security_pipeline_exemption_name": ai_security_pipeline_exemption_name,
            "ai_security_pipeline_exemption_reason": ai_security_pipeline_exemption_reason,
            "mask_applied": mask_applied,
            "masked_entity_types": list(masked_entity_types or []),
            "masked_text_count": masked_text_count,
            "privacy_filter_status": privacy_filter_status,
            "privacy_filter_used": privacy_filter_used,
            "finish_reason": finish_reason,
        },
        error=error,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )

    _record_audit_event(
        action=ACTION_LLM_CALL,
        entity_kind=ENTITY_KIND_LLM_TASK,
        entity_id=entity_id,
        summary_fields={
            "source": source,
            "pool": chosen_pool,
            "task_kind": task_kind,
            "workload_id": workload_id,
            "app_id": app_id,
            "status": status,
        },
        actor_user_id=actor_user_id,
        payload=payload,
        detected_values=detected_values,
    )


def log_ai_external_call(
    *,
    source: str,
    actor_user_id: str | None,
    principal_kind: str,
    principal_id: str | None,
    workspace_id: str,
    task_kind: str,
    capability: str,
    provider: str | None,
    status: str,
    latency_ms: int,
    policy_reason: str | None,
    app_id: str | None = None,
    pii_hits: list[str] | None = None,
    removed_entity_types: list[str] | None = None,
    blocked_entity_types: list[str] | None = None,
    sensitivity_labels: list[str] | None = None,
    content_origin: str | None = None,
    source_kinds: list[str] | None = None,
    ai_security_policy_effect: str | None = None,
    ai_security_policy_rule_id: str | None = None,
    ai_security_policy_reason: str | None = None,
    ai_security_policy_audit_only: bool = False,
    custom_block_term_count: int = 0,
    external_transfer_exception_id: str | None = None,
    external_transfer_exception_name: str | None = None,
    external_transfer_exception_reason: str | None = None,
    external_transfer_exception_blockers: list[str] | None = None,
    ai_security_pipeline_exemption_id: str | None = None,
    ai_security_pipeline_exemption_name: str | None = None,
    ai_security_pipeline_exemption_reason: str | None = None,
    mask_applied: bool = False,
    masked_entity_types: list[str] | None = None,
    masked_text_count: int = 0,
    privacy_filter_status: str | None = None,
    privacy_filter_used: bool = False,
    input_text_count: int = 0,
    input_char_count: int = 0,
    usage: dict[str, int] | None = None,
    metadata: dict[str, Any] | None = None,
    error: str | None = None,
    entity_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    detected_values: list[dict[str, object]] | None = None,
) -> None:
    """Record an external provider capability call without storing raw input."""
    payload = _with_trace_and_optional_fields(
        {
            **_identity_payload(
                source=source,
                actor_user_id=actor_user_id,
                principal_kind=principal_kind,
                principal_id=principal_id,
                workspace_id=workspace_id,
            ),
            "task_kind": task_kind,
            "app_id": app_id,
            "capability": capability,
            "provider": provider,
            "status": status,
            "latency_ms": latency_ms,
            "policy_reason": policy_reason,
            "pii_hits": list(pii_hits or []),
            "removed_entity_types": list(removed_entity_types or []),
            "blocked_entity_types": list(blocked_entity_types or []),
            "sensitivity_labels": list(sensitivity_labels or []),
            "content_origin": content_origin,
            "source_kinds": list(source_kinds or []),
            "ai_security_policy_effect": ai_security_policy_effect,
            "ai_security_policy_rule_id": ai_security_policy_rule_id,
            "ai_security_policy_reason": ai_security_policy_reason,
            "ai_security_policy_audit_only": ai_security_policy_audit_only,
            "custom_block_term_count": custom_block_term_count,
            "external_transfer_exception_id": external_transfer_exception_id,
            "external_transfer_exception_name": external_transfer_exception_name,
            "external_transfer_exception_reason": external_transfer_exception_reason,
            "external_transfer_exception_blockers": list(
                external_transfer_exception_blockers or []
            ),
            "ai_security_pipeline_exemption_id": ai_security_pipeline_exemption_id,
            "ai_security_pipeline_exemption_name": ai_security_pipeline_exemption_name,
            "ai_security_pipeline_exemption_reason": ai_security_pipeline_exemption_reason,
            "mask_applied": mask_applied,
            "masked_entity_types": list(masked_entity_types or []),
            "masked_text_count": masked_text_count,
            "privacy_filter_status": privacy_filter_status,
            "privacy_filter_used": privacy_filter_used,
            "input_text_count": input_text_count,
            "input_char_count": input_char_count,
            "usage": dict(usage) if usage else None,
            "metadata": dict(metadata or {}),
        },
        error=error,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )

    _record_audit_event(
        action=ACTION_AI_EXTERNAL_CALL,
        entity_kind=ENTITY_KIND_AI_EXTERNAL_CAPABILITY,
        entity_id=entity_id,
        summary_fields={
            "source": source,
            "capability": capability,
            "provider": provider,
            "status": status,
        },
        actor_user_id=actor_user_id,
        payload=payload,
        detected_values=detected_values,
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
    payload = _with_trace_and_optional_fields(
        {
            **_identity_payload(
                source=source,
                actor_user_id=actor_user_id,
                principal_kind=principal_kind,
                principal_id=principal_id,
                workspace_id=workspace_id,
            ),
            "tool_name": tool_name,
            "args_summary": args_summary,
            "status": status,
            "resource_ids": list(resource_ids or []),
            "latency_ms": latency_ms,
            "call_id": call_id,
            "approval_id": approval_id,
        },
        error=error,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )

    _record_audit_event(
        action=ACTION_LLM_TOOL_CALL,
        entity_kind=ENTITY_KIND_TOOL_CALL,
        entity_id=call_id,
        summary_fields={
            "source": source,
            "tool": tool_name,
            "status": status,
        },
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
    _record_audit_event(
        action=ACTION_LLM_TOOL_APPROVAL_RESOLVED,
        entity_kind=ENTITY_KIND_TOOL_APPROVAL,
        entity_id=approval_id,
        summary_fields={
            "tool": tool_name,
            "decision": decision,
            "approval_id": approval_id,
        },
        actor_user_id=actor_user_id,
        payload=payload,
    )


def _identity_payload(
    *,
    source: str,
    actor_user_id: str | None,
    principal_kind: str,
    principal_id: str | None,
    workspace_id: str,
) -> dict[str, Any]:
    return {
        "source": source,
        "actor_user_id": actor_user_id,
        "principal_kind": principal_kind,
        "principal_id": principal_id,
        "workspace_id": workspace_id,
    }


def _with_trace_and_optional_fields(
    payload: dict[str, Any],
    *,
    error: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    payload["trace_id"] = current_trace_id()
    _set_if_truthy(payload, "error", error)
    _set_if_truthy(payload, "agent_run_id", agent_run_id)
    _set_if_truthy(payload, "conversation_id", conversation_id)
    return payload


def _set_if_truthy(payload: dict[str, Any], key: str, value: Any) -> None:
    if value:
        payload[key] = value


def _record_audit_event(
    *,
    action: str,
    entity_kind: str,
    entity_id: str | None,
    summary_fields: dict[str, Any],
    actor_user_id: str | None,
    payload: dict[str, Any],
    detected_values: list[dict[str, object]] | None = None,
) -> None:
    _persist_audit_event(
        action=action,
        entity_kind=entity_kind,
        entity_id=entity_id,
        summary=_summary(action, summary_fields),
        actor_user_id=actor_user_id,
        payload=payload,
        detected_values=detected_values,
    )


def _summary(action: str, fields: dict[str, Any]) -> str:
    return f"{action} " + " ".join(f"{field}={value}" for field, value in fields.items())


def _persist_audit_event(
    *,
    action: str,
    entity_kind: str,
    entity_id: str | None,
    summary: str,
    actor_user_id: str | None,
    payload: dict[str, Any],
    detected_values: list[dict[str, object]] | None = None,
) -> None:
    audit_db = get_session_factory()()
    try:
        audit_log = record_audit_log(
            audit_db,
            action=action,
            entity_kind=entity_kind,
            entity_id=entity_id,
            summary=summary,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        if detected_values:
            audit_db.flush()
            record_ai_security_detected_values(
                audit_db,
                audit_log=audit_log,
                payload=payload,
                detected_values=detected_values,
            )
        _maybe_record_ai_interaction(
            audit_db,
            action=action,
            entity_kind=entity_kind,
            entity_id=entity_id,
            payload=payload,
        )
        audit_db.commit()
    except Exception:
        audit_db.rollback()
        logger.warning("Failed to persist AI audit log", exc_info=True)
    finally:
        audit_db.close()


def _maybe_record_ai_interaction(
    db,
    *,
    action: str,
    entity_kind: str,
    entity_id: str | None,
    payload: dict[str, Any],
) -> None:
    if action == ACTION_LLM_CALL:
        record_ai_interaction(
            db,
            action=action,
            source=str(payload.get("source") or ""),
            workspace_id=payload.get("workspace_id"),
            actor_user_id=payload.get("actor_user_id"),
            principal_kind=payload.get("principal_kind"),
            principal_id=payload.get("principal_id"),
            task_kind=payload.get("task_kind"),
            pool=payload.get("chosen_pool"),
            model=payload.get("model"),
            status=str(payload.get("status") or "unknown"),
            latency_ms=_int_or_none(payload.get("latency_ms")),
            usage=_dict_or_none(payload.get("usage")),
            pii_hits=_list_of_str(payload.get("pii_hits")),
            metadata=_compact_dict(
                {
                    "app_id": payload.get("app_id"),
                    "policy": payload.get("policy"),
                    "decision_reason": payload.get("decision_reason"),
                    "forced_local": payload.get("forced_local"),
                    "max_tokens": payload.get("max_tokens"),
                    "context_strategy": payload.get("context_strategy"),
                    "estimated_input_tokens": payload.get("estimated_input_tokens"),
                    "sensitivity_labels": payload.get("sensitivity_labels"),
                    "blocked_entity_types": payload.get("blocked_entity_types"),
                    "content_origin": payload.get("content_origin"),
                    "source_kinds": payload.get("source_kinds"),
                    "finish_reason": payload.get("finish_reason"),
                }
            ),
            conversation_id=payload.get("conversation_id"),
            entity_kind=entity_kind,
            entity_id=entity_id,
            agent_run_id=payload.get("agent_run_id"),
            trace_id=payload.get("trace_id"),
            error=payload.get("error"),
        )
        return

    if action == ACTION_AI_EXTERNAL_CALL:
        metadata = _dict_or_none(payload.get("metadata")) or {}
        metadata = {
            **metadata,
            **_compact_dict(
                {
                    "policy_reason": payload.get("policy_reason"),
                    "removed_entity_types": payload.get("removed_entity_types"),
                    "blocked_entity_types": payload.get("blocked_entity_types"),
                    "sensitivity_labels": payload.get("sensitivity_labels"),
                    "content_origin": payload.get("content_origin"),
                    "source_kinds": payload.get("source_kinds"),
                }
            ),
        }
        record_ai_interaction(
            db,
            action=action,
            source=str(payload.get("source") or ""),
            workspace_id=payload.get("workspace_id"),
            actor_user_id=payload.get("actor_user_id"),
            principal_kind=payload.get("principal_kind"),
            principal_id=payload.get("principal_id"),
            task_kind=payload.get("task_kind"),
            capability=payload.get("capability"),
            provider=payload.get("provider"),
            status=str(payload.get("status") or "unknown"),
            latency_ms=_int_or_none(payload.get("latency_ms")),
            usage=_dict_or_none(payload.get("usage")),
            input_text_count=_int_or_none(payload.get("input_text_count")),
            input_char_count=_int_or_none(payload.get("input_char_count")),
            pii_hits=_list_of_str(payload.get("pii_hits")),
            metadata=metadata,
            conversation_id=payload.get("conversation_id"),
            entity_kind=entity_kind,
            entity_id=entity_id,
            agent_run_id=payload.get("agent_run_id"),
            trace_id=payload.get("trace_id"),
            error=payload.get("error"),
        )


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _list_of_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if _has_compact_value(item)}


def _has_compact_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True
