"""add_file_manager_storage_cleanup_jobs

Revision ID: 5b8f2c1d9a04
Revises: 4a7c9e2d1b03
Create Date: 2026-05-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5b8f2c1d9a04"
down_revision: Union[str, Sequence[str], None] = "4a7c9e2d1b03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "file_manager_storage_cleanup_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','succeeded','failed')",
            name="ck_file_manager_storage_cleanup_jobs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_file_manager_storage_cleanup_jobs_status_retry",
        "file_manager_storage_cleanup_jobs",
        ["status", "next_retry_at", "created_at"],
    )
    op.create_index(
        op.f("ix_file_manager_storage_cleanup_jobs_storage_key"),
        "file_manager_storage_cleanup_jobs",
        ["storage_key"],
    )
    op.create_index(
        op.f("ix_file_manager_storage_cleanup_jobs_next_retry_at"),
        "file_manager_storage_cleanup_jobs",
        ["next_retry_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_file_manager_storage_cleanup_jobs_next_retry_at"),
        table_name="file_manager_storage_cleanup_jobs",
    )
    op.drop_index(
        op.f("ix_file_manager_storage_cleanup_jobs_storage_key"),
        table_name="file_manager_storage_cleanup_jobs",
    )
    op.drop_index(
        "ix_file_manager_storage_cleanup_jobs_status_retry",
        table_name="file_manager_storage_cleanup_jobs",
    )
    op.drop_table("file_manager_storage_cleanup_jobs")
