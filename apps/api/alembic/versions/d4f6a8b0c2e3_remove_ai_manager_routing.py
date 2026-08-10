"""remove retired AI manager routing override

Revision ID: d4f6a8b0c2e3
Revises: c3f5a7b9d1e2
Create Date: 2026-07-12 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d4f6a8b0c2e3"
down_revision: str | Sequence[str] | None = "c3f5a7b9d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    overrides = sa.Table("ai_model_route_overrides", metadata, autoload_with=bind)
    bind.execute(sa.delete(overrides).where(overrides.c.workload_id == "ai_manager"))


def downgrade() -> None:
    # The retired workload has no executable registration to restore. Historical
    # audit and usage rows remain untouched.
    pass
