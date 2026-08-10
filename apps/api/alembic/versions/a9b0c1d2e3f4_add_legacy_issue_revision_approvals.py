"""add legacy issue revision approvals

Revision ID: a9b0c1d2e3f4
Revises: f7b8c9d0e1f2
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a9b0c1d2e3f4"
down_revision: str | Sequence[str] | None = "f7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


USER_COLUMNS = (
    "reviewer_id",
    "approver_id",
    "review_requested_by_id",
    "approval_requested_by_id",
    "reviewed_by_id",
    "approved_by_id",
)

DATETIME_COLUMNS = (
    "review_requested_at",
    "approval_requested_at",
    "reviewed_at",
    "approved_at",
)


def upgrade() -> None:
    for column in USER_COLUMNS:
        op.add_column(
            "legacy_issue_data_revisions",
            sa.Column(column, sa.String(length=36), nullable=True),
        )
        op.create_index(
            op.f(f"ix_legacy_issue_data_revisions_{column}"),
            "legacy_issue_data_revisions",
            [column],
        )
        op.create_foreign_key(
            op.f(f"fk_legacy_issue_data_revisions_{column}_users"),
            "legacy_issue_data_revisions",
            "users",
            [column],
            ["id"],
        )
    for column in DATETIME_COLUMNS:
        op.add_column(
            "legacy_issue_data_revisions",
            sa.Column(column, sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    for column in reversed(DATETIME_COLUMNS):
        op.drop_column("legacy_issue_data_revisions", column)
    for column in reversed(USER_COLUMNS):
        op.drop_constraint(
            op.f(f"fk_legacy_issue_data_revisions_{column}_users"),
            "legacy_issue_data_revisions",
            type_="foreignkey",
        )
        op.drop_index(
            op.f(f"ix_legacy_issue_data_revisions_{column}"),
            table_name="legacy_issue_data_revisions",
        )
        op.drop_column("legacy_issue_data_revisions", column)
