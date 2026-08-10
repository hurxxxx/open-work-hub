"""update 2026-07-23 legacy issue grid release note

Revision ID: c8e4f6a0b3d5
Revises: b7d3e5f9a2c4
Create Date: 2026-07-23 18:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "c8e4f6a0b3d5"
down_revision: str | Sequence[str] | None = "b7d3e5f9a2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RELEASE_KEY = "2026-07-23-02"
ORIGINAL_SUMMARY = (
    "과거차 문제점 표의 행 높이 표시를 선택할 수 있게 하고, "
    "열교환기와 쿨링모듈을 더 쉽게 구분할 수 있도록 개선했습니다."
)
ORIGINAL_BODY = "\n".join(
    [
        "[과거차 문제점] 표 위쪽의 ‘행 높이 자동 맞춤’을 해제하면 모든 행을 일정한 높이로 볼 수 있습니다. 설정은 표별로 유지됩니다.",
        "[과거차 문제점] 열교환기와 쿨링모듈의 아이콘을 서로 다르게 표시해 메뉴에서 쉽게 구분할 수 있습니다.",
        "이미 접속 중인 사용자는 새로고침 후 확인해 주세요.",
    ]
)
UPDATED_SUMMARY = (
    "과거차 문제점 표의 행 높이 표시를 선택하고, 열교환기 메뉴와 최초 입력 흐름을 개선했습니다."
)
UPDATED_BODY = "\n".join(
    [
        "[과거차 문제점] 표 위쪽의 ‘행 높이 자동 맞춤’을 해제하면 모든 행을 일정한 높이로 볼 수 있습니다. 설정은 표별로 유지됩니다.",
        "[과거차 문제점] 열교환기와 쿨링모듈의 아이콘을 서로 다르게 표시해 메뉴에서 쉽게 구분할 수 있습니다.",
        "[과거차 문제점] 새로 추가된 열교환기처럼 아직 리비전이 없는 모듈도 ‘수정 시작’으로 최초 데이터를 입력할 수 있습니다.",
        "이미 접속 중인 사용자는 새로고침 후 확인해 주세요.",
    ]
)


def _update_release_note(*, summary: str, body: str, updated_at: datetime) -> None:
    op.execute(
        sa.text(
            """
            update release_notes
            set summary = :summary, body = :body, updated_at = :updated_at
            where release_key = :release_key
            """
        ).bindparams(
            summary=summary,
            body=body,
            updated_at=updated_at,
            release_key=RELEASE_KEY,
        )
    )


def upgrade() -> None:
    _update_release_note(
        summary=UPDATED_SUMMARY,
        body=UPDATED_BODY,
        updated_at=datetime(2026, 7, 23, 18, 15, 0),
    )


def downgrade() -> None:
    _update_release_note(
        summary=ORIGINAL_SUMMARY,
        body=ORIGINAL_BODY,
        updated_at=datetime(2026, 7, 23, 17, 57, 0),
    )
