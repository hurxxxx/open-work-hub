"""add_desktop_session_links

Revision ID: ab12cd34ef56
Revises: d1e2f3a4b5c6
Create Date: 2026-05-20 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "ab12cd34ef56"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "desktop_session_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("source_session_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["source_session_id"], ["auth_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_desktop_session_links_code_hash"), "desktop_session_links", ["code_hash"], unique=True)
    op.create_index(op.f("ix_desktop_session_links_consumed_at"), "desktop_session_links", ["consumed_at"], unique=False)
    op.create_index(op.f("ix_desktop_session_links_expires_at"), "desktop_session_links", ["expires_at"], unique=False)
    op.create_index(
        op.f("ix_desktop_session_links_source_session_id"),
        "desktop_session_links",
        ["source_session_id"],
        unique=False,
    )
    op.create_index(op.f("ix_desktop_session_links_user_id"), "desktop_session_links", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_desktop_session_links_user_id"), table_name="desktop_session_links")
    op.drop_index(op.f("ix_desktop_session_links_source_session_id"), table_name="desktop_session_links")
    op.drop_index(op.f("ix_desktop_session_links_expires_at"), table_name="desktop_session_links")
    op.drop_index(op.f("ix_desktop_session_links_consumed_at"), table_name="desktop_session_links")
    op.drop_index(op.f("ix_desktop_session_links_code_hash"), table_name="desktop_session_links")
    op.drop_table("desktop_session_links")
