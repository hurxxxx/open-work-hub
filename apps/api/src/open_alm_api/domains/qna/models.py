from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive

JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class QnaDocument(Base):
    """A single entry in the admin-team Q&A corpus.

    ``kind`` distinguishes admin uploads from crawled groupware notices; both are
    indexed into RAG under the same ``qna_doc`` source kind so the assistant can
    answer over the combined corpus.
    """

    __tablename__ = "qna_documents"
    __table_args__ = (
        UniqueConstraint(
            "scope_kind", "kind", "external_id", name="uq_qna_doc_scope_kind_external"
        ),
        Index("ix_qna_documents_scope_kind_kind", "scope_kind", "kind"),
        Index("ix_qna_documents_workspace_kind", "workspace_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope_kind: Mapped[str] = mapped_column(
        String(16),
        default="company",
        server_default=text("'company'"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # 'upload' (admin file upload) or 'notice' (crawled groupware notice).
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Stable identity within (workspace, kind): filename for uploads, notice num for notices.
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(
        String(120), default="일반", server_default=text("'일반'"), nullable=False
    )
    author: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Free-form posted date string as surfaced by the groupware board.
    posted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    body_text: Mapped[str] = mapped_column(
        Text, default="", server_default=text("''"), nullable=False
    )
    attachments: Mapped[list | None] = mapped_column(JSONB_COMPAT, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    char_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    content_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    uploaded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    mime_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    rag_status: Mapped[str] = mapped_column(
        String(24), default="pending", server_default=text("'pending'"), nullable=False
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
