"""add 2026-07-07 release note

Revision ID: f0a1b2c3d4e6
Revises: c9e1f2a3b4d5
Create Date: 2026-07-07 12:10:00.000000
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0a1b2c3d4e6"
down_revision: Union[str, Sequence[str], None] = "c9e1f2a3b4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RELEASE_NOTE_ID = "20260707-1210-4000-8000-000000000001"
RELEASE_KEY = "2026-07-07-ui-ux"


def upgrade() -> None:
    release_notes = sa.table(
        "release_notes",
        sa.column("id", sa.String()),
        sa.column("release_key", sa.String()),
        sa.column("title", sa.String()),
        sa.column("summary", sa.String()),
        sa.column("body", sa.Text()),
        sa.column("status", sa.String()),
        sa.column("published_at", sa.DateTime()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    now = datetime(2026, 7, 7, 12, 10, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 7월 7일 업데이트",
                "summary": (
                    "PMS 태스크와 캘린더, 과거차 문제점, PPT 생성 화면의 "
                    "사용 흐름을 더 편하게 개선했습니다."
                ),
                "body": "\n".join(
                    [
                        "PMS에서 새 태스크를 만들 때 상위 태스크를 함께 선택할 수 있습니다.",
                        "우측 위젯에서 새 태스크를 만들 때도 상위 태스크를 선택할 수 있습니다.",
                        "태스크 완료일을 화면에서 직접 입력하고 수정할 수 있습니다.",
                        "PMS 캘린더에서 태스크와 공휴일을 더 안정적으로 확인하고 연도를 이동할 수 있습니다.",
                        "과거차 문제점의 취소된 임시 수정본은 목록과 비교 선택지에서 보이지 않도록 정리했습니다.",
                        "과거차 문제점의 수정본 비교, 결재 상태, 피드백 표시를 더 읽기 쉽게 개선했습니다.",
                        "세미나와 출장 보고서 PPT 생성 결과에서 표와 일정 영역의 배치를 더 자연스럽게 다듬었습니다.",
                        "관리자 사용량 화면의 지표 설명과 차트 툴팁을 더 이해하기 쉽게 개선했습니다.",
                        "뉴스 저장과 DM 사용자 검색 진입 흐름을 개선했습니다.",
                        "이미 접속 중인 사용자는 새로고침 후 확인해 주세요.",
                    ]
                ),
                "status": "published",
                "published_at": now,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("delete from release_notes where release_key = :release_key").bindparams(
            release_key=RELEASE_KEY
        )
    )
