"""add 2026-07-16 PMS release note

Revision ID: b1d3f5a7c9e2
Revises: a9c1e3f5b7d9
Create Date: 2026-07-16 13:15:00.000000
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1d3f5a7c9e2"
down_revision: Union[str, Sequence[str], None] = "a9c1e3f5b7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RELEASE_NOTE_ID = "20260716-1315-4000-8000-000000000001"
RELEASE_KEY = "2026-07-16-01"


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
    now = datetime(2026, 7, 16, 13, 15, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 7월 16일 PMS 업데이트",
                "summary": (
                    "PMS에서 태스크를 묶어 보는 방식과 완료일 관리, "
                    "스페이스 정리 흐름을 더 편하게 개선했습니다."
                ),
                "body": "\n".join(
                    [
                        "PMS 태스크 목록을 상태 또는 담당자별로 묶어 보거나, 그룹 없이 볼 수 있습니다.",
                        "선택한 보기 방식은 작업공간별로 저장되어 다음에 다시 열어도 유지됩니다.",
                        "데스크톱 목록과 테이블에서 완료일을 바로 수정하고, 모바일에서도 완료일을 확인할 수 있습니다.",
                        "우측 PMS 위젯에서 전체 PMS 화면으로 바로 이동할 수 있습니다.",
                        "스페이스 상단에서 리스트 순서와 폴더 배치를 바로 변경할 수 있습니다.",
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
