"""Raw-free AI interaction usage ledger.

This table is intentionally smaller than audit logs and agent runtime traces.
It exists to answer operational questions such as "who used how many tokens
for which feature" without storing prompt or response text.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import utcnow_naive
from ai_do_api.domains.auth.security import new_id


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class AiInteraction(Base):
    __tablename__ = "ai_interactions"
    __table_args__ = (
        Index(
            "ix_ai_interactions_workspace_created",
            "workspace_id",
            "created_at",
        ),
        Index(
            "ix_ai_interactions_actor_created",
            "actor_user_id",
            "created_at",
        ),
        Index(
            "ix_ai_interactions_task_created",
            "task_kind",
            "created_at",
        ),
        Index(
            "ix_ai_interactions_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    principal_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    principal_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_kind: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    capability: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pool: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    input_text_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pii_hits_json: Mapped[list[str] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entity_kind: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


def record_ai_interaction(
    db: Session,
    *,
    action: str,
    source: str,
    status: str,
    workspace_id: str | None = None,
    actor_user_id: str | None = None,
    principal_kind: str | None = None,
    principal_id: str | None = None,
    task_kind: str | None = None,
    capability: str | None = None,
    provider: str | None = None,
    pool: str | None = None,
    model: str | None = None,
    latency_ms: int | None = None,
    usage: dict[str, Any] | None = None,
    input_text_count: int | None = None,
    input_char_count: int | None = None,
    pii_hits: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    entity_kind: str | None = None,
    entity_id: str | None = None,
    agent_run_id: str | None = None,
    trace_id: str | None = None,
    error: str | None = None,
) -> AiInteraction:
    interaction = AiInteraction(
        id=new_id(),
        action=action,
        workspace_id=_clean_optional(workspace_id),
        actor_user_id=_clean_optional(actor_user_id),
        principal_kind=_clean_optional(principal_kind),
        principal_id=_clean_optional(principal_id),
        source=source,
        task_kind=_clean_optional(task_kind),
        capability=_clean_optional(capability),
        provider=_clean_optional(provider),
        pool=_clean_optional(pool),
        model=_clean_optional(model),
        status=status,
        latency_ms=latency_ms,
        usage_json=dict(usage) if usage else None,
        input_text_count=input_text_count,
        input_char_count=input_char_count,
        pii_hits_json=list(pii_hits or []) or None,
        metadata_json=dict(metadata or {}) or None,
        conversation_id=_clean_optional(conversation_id),
        entity_kind=_clean_optional(entity_kind),
        entity_id=_clean_optional(entity_id),
        agent_run_id=_clean_optional(agent_run_id),
        trace_id=_clean_optional(trace_id),
        error=error,
    )
    db.add(interaction)
    return interaction


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
