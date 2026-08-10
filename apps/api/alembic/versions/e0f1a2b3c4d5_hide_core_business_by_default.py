"""hide_core_business_by_default

Revision ID: e0f1a2b3c4d5
Revises: d0e1f2a3b4c6
Create Date: 2026-06-16 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision: str = "e0f1a2b3c4d5"
down_revision: str | Sequence[str] | None = "d0e1f2a3b4c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PLATFORM_APP_VISIBILITY = sa.table(
    "platform_app_visibility",
    sa.column("id", sa.String),
    sa.column("app_id", sa.String),
    sa.column("visible", sa.Boolean),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)


def upgrade() -> None:
    connection = op.get_bind()
    existing_id = connection.execute(
        sa.select(PLATFORM_APP_VISIBILITY.c.id).where(
            PLATFORM_APP_VISIBILITY.c.app_id == "core-business"
        )
    ).scalar_one_or_none()
    now = _utcnow_naive()
    if existing_id is None:
        connection.execute(
            PLATFORM_APP_VISIBILITY.insert().values(
                id=str(uuid4()),
                app_id="core-business",
                visible=False,
                created_at=now,
                updated_at=now,
            )
        )
        return

    connection.execute(
        PLATFORM_APP_VISIBILITY.update()
        .where(PLATFORM_APP_VISIBILITY.c.app_id == "core-business")
        .values(visible=False, updated_at=now)
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        PLATFORM_APP_VISIBILITY.update()
        .where(PLATFORM_APP_VISIBILITY.c.app_id == "core-business")
        .values(visible=True, updated_at=_utcnow_naive())
    )


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
