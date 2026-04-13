"""add_meeting_recording_pipeline

Revision ID: c3e67d4f1a2b
Revises: 8b1b7fa4b72b
Create Date: 2026-04-13 23:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3e67d4f1a2b"
down_revision: Union[str, Sequence[str], None] = "8b1b7fa4b72b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meeting_recordings",
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "meeting_recordings",
        sa.Column("mime_type", sa.String(length=120), nullable=False, server_default="audio/webm"),
    )
    op.add_column(
        "meeting_recordings",
        sa.Column("idempotency_key", sa.String(length=80), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "meeting_recordings",
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "meeting_recordings",
        sa.Column("linked_task_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "meeting_recordings",
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "meeting_recordings",
        sa.Column("transcribe_started_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "meeting_recordings",
        sa.Column("transcribe_completed_at", sa.DateTime(), nullable=True),
    )
    op.alter_column("meeting_recordings", "failure_reason", type_=sa.Text(), existing_nullable=True)
    op.create_foreign_key(
        "fk_meeting_recordings_linked_task_id",
        "meeting_recordings",
        "pms_issues",
        ["linked_task_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_recording_idempotency",
        "meeting_recordings",
        ["meeting_id", "idempotency_key"],
    )
    op.create_index(
        op.f("ix_meeting_recordings_linked_task_id"),
        "meeting_recordings",
        ["linked_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meeting_recordings_celery_task_id"),
        "meeting_recordings",
        ["celery_task_id"],
        unique=False,
    )

    op.create_table(
        "meeting_recording_staging",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("spool_path", sa.String(length=512), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("bytes_received", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("highest_seq", sa.Integer(), nullable=False),
        sa.Column("chunks_meta", sa.JSON(), nullable=False),
        sa.Column("duration_sec_estimate", sa.Integer(), nullable=True),
        sa.Column("linked_task_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_chunk_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("promoted_recording_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["linked_task_id"], ["pms_issues.id"]),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.ForeignKeyConstraint(["promoted_recording_id"], ["meeting_recordings.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "idempotency_key", name="uq_recording_staging_idempotency"),
    )
    op.create_index(
        op.f("ix_meeting_recording_staging_meeting_id"),
        "meeting_recording_staging",
        ["meeting_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meeting_recording_staging_started_at"),
        "meeting_recording_staging",
        ["started_at"],
        unique=False,
    )

    op.alter_column("meeting_recordings", "file_size", server_default=None)
    op.alter_column("meeting_recordings", "mime_type", server_default=None)
    op.alter_column("meeting_recordings", "idempotency_key", server_default=None)
    op.alter_column("meeting_recordings", "progress_pct", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_meeting_recording_staging_started_at"), table_name="meeting_recording_staging")
    op.drop_index(op.f("ix_meeting_recording_staging_meeting_id"), table_name="meeting_recording_staging")
    op.drop_table("meeting_recording_staging")

    op.drop_index(op.f("ix_meeting_recordings_celery_task_id"), table_name="meeting_recordings")
    op.drop_index(op.f("ix_meeting_recordings_linked_task_id"), table_name="meeting_recordings")
    op.drop_constraint("uq_recording_idempotency", "meeting_recordings", type_="unique")
    op.drop_constraint("fk_meeting_recordings_linked_task_id", "meeting_recordings", type_="foreignkey")
    op.alter_column("meeting_recordings", "failure_reason", type_=sa.String(length=255), existing_nullable=True)
    op.drop_column("meeting_recordings", "transcribe_completed_at")
    op.drop_column("meeting_recordings", "transcribe_started_at")
    op.drop_column("meeting_recordings", "celery_task_id")
    op.drop_column("meeting_recordings", "linked_task_id")
    op.drop_column("meeting_recordings", "progress_pct")
    op.drop_column("meeting_recordings", "idempotency_key")
    op.drop_column("meeting_recordings", "mime_type")
    op.drop_column("meeting_recordings", "file_size")
