"""add_user_date_format

Revision ID: a8c5d3f1b2e4
Revises: f8b9c0d1e2f3
Create Date: 2026-05-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c5d3f1b2e4"
down_revision: Union[str, Sequence[str], None] = "f8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "date_format",
            sa.String(length=24),
            server_default="korean",
            nullable=False,
        ),
    )
    op.alter_column("users", "date_format", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "date_format")
