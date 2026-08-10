"""remove_empty_legacy_issue_module_records

Revision ID: d0e1f2a3b4c6
Revises: c0d1e2f3a4b5
Create Date: 2026-06-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "d0e1f2a3b4c6"
down_revision: str | Sequence[str] | None = "c0d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MODULE_RECORD_TABLES = (
    ("electrical-mechanical", "legacy_issue_electrical_mechanical_records"),
    ("electrical-control-hw", "legacy_issue_electrical_control_hw_records"),
    ("electrical-control-sw", "legacy_issue_electrical_control_sw_records"),
    ("interior", "legacy_issue_interior_records"),
    ("cooling-module", "legacy_issue_cooling_module_records"),
)


def upgrade() -> None:
    connection = op.get_bind()
    empty_json = "'{}'::jsonb" if connection.dialect.name == "postgresql" else "'{}'"
    for module_key, table_name in MODULE_RECORD_TABLES:
        empty_condition = f"field_values IS NULL OR field_values = {empty_json}"
        op.execute(
            f"""
            DELETE FROM legacy_issue_module_attachments
            WHERE module_key = '{module_key}'
              AND record_id IN (
                SELECT id FROM {table_name}
                WHERE {empty_condition}
              )
            """
        )
        op.execute(f"DELETE FROM {table_name} WHERE {empty_condition}")


def downgrade() -> None:
    pass
