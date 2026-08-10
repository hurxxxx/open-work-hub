"""add consolidated 2026-07-20 release note

Revision ID: f7a9b1c3d5e8
Revises: e5f7a9b1c3d6
Create Date: 2026-07-20 00:00:00.000000
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a9b1c3d5e8"
down_revision: Union[str, Sequence[str], None] = "e5f7a9b1c3d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RELEASE_NOTE_ID = "20260720-0000-4000-8000-000000000001"
RELEASE_KEY = "2026-07-20-01"
PRIOR_RELEASE_KEY = "2026-07-16-01"


def _set_prior_release_status(status: str) -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            update release_notes
            set status = :status
            where release_key = :release_key
            """
        ).bindparams(status=status, release_key=PRIOR_RELEASE_KEY)
    )
    if result.rowcount != 1:
        raise RuntimeError(
            f"expected exactly one release note for {PRIOR_RELEASE_KEY}, found {result.rowcount}"
        )


def upgrade() -> None:
    _set_prior_release_status("archived")
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
    published_at = datetime(2026, 7, 20, 0, 0, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 7월 20일 업데이트",
                "summary": (
                    "PMS 스페이스의 업무 보기와 리스트 정리 흐름을 개선하고, "
                    "과거차 문제점·플래너·커뮤니티·개인 위젯의 주요 변경사항을 "
                    "함께 안내합니다."
                ),
                "body": "\n".join(
                    [
                        "PMS 태스크 목록을 상태·담당자별 또는 그룹 없이 보고, 완료 항목 표시와 여러 상태 필터를 함께 사용할 수 있습니다.",
                        "PMS 태스크를 수동 순서, 시작일, 마감일, 등록일, 완료일 기준으로 정렬하고 오름차순과 내림차순을 선택할 수 있습니다.",
                        "선택한 그룹 방식은 작업공간별로 유지되며, 목록과 테이블에서 완료일을 바로 수정하고 모바일에서도 확인할 수 있습니다.",
                        "PMS 위젯에서 여러 작업공간의 담당 태스크를 함께 보고 전체 PMS 화면으로 이동할 수 있으며, 스페이스 상단에서 리스트 순서와 폴더 배치를 변경할 수 있습니다.",
                        "PMS를 열면 접근 가능한 첫 번째 스페이스의 개요로 이동하고, 리스트·보드·캘린더·간트·테이블에서 현재 스페이스의 활성 리스트를 함께 확인할 수 있습니다.",
                        "스페이스의 리스트 탭은 상태별로 묶지 않고 사용자 지정 순서를 기본으로 보여 줍니다.",
                        "완료된 PMS 리스트를 보관하면 태스크와 원래 폴더 위치가 유지되며, 보관 중에는 읽기 전용으로 확인하고 필요할 때 복원할 수 있습니다.",
                        "과거차 문제점의 데이터셋과 체크리스트를 읽기 쉬운 Excel로 내보내고, 데이터만 또는 첨부파일·파일명을 포함한 형식을 선택할 수 있습니다.",
                        "과거차 문제점의 첨부파일 추가·삭제를 다른 편집 내용과 함께 저장하고, 체크리스트가 없는 차종은 관리자가 영구 삭제할 수 있습니다.",
                        "아이두 챗봇 앱의 표시 여부와 관계없이 과거차 문제점의 AI 분석은 계속 사용할 수 있습니다.",
                        "플래너는 고정 개인 도구로, 커뮤니티는 전사 공용 앱으로 정리해 작업공간을 바꿔도 이어서 사용할 수 있습니다.",
                        "DM과 오늘 일정 위젯을 작업공간과 관계없이 개인 기준으로 사용할 수 있고, 캘린더에서 접근 가능한 작업공간의 회의와 담당 PMS 일정을 함께 볼 수 있습니다.",
                        "특허 비용 요약에서 공동 청구 금액과 환율 기준일을 더 정확하게 판독하도록 개선했습니다.",
                        "식당 전표 재판독 처리와 PPT 생성 결과 변환의 안정성을 개선했습니다.",
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
    _set_prior_release_status("published")
