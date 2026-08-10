"""add separate image model provider and profile settings

Revision ID: a6c2e8f4b1d9
Revises: e5f9a3b7c1d4
Create Date: 2026-07-22 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op


revision: str = "a6c2e8f4b1d9"
down_revision: str | Sequence[str] | None = "e5f9a3b7c1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_model_provider_configs",
        sa.Column("provider_id", sa.String(length=32), nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("supervisor_model_id", sa.String(length=160), nullable=True),
        sa.Column("generation_model_id", sa.String(length=160), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("provider_id"),
    )
    op.create_table(
        "image_model_profiles",
        sa.Column("profile_id", sa.String(length=32), nullable=False),
        sa.Column("active_provider_id", sa.String(length=32), nullable=True),
        sa.Column("brief_web_search_enabled", sa.Boolean(), nullable=False),
        sa.Column("generation_web_search_enabled", sa.Boolean(), nullable=False),
        sa.Column("max_iterations", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "max_iterations BETWEEN 1 AND 20",
            name="ck_image_model_profiles_max_iterations",
        ),
        sa.ForeignKeyConstraint(
            ["active_provider_id"],
            ["image_model_provider_configs.provider_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("profile_id"),
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    profiles = sa.table(
        "image_model_profiles",
        sa.column("profile_id", sa.String()),
        sa.column("active_provider_id", sa.String()),
        sa.column("brief_web_search_enabled", sa.Boolean()),
        sa.column("generation_web_search_enabled", sa.Boolean()),
        sa.column("max_iterations", sa.Integer()),
        sa.column("version", sa.Integer()),
        sa.column("updated_by", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        profiles,
        [
            {
                "profile_id": "default",
                "active_provider_id": None,
                "brief_web_search_enabled": True,
                "generation_web_search_enabled": True,
                "max_iterations": 10,
                "version": 1,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("image_model_profiles")
    op.drop_table("image_model_provider_configs")
