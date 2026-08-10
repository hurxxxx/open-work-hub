"""prevent duplicate vehicle master checklists

Revision ID: d1e2f3a4b5c7
Revises: c9a0b1c2d3e5
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "d1e2f3a4b5c7"
down_revision: str | Sequence[str] | None = "c9a0b1c2d3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_legacy_issue_vehicle_checklist_revisions_vehicle_master",
        "legacy_issue_vehicle_checklist_revisions",
        ["workspace_id", "vehicle_model_id", "source_master_revision_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_legacy_issue_vehicle_checklist_revisions_vehicle_master",
        "legacy_issue_vehicle_checklist_revisions",
        type_="unique",
    )
