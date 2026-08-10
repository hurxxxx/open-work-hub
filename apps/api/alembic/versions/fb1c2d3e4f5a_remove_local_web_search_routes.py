"""remove local web search route overrides

Revision ID: fb1c2d3e4f5a
Revises: f8b2d4e6a0c1
Create Date: 2026-07-13 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "fb1c2d3e4f5a"
down_revision: str | Sequence[str] | None = "f8b2d4e6a0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EXTERNAL_ONLY_WEB_WORKLOAD_IDS = (
    "web_search.answer",
    "research_trends.answer",
    "standards_monitor.answer",
    "ppt.research",
)


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    overrides = sa.Table("ai_model_route_overrides", metadata, autoload_with=bind)
    bind.execute(
        sa.delete(overrides).where(
            overrides.c.workload_id.in_(EXTERNAL_ONLY_WEB_WORKLOAD_IDS),
            overrides.c.route_mode == "local",
        )
    )


def downgrade() -> None:
    # A removed execution path cannot be restored safely. Existing external
    # overrides and historical audit/usage records remain untouched.
    pass
