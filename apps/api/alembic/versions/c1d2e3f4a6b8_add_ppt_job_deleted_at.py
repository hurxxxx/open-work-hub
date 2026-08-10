"""add ppt job deleted at

Revision ID: c1d2e3f4a6b8
Revises: b3c4d5e6f8a9
Create Date: 2026-06-23 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a6b8"
down_revision: str | Sequence[str] | None = "b3c4d5e6f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    if not _column_exists("ppt_jobs", "deleted_at"):
        op.add_column("ppt_jobs", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    if not _index_exists("ppt_jobs", "ix_ppt_jobs_workspace_user_deleted_created"):
        op.create_index(
            "ix_ppt_jobs_workspace_user_deleted_created",
            "ppt_jobs",
            ["workspace_id", "user_id", "deleted_at", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if _index_exists("ppt_jobs", "ix_ppt_jobs_workspace_user_deleted_created"):
        op.drop_index(
            "ix_ppt_jobs_workspace_user_deleted_created",
            table_name="ppt_jobs",
        )
    if _column_exists("ppt_jobs", "deleted_at"):
        op.drop_column("ppt_jobs", "deleted_at")
