"""add legacy issue multi reference fields

Revision ID: c0d1e2f3a5b7
Revises: b9c0d1e2f3a5
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c0d1e2f3a5b7"
down_revision: str | Sequence[str] | None = "b9c0d1e2f3a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_FIELD_TYPE_CHECK = (
    "field_type IN "
    "('text', 'longText', 'number', 'date', 'select', 'boolean', 'user', 'orgUnit')"
)
_OLD_FIELD_TYPE_CHECK = (
    "field_type IN ('text', 'longText', 'number', 'date', 'select', 'boolean')"
)


def upgrade() -> None:
    _add_allow_multiple_column(
        "legacy_issue_module_fields",
        "ck_legacy_issue_module_fields_type",
    )
    _add_allow_multiple_column(
        "legacy_issue_system_field_settings",
        "ck_legacy_issue_system_field_settings_type",
    )


def downgrade() -> None:
    _remove_allow_multiple_column(
        "legacy_issue_system_field_settings",
        "ck_legacy_issue_system_field_settings_type",
    )
    _remove_allow_multiple_column(
        "legacy_issue_module_fields",
        "ck_legacy_issue_module_fields_type",
    )


def _add_allow_multiple_column(table_name: str, constraint_name: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.drop_constraint(constraint_name, type_="check")
            batch_op.add_column(
                sa.Column(
                    "allow_multiple",
                    sa.Boolean(),
                    server_default=sa.text("false"),
                    nullable=False,
                )
            )
            batch_op.create_check_constraint(constraint_name, _NEW_FIELD_TYPE_CHECK)
        return
    op.drop_constraint(constraint_name, table_name, type_="check")
    op.add_column(
        table_name,
        sa.Column(
            "allow_multiple",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_check_constraint(constraint_name, table_name, _NEW_FIELD_TYPE_CHECK)


def _remove_allow_multiple_column(table_name: str, constraint_name: str) -> None:
    op.execute(
        f"""
        UPDATE {table_name}
        SET field_type = 'text', allow_multiple = false, options = NULL
        WHERE field_type IN ('user', 'orgUnit')
        """
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.drop_constraint(constraint_name, type_="check")
            batch_op.create_check_constraint(constraint_name, _OLD_FIELD_TYPE_CHECK)
            batch_op.drop_column("allow_multiple")
        return
    op.drop_constraint(constraint_name, table_name, type_="check")
    op.create_check_constraint(constraint_name, table_name, _OLD_FIELD_TYPE_CHECK)
    op.drop_column(table_name, "allow_multiple")
