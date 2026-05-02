"""add_user_locale

Revision ID: 7c4e1a92d8b6
Revises: e2f9a3c4b6d1
Create Date: 2026-05-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c4e1a92d8b6"
down_revision: Union[str, Sequence[str], None] = "e2f9a3c4b6d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "locale",
            sa.String(length=16),
            server_default="ko-KR",
            nullable=False,
        ),
    )
    op.alter_column("users", "locale", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "locale")
