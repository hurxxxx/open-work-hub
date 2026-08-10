from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ai_do_api.core.db import Base

# Postgres 는 JSONB, 테스트(sqlite)는 JSON 으로 폴백.
JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MealInvoiceOcrState(Base):
    """워크스페이스별 공유 학습/카탈로그 상태(교정·사전·기준 카탈로그).

    워크스페이스당 한 행. 갱신은 이 행을 트랜잭션 안에서 SELECT ... FOR UPDATE 로 잠그고
    read-modify-write 하므로, 다중 API 워커에서도 lost-update 없이 원자적으로 반영된다.
    (크롭 이미지는 해시 기반 불변 표시용 blob 이라 여기 두지 않고 오브젝트 저장소에 둔다.)
    """

    __tablename__ = "meal_invoice_ocr_state"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_meal_invoice_ocr_state_workspace"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 확인한 원본→교정 쌍 목록(학습 few-shot 원천). [{id,거래처,거래일,원본{},교정{},created_at,image_ref}]
    corrections_json: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    # 기준 카탈로그(영양사 대장). {품목: {단위,단위들,단위카운트,단가,원산지,count}}
    catalog_json: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    # 카탈로그 단위 목록(빈도 내림차순).
    units_json: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    # 품명 사전(자동 매칭 후보 원천).
    vocab_json: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )
