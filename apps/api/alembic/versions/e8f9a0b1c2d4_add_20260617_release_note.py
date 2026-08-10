"""add 2026-06-17 release note

Revision ID: e8f9a0b1c2d4
Revises: 9c8d7e6f5a4b
Create Date: 2026-06-17 01:30:00.000000
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f9a0b1c2d4"
down_revision: Union[str, Sequence[str], None] = "9c8d7e6f5a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RELEASE_NOTE_ID = "20260617-0130-4000-8000-000000000001"
RELEASE_KEY = "2026-06-17-01"


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
    now = datetime(2026, 6, 17, 1, 30, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 6월 17일 업데이트",
                "summary": "뉴스와 산업 리포트에서 AI 추천과 보관 흐름을 더 편하게 확인할 수 있습니다.",
                "body": "\n".join(
                    [
                        "📰 뉴스에서 최근 수집 기사 중 AI가 추천한 항목을 따로 확인할 수 있습니다.",
                        "뉴스와 산업 리포트에서 추천 항목과 내가 보관한 항목을 구분해 볼 수 있습니다.",
                        "산업 리포트에서 AI 추천 이유를 확인하고 필요한 자료를 더 빠르게 추릴 수 있습니다.",
                        "앱바 편집과 더보기 화면에서 앱을 찾고 고정하는 흐름을 개선했습니다.",
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
