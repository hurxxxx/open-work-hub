"""add_planner_event_time_flags

Revision ID: c1d2e3f4a5c8
Revises: c0d1e2f3a4b7
Create Date: 2026-07-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c1d2e3f4a5c8"
down_revision: Union[str, Sequence[str], None] = "c0d1e2f3a4b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "planner_events",
        sa.Column(
            "start_has_time",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "planner_events",
        sa.Column(
            "end_has_time",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE planner_events
        SET
          start_has_time = CASE WHEN all_day THEN FALSE ELSE TRUE END,
          end_has_time = CASE WHEN all_day THEN FALSE ELSE TRUE END
        """
    )
    op.alter_column("planner_events", "start_has_time", server_default=None)
    op.alter_column("planner_events", "end_has_time", server_default=None)


def downgrade() -> None:
    op.drop_column("planner_events", "end_has_time")
    op.drop_column("planner_events", "start_has_time")
