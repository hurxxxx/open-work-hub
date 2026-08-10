"""consolidate 2026-07-16 release note

Revision ID: d4f6a8b0c2e5
Revises: c2e4f6a8b0d3
Create Date: 2026-07-16 19:54:00.000000
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f6a8b0c2e5"
down_revision: Union[str, Sequence[str], None] = "c2e4f6a8b0d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RELEASE_KEY = "2026-07-16-01"

UPDATED_TITLE = "2026년 7월 16일 업데이트"
UPDATED_SUMMARY = (
    "PMS와 과거차 문제점의 주요 작업 흐름을 개선하고, 플래너와 커뮤니티, "
    "개인 위젯을 작업공간에 얽매이지 않게 정리했습니다."
)
UPDATED_BODY = "\n".join(
    [
        "PMS 태스크 목록을 상태·담당자별 또는 그룹 없이 보고, 완료 항목 표시와 여러 상태 필터를 함께 사용할 수 있습니다.",
        "PMS 태스크를 수동 순서, 시작일, 마감일, 등록일, 완료일 기준으로 정렬하고 오름차순과 내림차순을 선택할 수 있습니다.",
        "선택한 그룹 방식은 작업공간별로 유지되며, 목록과 테이블에서 완료일을 바로 수정하고 모바일에서도 확인할 수 있습니다.",
        "PMS 위젯에서 여러 작업공간의 담당 태스크를 함께 보고 전체 PMS 화면으로 이동할 수 있으며, 스페이스 상단에서 리스트 순서와 폴더 배치를 변경할 수 있습니다.",
        "과거차 문제점의 데이터셋과 체크리스트를 읽기 쉬운 Excel로 내보내고, 데이터만 또는 첨부파일·파일명을 포함한 형식을 선택할 수 있습니다.",
        "과거차 문제점의 첨부파일 추가·삭제를 다른 편집 내용과 함께 저장하고, 체크리스트가 없는 차종은 관리자가 영구 삭제할 수 있습니다.",
        "아이두 챗봇 앱의 표시 여부와 관계없이 과거차 문제점의 AI 분석은 계속 사용할 수 있습니다.",
        "플래너는 고정 개인 도구로, 커뮤니티는 전사 공용 앱으로 정리해 작업공간을 바꿔도 이어서 사용할 수 있습니다.",
        "DM과 오늘 일정 위젯을 작업공간과 관계없이 개인 기준으로 사용할 수 있고, 캘린더에서 접근 가능한 작업공간의 회의와 담당 PMS 일정을 함께 볼 수 있습니다.",
        "특허 비용 요약에서 공동 청구 금액과 환율 기준일을 더 정확하게 판독하도록 개선했습니다.",
        "식당 전표 재판독 처리와 PPT 생성 결과 변환의 안정성을 개선했습니다.",
        "이미 접속 중인 사용자는 새로고침 후 확인해 주세요.",
    ]
)
UPDATED_AT = datetime(2026, 7, 16, 19, 54, 0)

ORIGINAL_TITLE = "2026년 7월 16일 PMS 업데이트"
ORIGINAL_SUMMARY = (
    "PMS에서 태스크를 묶어 보는 방식과 완료일 관리, 스페이스 정리 흐름을 더 편하게 개선했습니다."
)
ORIGINAL_BODY = "\n".join(
    [
        "PMS 태스크 목록을 상태 또는 담당자별로 묶어 보거나, 그룹 없이 볼 수 있습니다.",
        "선택한 보기 방식은 작업공간별로 저장되어 다음에 다시 열어도 유지됩니다.",
        "데스크톱 목록과 테이블에서 완료일을 바로 수정하고, 모바일에서도 완료일을 확인할 수 있습니다.",
        "우측 PMS 위젯에서 전체 PMS 화면으로 바로 이동할 수 있습니다.",
        "스페이스 상단에서 리스트 순서와 폴더 배치를 바로 변경할 수 있습니다.",
        "이미 접속 중인 사용자는 새로고침 후 확인해 주세요.",
    ]
)
ORIGINAL_PUBLISHED_AT = datetime(2026, 7, 16, 13, 15, 0)


def _update_release_note(
    *,
    title: str,
    summary: str,
    body: str,
    published_at: datetime,
    updated_at: datetime,
) -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            update release_notes
            set title = :title,
                summary = :summary,
                body = :body,
                status = 'published',
                published_at = :published_at,
                updated_at = :updated_at
            where release_key = :release_key
            """
        ).bindparams(
            title=title,
            summary=summary,
            body=body,
            published_at=published_at,
            updated_at=updated_at,
            release_key=RELEASE_KEY,
        )
    )
    if result.rowcount != 1:
        raise RuntimeError(
            f"expected exactly one release note for {RELEASE_KEY}, found {result.rowcount}"
        )


def upgrade() -> None:
    _update_release_note(
        title=UPDATED_TITLE,
        summary=UPDATED_SUMMARY,
        body=UPDATED_BODY,
        published_at=UPDATED_AT,
        updated_at=UPDATED_AT,
    )


def downgrade() -> None:
    _update_release_note(
        title=ORIGINAL_TITLE,
        summary=ORIGINAL_SUMMARY,
        body=ORIGINAL_BODY,
        published_at=ORIGINAL_PUBLISHED_AT,
        updated_at=ORIGINAL_PUBLISHED_AT,
    )
