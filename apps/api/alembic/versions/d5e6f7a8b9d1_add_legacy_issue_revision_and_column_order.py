"""add legacy issue revision and column order fields

Revision ID: d5e6f7a8b9d1
Revises: d4e5f6a7b8c0
Create Date: 2026-07-02 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d5e6f7a8b9d1"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "legacy_issue_records",
        sa.Column("introduced_revision_no", sa.Integer(), nullable=True),
    )
    op.add_column(
        "legacy_issue_records",
        sa.Column("countermeasure_type", sa.Text(), nullable=True),
    )
    op.add_column(
        "legacy_issue_records",
        sa.Column("oem_disclosure_status", sa.Text(), nullable=True),
    )
    op.add_column(
        "legacy_issue_records",
        sa.Column("claim_region", sa.Text(), nullable=True),
    )

    op.create_table(
        "legacy_issue_column_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("view_key", sa.String(length=80), nullable=False),
        sa.Column("column_order", JSONB_COMPAT, nullable=True),
        sa.Column("updated_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "view_key",
            name="uq_legacy_issue_column_orders_workspace_view",
        ),
    )
    op.create_index(
        "ix_legacy_issue_column_orders_workspace_view",
        "legacy_issue_column_orders",
        ["workspace_id", "view_key"],
    )
    for column in ("workspace_id", "view_key", "updated_by_id"):
        op.create_index(
            op.f(f"ix_legacy_issue_column_orders_{column}"),
            "legacy_issue_column_orders",
            [column],
        )


def downgrade() -> None:
    for column in ("updated_by_id", "view_key", "workspace_id"):
        op.drop_index(
            op.f(f"ix_legacy_issue_column_orders_{column}"), table_name="legacy_issue_column_orders"
        )
    op.drop_index(
        "ix_legacy_issue_column_orders_workspace_view",
        table_name="legacy_issue_column_orders",
    )
    op.drop_table("legacy_issue_column_orders")

    op.drop_column("legacy_issue_records", "claim_region")
    op.drop_column("legacy_issue_records", "oem_disclosure_status")
    op.drop_column("legacy_issue_records", "countermeasure_type")
    op.drop_column("legacy_issue_records", "introduced_revision_no")
