"""set legacy issue received date field type

Revision ID: d1a7c9e3f5b8
Revises: c8e4f6a0b3d5
Create Date: 2026-07-24 10:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d1a7c9e3f5b8"
down_revision: str | Sequence[str] | None = "c8e4f6a0b3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DATASET_KEY = "common-master"
RECEIVED_DATE_FIELD_KEY = "received_date"
SNAPSHOT_TABLE_NAMES = (
    "legacy_issue_vehicle_checklist_revisions",
    "legacy_issue_vehicle_module_checklists",
)


def _updated_definition_snapshot(
    snapshot: Any,
    *,
    field_type: str,
) -> tuple[Any, bool]:
    if not isinstance(snapshot, dict):
        return snapshot, False
    fields = snapshot.get("fields")
    if not isinstance(fields, list):
        return snapshot, False

    changed = False
    next_fields: list[Any] = []
    for field in fields:
        if not isinstance(field, dict) or field.get("key") != RECEIVED_DATE_FIELD_KEY:
            next_fields.append(field)
            continue
        next_field = dict(field)
        if next_field.get("field_type") != field_type:
            next_field["field_type"] = field_type
            changed = True
        next_fields.append(next_field)

    if not changed:
        return snapshot, False
    next_snapshot = dict(snapshot)
    next_snapshot["fields"] = next_fields
    return next_snapshot, True


def _rewrite_snapshot_tables(*, field_type: str) -> None:
    bind = op.get_bind()
    for table_name in SNAPSHOT_TABLE_NAMES:
        table = sa.table(
            table_name,
            sa.column("id", sa.String()),
            sa.column("definition_snapshot", postgresql.JSONB(astext_type=sa.Text())),
        )
        rows = bind.execute(sa.select(table.c.id, table.c.definition_snapshot)).mappings()
        for row in rows:
            next_snapshot, changed = _updated_definition_snapshot(
                row["definition_snapshot"],
                field_type=field_type,
            )
            if not changed:
                continue
            bind.execute(
                table.update()
                .where(table.c.id == row["id"])
                .values(definition_snapshot=next_snapshot)
            )


def _rewrite_system_field_settings(*, field_type: str) -> None:
    settings = sa.table(
        "legacy_issue_system_field_settings",
        sa.column("dataset_key", sa.String()),
        sa.column("field_key", sa.String()),
        sa.column("field_type", sa.String()),
    )
    op.get_bind().execute(
        settings.update()
        .where(
            settings.c.dataset_key == DATASET_KEY,
            settings.c.field_key == RECEIVED_DATE_FIELD_KEY,
        )
        .values(field_type=field_type)
    )


def upgrade() -> None:
    _rewrite_system_field_settings(field_type="date")
    _rewrite_snapshot_tables(field_type="date")


def downgrade() -> None:
    _rewrite_system_field_settings(field_type="text")
    _rewrite_snapshot_tables(field_type="text")
