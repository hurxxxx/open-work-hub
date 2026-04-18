from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from aidoo_api.core.db import Base
from aidoo_api.domains.meeting.models import utcnow_naive


class LlmPolicy(Base):
    """Maps a `task_kind` to a pool-selection policy (local_only | external).

    One row per task_kind. Rows may be created/edited by admins; missing rows
    resolve to `local_only` (fail-safe) in `policy_service.resolve_policy`.
    """

    __tablename__ = "llm_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_kind: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    policy_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )
