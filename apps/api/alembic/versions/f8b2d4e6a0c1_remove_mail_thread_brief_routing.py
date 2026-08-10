"""remove unused mail thread brief routing override

Revision ID: f8b2d4e6a0c1
Revises: d4f6a8b0c2e3
Create Date: 2026-07-13 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f8b2d4e6a0c1"
down_revision: str | Sequence[str] | None = "d4f6a8b0c2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    overrides = sa.Table("ai_model_route_overrides", metadata, autoload_with=bind)
    bind.execute(sa.delete(overrides).where(overrides.c.workload_id == "mail_thread_brief"))


def downgrade() -> None:
    # The retired workload has no executable registration to restore. Historical
    # audit and usage rows remain untouched.
    pass
