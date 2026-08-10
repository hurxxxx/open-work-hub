"""add_pms_issue_followers

Revision ID: 4a7c9e2d1b03
Revises: 2f4c6d8e1a90
Create Date: 2026-05-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a7c9e2d1b03"
down_revision: Union[str, Sequence[str], None] = "2f4c6d8e1a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pms_issue_followers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issue_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["pms_issues.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_id", "user_id", name="uq_pms_issue_follower"),
    )
    op.create_index(
        op.f("ix_pms_issue_followers_issue_id"),
        "pms_issue_followers",
        ["issue_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pms_issue_followers_user_id"),
        "pms_issue_followers",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pms_issue_followers_user_id"), table_name="pms_issue_followers")
    op.drop_index(op.f("ix_pms_issue_followers_issue_id"), table_name="pms_issue_followers")
    op.drop_table("pms_issue_followers")
