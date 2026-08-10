"""repair missing sysperf tables

Revision ID: e0a1b2c3d4f5
Revises: d9f0a1b2c3d4
Create Date: 2026-06-22 00:00:00.000000

Some dev databases were stamped at head before the system-performance
tables from b7d3f1a9c5e2 existed physically. This migration is intentionally
idempotent: fresh databases already have these tables, while drifted local
databases get the missing schema materialized.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from ai_do_api.core.db import Base
from ai_do_api.domains.dataviz import sys_perf_models as _sys_perf_models  # noqa: F401


revision: str = "e0a1b2c3d4f5"
down_revision: str | Sequence[str] | None = "d9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SYS_PERF_TABLE_NAMES = (
    "sysperf_standard_columns",
    "sysperf_refrigerant_master",
    "sysperf_refrigerant_props",
    "sysperf_refrigerant_state_points",
    "sysperf_item_keywords",
    "sysperf_car_models",
    "sysperf_parts_catalog",
    "sysperf_parts_spec",
    "sysperf_file_master",
    "sysperf_test_master",
    "sysperf_sheet_header",
    "sysperf_test_info",
    "sysperf_column_mapping",
    "sysperf_system_config",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in SYS_PERF_TABLE_NAMES:
        table = Base.metadata.tables[table_name]
        table.create(bind, checkfirst=True)
        for index in table.indexes:
            index.create(bind, checkfirst=True)


def downgrade() -> None:
    # Repair-only migration. The canonical sysperf schema still belongs to
    # b7d3f1a9c5e2, so downgrading this repair step must not drop its tables.
    pass
