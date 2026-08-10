"""add_review_status_to_default_pms_workflows

Revision ID: f8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-05-26 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "f8b9c0d1e2f3"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_WORKFLOW_SLUGS = (
    "todo",
    "in_progress",
    "review",
    "done",
    "complete",
    "canceled",
)


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC).replace(tzinfo=None)

    team_ids_missing_review = bind.execute(
        sa.text(
            """
            SELECT DISTINCT tl.team_id
            FROM pms_task_lists tl
            WHERE tl.team_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM pms_space_statuses ps
                WHERE ps.team_id = tl.team_id
                  AND ps.slug = 'review'
              )
            """
        )
    ).scalars()
    for team_id in team_ids_missing_review:
        bind.execute(
            sa.text(
                """
                INSERT INTO pms_space_statuses
                    (id, team_id, slug, name, color, category, sort_order, created_at)
                VALUES
                    (:id, :team_id, 'review', 'Review', '#8b5cf6', 'active', 2, :created_at)
                ON CONFLICT (team_id, slug) DO NOTHING
                """
            ),
            {"id": str(uuid4()), "team_id": team_id, "created_at": now},
        )

    default_like_list_ids = list(
        bind.execute(
            sa.text(
                """
                WITH status_summary AS (
                    SELECT
                        list_id,
                        bool_or(slug = 'todo') AS has_todo,
                        bool_or(slug = 'in_progress') AS has_in_progress,
                        bool_or(slug = 'done') AS has_done,
                        bool_or(slug = 'review') AS has_review,
                        count(*) FILTER (
                            WHERE slug NOT IN :default_workflow_slugs
                        ) AS non_default_count
                    FROM pms_task_list_statuses
                    GROUP BY list_id
                )
                SELECT list_id
                FROM status_summary
                WHERE has_todo
                  AND has_in_progress
                  AND has_done
                  AND NOT has_review
                  AND non_default_count = 0
                """
            ).bindparams(
                sa.bindparam(
                    "default_workflow_slugs",
                    expanding=True,
                    value=DEFAULT_WORKFLOW_SLUGS,
                )
            )
        ).scalars()
    )
    for list_id in default_like_list_ids:
        bind.execute(
            sa.text(
                """
                INSERT INTO pms_task_list_statuses
                    (id, list_id, slug, name, color, category, sort_order, created_at)
                VALUES
                    (:id, :list_id, 'review', 'Review', '#8b5cf6', 'active', 2, :created_at)
                ON CONFLICT (list_id, slug) DO NOTHING
                """
            ),
            {"id": str(uuid4()), "list_id": list_id, "created_at": now},
        )

    op.execute(
        """
        WITH status_summary AS (
            SELECT
                list_id,
                bool_or(slug = 'todo') AS has_todo,
                bool_or(slug = 'in_progress') AS has_in_progress,
                bool_or(slug = 'done') AS has_done,
                count(*) FILTER (
                    WHERE slug NOT IN (
                        'todo',
                        'in_progress',
                        'review',
                        'done',
                        'complete',
                        'canceled'
                    )
                ) AS non_default_count
            FROM pms_task_list_statuses
            GROUP BY list_id
        )
        UPDATE pms_task_list_statuses ps
        SET sort_order = CASE ps.slug
            WHEN 'todo' THEN 0
            WHEN 'in_progress' THEN 1
            WHEN 'review' THEN 2
            WHEN 'done' THEN 3
            WHEN 'complete' THEN 4
            WHEN 'canceled' THEN 5
            ELSE ps.sort_order
        END
        FROM status_summary ss
        WHERE ps.list_id = ss.list_id
          AND ss.has_todo
          AND ss.has_in_progress
          AND ss.has_done
          AND ss.non_default_count = 0
          AND ps.slug IN (
            'todo',
            'in_progress',
            'review',
            'done',
            'complete',
            'canceled'
          )
        """
    )

    op.execute(
        """
        UPDATE pms_space_statuses
        SET sort_order = CASE slug
            WHEN 'todo' THEN 0
            WHEN 'in_progress' THEN 1
            WHEN 'review' THEN 2
            WHEN 'done' THEN 3
            WHEN 'complete' THEN 4
            ELSE sort_order
        END
        WHERE slug IN ('todo', 'in_progress', 'review', 'done', 'complete')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        WITH status_summary AS (
            SELECT
                list_id,
                bool_or(slug = 'todo') AS has_todo,
                bool_or(slug = 'in_progress') AS has_in_progress,
                bool_or(slug = 'done') AS has_done,
                count(*) FILTER (
                    WHERE slug NOT IN (
                        'todo',
                        'in_progress',
                        'review',
                        'done',
                        'complete',
                        'canceled'
                    )
                ) AS non_default_count
            FROM pms_task_list_statuses
            GROUP BY list_id
        )
        UPDATE pms_tasks t
        SET status = 'in_progress'
        FROM status_summary ss
        WHERE t.list_id = ss.list_id
          AND t.status = 'review'
          AND ss.has_todo
          AND ss.has_in_progress
          AND ss.has_done
          AND ss.non_default_count = 0
        """
    )
    op.execute(
        """
        WITH status_summary AS (
            SELECT
                list_id,
                bool_or(slug = 'todo') AS has_todo,
                bool_or(slug = 'in_progress') AS has_in_progress,
                bool_or(slug = 'done') AS has_done,
                count(*) FILTER (
                    WHERE slug NOT IN (
                        'todo',
                        'in_progress',
                        'review',
                        'done',
                        'complete',
                        'canceled'
                    )
                ) AS non_default_count
            FROM pms_task_list_statuses
            GROUP BY list_id
        )
        UPDATE pms_task_templates tt
        SET default_status = 'in_progress'
        FROM status_summary ss
        WHERE tt.list_id = ss.list_id
          AND tt.default_status = 'review'
          AND ss.has_todo
          AND ss.has_in_progress
          AND ss.has_done
          AND ss.non_default_count = 0
        """
    )
    op.execute(
        """
        WITH status_summary AS (
            SELECT
                list_id,
                bool_or(slug = 'todo') AS has_todo,
                bool_or(slug = 'in_progress') AS has_in_progress,
                bool_or(slug = 'done') AS has_done,
                count(*) FILTER (
                    WHERE slug NOT IN (
                        'todo',
                        'in_progress',
                        'review',
                        'done',
                        'complete',
                        'canceled'
                    )
                ) AS non_default_count
            FROM pms_task_list_statuses
            GROUP BY list_id
        )
        DELETE FROM pms_task_list_statuses ps
        USING status_summary ss
        WHERE ps.list_id = ss.list_id
          AND ps.slug = 'review'
          AND ss.has_todo
          AND ss.has_in_progress
          AND ss.has_done
          AND ss.non_default_count = 0
        """
    )
    op.execute("DELETE FROM pms_space_statuses WHERE slug = 'review'")
    op.execute(
        """
        UPDATE pms_task_list_statuses
        SET sort_order = CASE slug
            WHEN 'todo' THEN 0
            WHEN 'in_progress' THEN 1
            WHEN 'done' THEN 2
            WHEN 'complete' THEN 3
            WHEN 'canceled' THEN 4
            ELSE sort_order
        END
        WHERE slug IN ('todo', 'in_progress', 'done', 'complete', 'canceled')
        """
    )
    op.execute(
        """
        UPDATE pms_space_statuses
        SET sort_order = CASE slug
            WHEN 'todo' THEN 0
            WHEN 'in_progress' THEN 1
            WHEN 'done' THEN 2
            WHEN 'complete' THEN 3
            ELSE sort_order
        END
        WHERE slug IN ('todo', 'in_progress', 'done', 'complete')
        """
    )
