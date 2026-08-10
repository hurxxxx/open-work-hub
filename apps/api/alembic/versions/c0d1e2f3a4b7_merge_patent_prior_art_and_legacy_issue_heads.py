"""merge patent prior art and legacy issue heads

Revision ID: c0d1e2f3a4b7
Revises: aa1b2c3d4e5f, b7c8d9e0f1a2
Create Date: 2026-06-30
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "c0d1e2f3a4b7"
down_revision: str | Sequence[str] | None = ("aa1b2c3d4e5f", "b7c8d9e0f1a2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
