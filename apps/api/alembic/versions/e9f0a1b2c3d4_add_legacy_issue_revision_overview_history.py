"""add legacy issue revision overview history

Revision ID: e9f0a1b2c3d4
Revises: e8f9a0b1c2d3
Create Date: 2026-07-14 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e9f0a1b2c3d4"
down_revision: str | Sequence[str] | None = "e8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legacy_issue_revision_overview_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=120), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=True),
        sa.Column("revision_label", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("revised_on", sa.Date(), nullable=True),
        sa.Column("vehicle_models", sa.Text(), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("reviewer_name", sa.String(length=255), nullable=True),
        sa.Column("approver_name", sa.String(length=255), nullable=True),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_sheet", sa.String(length=255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "dataset_key",
            "source_filename",
            "source_sheet",
            "source_row",
            name="uq_legacy_issue_revision_overview_history_source_row",
        ),
    )
    op.create_index(
        "ix_legacy_issue_revision_overview_history_dataset_order",
        "legacy_issue_revision_overview_history",
        ["workspace_id", "dataset_key", "sort_order"],
        unique=False,
    )
    op.create_index(
        "ix_legacy_issue_revision_overview_history_dataset_key",
        "legacy_issue_revision_overview_history",
        ["dataset_key"],
        unique=False,
    )
    op.create_index(
        "ix_legacy_issue_revision_overview_history_workspace_id",
        "legacy_issue_revision_overview_history",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_legacy_issue_revision_overview_history_workspace_id",
        table_name="legacy_issue_revision_overview_history",
    )
    op.drop_index(
        "ix_legacy_issue_revision_overview_history_dataset_key",
        table_name="legacy_issue_revision_overview_history",
    )
    op.drop_index(
        "ix_legacy_issue_revision_overview_history_dataset_order",
        table_name="legacy_issue_revision_overview_history",
    )
    op.drop_table("legacy_issue_revision_overview_history")
