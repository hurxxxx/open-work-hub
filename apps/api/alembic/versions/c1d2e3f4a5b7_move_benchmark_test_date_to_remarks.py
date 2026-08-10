"""move benchmark test_date to remarks

Revision ID: c1d2e3f4a5b7
Revises: d8e9f0a1b2c3
Create Date: 2026-05-29 00:00:00.000000

Benchmark 행에서 test_date 컬럼에는 실제 평가일자가 아니라 "한온 벤치마킹 데이터
확보"처럼 비고성 텍스트가 들어가 있어, 해당 텍스트를 remarks 컬럼으로 이동하고
test_date는 비운다. remarks가 이미 채워져 있으면 덮어쓰지 않고 건너뛴다.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c1d2e3f4a5b7"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. remarks가 비어 있는 Benchmark 행에서만 test_date → remarks 로 옮긴다.
    op.execute(
        """
        UPDATE dataviz_perf_data
           SET remarks = test_date
         WHERE capacity = 'Benchmark'
           AND COALESCE(test_date, '') <> ''
           AND COALESCE(remarks, '') = ''
        """
    )
    # 2. Benchmark 행의 test_date 는 모두 비운다 (이미 remarks로 옮겼거나, 옮길
    #    수 없는 경우라도 평가일자 컬럼에 비고 텍스트가 남아 있으면 안 되므로
    #    일괄 클리어한다).
    op.execute(
        """
        UPDATE dataviz_perf_data
           SET test_date = ''
         WHERE capacity = 'Benchmark'
        """
    )


def downgrade() -> None:
    # 비가역적인 마이그레이션 — 원본 test_date 와 remarks 의 경계가 사라지므로
    # 자동 롤백은 제공하지 않는다. 필요 시 백업에서 복원할 것.
    pass
