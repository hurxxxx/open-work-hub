"""add_user_time_zone

Revision ID: e2f9a3c4b6d1
Revises: 2a9f4d6c8e10
Create Date: 2026-05-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f9a3c4b6d1"
down_revision: Union[str, Sequence[str], None] = "2a9f4d6c8e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "time_zone",
            sa.String(length=64),
            server_default="Asia/Seoul",
            nullable=False,
        ),
    )
    op.alter_column("users", "time_zone", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "time_zone")
