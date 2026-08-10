"""default workspace app entitlement enabled for compatibility

Revision ID: 3f8a0b5c2d4e
Revises: 2e7f9a4b1c3d
Create Date: 2026-07-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "3f8a0b5c2d4e"
down_revision: str | Sequence[str] | None = "2e7f9a4b1c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The new API no longer maps this legacy column, while the previous API
    # still requires it during a rolling deploy or rollback. A database default
    # lets new inserts omit it without changing the value seen by the old API.
    op.alter_column(
        "workspace_app_entitlements",
        "enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )


def downgrade() -> None:
    # Keep the default so downgrading this revision cannot break inserts from
    # the new API while processes are being replaced.
    pass
