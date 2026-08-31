from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_work_hub_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AgentTerminalSession(Base):
    __tablename__ = "agent_terminal_sessions"
    __table_args__ = (
        CheckConstraint("tool IN ('codex')", name="ck_agent_terminal_sessions_tool"),
        CheckConstraint(
            "status IN ('starting', 'running', 'exited', 'terminated', 'failed')",
            name="ck_agent_terminal_sessions_status",
        ),
        Index(
            "ix_agent_terminal_sessions_owner_created",
            "owner_id",
            "created_at",
        ),
        Index(
            "ix_agent_terminal_sessions_status_updated",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tool: Mapped[str] = mapped_column(
        String(24), default="codex", server_default=text("'codex'"), nullable=False
    )
    root_key: Mapped[str] = mapped_column(String(64), nullable=False)
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="starting", server_default=text("'starting'"), nullable=False
    )
    runtime_instance_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    owner = relationship("User")
