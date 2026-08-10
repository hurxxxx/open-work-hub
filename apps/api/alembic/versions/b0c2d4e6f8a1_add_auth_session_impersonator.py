"""add_auth_session_impersonator

Revision ID: b0c2d4e6f8a1
Revises: a9b8c7d6e5f4
Create Date: 2026-06-10 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b0c2d4e6f8a1"
down_revision: str | Sequence[str] | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("impersonator_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_auth_sessions_impersonator_user_id",
        "auth_sessions",
        ["impersonator_user_id"],
    )
    op.create_foreign_key(
        "fk_auth_sessions_impersonator_user_id_users",
        "auth_sessions",
        "users",
        ["impersonator_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_auth_sessions_impersonator_user_id_users",
        "auth_sessions",
        type_="foreignkey",
    )
    op.drop_index("ix_auth_sessions_impersonator_user_id", table_name="auth_sessions")
    op.drop_column("auth_sessions", "impersonator_user_id")
