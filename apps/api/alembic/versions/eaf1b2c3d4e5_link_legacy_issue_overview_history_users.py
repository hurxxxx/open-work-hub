"""link legacy issue overview history users

Revision ID: eaf1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-07-14 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "eaf1b2c3d4e5"
down_revision: str | Sequence[str] | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for role in ("author", "reviewer", "approver"):
        column_name = f"{role}_user_id"
        index_name = f"ix_legacy_issue_revision_overview_history_{column_name}"
        op.add_column(
            "legacy_issue_revision_overview_history",
            sa.Column(column_name, sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            f"fk_legacy_issue_revision_overview_history_{role}_user",
            "legacy_issue_revision_overview_history",
            "users",
            [column_name],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            index_name,
            "legacy_issue_revision_overview_history",
            [column_name],
            unique=False,
        )


def downgrade() -> None:
    for role in reversed(("author", "reviewer", "approver")):
        column_name = f"{role}_user_id"
        op.drop_index(
            f"ix_legacy_issue_revision_overview_history_{column_name}",
            table_name="legacy_issue_revision_overview_history",
        )
        op.drop_constraint(
            f"fk_legacy_issue_revision_overview_history_{role}_user",
            "legacy_issue_revision_overview_history",
            type_="foreignkey",
        )
        op.drop_column("legacy_issue_revision_overview_history", column_name)
