"""add tol_lower to tol profile for asymmetric tolerance

Revision ID: a1f7c3e9d2b4
Revises: d2e3f4a5b6c7
Create Date: 2026-06-01 00:00:00.000000

편측공차(+100/-50)를 담기 위해 dataviz_perf_tol_profiles 에 tol_lower(하한 편차)
컬럼을 추가한다. sign='편측'일 때만 사용하고, tol_value 는 상한(+) 편차로 쓴다.
±/+/- 인 경우 tol_value 가 단일 공차폭이며 tol_lower 는 NULL 이다. 가산적 변경.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a1f7c3e9d2b4"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — 공유 dev DB 에 손으로 먼저 추가했을 수 있으므로 가드한다.
    op.execute(
        "ALTER TABLE dataviz_perf_tol_profiles "
        "ADD COLUMN IF NOT EXISTS tol_lower double precision"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE dataviz_perf_tol_profiles DROP COLUMN IF EXISTS tol_lower")
