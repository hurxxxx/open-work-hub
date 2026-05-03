"""image_generations: add template_id

Revision ID: d4b8e1c79a02
Revises: c3a7e9d52f81
Create Date: 2026-05-03 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4b8e1c79a02"
down_revision: Union[str, Sequence[str], None] = "c3a7e9d52f81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "image_generations",
        sa.Column("template_id", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("image_generations", "template_id")
