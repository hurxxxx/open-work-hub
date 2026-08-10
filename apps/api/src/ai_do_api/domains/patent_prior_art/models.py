from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class PatentPriorArtJob(Base):
    """One private, durable prior-art run owned by a workspace user.

    The invention body is deliberately absent from this table. It is stored in
    the platform object store and addressed by ``input_storage_key``.
    """

    __tablename__ = "patent_prior_art_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_patent_prior_art_jobs_status",
        ),
        CheckConstraint(
            "stage IN ("
            "'queued','retry_waiting','loading_input','searching','ranking','assessing','reporting',"
            "'persisting','completed','failed','cancelled','cleanup_pending'"
            ")",
            name="ck_patent_prior_art_jobs_stage",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_patent_prior_art_jobs_progress",
        ),
        CheckConstraint(
            "dispatch_attempts >= 0",
            name="ck_patent_prior_art_jobs_dispatch_attempts",
        ),
        CheckConstraint(
            "execution_attempts >= 0",
            name="ck_patent_prior_art_jobs_execution_attempts",
        ),
        CheckConstraint(
            "automatic_restart_count >= 0 AND automatic_restart_count <= 1",
            name="ck_patent_prior_art_jobs_automatic_restart_count",
        ),
        UniqueConstraint(
            "tenant_scope_id",
            "owner_principal_id",
            "idempotency_key",
            name="uq_patent_prior_art_jobs_owner_idempotency",
        ),
        Index(
            "ix_patent_prior_art_jobs_tenant_owner_created",
            "tenant_scope_id",
            "owner_principal_id",
            "created_at",
        ),
        Index(
            "ix_patent_prior_art_jobs_tenant_status_created",
            "tenant_scope_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_patent_prior_art_jobs_dispatch_pending",
            "status",
            "dispatch_published_at",
            "updated_at",
        ),
        Index(
            "ix_patent_prior_art_jobs_recovery_due",
            "status",
            "stage",
            "next_attempt_at",
            "execution_lease_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Physical names make these app-owned opaque references rather than shared
    # schema dependencies. Core membership/entitlement checks validate both IDs.
    workspace_id: Mapped[str] = mapped_column(
        "tenant_scope_id", String(36), index=True, nullable=False
    )
    owner_id: Mapped[str] = mapped_column(
        "owner_principal_id", String(36), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="queued",
        server_default=text("'queued'"),
        index=True,
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(
        String(40), default="queued", server_default=text("'queued'"), nullable=False
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    jurisdictions: Mapped[list[str]] = mapped_column(JSONB_COMPAT, default=list, nullable=False)
    search_plan: Mapped[dict] = mapped_column(
        "plan_payload", JSONB_COMPAT, default=dict, nullable=False
    )
    input_storage_key: Mapped[str] = mapped_column(String(320), nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    dispatch_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    dispatch_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    execution_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    automatic_restart_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    execution_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    cleanup_failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    candidates = relationship(
        "PatentPriorArtCandidate",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    executed_queries = relationship(
        "PatentPriorArtExecutedQuery",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    artifacts = relationship(
        "PatentPriorArtArtifact",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PatentPriorArtCandidate(Base):
    __tablename__ = "patent_prior_art_candidates"
    __table_args__ = (
        CheckConstraint(
            "relevance_band IN ('high','medium','low','unrated')",
            name="ck_patent_prior_art_candidates_relevance_band",
        ),
        UniqueConstraint("job_id", "rank", name="uq_patent_prior_art_candidates_job_rank"),
        Index(
            "ix_patent_prior_art_candidates_tenant_job",
            "tenant_scope_id",
            "job_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column("tenant_scope_id", String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("patent_prior_art_jobs.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    publication_number: Mapped[str] = mapped_column(String(96), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    assignees: Mapped[list[str]] = mapped_column(JSONB_COMPAT, default=list, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False)
    filing_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publication_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification_codes: Mapped[list[str]] = mapped_column(
        JSONB_COMPAT, default=list, nullable=False
    )
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance_band: Mapped[str] = mapped_column(
        String(16),
        default="unrated",
        server_default=text("'unrated'"),
        nullable=False,
    )
    match_reasons: Mapped[list[str]] = mapped_column(JSONB_COMPAT, default=list, nullable=False)
    external_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class PatentPriorArtExecutedQuery(Base):
    __tablename__ = "patent_prior_art_executed_queries"
    __table_args__ = (
        UniqueConstraint("job_id", "position", name="uq_patent_prior_art_queries_job_position"),
        CheckConstraint(
            "status IN ('succeeded','failed')",
            name="ck_patent_prior_art_queries_status",
        ),
        Index(
            "ix_patent_prior_art_queries_tenant_job",
            "tenant_scope_id",
            "job_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column("tenant_scope_id", String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("patent_prior_art_jobs.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_label: Mapped[str] = mapped_column(String(160), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="succeeded", server_default=text("'succeeded'"), nullable=False
    )
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class PatentPriorArtArtifact(Base):
    __tablename__ = "patent_prior_art_artifacts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('result_json','report_markdown')",
            name="ck_patent_prior_art_artifacts_kind",
        ),
        UniqueConstraint("job_id", "kind", name="uq_patent_prior_art_artifacts_job_kind"),
        Index(
            "ix_patent_prior_art_artifacts_tenant_job",
            "tenant_scope_id",
            "job_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column("tenant_scope_id", String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("patent_prior_art_jobs.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(180), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(96), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
