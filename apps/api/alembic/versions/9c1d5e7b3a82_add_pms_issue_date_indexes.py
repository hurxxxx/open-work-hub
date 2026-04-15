"""add_pms_issue_date_indexes

Adds indexes on pms_issues.due_date and pms_issues.start_date so the unified
/api/v1/calendar/events endpoint (Phase 2 of the calendar foundation work)
can efficiently filter by date range across all issues for a user.

Per autoplan Round 2 Eng review finding ENG-HIGH-1.

Revision ID: 9c1d5e7b3a82
Revises: 7a3c2b9f11e8
Create Date: 2026-04-15 17:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "9c1d5e7b3a82"
down_revision: Union[str, Sequence[str], None] = "7a3c2b9f11e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_pms_issues_due_date",
        "pms_issues",
        ["due_date"],
    )
    op.create_index(
        "ix_pms_issues_start_date",
        "pms_issues",
        ["start_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_pms_issues_start_date", table_name="pms_issues")
    op.drop_index("ix_pms_issues_due_date", table_name="pms_issues")
