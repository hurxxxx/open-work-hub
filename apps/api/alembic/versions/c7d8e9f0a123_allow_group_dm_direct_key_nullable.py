"""allow_group_dm_direct_key_nullable

Revision ID: c7d8e9f0a123
Revises: b6c8d9e0f123
Create Date: 2026-05-19 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a123"
down_revision: str | Sequence[str] | None = "b6c8d9e0f123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("dm_conversations"):
        return
    columns = {column["name"] for column in inspector.get_columns("dm_conversations")}
    if "direct_key" not in columns:
        return
    op.alter_column(
        "dm_conversations",
        "direct_key",
        existing_type=sa.String(length=96),
        nullable=True,
    )


def downgrade() -> None:
    return
