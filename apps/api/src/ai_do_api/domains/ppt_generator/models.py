from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_do_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PptJob(Base):
    """PPT 자동 생성 작업. Celery 워커가 LLM→pptx→미리보기 PNG→MinIO 파이프라인을 실행하고
    상태/산출물 키를 이 행에 갱신한다."""

    __tablename__ = "ppt_jobs"
    __table_args__ = (
        Index("ix_ppt_jobs_workspace_user_created", "workspace_id", "user_id", "created_at"),
        Index(
            "ix_ppt_jobs_workspace_user_deleted_created",
            "workspace_id",
            "user_id",
            "deleted_at",
            "created_at",
        ),
        Index("ix_ppt_jobs_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    # pending | running | completed | error
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 기본값은 카탈로그의 DEFAULT_FAMILY(doowon-house)과 일치시킴. 카탈로그에서 제외된 family 를
    # 기본값으로 두면 resolve_family 가 조용히 치환해 행 메타가 어긋나므로 항상 노출 family 로 둔다.
    family: Mapped[str] = mapped_column(String(40), default="doowon-house", nullable=False)
    aspect: Mapped[str] = mapped_column(String(8), default="A4", nullable=False)
    n_slides: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 생성 파라미터(language/tone/instructions/toggles 등) — 워커가 참조
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 입력 본문(주제 + 첨부 추출 텍스트)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 빌드된 슬라이드 spec — 챗봇 수정에서 재사용
    slides_spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    pptx_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # legacy: HTML 우선 미리보기 전환 후 미사용(항상 0). 컬럼은 마이그레이션 회피를
    # 위해 유지 — 추후 drop 마이그레이션으로 정리.
    preview_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)

    # 챗봇 수정(단계 3) 최신 턴 결과 — 워커가 비동기로 갱신, 프론트가 폴링
    #   {status: idle|processing|done|error, answer, intent, refreshed_slide_index, rev}
    chat_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, server_default=sa_text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        server_default=sa_text("now()"),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workspace = relationship("Workspace")
    user = relationship("User", foreign_keys=[user_id])


class PptTemplatePreviewImage(Base):
    """Uploaded preview image attached to a PPT template family."""

    __tablename__ = "ppt_template_preview_images"
    __table_args__ = (
        Index(
            "ix_ppt_template_preview_images_workspace_family_sort",
            "workspace_id",
            "family_id",
            "deleted_at",
            "sort_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    family_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    media_id: Mapped[str] = mapped_column(ForeignKey("media_files.id"), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workspace = relationship("Workspace")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])
    media = relationship("MediaFile")
