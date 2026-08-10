"""add AI model discovery metadata and provider endpoints

Revision ID: a2b3c4d5e6f8
Revises: fb1c2d3e4f5a
Create Date: 2026-07-13 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f8"
down_revision: str | Sequence[str] | None = "fb1c2d3e4f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OFFICIAL_PROVIDER_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
}


def upgrade() -> None:
    op.add_column(
        "ai_model_catalog_entries",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="manual",
        ),
    )
    op.add_column(
        "ai_model_catalog_entries",
        sa.Column(
            "discovery_status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "ai_model_catalog_entries",
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    )
    op.create_check_constraint(
        "ck_ai_model_catalog_entries_source",
        "ai_model_catalog_entries",
        "source IN ('manual', 'discovered')",
    )
    op.create_check_constraint(
        "ck_ai_model_catalog_entries_discovery_status",
        "ai_model_catalog_entries",
        "discovery_status IN ('active', 'stale')",
    )
    op.alter_column(
        "ai_model_catalog_entries",
        "source",
        server_default=None,
    )
    op.alter_column(
        "ai_model_catalog_entries",
        "discovery_status",
        server_default=None,
    )

    bind = op.get_bind()
    metadata = sa.MetaData()
    providers = sa.Table("ai_model_provider_configs", metadata, autoload_with=bind)
    for provider_id, endpoint_url in OFFICIAL_PROVIDER_ENDPOINTS.items():
        bind.execute(
            sa.update(providers)
            .where(
                providers.c.provider_id == provider_id,
                providers.c.endpoint_url.is_(None),
            )
            .values(endpoint_url=endpoint_url)
        )


def downgrade() -> None:
    # Endpoint backfills are intentionally retained: after upgrade an official
    # endpoint is indistinguishable from an administrator-saved identical URL.
    op.drop_constraint(
        "ck_ai_model_catalog_entries_discovery_status",
        "ai_model_catalog_entries",
        type_="check",
    )
    op.drop_constraint(
        "ck_ai_model_catalog_entries_source",
        "ai_model_catalog_entries",
        type_="check",
    )
    op.drop_column("ai_model_catalog_entries", "last_seen_at")
    op.drop_column("ai_model_catalog_entries", "discovery_status")
    op.drop_column("ai_model_catalog_entries", "source")
