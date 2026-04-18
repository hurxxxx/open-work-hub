"""Policy resolution for LLM pool routing.

A policy is `local_only` or `external`. Selection by `task_kind` is read from the
`llm_policies` table. Absent rows resolve to `local_only` (fail-safe).
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.domains.ai.models import LlmPolicy


LlmPolicyMode = Literal["local_only", "external"]

DEFAULT_POLICY: LlmPolicyMode = "local_only"


def resolve_policy(task_kind: str, db: Session) -> LlmPolicyMode:
    """Return the configured policy for the given `task_kind`.

    Missing rows are treated as `local_only` (fail-safe). Unexpected stored
    values are also clamped to `local_only` rather than surfacing as `external`.
    """
    if not task_kind:
        return DEFAULT_POLICY
    stmt = select(LlmPolicy.policy_mode).where(LlmPolicy.task_kind == task_kind)
    value = db.execute(stmt).scalar_one_or_none()
    if value == "external":
        return "external"
    return DEFAULT_POLICY
