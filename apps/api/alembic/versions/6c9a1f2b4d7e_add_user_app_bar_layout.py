"""add_user_app_bar_layout

Revision ID: 6c9a1f2b4d7e
Revises: 5b8f2c1d9a04
Create Date: 2026-05-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6c9a1f2b4d7e"
down_revision: Union[str, Sequence[str], None] = "5b8f2c1d9a04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("app_bar_layout", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "app_bar_layout")
