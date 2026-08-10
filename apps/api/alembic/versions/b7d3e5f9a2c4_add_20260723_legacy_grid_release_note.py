"""add 2026-07-23 legacy issue grid release note

Revision ID: b7d3e5f9a2c4
Revises: a8c1e4f7b2d5
Create Date: 2026-07-23 17:57:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "b7d3e5f9a2c4"
down_revision: str | Sequence[str] | None = "a8c1e4f7b2d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RELEASE_NOTE_ID = "20260723-1757-4000-8000-000000000002"
RELEASE_KEY = "2026-07-23-02"


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
    published_at = datetime(2026, 7, 23, 17, 57, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 7월 23일 추가 업데이트",
                "summary": (
                    "과거차 문제점 표의 행 높이 표시를 선택할 수 있게 하고, "
                    "열교환기와 쿨링모듈을 더 쉽게 구분할 수 있도록 개선했습니다."
                ),
                "body": "\n".join(
                    [
                        "[과거차 문제점] 표 위쪽의 ‘행 높이 자동 맞춤’을 해제하면 모든 행을 일정한 높이로 볼 수 있습니다. 설정은 표별로 유지됩니다.",
                        "[과거차 문제점] 열교환기와 쿨링모듈의 아이콘을 서로 다르게 표시해 메뉴에서 쉽게 구분할 수 있습니다.",
                        "이미 접속 중인 사용자는 새로고침 후 확인해 주세요.",
                    ]
                ),
                "status": "published",
                "published_at": published_at,
                "created_at": published_at,
                "updated_at": published_at,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("delete from release_notes where release_key = :release_key").bindparams(
            release_key=RELEASE_KEY
        )
    )
