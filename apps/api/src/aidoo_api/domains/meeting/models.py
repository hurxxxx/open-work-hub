from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aidoo_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    organizer_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    notes_doc_id: Mapped[str | None] = mapped_column(
        ForeignKey("docs_native_docs.id"), nullable=True
    )
    notes_page_id: Mapped[str | None] = mapped_column(
        ForeignKey("docs_native_doc_pages.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    agenda: Mapped[str] = mapped_column(Text, default="", nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="scheduled", index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    organizer = relationship("User")
    attendees: Mapped[list["MeetingAttendee"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    task_links: Mapped[list["MeetingTaskLink"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    doc_links: Mapped[list["MeetingDocLink"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    file_attachments: Mapped[list["MeetingFileAttachment"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    recordings: Mapped[list["MeetingRecording"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    recording_staging: Mapped[list["MeetingRecordingStaging"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )


class MeetingAttendee(Base):
    __tablename__ = "meeting_attendees"
    __table_args__ = (
        UniqueConstraint("meeting_id", "user_id", name="uq_meeting_attendee"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(24), default="required", nullable=False)
    response: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="attendees")
    user = relationship("User")


class MeetingTaskLink(Base):
    __tablename__ = "meeting_task_links"
    __table_args__ = (
        UniqueConstraint("meeting_id", "issue_id", name="uq_meeting_task_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id"), index=True, nullable=False
    )
    issue_id: Mapped[str] = mapped_column(
        ForeignKey("pms_issues.id"), index=True, nullable=False
    )
    added_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="task_links")
    added_by = relationship("User")


class MeetingDocLink(Base):
    __tablename__ = "meeting_doc_links"
    __table_args__ = (
        UniqueConstraint("meeting_id", "doc_id", name="uq_meeting_doc_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id"), index=True, nullable=False
    )
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("docs_native_docs.id"), index=True, nullable=False
    )
    added_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="doc_links")
    added_by = relationship("User")


class MeetingFileAttachment(Base):
    """A binary file attached to a meeting (uploaded by organizer or any
    attendee). Stored in MinIO under ``meeting/<meeting_id>/<id>/<filename>``.

    Removal is restricted by ``ensure_link_remover`` — only the organizer or
    the original uploader can delete an attachment.
    """

    __tablename__ = "meeting_file_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(120), default="application/octet-stream", nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    added_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="file_attachments")
    added_by = relationship("User")


class MeetingRecording(Base):
    __tablename__ = "meeting_recordings"
    __table_args__ = (
        UniqueConstraint("meeting_id", "idempotency_key", name="uq_recording_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id"), index=True, nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="audio/webm", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    uploaded_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), default="manual_upload", nullable=False)
    transcription_status: Mapped[str] = mapped_column(
        String(24), default="pending", index=True, nullable=False
    )
    progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_doc_id: Mapped[str | None] = mapped_column(
        ForeignKey("docs_native_docs.id"), nullable=True
    )
    linked_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("pms_issues.id"), index=True, nullable=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    transcribe_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    transcribe_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="recordings")
    uploaded_by = relationship("User")


class MeetingRecordingStaging(Base):
    __tablename__ = "meeting_recording_staging"
    __table_args__ = (
        UniqueConstraint("meeting_id", "idempotency_key", name="uq_recording_staging_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id"), index=True, nullable=False
    )
    uploaded_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="recording", nullable=False)
    spool_path: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="audio/webm", nullable=False)
    bytes_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    highest_seq: Mapped[int] = mapped_column(Integer, default=-1, nullable=False)
    chunks_meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    duration_sec_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    linked_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("pms_issues.id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, index=True, nullable=False
    )
    last_chunk_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    promoted_recording_id: Mapped[str | None] = mapped_column(
        ForeignKey("meeting_recordings.id"), nullable=True
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="recording_staging")
    uploaded_by = relationship("User")
