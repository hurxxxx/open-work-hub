"""add 2026-07-23 release note

Revision ID: a8c1e4f7b2d5
Revises: fd7a9c1e4b20
Create Date: 2026-07-23 16:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "a8c1e4f7b2d5"
down_revision: str | Sequence[str] | None = "fd7a9c1e4b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RELEASE_NOTE_ID = "20260723-1645-4000-8000-000000000001"
RELEASE_KEY = "2026-07-23-01"


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
    published_at = datetime(2026, 7, 23, 16, 45, 0)
    op.bulk_insert(
        release_notes,
        [
            {
                "id": RELEASE_NOTE_ID,
                "release_key": RELEASE_KEY,
                "title": "2026년 7월 23일 업데이트",
                "summary": (
                    "과거차 문제점의 체크리스트·권한·엑셀 사용성을 개선하고, "
                    "파일 검색과 사내 Q&A 문서 인식, 식당 명세서 OCR 정확도를 "
                    "높였습니다."
                ),
                "body": "\n".join(
                    [
                        "[과거차 문제점] 마스터 CHECK에 작성된 점검방안·적용유무·반영/검토결과를 새 차종별 체크리스트의 기본값으로 가져옵니다.",
                        "[과거차 문제점] 플랫폼 관리자는 모듈별 직접 수정 권한자를 한 화면에서 지정할 수 있습니다. 권한자는 해당 모듈의 기존 데이터와 첨부파일을 리비전 증가 없이 수정하고, 다른 사용자가 작업 중인 초안을 경고 확인 후 취소할 수 있습니다.",
                        "[과거차 문제점] 엑셀 다운로드에 화면에 표시된 데이터 열의 순서와 표시/숨김 상태를 반영합니다.",
                        "[과거차 문제점] 여러 줄 텍스트에 맞춰 행 높이를 자동으로 조정합니다. 열 너비·순서·표시/숨김 상태는 시트 저장 때 모든 사용자의 공유 설정으로 저장되며 마지막 저장값이 적용됩니다.",
                        "[과거차 문제점] 열교환기 모듈을 추가해 마스터, 직접 수정 권한, 차종별 체크리스트와 엑셀 기능에서 관리할 수 있습니다.",
                        "[파일] 접근 권한이 있는 파일을 키워드·의미·하이브리드 검색으로 찾고, 일치한 내용을 확인한 뒤 바로 다운로드할 수 있습니다. 관련도가 낮은 결과도 줄였습니다.",
                        "[사내 관리팀 Q&A] 표가 포함되거나 스캔된 PDF 첨부를 더 정확히 읽고, 원본과 변환본이 겹치면 원본을 우선합니다. 교체된 첨부 내용도 다시 반영합니다.",
                        "[사내 관리팀 Q&A] 작업공간별 앱 설정과 관계없이 전사 공용 앱으로 동일하게 사용할 수 있습니다.",
                        "[식당 명세서 OCR] 같은 거래처에서 교정한 품명·원산지·단위를 이후 명세서의 유사한 OCR 표기에도 자동 반영하고, 원산지 약어와 단위 표기를 정리합니다.",
                        "[식당 명세서 OCR] 문서 상단의 불필요한 합계금액 입력란을 숨겼습니다. 해당 값은 합계 검증과 엑셀 결과에는 그대로 유지됩니다.",
                        "[문서 번역·요약] 원문에 없는 목적이나 결론을 덧붙이지 않고 수치와 고유명사를 더 충실하게 반영하도록 개선했습니다.",
                        "[홈] 현재 작업공간에서 사용하지 않는 회의·PMS·문서·플래너 위젯과 바로가기를 숨겨 불필요한 권한 오류를 줄였습니다.",
                        "[관리자] LLM과 이미지 생성 제공자·모델, 웹 검색과 이미지 생성 옵션을 관리 화면에서 설정하고 실행 준비 상태를 확인할 수 있습니다.",
                        "[관리자] 사용자를 로그인 차단하면 기존 로그인 세션도 종료되며, 워크스페이스 영구 삭제 메뉴를 제거해 실수로 데이터를 삭제할 위험을 줄였습니다.",
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
