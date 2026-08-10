from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ReleaseNote(Base):
    __tablename__ = "release_notes"
    __table_args__ = (
        UniqueConstraint("release_key", name="uq_release_notes_release_key"),
        Index("ix_release_notes_status_published", "status", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    release_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    reads: Mapped[list["ReleaseNoteRead"]] = relationship(
        back_populates="release_note",
        cascade="all, delete-orphan",
    )


class ReleaseNoteRead(Base):
    __tablename__ = "release_note_reads"
    __table_args__ = (Index("ix_release_note_reads_user_dismissed", "user_id", "dismissed_at"),)

    release_note_id: Mapped[str] = mapped_column(
        ForeignKey("release_notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    release_note = relationship("ReleaseNote", back_populates="reads")
    user = relationship("User")
