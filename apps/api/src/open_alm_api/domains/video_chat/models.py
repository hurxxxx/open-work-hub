from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class VideoChatSession(Base):
    __tablename__ = "video_chat_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','ended')",
            name="ck_video_chat_sessions_status",
        ),
        CheckConstraint(
            "recording_status IN ('idle','starting','recording','stopping','failed','saved')",
            name="ck_video_chat_sessions_recording_status",
        ),
        CheckConstraint(
            "captions_status IN ('off','starting','on','stopping','failed')",
            name="ck_video_chat_sessions_captions_status",
        ),
        Index(
            "ix_video_chat_sessions_workspace_status_started",
            "workspace_id",
            "status",
            "started_at",
        ),
        Index("ix_video_chat_sessions_meeting_status", "meeting_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id"), index=True, nullable=True
    )
    room_name: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(24), default="livekit", nullable=False)
    started_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, index=True, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recording_status: Mapped[str] = mapped_column(
        String(24), default="idle", index=True, nullable=False
    )
    recording_egress_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    recording_id: Mapped[str | None] = mapped_column(
        ForeignKey("recordings.id"), index=True, nullable=True
    )
    captions_status: Mapped[str] = mapped_column(String(24), default="off", nullable=False)
    captions_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    captions_ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    workspace = relationship("Workspace")
    meeting = relationship("Meeting")
    started_by = relationship("User")
    recording = relationship("Recording")
