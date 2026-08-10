"""add 2026-07-01 ui ux release note

Revision ID: d3e4f5a6b7c8
Revises: c1d2e3f4a5c8
Create Date: 2026-07-01 11:30:00.000000
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RELEASE_NOTE_ID = "20260701-1130-4000-8000-000000000001"
RELEASE_KEY = "2026-07-01-ui-ux"


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
    now = datetime(2026, 7, 1, 11, 30, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 7월 1일 우측 dock 업데이트",
                "summary": (
                    "우측 개인 dock에서 Todo, 메모, PMS, Today를 더 빠르게 "
                    "확인하고 오갈 수 있도록 개선했습니다."
                ),
                "body": "\n".join(
                    [
                        "우측 dock에서 Todo, 메모, PMS, Today 위젯을 바로 열 수 있습니다.",
                        "Todo와 메모를 업무 화면을 벗어나지 않고 빠르게 확인하고 정리할 수 있습니다.",
                        "PMS 위젯에서 내게 배정된 태스크를 더 쉽게 확인할 수 있습니다.",
                        "Today 위젯에서 오늘 남은 일정을 바로 훑어볼 수 있습니다.",
                        "dock 위젯을 닫았다 다시 열어도 보던 흐름을 자연스럽게 이어갈 수 있도록 다듬었습니다.",
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
