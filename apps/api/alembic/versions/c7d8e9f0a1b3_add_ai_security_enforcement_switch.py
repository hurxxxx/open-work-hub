"""add ai security enforcement switch

Revision ID: c7d8e9f0a1b3
Revises: b6c7d8e9f0a2
Create Date: 2026-06-25 15:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b3"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_security_data_protection_settings",
        sa.Column(
            "enforcement_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "ai_security_data_protection_settings",
        sa.Column(
            "enforcement_disabled_reason",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "ai_security_data_protection_settings",
            "enforcement_enabled",
            server_default=None,
        )
        op.alter_column(
            "ai_security_data_protection_settings",
            "enforcement_disabled_reason",
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column(
        "ai_security_data_protection_settings",
        "enforcement_disabled_reason",
    )
    op.drop_column("ai_security_data_protection_settings", "enforcement_enabled")
