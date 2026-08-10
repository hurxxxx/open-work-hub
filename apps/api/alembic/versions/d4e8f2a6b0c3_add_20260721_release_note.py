"""add 2026-07-21 release note

Revision ID: d4e8f2a6b0c3
Revises: c3d7e9f1a5b2
Create Date: 2026-07-21 17:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "d4e8f2a6b0c3"
down_revision: str | Sequence[str] | None = "c3d7e9f1a5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RELEASE_NOTE_ID = "20260721-1700-4000-8000-000000000001"
RELEASE_KEY = "2026-07-21-01"


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
    published_at = datetime(2026, 7, 21, 17, 0, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 7월 21일 업데이트",
                "summary": (
                    "워크스페이스 검색과 식당 명세서 검수, 과거차 초안 협업을 개선하고 "
                    "뉴스·관리 화면과 업무 바로가기를 정리했습니다."
                ),
                "body": "\n".join(
                    [
                        "[검색] 챗봇 앱 표시 여부와 관계없이 워크스페이스 검색을 사용할 수 있으며, 현재 사용할 수 있는 자료 유형만 검색 조건으로 보여 줍니다.",
                        "[검색] 검색어와 직접 관련된 문장을 결과에 더 잘 보여 주고, 여러 검색 방식을 함께 활용해 관련도 높은 결과를 찾도록 개선했습니다.",
                        "[식당 명세서 OCR] 사진을 여러 번 나누어 추가하고 불필요한 사진만 결과에서 뺄 수 있습니다. 같은 이름의 서로 다른 파일도 빠뜨리지 않고 처리합니다.",
                        "[식당 명세서 OCR] 원래 공급가액과 품목 합계의 차이를 바로 확인할 수 있으며, 거래처별 품명·단위·원산지 교정과 혼동하기 쉬운 품목 판독을 개선했습니다.",
                        "[과거차 문제점] 초안을 저장하고 편집을 종료하면 다른 담당자가 이어서 편집할 수 있으며, 기준 리비전에서 바뀐 셀을 표시합니다.",
                        "[뉴스·리포트] 작업공간을 바꿔도 같은 뉴스와 내 스크랩을 이어서 볼 수 있도록 전사 공용 화면으로 정리했습니다. GeekNews 채널은 종료했습니다.",
                        "[관리자] 전사 앱, 워크스페이스 앱, 앱바 설정을 각각 관리하고, 모든 워크스페이스가 상속하는 앱 기본 노출을 설정할 수 있습니다.",
                        "[관리자] 배치 작업에서 ERP 인사 원본 스냅샷을 실행하고 수집된 행 수를 확인할 수 있습니다.",
                        "[PMS] 태스크 목록의 가로 스크롤바가 화면 밖으로 내려가 보이지 않던 현상을 개선했습니다.",
                        "[업무 사이트] 복지몰 바로가기를 추가하고 그룹웨어 바로가기 연결을 수정했습니다.",
                        "이미 접속 중인 사용자는 새로고침 후 확인해 주세요. 기존 뉴스 즐겨찾기 주소는 새 뉴스 화면으로 자동 이동합니다.",
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
