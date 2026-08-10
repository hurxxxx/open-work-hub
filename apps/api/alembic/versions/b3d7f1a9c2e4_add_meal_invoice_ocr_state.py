"""add_meal_invoice_ocr_state

Revision ID: b3d7f1a9c2e4
Revises: d1e2f3a4b5c7
Create Date: 2026-07-09 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3d7f1a9c2e4"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "meal_invoice_ocr_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("corrections_json", JSONB, nullable=False),
        sa.Column("catalog_json", JSONB, nullable=False),
        sa.Column("units_json", JSONB, nullable=False),
        sa.Column("vocab_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", name="uq_meal_invoice_ocr_state_workspace"),
    )
    op.create_index(
        "ix_meal_invoice_ocr_state_workspace_id",
        "meal_invoice_ocr_state",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_meal_invoice_ocr_state_workspace_id",
        table_name="meal_invoice_ocr_state",
    )
    op.drop_table("meal_invoice_ocr_state")
