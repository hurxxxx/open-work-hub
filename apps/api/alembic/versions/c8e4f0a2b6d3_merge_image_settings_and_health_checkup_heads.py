"""merge image settings and management health checkup heads

Revision ID: c8e4f0a2b6d3
Revises: b7d3e9f1a5c2, e5f7a9b1c3d4
Create Date: 2026-07-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "c8e4f0a2b6d3"
down_revision: str | Sequence[str] | None = (
    "b7d3e9f1a5c2",
    "e5f7a9b1c3d4",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
