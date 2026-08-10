"""consolidate 2026-07-07 release note

Revision ID: f6e7d8c9b0a1
Revises: d5e6f7a8b9c1
Create Date: 2026-07-07 13:50:00.000000
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6e7d8c9b0a1"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRIMARY_RELEASE_KEY = "2026-07-07-ui-ux"
FOLLOWUP_RELEASE_KEY = "2026-07-07-02-ui-ux"

PRIMARY_TITLE = "2026년 7월 7일 업데이트"
PRIMARY_SUMMARY = (
    "PMS, 캘린더, 커뮤니티, 관리자 콘솔, 사내 업무 사이트 접근 흐름을 "
    "더 편하게 개선했습니다."
)
PRIMARY_BODY = "\n".join(
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
        "좌측 앱 바에서 자주 쓰는 사내 업무 사이트를 바로 열 수 있습니다.",
        "두원공조 그룹웨어를 새 창으로 빠르게 열 수 있습니다.",
        "커뮤니티 채널을 읽기 전용으로 운영할 수 있습니다.",
        "읽기 전용 채널에서는 글과 댓글을 등록하거나 수정할 수 없다는 안내가 표시됩니다.",
        "채널 관리 화면에서 읽기 전용 여부를 설정할 수 있습니다.",
        "커뮤니티 글 목록은 검색어를 입력한 뒤 검색 버튼을 눌렀을 때 결과가 바뀝니다.",
        "관리자 콘솔의 자동 작업 화면에서 실행 상태와 주요 지표를 더 한눈에 확인할 수 있습니다.",
        "이미 접속 중인 사용자는 새로고침 후 확인해 주세요.",
    ]
)

ORIGINAL_PRIMARY_SUMMARY = (
    "PMS 태스크와 캘린더, 과거차 문제점, PPT 생성 화면의 "
    "사용 흐름을 더 편하게 개선했습니다."
)
ORIGINAL_PRIMARY_BODY = "\n".join(
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
)


def upgrade() -> None:
    now = datetime(2026, 7, 7, 13, 50, 0)
    op.execute(
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
            title=PRIMARY_TITLE,
            summary=PRIMARY_SUMMARY,
            body=PRIMARY_BODY,
            published_at=now,
            updated_at=now,
            release_key=PRIMARY_RELEASE_KEY,
        )
    )
    op.execute(
        sa.text(
            """
            update release_notes
            set status = 'archived',
                updated_at = :updated_at
            where release_key = :release_key
            """
        ).bindparams(updated_at=now, release_key=FOLLOWUP_RELEASE_KEY)
    )
    op.execute(
        sa.text(
            """
            delete from release_note_reads
            where release_note_id in (
                select id from release_notes where release_key = :release_key
            )
            """
        ).bindparams(release_key=PRIMARY_RELEASE_KEY)
    )


def downgrade() -> None:
    primary_published_at = datetime(2026, 7, 7, 12, 10, 0)
    followup_updated_at = datetime(2026, 7, 7, 12, 45, 0)
    op.execute(
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
            title=PRIMARY_TITLE,
            summary=ORIGINAL_PRIMARY_SUMMARY,
            body=ORIGINAL_PRIMARY_BODY,
            published_at=primary_published_at,
            updated_at=primary_published_at,
            release_key=PRIMARY_RELEASE_KEY,
        )
    )
    op.execute(
        sa.text(
            """
            update release_notes
            set status = 'published',
                updated_at = :updated_at
            where release_key = :release_key
            """
        ).bindparams(
            updated_at=followup_updated_at,
            release_key=FOLLOWUP_RELEASE_KEY,
        )
    )
