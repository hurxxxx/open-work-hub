"""add_canonical_recording_tables

Revision ID: b6d8a1f4c2e0
Revises: a3c9d8e7f6b5
Create Date: 2026-05-02 16:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6d8a1f4c2e0"
down_revision: Union[str, Sequence[str], None] = "a3c9d8e7f6b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recordings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("audio_status", sa.String(length=24), nullable=False),
        sa.Column("transcript_status", sa.String(length=24), nullable=False),
        sa.Column("raw_transcript_doc_status", sa.String(length=24), nullable=False),
        sa.Column("minutes_doc_status", sa.String(length=24), nullable=False),
        sa.Column("meeting_insight_status", sa.String(length=24), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("raw_transcript_doc_id", sa.String(length=36), nullable=True),
        sa.Column("minutes_doc_id", sa.String(length=36), nullable=True),
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
        sa.Column("transcribe_started_at", sa.DateTime(), nullable=True),
        sa.Column("transcribe_completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("trashed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["minutes_doc_id"], ["docs_native_docs.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["raw_transcript_doc_id"], ["docs_native_docs.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        op.f("ix_recordings_audio_status"), "recordings", ["audio_status"], unique=False
    )
    op.create_index(
        op.f("ix_recordings_celery_task_id"), "recordings", ["celery_task_id"], unique=False
    )
    op.create_index(
        op.f("ix_recordings_meeting_insight_status"),
        "recordings",
        ["meeting_insight_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recordings_minutes_doc_status"), "recordings", ["minutes_doc_status"], unique=False
    )
    op.create_index(op.f("ix_recordings_owner_id"), "recordings", ["owner_id"], unique=False)
    op.create_index(
        op.f("ix_recordings_raw_transcript_doc_status"),
        "recordings",
        ["raw_transcript_doc_status"],
        unique=False,
    )
    op.create_index(op.f("ix_recordings_started_at"), "recordings", ["started_at"], unique=False)
    op.create_index(
        op.f("ix_recordings_transcript_status"), "recordings", ["transcript_status"], unique=False
    )
    op.create_index(op.f("ix_recordings_trashed_at"), "recordings", ["trashed_at"], unique=False)
    op.create_index(
        op.f("ix_recordings_workspace_id"), "recordings", ["workspace_id"], unique=False
    )
    op.create_index(
        "ix_recordings_workspace_audio_status",
        "recordings",
        ["workspace_id", "audio_status"],
        unique=False,
    )
    op.create_index(
        "ix_recordings_workspace_owner_started",
        "recordings",
        ["workspace_id", "owner_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_recordings_workspace_transcript_status",
        "recordings",
        ["workspace_id", "transcript_status"],
        unique=False,
    )

    op.create_table(
        "recording_staging",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
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
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_chunk_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("promoted_recording_id", sa.String(length=36), nullable=True),
        sa.Column("initial_container_app", sa.String(length=64), nullable=True),
        sa.Column("initial_container_type", sa.String(length=64), nullable=True),
        sa.Column("initial_container_id", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["promoted_recording_id"], ["recordings.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "uploaded_by_id",
            "idempotency_key",
            name="uq_recording_staging_workspace_uploader_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_recording_staging_started_at"), "recording_staging", ["started_at"], unique=False
    )
    op.create_index(
        op.f("ix_recording_staging_status"), "recording_staging", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_recording_staging_uploaded_by_id"),
        "recording_staging",
        ["uploaded_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recording_staging_workspace_id"),
        "recording_staging",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_recording_staging_initial_container",
        "recording_staging",
        [
            "workspace_id",
            "initial_container_app",
            "initial_container_type",
            "initial_container_id",
            "completed_at",
        ],
        unique=False,
    )
    op.create_index(
        "ix_recording_staging_workspace_started",
        "recording_staging",
        ["workspace_id", "started_at"],
        unique=False,
    )

    op.create_table(
        "recording_containers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("container_app", sa.String(length=64), nullable=False),
        sa.Column("container_type", sa.String(length=64), nullable=False),
        sa.Column("container_id", sa.String(length=128), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("added_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["added_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["recording_id"], ["recordings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recording_id",
            "container_app",
            "container_type",
            "container_id",
            name="uq_recording_containers_recording_container",
        ),
    )
    op.create_index(
        op.f("ix_recording_containers_added_by_id"),
        "recording_containers",
        ["added_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recording_containers_container_app"),
        "recording_containers",
        ["container_app"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recording_containers_container_id"),
        "recording_containers",
        ["container_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recording_containers_container_type"),
        "recording_containers",
        ["container_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recording_containers_is_primary"),
        "recording_containers",
        ["is_primary"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recording_containers_recording_id"),
        "recording_containers",
        ["recording_id"],
        unique=False,
    )
    op.create_index(
        "ix_recording_containers_lookup",
        "recording_containers",
        ["container_app", "container_type", "container_id"],
        unique=False,
    )
    op.create_index(
        "uq_recording_containers_primary",
        "recording_containers",
        ["recording_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_recording_containers_primary", table_name="recording_containers")
    op.drop_index("ix_recording_containers_lookup", table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_recording_id"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_is_primary"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_container_type"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_container_id"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_container_app"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_added_by_id"), table_name="recording_containers")
    op.drop_table("recording_containers")

    op.drop_index("ix_recording_staging_workspace_started", table_name="recording_staging")
    op.drop_index("ix_recording_staging_initial_container", table_name="recording_staging")
    op.drop_index(op.f("ix_recording_staging_workspace_id"), table_name="recording_staging")
    op.drop_index(op.f("ix_recording_staging_uploaded_by_id"), table_name="recording_staging")
    op.drop_index(op.f("ix_recording_staging_status"), table_name="recording_staging")
    op.drop_index(op.f("ix_recording_staging_started_at"), table_name="recording_staging")
    op.drop_table("recording_staging")

    op.drop_index("ix_recordings_workspace_transcript_status", table_name="recordings")
    op.drop_index("ix_recordings_workspace_owner_started", table_name="recordings")
    op.drop_index("ix_recordings_workspace_audio_status", table_name="recordings")
    op.drop_index(op.f("ix_recordings_workspace_id"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_trashed_at"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_transcript_status"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_started_at"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_raw_transcript_doc_status"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_owner_id"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_minutes_doc_status"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_meeting_insight_status"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_celery_task_id"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_audio_status"), table_name="recordings")
    op.drop_table("recordings")
