"""add video chat sessions

Revision ID: c8a9d0e1f2b3
Revises: b7d3f1a9c5e2
Create Date: 2026-06-07 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8a9d0e1f2b3"
down_revision: Union[str, Sequence[str], None] = "b7d3f1a9c5e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_chat_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=True),
        sa.Column("room_name", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("started_by_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("recording_status", sa.String(length=24), nullable=False),
        sa.Column("recording_egress_id", sa.String(length=120), nullable=True),
        sa.Column("recording_id", sa.String(length=36), nullable=True),
        sa.Column("captions_status", sa.String(length=24), nullable=False),
        sa.Column("captions_started_at", sa.DateTime(), nullable=True),
        sa.Column("captions_ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open','ended')",
            name="ck_video_chat_sessions_status",
        ),
        sa.CheckConstraint(
            "recording_status IN ('idle','starting','recording','stopping','failed','saved')",
            name="ck_video_chat_sessions_recording_status",
        ),
        sa.CheckConstraint(
            "captions_status IN ('off','starting','on','stopping','failed')",
            name="ck_video_chat_sessions_captions_status",
        ),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.ForeignKeyConstraint(["recording_id"], ["recordings.id"]),
        sa.ForeignKeyConstraint(["started_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_video_chat_sessions_workspace_id",
        "video_chat_sessions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_video_chat_sessions_meeting_id",
        "video_chat_sessions",
        ["meeting_id"],
    )
    op.create_index(
        "ix_video_chat_sessions_room_name",
        "video_chat_sessions",
        ["room_name"],
        unique=True,
    )
    op.create_index(
        "ix_video_chat_sessions_status",
        "video_chat_sessions",
        ["status"],
    )
    op.create_index(
        "ix_video_chat_sessions_started_by_id",
        "video_chat_sessions",
        ["started_by_id"],
    )
    op.create_index(
        "ix_video_chat_sessions_started_at",
        "video_chat_sessions",
        ["started_at"],
    )
    op.create_index(
        "ix_video_chat_sessions_recording_status",
        "video_chat_sessions",
        ["recording_status"],
    )
    op.create_index(
        "ix_video_chat_sessions_recording_egress_id",
        "video_chat_sessions",
        ["recording_egress_id"],
    )
    op.create_index(
        "ix_video_chat_sessions_recording_id",
        "video_chat_sessions",
        ["recording_id"],
    )
    op.create_index(
        "ix_video_chat_sessions_workspace_status_started",
        "video_chat_sessions",
        ["workspace_id", "status", "started_at"],
    )
    op.create_index(
        "ix_video_chat_sessions_meeting_status",
        "video_chat_sessions",
        ["meeting_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_video_chat_sessions_meeting_status",
        table_name="video_chat_sessions",
    )
    op.drop_index(
        "ix_video_chat_sessions_workspace_status_started",
        table_name="video_chat_sessions",
    )
    op.drop_index("ix_video_chat_sessions_recording_id", table_name="video_chat_sessions")
    op.drop_index(
        "ix_video_chat_sessions_recording_egress_id",
        table_name="video_chat_sessions",
    )
    op.drop_index(
        "ix_video_chat_sessions_recording_status",
        table_name="video_chat_sessions",
    )
    op.drop_index("ix_video_chat_sessions_started_at", table_name="video_chat_sessions")
    op.drop_index("ix_video_chat_sessions_started_by_id", table_name="video_chat_sessions")
    op.drop_index("ix_video_chat_sessions_status", table_name="video_chat_sessions")
    op.drop_index("ix_video_chat_sessions_room_name", table_name="video_chat_sessions")
    op.drop_index("ix_video_chat_sessions_meeting_id", table_name="video_chat_sessions")
    op.drop_index("ix_video_chat_sessions_workspace_id", table_name="video_chat_sessions")
    op.drop_table("video_chat_sessions")
