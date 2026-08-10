"""add AI model provider, catalog, and workload route settings

Revision ID: e7a1c3d5f9b2
Revises: d9e0f1a2b3c4
Create Date: 2026-07-10 18:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e7a1c3d5f9b2"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "ai_model_provider_configs",
        sa.Column("provider_id", sa.String(length=32), nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("default_model_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "provider_id IN ('local', 'openai', 'anthropic', 'gemini')",
            name="ck_ai_model_provider_configs_provider_id",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("provider_id"),
    )
    op.create_table(
        "ai_model_catalog_entries",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=32), nullable=False),
        sa.Column("model_key", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("capabilities_json", JSONB, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["ai_model_provider_configs.provider_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_id",
            "model_key",
            name="uq_ai_model_catalog_entries_provider_model",
        ),
    )
    op.create_index(
        op.f("ix_ai_model_catalog_entries_provider_id"),
        "ai_model_catalog_entries",
        ["provider_id"],
        unique=False,
    )
    op.create_table(
        "ai_model_route_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workload_id", sa.String(length=160), nullable=False),
        sa.Column("route_mode", sa.String(length=16), nullable=False),
        sa.Column("provider_id", sa.String(length=32), nullable=True),
        sa.Column("model_ids_json", JSONB, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "route_mode IN ('local', 'external')",
            name="ck_ai_model_route_overrides_route_mode",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["ai_model_provider_configs.provider_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workload_id",
            name="uq_ai_model_route_overrides_workload",
        ),
    )
    op.create_index(
        op.f("ix_ai_model_route_overrides_provider_id"),
        "ai_model_route_overrides",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_model_route_overrides_workload_id"),
        "ai_model_route_overrides",
        ["workload_id"],
        unique=False,
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    providers = sa.table(
        "ai_model_provider_configs",
        sa.column("provider_id", sa.String()),
        sa.column("endpoint_url", sa.Text()),
        sa.column("api_key_ciphertext", sa.Text()),
        sa.column("enabled", sa.Boolean()),
        sa.column("default_model_id", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("updated_by", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        providers,
        [
            {
                "provider_id": "local",
                "endpoint_url": None,
                "api_key_ciphertext": None,
                "enabled": True,
                "default_model_id": None,
                "version": 1,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "provider_id": "openai",
                "endpoint_url": None,
                "api_key_ciphertext": None,
                "enabled": False,
                "default_model_id": None,
                "version": 1,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "provider_id": "anthropic",
                "endpoint_url": None,
                "api_key_ciphertext": None,
                "enabled": False,
                "default_model_id": "anthropic-claude-sonnet-4-6",
                "version": 1,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "provider_id": "gemini",
                "endpoint_url": None,
                "api_key_ciphertext": None,
                "enabled": False,
                "default_model_id": None,
                "version": 1,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    models = sa.table(
        "ai_model_catalog_entries",
        sa.column("id", sa.String()),
        sa.column("provider_id", sa.String()),
        sa.column("model_key", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("capabilities_json", JSONB),
        sa.column("enabled", sa.Boolean()),
        sa.column("version", sa.Integer()),
        sa.column("created_by", sa.String()),
        sa.column("updated_by", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        models,
        [
            {
                "id": "anthropic-claude-sonnet-4-6",
                "provider_id": "anthropic",
                "model_key": "claude-sonnet-4-6",
                "display_name": "Claude Sonnet 4.6",
                "capabilities_json": ["chat", "tool_calling", "vision"],
                "enabled": True,
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ai_model_route_overrides_workload_id"),
        table_name="ai_model_route_overrides",
    )
    op.drop_index(
        op.f("ix_ai_model_route_overrides_provider_id"),
        table_name="ai_model_route_overrides",
    )
    op.drop_table("ai_model_route_overrides")
    op.drop_index(
        op.f("ix_ai_model_catalog_entries_provider_id"),
        table_name="ai_model_catalog_entries",
    )
    op.drop_table("ai_model_catalog_entries")
    op.drop_table("ai_model_provider_configs")
