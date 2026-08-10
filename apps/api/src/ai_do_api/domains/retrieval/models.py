from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")
BIGINT_IDENTITY_COMPAT = BigInteger().with_variant(Integer(), "sqlite")


class RetrievalPartitionCandidateScope(StrEnum):
    COMPANY = "company"
    WORKSPACE = "workspace"
    PERSONAL = "personal"


class RetrievalPartitionState(StrEnum):
    ACTIVE = "active"
    TRANSITIONING = "transitioning"
    RETIRED = "retired"


class RetrievalProjectionChangeKind(StrEnum):
    CONTENT = "content"
    VISIBILITY = "visibility"
    DELETE = "delete"
    REPAIR = "repair"


class RetrievalProjectionDesiredState(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class RetrievalProjectionBackend(StrEnum):
    OPENSEARCH = "opensearch"
    QDRANT = "qdrant"


class RetrievalProjectionGenerationState(StrEnum):
    PREPARING = "preparing"
    BASELINING = "baselining"
    REPLAYING = "replaying"
    VALIDATING = "validating"
    READY = "ready"
    ACTIVATING = "activating"
    ACTIVE = "active"
    ROLLBACK = "rollback"
    COMPENSATION_REQUIRED = "compensation_required"
    FAILED = "failed"
    RETIRED = "retired"


class RetrievalProjectionValidationState(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class RetrievalPartition(Base):
    __tablename__ = "retrieval_partitions"
    __table_args__ = (
        CheckConstraint(
            "candidate_scope_kind IN ('company','workspace','personal')",
            name="ck_retrieval_partitions_candidate_scope_kind",
        ),
        CheckConstraint(
            "state IN ('active','transitioning','retired')",
            name="ck_retrieval_partitions_state",
        ),
        CheckConstraint(
            "metadata_version >= 1",
            name="ck_retrieval_partitions_metadata_version",
        ),
        CheckConstraint(
            "(candidate_scope_kind = 'company' "
            "AND candidate_workspace_id IS NULL AND candidate_user_id IS NULL) "
            "OR (candidate_scope_kind = 'workspace' "
            "AND candidate_workspace_id IS NOT NULL AND candidate_user_id IS NULL) "
            "OR (candidate_scope_kind = 'personal' "
            "AND candidate_workspace_id IS NULL AND candidate_user_id IS NOT NULL)",
            name="ck_retrieval_partitions_candidate_target",
        ),
        CheckConstraint(
            "state <> 'retired' OR is_default_ingest IS FALSE",
            name="ck_retrieval_partitions_retired_not_default",
        ),
        Index(
            "ix_retrieval_partitions_namespace_state",
            "source_namespace",
            "state",
        ),
        Index(
            "ix_retrieval_partitions_candidate_workspace",
            "candidate_scope_kind",
            "candidate_workspace_id",
            "state",
        ),
        Index(
            "ix_retrieval_partitions_candidate_user",
            "candidate_scope_kind",
            "candidate_user_id",
            "state",
        ),
        Index(
            "uq_retrieval_partitions_default_managed_workspace",
            "source_namespace",
            "managed_workspace_id",
            unique=True,
            postgresql_where=text(
                "is_default_ingest IS TRUE AND state <> 'retired' "
                "AND managed_workspace_id IS NOT NULL AND candidate_user_id IS NULL"
            ),
            sqlite_where=text(
                "is_default_ingest = 1 AND state <> 'retired' "
                "AND managed_workspace_id IS NOT NULL AND candidate_user_id IS NULL"
            ),
        ),
        Index(
            "uq_retrieval_partitions_default_company",
            "source_namespace",
            unique=True,
            postgresql_where=text(
                "is_default_ingest IS TRUE AND state <> 'retired' "
                "AND managed_workspace_id IS NULL "
                "AND candidate_scope_kind = 'company'"
            ),
            sqlite_where=text(
                "is_default_ingest = 1 AND state <> 'retired' "
                "AND managed_workspace_id IS NULL "
                "AND candidate_scope_kind = 'company'"
            ),
        ),
        Index(
            "uq_retrieval_partitions_default_personal",
            "source_namespace",
            "candidate_user_id",
            unique=True,
            postgresql_where=text(
                "is_default_ingest IS TRUE AND state <> 'retired' "
                "AND candidate_scope_kind = 'personal' AND candidate_user_id IS NOT NULL"
            ),
            sqlite_where=text(
                "is_default_ingest = 1 AND state <> 'retired' "
                "AND candidate_scope_kind = 'personal' AND candidate_user_id IS NOT NULL"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    source_namespace: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    managed_workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    candidate_scope_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
    )
    candidate_workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    candidate_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RetrievalPartitionState.ACTIVE.value,
        server_default=text("'active'"),
        index=True,
    )
    metadata_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    is_default_ingest: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    @validates("id")
    def _keep_id_immutable(self, _key: str, value: str) -> str:
        current = getattr(self, "id", None)
        if current is not None and current != value:
            raise ValueError("retrieval partition id is immutable")
        return value


class RetrievalProjectionHead(Base):
    __tablename__ = "retrieval_projection_heads"
    __table_args__ = (
        CheckConstraint(
            "projection_version >= 1",
            name="ck_retrieval_projection_heads_version",
        ),
        CheckConstraint(
            "desired_state IN ('active','deleted')",
            name="ck_retrieval_projection_heads_desired_state",
        ),
        Index(
            "ix_retrieval_projection_heads_partition",
            "retrieval_partition_id",
        ),
    )

    resource_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    projection_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    retrieval_partition_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    desired_state: Mapped[str] = mapped_column(String(16), nullable=False)
    content_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visibility_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    diagnostic_workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )


class RetrievalProjectionEvent(Base):
    __tablename__ = "retrieval_projection_events"
    __table_args__ = (
        CheckConstraint(
            "projection_version >= 1",
            name="ck_retrieval_projection_events_version",
        ),
        CheckConstraint(
            "change_kind IN ('content','visibility','delete','repair')",
            name="ck_retrieval_projection_events_change_kind",
        ),
        CheckConstraint(
            "desired_state IN ('active','deleted')",
            name="ck_retrieval_projection_events_desired_state",
        ),
        UniqueConstraint(
            "resource_type",
            "resource_id",
            "projection_version",
            name="uq_retrieval_projection_events_resource_version",
        ),
        Index(
            "ix_retrieval_projection_events_partition",
            "retrieval_partition_id",
        ),
    )

    event_sequence: Mapped[int] = mapped_column(
        BIGINT_IDENTITY_COMPAT,
        Identity(),
        primary_key=True,
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    projection_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    retrieval_partition_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    change_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    desired_state: Mapped[str] = mapped_column(String(16), nullable=False)
    content_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visibility_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    diagnostic_workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=True,
    )
    trace_context: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
    )


class RetrievalProjectionGeneration(Base):
    """PostgreSQL control-plane record for one physical backend generation."""

    __tablename__ = "retrieval_projection_generations"
    __table_args__ = (
        CheckConstraint(
            "backend IN ('opensearch','qdrant')",
            name="ck_retrieval_projection_generations_backend",
        ),
        CheckConstraint(
            "state IN ('preparing','baselining','replaying','validating','ready',"
            "'activating','active','rollback','compensation_required','failed','retired')",
            name="ck_retrieval_projection_generations_state",
        ),
        CheckConstraint(
            "validation_state IN ('pending','passed','failed')",
            name="ck_retrieval_projection_generations_validation_state",
        ),
        CheckConstraint(
            "schema_version >= 1",
            name="ck_retrieval_projection_generations_schema_version",
        ),
        CheckConstraint(
            "baseline_event_sequence >= 0 AND replay_event_sequence >= baseline_event_sequence",
            name="ck_retrieval_projection_generations_watermark",
        ),
        UniqueConstraint(
            "backend",
            "generation_key",
            name="uq_retrieval_projection_generations_backend_key",
        ),
        UniqueConstraint(
            "backend",
            "physical_name",
            name="uq_retrieval_projection_generations_backend_physical",
        ),
        Index(
            "uq_retrieval_projection_generations_active_backend",
            "backend",
            unique=True,
            postgresql_where=text("state = 'active'"),
            sqlite_where=text("state = 'active'"),
        ),
        Index(
            "ix_retrieval_projection_generations_backend_state",
            "backend",
            "state",
        ),
    )

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    backend: Mapped[str] = mapped_column(String(16), nullable=False)
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    physical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RetrievalProjectionGenerationState.PREPARING.value,
        server_default=text("'preparing'"),
    )
    baseline_event_sequence: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    replay_event_sequence: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    validation_state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RetrievalProjectionValidationState.PENDING.value,
        server_default=text("'pending'"),
    )
    validation_details: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    expected_projection_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    previous_generation_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("retrieval_projection_generations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rollback_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )


class RetrievalProjectionGenerationAttestation(Base):
    """Append-only evidence attached after an active generation receives data."""

    __tablename__ = "retrieval_projection_generation_attestations"
    __table_args__ = (
        CheckConstraint(
            "attestation_kind = 'quality'",
            name="ck_retrieval_projection_generation_attestations_kind",
        ),
        CheckConstraint(
            "source_files_event_watermark >= 0 AND source_resource_count > 0",
            name="ck_retrieval_projection_generation_attestations_source",
        ),
        UniqueConstraint(
            "generation_key",
            "source_files_event_watermark",
            name="uq_retrieval_projection_generation_attestations_watermark",
        ),
        Index(
            "ix_retrieval_gen_attestations_generation_created",
            "generation_key",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    opensearch_generation_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("retrieval_projection_generations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qdrant_generation_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("retrieval_projection_generations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attestation_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="quality",
        server_default=text("'quality'"),
    )
    source_files_event_watermark: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_resource_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quality_artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_corpus_id: Mapped[str] = mapped_column(String(255), nullable=False)
    quality_corpus_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_coverage: Mapped[list[str]] = mapped_column(JSONB_COMPAT, nullable=False)
    quality_details: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
    )


__all__ = [
    "RetrievalPartition",
    "RetrievalPartitionCandidateScope",
    "RetrievalPartitionState",
    "RetrievalProjectionChangeKind",
    "RetrievalProjectionBackend",
    "RetrievalProjectionDesiredState",
    "RetrievalProjectionEvent",
    "RetrievalProjectionGeneration",
    "RetrievalProjectionGenerationState",
    "RetrievalProjectionHead",
    "RetrievalProjectionValidationState",
]
