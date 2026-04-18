"""Audit helpers for LLM requests.

Intentionally minimal: one function, one payload shape. The raw prompt/content
is **never** stored — only identity + decision + counters + error summary.
"""

from __future__ import annotations

import logging
from typing import Any

from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import record_audit_log


ACTION_LLM_CALL = "llm_call"
ENTITY_KIND_LLM_TASK = "llm_task"
logger = logging.getLogger(__name__)


def log_llm_call(
    *,
    source: str,
    actor_user_id: str | None,
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
    error: str | None = None,
    entity_id: str | None = None,
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
    }
    if error:
        payload["error"] = error

    summary = (
        f"llm_call source={source} pool={chosen_pool} task_kind={task_kind} "
        f"status={status}"
    )

    audit_db = get_session_factory()()
    try:
        record_audit_log(
            audit_db,
            action=ACTION_LLM_CALL,
            entity_kind=ENTITY_KIND_LLM_TASK,
            entity_id=entity_id,
            summary=summary,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        audit_db.commit()
    except Exception:
        audit_db.rollback()
        logger.warning("Failed to persist llm_call audit log", exc_info=True)
    finally:
        audit_db.close()
