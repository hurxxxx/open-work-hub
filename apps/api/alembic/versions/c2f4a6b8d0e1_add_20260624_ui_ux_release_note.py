"""add 2026-06-24 ui ux release note

Revision ID: c2f4a6b8d0e1
Revises: b0c1d2e3f4a6
Create Date: 2026-06-24 18:30:00.000000
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f4a6b8d0e1"
down_revision: Union[str, Sequence[str], None] = "b0c1d2e3f4a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RELEASE_NOTE_ID = "20260624-1830-4000-8000-000000000001"
RELEASE_KEY = "2026-06-24-ui-ux"


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
    now = datetime(2026, 6, 24, 18, 30, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 6월 24일 UI/UX 개선 업데이트",
                "summary": (
                    "Open ALM의 주요 업무 화면, 앱 탐색, AI 도구 사용 흐름을 "
                    "더 찾기 쉽고 읽기 편하게 개선했습니다."
                ),
                "body": "\n".join(
                    [
                        "앱 런처와 업무 영역 구성을 정리해 필요한 앱을 더 쉽게 찾을 수 있도록 개선했습니다.",
                        "AI 도구들의 입력, 결과 확인, 출처 표시 흐름을 더 일관되게 다듬었습니다.",
                        "PPT 생성, 특허 분석, 검색형 AI 도구 화면에서 진행 상태와 결과를 더 보기 쉽게 정리했습니다.",
                        "관리자 화면의 사용량, 감사 로그, 배치 현황을 더 빠르게 훑어볼 수 있도록 가독성을 개선했습니다.",
                        "화면 전반의 글자 크기, 간격, 다크 모드 대비를 정리해 장시간 사용 시 읽기 편하도록 개선했습니다.",
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
