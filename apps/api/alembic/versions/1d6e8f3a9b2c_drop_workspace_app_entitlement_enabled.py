"""defer dropping workspace app entitlement enabled

Revision ID: 1d6e8f3a9b2c
Revises: eb02c3d4e5f6
Create Date: 2026-07-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "1d6e8f3a9b2c"
down_revision: str | Sequence[str] | None = "eb02c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep the legacy column through the registry refactor release. The
    # production deploy migrates before stopping the old API, so dropping it
    # here would make the still-running old process query a missing column.
    # Remove it only in a later contract release after rollback compatibility
    # is no longer required.
    pass


def downgrade() -> None:
    pass
