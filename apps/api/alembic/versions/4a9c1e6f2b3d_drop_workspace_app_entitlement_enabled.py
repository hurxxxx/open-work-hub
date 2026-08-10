"""drop workspace app entitlement enabled

Revision ID: 4a9c1e6f2b3d
Revises: 3f8a0b5c2d4e
Create Date: 2026-07-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "4a9c1e6f2b3d"
down_revision: str | Sequence[str] | None = "3f8a0b5c2d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        op.f("ix_workspace_app_entitlements_enabled"),
        table_name="workspace_app_entitlements",
    )
    op.drop_column("workspace_app_entitlements", "enabled")


def downgrade() -> None:
    op.add_column(
        "workspace_app_entitlements",
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_workspace_app_entitlements_enabled"),
        "workspace_app_entitlements",
        ["enabled"],
        unique=False,
    )
