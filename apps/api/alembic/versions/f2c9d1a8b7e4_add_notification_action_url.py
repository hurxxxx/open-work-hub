"""notifications: add action_url

Revision ID: f2c9d1a8b7e4
Revises: e9b7f6a4c2d1
Create Date: 2026-05-03 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2c9d1a8b7e4"
down_revision: Union[str, Sequence[str], None] = "e9b7f6a4c2d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pms_notifications", sa.Column("action_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pms_notifications", "action_url")
