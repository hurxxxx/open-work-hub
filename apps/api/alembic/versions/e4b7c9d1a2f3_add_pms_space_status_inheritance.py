"""add_pms_space_status_inheritance

Revision ID: e4b7c9d1a2f3
Revises: d6e7f8a9b0c1
Create Date: 2026-05-21 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "e4b7c9d1a2f3"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_SPACE_STATUSES = [
    ("todo", "To Do", "#9ca3af", "not_started", 0),
    ("in_progress", "In Progress", "#3b82f6", "active", 1),
    ("review", "Review", "#8b5cf6", "active", 2),
    ("done", "Done", "#22c55e", "done", 3),
    ("complete", "Complete", "#16a34a", "closed", 4),
]


def upgrade() -> None:
    op.create_table(
        "pms_space_statuses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("color", sa.String(length=24), nullable=False, server_default="#6b7280"),
        sa.Column("category", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "slug", name="uq_pms_space_status_slug"),
    )
    op.create_index(
        op.f("ix_pms_space_statuses_team_id"),
        "pms_space_statuses",
        ["team_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pms_space_statuses_slug"),
        "pms_space_statuses",
        ["slug"],
        unique=False,
    )
    op.add_column(
        "pms_task_lists",
        sa.Column("status_mode", sa.String(length=16), nullable=False, server_default="custom"),
    )
    op.alter_column("pms_task_lists", "status_mode", server_default=None)
    op.execute(
        """
        UPDATE pms_task_list_statuses
        SET category = CASE
            WHEN slug = 'todo' THEN 'not_started'
            WHEN category = 'canceled' THEN 'closed'
            ELSE category
        END
        """
    )

    bind = op.get_bind()
    team_ids = bind.execute(
        sa.text(
            """
            SELECT DISTINCT team_id
            FROM pms_task_lists
            WHERE team_id IS NOT NULL
            """
        )
    ).scalars()
    now = datetime.now(UTC).replace(tzinfo=None)
    for team_id in team_ids:
        for slug, name, color, category, sort_order in DEFAULT_SPACE_STATUSES:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO pms_space_statuses
                        (id, team_id, slug, name, color, category, sort_order, created_at)
                    VALUES
                        (:id, :team_id, :slug, :name, :color, :category, :sort_order, :created_at)
                    ON CONFLICT (team_id, slug) DO NOTHING
                    """
                ),
                {
                    "id": str(uuid4()),
                    "team_id": team_id,
                    "slug": slug,
                    "name": name,
                    "color": color,
                    "category": category,
                    "sort_order": sort_order,
                    "created_at": now,
                },
            )


    op.alter_column("pms_space_statuses", "color", server_default=None)
    op.alter_column("pms_space_statuses", "category", server_default=None)
    op.alter_column("pms_space_statuses", "sort_order", server_default=None)


def downgrade() -> None:
    op.execute(
        """
        UPDATE pms_task_list_statuses
        SET category = CASE
            WHEN category = 'not_started' THEN 'active'
            WHEN category = 'closed' THEN 'canceled'
            ELSE category
        END
        """
    )
    op.drop_column("pms_task_lists", "status_mode")
    op.drop_index(op.f("ix_pms_space_statuses_slug"), table_name="pms_space_statuses")
    op.drop_index(op.f("ix_pms_space_statuses_team_id"), table_name="pms_space_statuses")
    op.drop_table("pms_space_statuses")
