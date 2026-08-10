"""allow registered LLM provider ids

Revision ID: e5f9a3b7c1d4
Revises: d4e8f2a6b0c3
Create Date: 2026-07-22 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "e5f9a3b7c1d4"
down_revision: str | Sequence[str] | None = "d4e8f2a6b0c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_ai_model_provider_configs_provider_id",
        "ai_model_provider_configs",
        type_="check",
    )


def downgrade() -> None:
    op.create_check_constraint(
        "ck_ai_model_provider_configs_provider_id",
        "ai_model_provider_configs",
        "provider_id IN ('local', 'openai', 'anthropic', 'gemini')",
    )
