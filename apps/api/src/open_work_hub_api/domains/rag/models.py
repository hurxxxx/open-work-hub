from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive

JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class RagSyncJob(Base):
    __tablename__ = "rag_sync_jobs"
    __table_args__ = (
        CheckConstraint(
            "lane IN ('realtime','backfill')",
            name="ck_rag_sync_jobs_lane",
        ),
        CheckConstraint(
            "operation IN ('upsert','delete','visibility_update')",
            name="ck_rag_sync_jobs_operation",
        ),
        CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_rag_sync_jobs_status",
        ),
        CheckConstraint(
            "scope_kind IN ('company')",
            name="ck_rag_sync_jobs_scope_kind",
        ),
        CheckConstraint(
            "desired_state IS NULL OR desired_state IN ('active','deleted')",
            name="ck_rag_sync_jobs_desired_state",
        ),
        Index(
            "ix_rag_sync_jobs_lane_status_retry",
            "scope_kind",
            "lane",
            "status",
            "next_retry_at",
        ),
        Index(
            "ix_rag_sync_jobs_resource_status",
            "resource_type",
            "resource_id",
            "status",
        ),
        Index(
            "ix_rag_sync_jobs_lane_status_created",
            "scope_kind",
            "lane",
            "status",
            "created_at",
        ),
        Index(
            "ix_rag_sync_jobs_lane_status_updated",
            "lane",
            "status",
            "updated_at",
        ),
        Index(
            "uq_rag_sync_jobs_pending_company_resource_lane",
            "scope_kind",
            "lane",
            "resource_type",
            "resource_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND projection_version IS NULL"),
            sqlite_where=text("status = 'pending' AND projection_version IS NULL"),
        ),
        Index(
            "uq_rag_sync_jobs_pending_versioned_resource_lane",
            "lane",
            "resource_type",
            "resource_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND projection_version IS NOT NULL"),
            sqlite_where=text("status = 'pending' AND projection_version IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="company",
        server_default=text("'company'"),
        index=True,
    )
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    projection_event_sequence: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("retrieval_projection_events.event_sequence", ondelete="RESTRICT"),
        nullable=True,
    )
    projection_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    desired_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    lane: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="realtime",
        server_default=text("'realtime'"),
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="upsert",
        server_default=text("'upsert'"),
    )
    content_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visibility_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_context: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        index=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class RagVisibilityRecomputeJob(Base):
    __tablename__ = "rag_visibility_recompute_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_rag_visibility_recompute_jobs_status",
        ),
        Index(
            "ix_rag_visibility_recompute_jobs_status_retry",
            "status",
            "next_retry_at",
        ),
        Index(
            "ix_rag_visibility_recompute_jobs_scope_status",
            "scope_type",
            "scope_id",
            "status",
        ),
        Index(
            "ix_rag_visibility_jobs_status_updated",
            "status",
            "updated_at",
        ),
        Index(
            "uq_rag_visibility_recompute_jobs_pending_scope",
            "scope_type",
            "scope_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trace_context: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    cursor: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        index=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
