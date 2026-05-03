"""image_generations: add is_template

Revision ID: e9b7f6a4c2d1
Revises: d4b8e1c79a02
Create Date: 2026-05-03 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9b7f6a4c2d1"
down_revision: Union[str, Sequence[str], None] = "d4b8e1c79a02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "image_generations",
        sa.Column(
            "is_template",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("image_generations", "is_template", server_default=None)
    op.create_index(
        "ix_image_generations_workspace_owner_template_created",
        "image_generations",
        ["workspace_id", "owner_id", "is_template", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_generations_workspace_owner_template_created",
        table_name="image_generations",
    )
    op.drop_column("image_generations", "is_template")
