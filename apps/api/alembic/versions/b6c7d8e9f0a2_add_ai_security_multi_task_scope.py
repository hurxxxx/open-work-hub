"""add ai security multi task scope

Revision ID: b6c7d8e9f0a2
Revises: e4f5a6b7c8d9
Create Date: 2026-06-25 11:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b6c7d8e9f0a2"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _backfill_task_kinds(table_name: str) -> None:
    bind = op.get_bind()
    table = sa.table(
        table_name,
        sa.column("id", sa.String()),
        sa.column("task_kind", sa.String()),
        sa.column("task_kinds_json", JSONB_COMPAT),
    )
    rows = bind.execute(sa.select(table.c.id, table.c.task_kind)).all()
    for row in rows:
        task_kind = (row.task_kind or "").strip()
        bind.execute(
            table.update()
            .where(table.c.id == row.id)
            .values(task_kinds_json=[task_kind] if task_kind else [])
        )


def upgrade() -> None:
    op.add_column(
        "ai_security_policy_rules",
        sa.Column("task_kinds_json", JSONB_COMPAT, nullable=True),
    )
    op.add_column(
        "ai_security_external_transfer_exceptions",
        sa.Column("task_kinds_json", JSONB_COMPAT, nullable=True),
    )
    _backfill_task_kinds("ai_security_policy_rules")
    _backfill_task_kinds("ai_security_external_transfer_exceptions")


def downgrade() -> None:
    op.drop_column("ai_security_external_transfer_exceptions", "task_kinds_json")
    op.drop_column("ai_security_policy_rules", "task_kinds_json")
