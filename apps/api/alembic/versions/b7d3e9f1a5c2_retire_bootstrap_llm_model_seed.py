"""retire the historical bootstrap LLM model selection

Revision ID: b7d3e9f1a5c2
Revises: a6c2e8f4b1d9
Create Date: 2026-07-22 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision: str = "b7d3e9f1a5c2"
down_revision: str | Sequence[str] | None = "a6c2e8f4b1d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SEED_PROVIDER_ID = "anthropic"
_SEED_MODEL_ID = "anthropic-claude-sonnet-4-6"


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    providers = sa.Table("ai_model_provider_configs", metadata, autoload_with=bind)
    models = sa.Table("ai_model_catalog_entries", metadata, autoload_with=bind)
    routes = sa.Table("ai_model_route_overrides", metadata, autoload_with=bind)
    now = datetime.now(UTC).replace(tzinfo=None)

    # Clear only the untouched provider default created by the historical
    # bootstrap migration. Any credential, activation, version, or actor change
    # means an administrator/importer has taken ownership and must be preserved.
    bind.execute(
        sa.update(providers)
        .where(
            providers.c.provider_id == _SEED_PROVIDER_ID,
            providers.c.default_model_id == _SEED_MODEL_ID,
            providers.c.api_key_ciphertext.is_(None),
            providers.c.enabled.is_(False),
            providers.c.updated_by.is_(None),
            providers.c.version == 1,
        )
        .values(
            default_model_id=None,
            version=providers.c.version + 1,
            updated_at=now,
        )
    )

    provider_reference = bind.scalar(
        sa.select(sa.func.count())
        .select_from(providers)
        .where(providers.c.default_model_id == _SEED_MODEL_ID)
    )
    route_reference = any(
        _SEED_MODEL_ID in _model_ids(value)
        for value in bind.execute(sa.select(routes.c.model_ids_json)).scalars()
    )
    if provider_reference or route_reference:
        return

    bind.execute(
        sa.delete(models).where(
            models.c.id == _SEED_MODEL_ID,
            models.c.provider_id == _SEED_PROVIDER_ID,
            models.c.created_by.is_(None),
            models.c.updated_by.is_(None),
            models.c.version == 1,
        )
    )


def downgrade() -> None:
    # Deliberately irreversible: recreating an obsolete model selection would
    # override the administrator-owned control plane during rollback.
    pass


def _model_ids(value: object) -> set[str]:
    if not isinstance(value, dict):
        return set()
    return {str(model_id) for model_id in value.values() if str(model_id).strip()}
