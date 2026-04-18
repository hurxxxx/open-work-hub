"""add_llm_policies

Revision ID: c7a2f1e8b3d4
Revises: b4c1a2d9e6f0
Create Date: 2026-04-18 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7a2f1e8b3d4"
down_revision: Union[str, Sequence[str], None] = "b4c1a2d9e6f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_kind", sa.String(length=64), nullable=False),
        sa.Column("policy_mode", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_llm_policies_task_kind"),
        "llm_policies",
        ["task_kind"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_policies_task_kind"), table_name="llm_policies")
    op.drop_table("llm_policies")
