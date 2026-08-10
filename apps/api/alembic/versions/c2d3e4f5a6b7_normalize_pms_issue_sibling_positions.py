"""normalize_pms_issue_sibling_positions

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-21 12:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "c2d3e4f5a6b7"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ordered AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY list_id, parent_id
                    ORDER BY board_position ASC, created_at ASC, issue_number ASC, id ASC
                ) AS next_position
            FROM pms_issues
        )
        UPDATE pms_issues AS issue
        SET board_position = ordered.next_position
        FROM ordered
        WHERE issue.id = ordered.id
          AND issue.board_position <> ordered.next_position
        """
    )


def downgrade() -> None:
    pass
