"""add platform API keys

Revision ID: e4a8c2d6f0b3
Revises: d3f7a1b5e9c2
Create Date: 2026-07-29 22:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e4a8c2d6f0b3"
down_revision: str | Sequence[str] | None = "d3f7a1b5e9c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("key_prefix", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_platform_api_keys_status",
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_platform_api_keys_name",
        ),
        sa.CheckConstraint(
            "substr(key_prefix, 1, 8) = 'aido_pk_'",
            name="ck_platform_api_keys_prefix",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL AND revoked_by_user_id IS NULL) "
            "OR (status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_platform_api_keys_revocation",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns, unique in (
        ("ix_platform_api_keys_token_hash", ["token_hash"], True),
        ("ix_platform_api_keys_key_prefix", ["key_prefix"], True),
        ("ix_platform_api_keys_name", ["name"], False),
        ("ix_platform_api_keys_status", ["status"], False),
        ("ix_platform_api_keys_created_by_user_id", ["created_by_user_id"], False),
        ("ix_platform_api_keys_created_at", ["created_at"], False),
        ("ix_platform_api_keys_revoked_by_user_id", ["revoked_by_user_id"], False),
        ("ix_platform_api_keys_revoked_at", ["revoked_at"], False),
        ("ix_platform_api_keys_last_used_at", ["last_used_at"], False),
        (
            "ix_platform_api_keys_status_created",
            ["status", "created_at", "id"],
            False,
        ),
    ):
        op.create_index(index_name, "platform_api_keys", columns, unique=unique)


def downgrade() -> None:
    op.drop_table("platform_api_keys")
