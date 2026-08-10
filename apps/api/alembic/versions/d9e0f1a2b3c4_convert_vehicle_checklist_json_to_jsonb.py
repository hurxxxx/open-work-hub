"""convert_vehicle_checklist_json_to_jsonb

Revision ID: d9e0f1a2b3c4
Revises: c4d8e2f6a1b3
Create Date: 2026-07-10 16:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c4d8e2f6a1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.alter_column(
        "legacy_issue_vehicle_checklist_revisions",
        "definition_snapshot",
        existing_type=sa.JSON(),
        type_=JSONB,
        existing_nullable=False,
        postgresql_using="definition_snapshot::jsonb",
    )
    op.alter_column(
        "legacy_issue_vehicle_checklist_records",
        "field_values",
        existing_type=sa.JSON(),
        type_=JSONB,
        existing_nullable=True,
        postgresql_using="field_values::jsonb",
    )


def downgrade() -> None:
    op.alter_column(
        "legacy_issue_vehicle_checklist_records",
        "field_values",
        existing_type=JSONB,
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="field_values::json",
    )
    op.alter_column(
        "legacy_issue_vehicle_checklist_revisions",
        "definition_snapshot",
        existing_type=JSONB,
        type_=sa.JSON(),
        existing_nullable=False,
        postgresql_using="definition_snapshot::json",
    )
