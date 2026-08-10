"""add_spec_compare_spec_items

Revision ID: 5d7a9c2e4f10
Revises: 3a9c7e5d1b20
Create Date: 2026-05-14 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "5d7a9c2e4f10"
down_revision: str | Sequence[str] | None = "3a9c7e5d1b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spec_compare_spec_items",
        sa.Column("id", sa.String(length=140), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("document_role", sa.String(length=16), nullable=False),
        sa.Column("item_id", sa.String(length=100), nullable=False),
        sa.Column("normalized_key", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=300), nullable=False),
        sa.Column("item_name", sa.String(length=300), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("condition", sa.String(length=500), nullable=False),
        sa.Column("evidence_id", sa.String(length=160), nullable=False),
        sa.Column("locator_label", sa.String(length=160), nullable=False),
        sa.Column("section_path", sa.String(length=300), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extraction_method", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "document_role IN ('base','target')",
            name="ck_spec_compare_spec_items_document_role",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["spec_compare_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "document_role",
            "item_id",
            name="uq_spec_compare_spec_items_job_role_item",
        ),
    )
    op.create_index(
        "ix_spec_compare_spec_items_job_role",
        "spec_compare_spec_items",
        ["job_id", "document_role"],
    )
    op.create_index(
        "ix_spec_compare_spec_items_normalized_key",
        "spec_compare_spec_items",
        ["normalized_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_spec_compare_spec_items_normalized_key",
        table_name="spec_compare_spec_items",
    )
    op.drop_index("ix_spec_compare_spec_items_job_role", table_name="spec_compare_spec_items")
    op.drop_table("spec_compare_spec_items")
