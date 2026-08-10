"""default ai security enforcement off

Revision ID: d8e9f0a1b3c4
Revises: c7d8e9f0a1b3
Create Date: 2026-06-25 16:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e9f0a1b3c4"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE ai_security_data_protection_settings
            SET enforcement_enabled = false,
                enforcement_disabled_reason = CASE
                    WHEN btrim(coalesce(enforcement_disabled_reason, '')) = ''
                    THEN 'default_off'
                    ELSE enforcement_disabled_reason
                END
            WHERE id = 'global'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE ai_security_data_protection_settings
            SET enforcement_enabled = true,
                enforcement_disabled_reason = ''
            WHERE id = 'global'
            """
        )
    )
