"""add ai security external app actions

Revision ID: e4f5a6b7c8d9
Revises: df67ea90bc12
Create Date: 2026-06-25 10:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "df67ea90bc12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "ai_security_data_protection_settings",
        sa.Column("external_app_actions_json", JSONB_COMPAT, nullable=True),
    )


def downgrade() -> None:
    op.drop_column(
        "ai_security_data_protection_settings",
        "external_app_actions_json",
    )
