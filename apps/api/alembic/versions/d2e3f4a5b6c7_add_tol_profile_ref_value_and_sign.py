"""add ref_value and sign to tol profile

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b7
Create Date: 2026-06-01 00:00:00.000000

승인도 성능 기준값(시험공차) 프로필이 항목별로 "기준값 ± 공차폭"을 담도록
dataviz_perf_tol_profiles 에 ref_value(기준값)와 sign(부호 '±'|'+'|'-') 컬럼을
추가한다. 기존 tol_value 는 공차폭으로 그대로 둔다. 가산적 변경(additive)이다.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — 공유 dev DB 는 alembic stamp 가 서버 메인 라인에 있어 이 컬럼을
    # 손으로 먼저 추가했을 수 있다. 정식 적용 시 중복 추가 충돌을 피하기 위해 가드한다.
    op.execute(
        "ALTER TABLE dataviz_perf_tol_profiles "
        "ADD COLUMN IF NOT EXISTS ref_value double precision"
    )
    op.execute(
        "ALTER TABLE dataviz_perf_tol_profiles "
        "ADD COLUMN IF NOT EXISTS sign varchar(8) NOT NULL DEFAULT '±'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE dataviz_perf_tol_profiles DROP COLUMN IF EXISTS sign")
    op.execute("ALTER TABLE dataviz_perf_tol_profiles DROP COLUMN IF EXISTS ref_value")
