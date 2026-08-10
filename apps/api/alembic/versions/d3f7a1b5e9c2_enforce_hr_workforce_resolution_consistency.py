"""enforce HR workforce resolution consistency

Revision ID: d3f7a1b5e9c2
Revises: c2e6f9a3d5b7
Create Date: 2026-07-29 21:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "d3f7a1b5e9c2"
down_revision: str | Sequence[str] | None = "c2e6f9a3d5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RESOLUTION_CONDITION = (
    "(workforce_category_resolution_kind = 'inferred' "
    "AND workforce_assignment_id IS NULL "
    "AND workforce_category = inferred_workforce_category) "
    "OR (workforce_category_resolution_kind = 'manual' "
    "AND workforce_assignment_id IS NOT NULL)"
)


def upgrade() -> None:
    op.create_check_constraint(
        "ck_hr_master_person_rows_workforce_resolution",
        "hr_master_person_rows",
        _RESOLUTION_CONDITION,
    )
    op.create_check_constraint(
        "ck_hr_master_external_rows_workforce_resolution",
        "hr_master_external_person_rows",
        _RESOLUTION_CONDITION,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_hr_master_external_rows_workforce_resolution",
        "hr_master_external_person_rows",
        type_="check",
    )
    op.drop_constraint(
        "ck_hr_master_person_rows_workforce_resolution",
        "hr_master_person_rows",
        type_="check",
    )
