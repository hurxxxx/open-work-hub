"""add legacy issue attachment ai summary

Revision ID: f3b7c2d9a6e1
Revises: e0f2a3b4c5d6
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f3b7c2d9a6e1"
down_revision: str | Sequence[str] | None = "e0f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("legacy_issue_attachments", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.add_column(
        "legacy_issue_attachments",
        sa.Column(
            "ai_summary_status",
            sa.String(length=32),
            server_default=sa.text("'not_summarized'"),
            nullable=False,
        ),
    )
    op.add_column(
        "legacy_issue_attachments",
        sa.Column("ai_summary_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "legacy_issue_attachments",
        sa.Column("ai_summary_model", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "legacy_issue_attachments",
        sa.Column(
            "ai_summary_version",
            sa.String(length=80),
            server_default=sa.text("'legacy_issue_attachment_summary.v1'"),
            nullable=False,
        ),
    )
    op.add_column(
        "legacy_issue_attachments",
        sa.Column("ai_summarized_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_legacy_issue_attachments_summary_status",
        "legacy_issue_attachments",
        ["workspace_id", "ai_summary_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_legacy_issue_attachments_summary_status",
        table_name="legacy_issue_attachments",
    )
    op.drop_column("legacy_issue_attachments", "ai_summarized_at")
    op.drop_column("legacy_issue_attachments", "ai_summary_version")
    op.drop_column("legacy_issue_attachments", "ai_summary_model")
    op.drop_column("legacy_issue_attachments", "ai_summary_error")
    op.drop_column("legacy_issue_attachments", "ai_summary_status")
    op.drop_column("legacy_issue_attachments", "ai_summary")
