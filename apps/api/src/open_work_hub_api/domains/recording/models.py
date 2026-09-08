from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_work_hub_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = (Index("ix_recordings_owner_started", "owner_id", "started_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
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
    summary_status: Mapped[str] = mapped_column(
        String(24), default="pending", index=True, nullable=False
    )
    meeting_insight_status: Mapped[str] = mapped_column(
        String(24), default="none", index=True, nullable=False
    )
    progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    transcribe_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    transcribe_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    owner = relationship("User", foreign_keys=[owner_id])
    result: Mapped["RecordingResult | None"] = relationship(
        back_populates="recording",
        cascade="all, delete-orphan",
        uselist=False,
    )
    publications: Mapped[list["RecordingPublication"]] = relationship(
        back_populates="recording",
        cascade="all, delete-orphan",
        order_by="RecordingPublication.created_at",
    )
    targets: Mapped[list["RecordingTarget"]] = relationship(
        back_populates="recording",
        cascade="all, delete-orphan",
    )


class RecordingResult(Base):
    __tablename__ = "recording_results"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_recording_results_version"),)

    recording_id: Mapped[str] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    verifier_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    recording: Mapped[Recording] = relationship(back_populates="result")


class RecordingPublication(Base):
    __tablename__ = "recording_publications"
    __table_args__ = (
        UniqueConstraint(
            "recording_id",
            "target_app",
            "result_version",
            name="uq_recording_publication_result_version",
        ),
        Index("ix_recording_publications_target", "target_app", "target_resource_id"),
        CheckConstraint(
            "result_version >= 1",
            name="ck_recording_publications_result_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recording_id: Mapped[str] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    target_app: Mapped[str] = mapped_column(String(64), nullable=False)
    target_resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    result_version: Mapped[int] = mapped_column(Integer, nullable=False)
    published_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    recording: Mapped[Recording] = relationship(back_populates="publications")
    published_by = relationship("User")


class RecordingStaging(Base):
    __tablename__ = "recording_staging"
    __table_args__ = (
        UniqueConstraint(
            "uploaded_by_id",
            "idempotency_key",
            name="uq_recording_staging_uploader_idempotency",
        ),
        Index(
            "ix_recording_staging_initial_target",
            "initial_target_app",
            "initial_target_type",
            "initial_target_id",
            "completed_at",
        ),
        Index("ix_recording_staging_started", "started_at"),
        Index("ix_recording_staging_promoted_recording", "promoted_recording_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
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
