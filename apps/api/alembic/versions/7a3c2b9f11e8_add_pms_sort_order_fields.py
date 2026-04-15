"""add_pms_sort_order_fields

Revision ID: 7a3c2b9f11e8
Revises: 3e4983704c82
Create Date: 2026-04-15 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a3c2b9f11e8"
down_revision: Union[str, Sequence[str], None] = "3e4983704c82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pms_task_lists",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pms_space_docs",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )

    # Backfill: rank by updated_at DESC within each (team_id, folder_id) bucket for lists,
    # and within each team_id bucket for space docs. The most-recently-updated item gets
    # sort_order=0 so the new tree order matches the old updated_at DESC listing.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                (ROW_NUMBER() OVER (
                    PARTITION BY team_id, COALESCE(folder_id, '')
                    ORDER BY updated_at DESC, name ASC
                ) - 1) * 1000 AS new_sort_order
            FROM pms_task_lists
        )
        UPDATE pms_task_lists
        SET sort_order = ranked.new_sort_order
        FROM ranked
        WHERE pms_task_lists.id = ranked.id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                (ROW_NUMBER() OVER (
                    PARTITION BY team_id
                    ORDER BY updated_at DESC, title ASC
                ) - 1) * 1000 AS new_sort_order
            FROM pms_space_docs
            WHERE trashed_at IS NULL
        )
        UPDATE pms_space_docs
        SET sort_order = ranked.new_sort_order
        FROM ranked
        WHERE pms_space_docs.id = ranked.id
        """
    )

    op.alter_column("pms_task_lists", "sort_order", server_default=None)
    op.alter_column("pms_space_docs", "sort_order", server_default=None)


def downgrade() -> None:
    op.drop_column("pms_space_docs", "sort_order")
    op.drop_column("pms_task_lists", "sort_order")
