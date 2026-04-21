"""add_meeting_insights

Revision ID: a9c4d7e1f2b3
Revises: f6e4b2a1c9d8
Create Date: 2026-04-21 22:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a9c4d7e1f2b3"
down_revision: Union[str, Sequence[str], None] = "f6e4b2a1c9d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meeting_insights",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("insight_type", sa.String(length=24), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_span", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("accepted_as_kind", sa.String(length=24), nullable=True),
        sa.Column("accepted_as_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "insight_type IN ('action','decision','followup_schedule')",
            name="ck_meeting_insights_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft','accepted','rejected','superseded')",
            name="ck_meeting_insights_status",
        ),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["meeting_recordings.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meeting_insights_meeting_id", "meeting_insights", ["meeting_id"])
    op.create_index("ix_meeting_insights_recording_id", "meeting_insights", ["recording_id"])
    op.create_index("ix_meeting_insights_workspace_id", "meeting_insights", ["workspace_id"])
    op.create_index(
        "ix_meeting_insights_meeting_type_status",
        "meeting_insights",
        ["meeting_id", "insight_type", "status"],
    )
    op.create_index(
        "ix_meeting_insights_workspace_status",
        "meeting_insights",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_meeting_insights_workspace_status", table_name="meeting_insights")
    op.drop_index("ix_meeting_insights_meeting_type_status", table_name="meeting_insights")
    op.drop_index("ix_meeting_insights_workspace_id", table_name="meeting_insights")
    op.drop_index("ix_meeting_insights_recording_id", table_name="meeting_insights")
    op.drop_index("ix_meeting_insights_meeting_id", table_name="meeting_insights")
    op.drop_table("meeting_insights")
