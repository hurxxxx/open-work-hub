"""add_legacy_issue_record_page_index

Revision ID: c9f0a1b2d3e4
Revises: b8d9e0f1a2c3
Create Date: 2026-06-01 18:45:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "c9f0a1b2d3e4"
down_revision: str | Sequence[str] | None = "b8d9e0f1a2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_legacy_issue_records_workspace_dataset_order",
        "legacy_issue_records",
        ["workspace_id", "dataset_id", "source_filename", "sheet_name", "row_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_legacy_issue_records_workspace_dataset_order",
        table_name="legacy_issue_records",
    )
