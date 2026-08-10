from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base
from open_alm_api.domains.docs.models import NativeDoc


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = (
        Index("ix_recordings_workspace_owner_started", "workspace_id", "owner_id", "started_at"),
        Index("ix_recordings_workspace_audio_status", "workspace_id", "audio_status"),
        Index("ix_recordings_workspace_transcript_status", "workspace_id", "transcript_status"),
        Index("ix_recordings_minutes_doc_id", "minutes_doc_id"),
        Index("ix_recordings_raw_transcript_doc_id", "raw_transcript_doc_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, index=True, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="quick_record", nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), unique=True, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="audio/webm", nullable=False)
    audio_status: Mapped[str] = mapped_column(
        String(24), default="saved", index=True, nullable=False
    )
    transcript_status: Mapped[str] = mapped_column(
        String(24), default="pending", index=True, nullable=False
    )
    raw_transcript_doc_status: Mapped[str] = mapped_column(
        String(24), default="pending", index=True, nullable=False
    )
    minutes_doc_status: Mapped[str] = mapped_column(
        String(24), default="pending", index=True, nullable=False
    )
    meeting_insight_status: Mapped[str] = mapped_column(
        String(24), default="none", index=True, nullable=False
    )
    progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_transcript_doc_id: Mapped[str | None] = mapped_column(
        ForeignKey("docs_native_docs.id"), nullable=True
    )
    minutes_doc_id: Mapped[str | None] = mapped_column(
        ForeignKey("docs_native_docs.id"), nullable=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    transcribe_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    transcribe_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    workspace = relationship("Workspace")
    owner = relationship("User", foreign_keys=[owner_id])
    raw_transcript_doc = relationship(NativeDoc, foreign_keys=[raw_transcript_doc_id])
    minutes_doc = relationship(NativeDoc, foreign_keys=[minutes_doc_id])
    targets: Mapped[list["RecordingTarget"]] = relationship(
        back_populates="recording",
        cascade="all, delete-orphan",
    )


class RecordingStaging(Base):
    __tablename__ = "recording_staging"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "uploaded_by_id",
            "idempotency_key",
            name="uq_recording_staging_workspace_uploader_idempotency",
        ),
        Index(
            "ix_recording_staging_initial_target",
            "workspace_id",
            "initial_target_app",
            "initial_target_type",
            "initial_target_id",
            "completed_at",
        ),
        Index("ix_recording_staging_workspace_started", "workspace_id", "started_at"),
        Index("ix_recording_staging_promoted_recording", "promoted_recording_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="recording", index=True, nullable=False)
    spool_path: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="audio/webm", nullable=False)
    bytes_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    highest_seq: Mapped[int] = mapped_column(Integer, default=-1, nullable=False)
    chunks_meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    duration_sec_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, index=True, nullable=False
    )
    last_chunk_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    promoted_recording_id: Mapped[str | None] = mapped_column(
        ForeignKey("recordings.id"), nullable=True
    )
    initial_target_app: Mapped[str | None] = mapped_column(String(64), nullable=True)
    initial_target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    initial_target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    workspace = relationship("Workspace")
    uploaded_by = relationship("User")
    promoted_recording = relationship("Recording")


class RecordingTarget(Base):
    __tablename__ = "recording_targets"
    __table_args__ = (
        Index(
            "ix_recording_targets_lookup",
            "target_app",
            "target_type",
            "target_id",
        ),
        Index(
            "uq_recording_targets_primary",
            "recording_id",
            unique=True,
            postgresql_where=text("is_primary IS TRUE"),
        ),
        UniqueConstraint(
            "recording_id",
            "target_app",
            "target_type",
            "target_id",
            name="uq_recording_targets_recording_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recording_id: Mapped[str] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_app: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    recording: Mapped[Recording] = relationship(back_populates="targets")
    added_by = relationship("User")
