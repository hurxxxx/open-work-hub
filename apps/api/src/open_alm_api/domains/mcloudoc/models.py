from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class McloudocSource(Base):
    """A disabled-by-default binding between one source and one Files corpus."""

    __tablename__ = "mcloudoc_sources"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('workspace','company')",
            name="ck_mcloudoc_sources_scope_type",
        ),
        UniqueConstraint(
            "scope_type",
            "scope_id",
            "name",
            name="uq_mcloudoc_sources_scope_name",
        ),
        UniqueConstraint(
            "corpus_id",
            name="uq_mcloudoc_sources_corpus",
        ),
        Index("ix_mcloudoc_sources_scope", "scope_type", "scope_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(36), nullable=False)
    corpus_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("file_manager_corpora.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ingest_owner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True,
    )
    current_continuation: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class McloudocIngestRun(Base):
    """One serialized incremental delivery or snapshot delivery."""

    __tablename__ = "mcloudoc_ingest_runs"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('incremental','snapshot')",
            name="ck_mcloudoc_ingest_runs_mode",
        ),
        CheckConstraint(
            "status IN ('running','completed','failed')",
            name="ck_mcloudoc_ingest_runs_status",
        ),
        CheckConstraint(
            "received_count >= 0 AND upserted_count >= 0 AND deleted_count >= 0 "
            "AND unchanged_count >= 0 AND quarantined_count >= 0 AND failed_count >= 0",
            name="ck_mcloudoc_ingest_runs_counts_nonnegative",
        ),
        UniqueConstraint(
            "source_id",
            "delivery_id_sha256",
            name="uq_mcloudoc_ingest_runs_source_delivery",
        ),
        Index("ix_mcloudoc_ingest_runs_source_status", "source_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mcloudoc_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    delivery_id: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_id_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        default="running",
        server_default=text("'running'"),
        nullable=False,
    )
    continuation_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    continuation_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_complete: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    received_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    upserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quarantined_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list[dict]] = mapped_column(JSONB_COMPAT, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class McloudocDocument(Base):
    """Stable upstream identity mapped to at most one stable Files resource."""

    __tablename__ = "mcloudoc_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','deleted','quarantined')",
            name="ck_mcloudoc_documents_status",
        ),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_mcloudoc_documents_size_nonnegative",
        ),
        UniqueConstraint(
            "source_id",
            "external_id_sha256",
            name="uq_mcloudoc_documents_source_external_id",
        ),
        Index("ix_mcloudoc_documents_source_status", "source_id", "status"),
        UniqueConstraint(
            "file_id",
            name="uq_mcloudoc_documents_file",
        ),
        Index("ix_mcloudoc_documents_last_seen_run", "source_id", "last_seen_run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mcloudoc_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_id_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("file_manager_files.id", ondelete="RESTRICT"),
        nullable=True,
    )
    opaque_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    opaque_checksum: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    quarantine_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    quarantine_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    author: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    department: Mapped[str | None] = mapped_column(String(512), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    raw_metadata: Mapped[dict] = mapped_column(JSONB_COMPAT, default=dict, nullable=False)
    raw_acl: Mapped[dict | list | None] = mapped_column(JSONB_COMPAT, nullable=True)
    resolved_grants: Mapped[list[dict]] = mapped_column(JSONB_COMPAT, default=list, nullable=False)
    last_delivery_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_delivery_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mcloudoc_ingest_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
