from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Boolean,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")
ARTIFACT_TYPES = ("report", "analysis")
ARTIFACT_STATUSES = ("pending", "building", "completed", "failed")
ARTIFACT_VISIBILITIES = ("private", "workspace")
ARTIFACT_EXACTNESS = ("exact", "estimated", "semantic", "mixed", "unknown")
INDEX_GENERATION_STATUSES = ("staging", "active", "failed", "retired")
INDEX_VALIDATION_STATUSES = ("pending", "passed", "failed")


def _sql_in_clause(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ",".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


class AiArtifact(Base):
    __tablename__ = "ai_artifacts"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("artifact_type", ARTIFACT_TYPES),
            name="ck_ai_artifacts_type",
        ),
        CheckConstraint(
            _sql_in_clause("status", ARTIFACT_STATUSES),
            name="ck_ai_artifacts_status",
        ),
        CheckConstraint(
            _sql_in_clause("visibility", ARTIFACT_VISIBILITIES),
            name="ck_ai_artifacts_visibility",
        ),
        CheckConstraint(
            "(artifact_type = 'report' AND artifact_number LIKE 'AIR-%') OR "
            "(artifact_type = 'analysis' AND artifact_number LIKE 'AIA-%')",
            name="ck_ai_artifacts_number_prefix",
        ),
        CheckConstraint(
            "supersedes_artifact_id IS NULL OR supersedes_artifact_id <> id",
            name="ck_ai_artifacts_not_self_superseding",
        ),
        CheckConstraint(
            "owner_user_id IS NOT NULL OR visibility = 'workspace'",
            name="ck_ai_artifacts_owner_or_workspace_visibility",
        ),
        CheckConstraint(
            "(status <> 'completed' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL "
            "AND content_sha256 IS NOT NULL AND content_size_bytes IS NOT NULL "
            "AND (content_text IS NOT NULL OR payload_json IS NOT NULL))",
            name="ck_ai_artifacts_completion",
        ),
        Index(
            "ix_ai_artifacts_workspace_owner_created",
            "workspace_id",
            "owner_user_id",
            "created_at",
        ),
        Index(
            "ix_ai_artifacts_workspace_type_created",
            "workspace_id",
            "artifact_type",
            "created_at",
        ),
        Index("ix_ai_artifacts_graph_run", "graph_run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    graph_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_graph_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_turn_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("conversation_turns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supersedes_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_artifacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    app_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB_COMPAT,
        nullable=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visibility: Mapped[str] = mapped_column(
        String(24),
        default="private",
        server_default=text("'private'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        default="building",
        server_default=text("'building'"),
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    sources: Mapped[list["AiArtifactSource"]] = relationship(
        back_populates="artifact",
        cascade="all, delete-orphan",
        order_by="AiArtifactSource.ordinal",
    )
    queries: Mapped[list["AiArtifactQuery"]] = relationship(
        back_populates="artifact",
        cascade="all, delete-orphan",
        order_by="AiArtifactQuery.ordinal",
    )
    index_generations: Mapped[list["AiArtifactIndexGeneration"]] = relationship(
        back_populates="artifact",
        cascade="all, delete-orphan",
        order_by="AiArtifactIndexGeneration.ordinal",
    )


class AiArtifactSource(Base):
    __tablename__ = "ai_artifact_sources"
    __table_args__ = (
        UniqueConstraint("artifact_id", "ordinal", name="uq_ai_artifact_sources_ordinal"),
        UniqueConstraint(
            "artifact_id",
            "source_kind",
            "source_ref",
            "source_version",
            name="uq_ai_artifact_sources_identity",
        ),
        CheckConstraint("ordinal >= 0", name="ck_ai_artifact_sources_ordinal"),
        CheckConstraint(
            "row_count IS NULL OR row_count >= 0",
            name="ck_ai_artifact_sources_row_count",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("ai_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    locator_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grid_columns_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB_COMPAT,
        nullable=True,
    )
    grid_rows_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB_COMPAT,
        nullable=True,
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    artifact: Mapped[AiArtifact] = relationship(back_populates="sources")


class AiArtifactQuery(Base):
    __tablename__ = "ai_artifact_queries"
    __table_args__ = (
        UniqueConstraint("artifact_id", "ordinal", name="uq_ai_artifact_queries_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_ai_artifact_queries_ordinal"),
        CheckConstraint(
            _sql_in_clause("exactness", ARTIFACT_EXACTNESS),
            name="ck_ai_artifact_queries_exactness",
        ),
        CheckConstraint(
            "row_count IS NULL OR row_count >= 0",
            name="ck_ai_artifact_queries_row_count",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_ai_artifact_queries_duration",
        ),
        CheckConstraint(
            "payload_bytes IS NULL OR payload_bytes >= 0",
            name="ck_ai_artifact_queries_payload_bytes",
        ),
        CheckConstraint(
            "execution_status IN ('not_executed','completed','failed')",
            name="ck_ai_artifact_queries_execution_status",
        ),
        CheckConstraint(
            "execution_status <> 'failed' OR error_code IS NOT NULL",
            name="ck_ai_artifact_queries_failed_error",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("ai_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    query_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    family_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    query_spec_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    statement_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    typed_params_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    execution_status: Mapped[str] = mapped_column(
        String(24),
        default="not_executed",
        server_default=text("'not_executed'"),
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_schema_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB_COMPAT,
        nullable=True,
    )
    result_rows_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB_COMPAT,
        nullable=True,
    )
    query_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    payload_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exactness: Mapped[str] = mapped_column(
        String(24),
        default="unknown",
        server_default=text("'unknown'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    artifact: Mapped[AiArtifact] = relationship(back_populates="queries")


class AiArtifactIndexGeneration(Base):
    __tablename__ = "ai_artifact_index_generations"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id",
            "ordinal",
            name="uq_ai_artifact_index_generations_ordinal",
        ),
        UniqueConstraint(
            "artifact_id",
            "index_generation_id",
            name="uq_ai_artifact_index_generations_identity",
        ),
        CheckConstraint("ordinal >= 0", name="ck_ai_artifact_index_generations_ordinal"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("ai_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    index_generation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_index_generations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    artifact: Mapped[AiArtifact] = relationship(back_populates="index_generations")


class AiIndexGeneration(Base):
    """Control-plane generation that can be validated before atomic cutover."""

    __tablename__ = "ai_index_generations"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("status", INDEX_GENERATION_STATUSES),
            name="ck_ai_index_generations_status",
        ),
        CheckConstraint(
            _sql_in_clause("validation_status", INDEX_VALIDATION_STATUSES),
            name="ck_ai_index_generations_validation_status",
        ),
        CheckConstraint(
            "schema_version >= 1 AND source_count >= 0 AND document_count >= 0 "
            "AND chunk_count >= 0",
            name="ck_ai_index_generations_counts",
        ),
        CheckConstraint(
            "embedding_dimensions IS NULL OR embedding_dimensions > 0",
            name="ck_ai_index_generations_dimensions",
        ),
        UniqueConstraint(
            "workspace_id",
            "app_id",
            "backend",
            "source_namespace",
            "generation_key",
            name="uq_ai_index_generations_identity",
        ),
        Index(
            "ix_ai_index_generations_workspace_app_status",
            "workspace_id",
            "app_id",
            "status",
        ),
        Index(
            "ix_ai_index_generations_namespace_created",
            "source_namespace",
            "created_at",
        ),
        Index(
            "uq_ai_index_generations_active_scope",
            "workspace_id",
            "app_id",
            "backend",
            "source_namespace",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    app_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    generation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="staging",
        server_default=text("'staging'"),
        nullable=False,
    )
    backend: Mapped[str] = mapped_column(String(64), nullable=False)
    source_namespace: Mapped[str] = mapped_column(String(256), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    embedding_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    document_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    corpus_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cutover_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
