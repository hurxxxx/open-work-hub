"""restore workspace app entitlement enabled compatibility

Revision ID: 2e7f9a4b1c3d
Revises: 1d6e8f3a9b2c
Create Date: 2026-07-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "2e7f9a4b1c3d"
down_revision: str | Sequence[str] | None = "1d6e8f3a9b2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Repair development databases that applied the earlier destructive draft."""
    inspector = sa.inspect(op.get_bind())
    column_names = {
        column["name"]
        for column in inspector.get_columns("workspace_app_entitlements")
    }
    added_column = "enabled" not in column_names
    if added_column:
        op.add_column(
            "workspace_app_entitlements",
            sa.Column(
                "enabled",
                sa.Boolean(),
                server_default=sa.true(),
                nullable=False,
            ),
        )

    inspector = sa.inspect(op.get_bind())
    index_names = {
        index["name"]
        for index in inspector.get_indexes("workspace_app_entitlements")
    }
    if "ix_workspace_app_entitlements_enabled" not in index_names:
        op.create_index(
            op.f("ix_workspace_app_entitlements_enabled"),
            "workspace_app_entitlements",
            ["enabled"],
            unique=False,
        )

    if added_column:
        op.alter_column(
            "workspace_app_entitlements",
            "enabled",
            existing_type=sa.Boolean(),
            server_default=None,
        )


def downgrade() -> None:
    # This compatibility revision intentionally keeps the legacy column so a
    # rollback to the pre-refactor API remains safe.
    pass
