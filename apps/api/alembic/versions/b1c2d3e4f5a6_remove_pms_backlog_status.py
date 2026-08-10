"""remove_pms_backlog_status

Revision ID: b1c2d3e4f5a6
Revises: ab12cd34ef56
Create Date: 2026-05-21 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "ab12cd34ef56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE pms_issues SET status = 'todo' WHERE status = 'backlog'")
    op.execute(
        "UPDATE pms_task_templates SET default_status = 'todo' "
        "WHERE default_status = 'backlog'"
    )
    op.execute(
        "UPDATE pms_task_list_statuses SET category = 'active' "
        "WHERE category = 'backlog'"
    )
    op.execute("DELETE FROM pms_task_list_statuses WHERE slug = 'backlog'")
    op.execute(
        """
        UPDATE pms_task_list_statuses
        SET sort_order = CASE slug
            WHEN 'todo' THEN 0
            WHEN 'in_progress' THEN 1
            WHEN 'done' THEN 2
            WHEN 'canceled' THEN 3
            ELSE sort_order
        END
        WHERE slug IN ('todo', 'in_progress', 'done', 'canceled')
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(
        bind.execute(
            sa.text("SELECT list_id FROM pms_task_list_statuses WHERE slug = 'backlog'")
        ).scalars()
    )
    list_ids = bind.execute(sa.text("SELECT id FROM pms_task_lists")).scalars()
    now = datetime.now(UTC).replace(tzinfo=None)

    for list_id in list_ids:
        if list_id in existing:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO pms_task_list_statuses
                    (id, list_id, slug, name, color, category, sort_order, created_at)
                VALUES
                    (:id, :list_id, 'backlog', 'Backlog', '#6b7280', 'backlog', 0, :created_at)
                """
            ),
            {"id": str(uuid4()), "list_id": list_id, "created_at": now},
        )

    op.execute(
        """
        UPDATE pms_task_list_statuses
        SET sort_order = CASE slug
            WHEN 'backlog' THEN 0
            WHEN 'todo' THEN 1
            WHEN 'in_progress' THEN 2
            WHEN 'done' THEN 3
            WHEN 'canceled' THEN 4
            ELSE sort_order
        END
        WHERE slug IN ('backlog', 'todo', 'in_progress', 'done', 'canceled')
        """
    )
