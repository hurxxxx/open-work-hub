"""add legacy issue assistant runs

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-06-17 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c6d7e8f9a0b1"
down_revision: str | Sequence[str] | None = "b5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "legacy_issue_assistant_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_id", sa.String(length=36), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_markdown", sa.Text(), nullable=False),
        sa.Column("analysis_plan", JSONB_COMPAT, nullable=False),
        sa.Column("evidence", JSONB_COMPAT, nullable=False),
        sa.Column("search_profile", JSONB_COMPAT, nullable=False),
        sa.Column("gateway_decisions", JSONB_COMPAT, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_legacy_issue_assistant_runs_workspace_id"),
        "legacy_issue_assistant_runs",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_assistant_runs_requested_by_id"),
        "legacy_issue_assistant_runs",
        ["requested_by_id"],
    )
    op.create_index(
        "ix_legacy_issue_assistant_runs_workspace_created",
        "legacy_issue_assistant_runs",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_legacy_issue_assistant_runs_requested_by_created",
        "legacy_issue_assistant_runs",
        ["requested_by_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("legacy_issue_assistant_runs")
