"""add 2026-07-07 follow-up release note

Revision ID: d5e6f7a8b9c1
Revises: c4e5f6a7b8d0
Create Date: 2026-07-07 12:45:00.000000
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c1"
down_revision: Union[str, Sequence[str], None] = "c4e5f6a7b8d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RELEASE_NOTE_ID = "20260707-1245-4000-8000-000000000001"
RELEASE_KEY = "2026-07-07-02-ui-ux"


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
    now = datetime(2026, 7, 7, 12, 45, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 7월 7일 추가 업데이트",
                "summary": (
                    "커뮤니티 채널 운영 방식과 사내 업무 사이트 접근 흐름을 "
                    "더 편하게 개선했습니다."
                ),
                "body": "\n".join(
                    [
                        "좌측 앱 바에서 자주 쓰는 사내 업무 사이트를 바로 열 수 있습니다.",
                        "Open ALM 그룹웨어를 새 창으로 빠르게 열 수 있습니다.",
                        "커뮤니티 채널을 읽기 전용으로 운영할 수 있습니다.",
                        "읽기 전용 채널에서는 글과 댓글을 등록하거나 수정할 수 없다는 안내가 표시됩니다.",
                        "채널 관리 화면에서 읽기 전용 여부를 설정할 수 있습니다.",
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
