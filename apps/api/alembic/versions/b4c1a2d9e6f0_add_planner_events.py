"""add_planner_events

Revision ID: b4c1a2d9e6f0
Revises: 9c1d5e7b3a82
Create Date: 2026-04-16 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4c1a2d9e6f0"
down_revision: Union[str, Sequence[str], None] = "9c1d5e7b3a82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planner_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=240), nullable=False),
        sa.Column("visibility", sa.String(length=24), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_planner_events_owner_id"),
        "planner_events",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_planner_events_visibility"),
        "planner_events",
        ["visibility"],
        unique=False,
    )
    op.create_index(
        op.f("ix_planner_events_workspace_id"),
        "planner_events",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_planner_events_workspace_owner_start",
        "planner_events",
        ["workspace_id", "owner_id", "start_at"],
        unique=False,
    )
    op.create_index(
        "ix_planner_events_workspace_owner_end",
        "planner_events",
        ["workspace_id", "owner_id", "end_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_planner_events_workspace_owner_end", table_name="planner_events")
    op.drop_index("ix_planner_events_workspace_owner_start", table_name="planner_events")
    op.drop_index(op.f("ix_planner_events_workspace_id"), table_name="planner_events")
    op.drop_index(op.f("ix_planner_events_visibility"), table_name="planner_events")
    op.drop_index(op.f("ix_planner_events_owner_id"), table_name="planner_events")
    op.drop_table("planner_events")
