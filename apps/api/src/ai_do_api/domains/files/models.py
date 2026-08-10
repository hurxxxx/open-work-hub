from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class FileManagerCorpus(Base):
    __tablename__ = "file_manager_corpora"
    __table_args__ = (
        CheckConstraint(
            "access_scope_kind IN ('workspace','company')",
            name="ck_file_manager_corpora_access_scope_kind",
        ),
        CheckConstraint(
            "metadata_version >= 1",
            name="ck_file_manager_corpora_metadata_version",
        ),
        CheckConstraint(
            "authorization_mode IN ('cohort','explicit_grants')",
            name="ck_file_manager_corpora_authorization_mode",
        ),
        CheckConstraint(
            "authorization_mode = 'cohort' OR source_managed = true",
            name="ck_file_manager_corpora_explicit_grants_source_managed",
        ),
        UniqueConstraint(
            "retrieval_partition_id",
            name="uq_file_manager_corpora_retrieval_partition_id",
        ),
        Index(
            "ix_file_manager_corpora_workspace_scope",
            "managed_workspace_id",
            "access_scope_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    managed_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    access_scope_kind: Mapped[str] = mapped_column(
        String(16),
        default="workspace",
        server_default=text("'workspace'"),
        nullable=False,
        index=True,
    )
    retrieval_partition_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    metadata_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )
    operator_managed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True,
    )
    source_managed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True,
    )
    authorization_mode: Mapped[str] = mapped_column(
        String(24),
        default="cohort",
        server_default=text("'cohort'"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    managed_workspace = relationship("Workspace", foreign_keys=[managed_workspace_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    folders: Mapped[list["FileManagerFolder"]] = relationship(back_populates="corpus")
    files: Mapped[list["FileManagerFile"]] = relationship(back_populates="corpus")
    bulk_ingest_runs: Mapped[list["FileManagerBulkIngestRun"]] = relationship(
        back_populates="corpus"
    )
    source_file_metadata: Mapped[list["FileManagerFileSourceMetadata"]] = relationship(
        back_populates="corpus"
    )


class FileManagerCorpusTransitionAudit(Base):
    __tablename__ = "file_manager_corpus_transition_audits"
    __table_args__ = (
        CheckConstraint(
            "from_access_scope_kind IN ('workspace','company')",
            name="ck_file_manager_corpus_transition_audits_from_scope",
        ),
        CheckConstraint(
            "to_access_scope_kind IN ('workspace','company')",
            name="ck_file_manager_corpus_transition_audits_to_scope",
        ),
        CheckConstraint(
            "from_metadata_version >= 1 AND to_metadata_version > from_metadata_version",
            name="ck_file_manager_corpus_transition_audits_versions",
        ),
        Index(
            "ix_file_corpus_transition_audits_corpus_created",
            "corpus_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("file_manager_corpora.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    from_access_scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    to_access_scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    from_managed_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    to_managed_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_metadata_version: Mapped[int] = mapped_column(Integer, nullable=False)
    to_metadata_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class FileManagerFolder(Base):
    __tablename__ = "file_manager_folders"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('private','workspace')",
            name="ck_file_manager_folders_visibility",
        ),
        Index("ix_file_manager_folders_workspace_parent", "workspace_id", "parent_id"),
        Index("ix_file_manager_folders_workspace_owner", "workspace_id", "owner_id"),
        Index("ix_file_manager_folders_workspace_visibility", "workspace_id", "visibility"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    corpus_id: Mapped[str | None] = mapped_column(
        ForeignKey("file_manager_corpora.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("file_manager_folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    visibility: Mapped[str] = mapped_column(String(24), default="private", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    workspace = relationship("Workspace")
    owner = relationship("User")
    corpus: Mapped["FileManagerCorpus | None"] = relationship(back_populates="folders")
    parent: Mapped["FileManagerFolder | None"] = relationship(
        remote_side="FileManagerFolder.id",
        back_populates="children",
    )
    children: Mapped[list["FileManagerFolder"]] = relationship(back_populates="parent")


class FileManagerFile(Base):
    __tablename__ = "file_manager_files"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('private','workspace')",
            name="ck_file_manager_files_visibility",
        ),
        CheckConstraint(
            "extraction_status IN ('pending','ready','unsupported','failed')",
            name="ck_file_manager_files_extraction_status",
        ),
        Index("ix_file_manager_files_workspace_folder", "workspace_id", "folder_id"),
        Index("ix_file_manager_files_workspace_owner", "workspace_id", "owner_id"),
        Index("ix_file_manager_files_workspace_visibility", "workspace_id", "visibility"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    corpus_id: Mapped[str | None] = mapped_column(
        ForeignKey("file_manager_corpora.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("file_manager_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(160), default="application/octet-stream", nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    visibility: Mapped[str] = mapped_column(String(24), default="private", nullable=False)
    extraction_status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False, index=True
    )
    extraction_content_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_text: Mapped[str | None] = mapped_column(Text, nullable=True, deferred=True)
    extraction_blocks: Mapped[list[dict]] = mapped_column(
        JSONB_COMPAT, default=list, nullable=False, deferred=True
    )
    extraction_metadata: Mapped[dict] = mapped_column(
        JSONB_COMPAT, default=dict, nullable=False, deferred=True
    )
    extraction_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    workspace = relationship("Workspace")
    folder = relationship("FileManagerFolder")
    owner = relationship("User")
    corpus: Mapped["FileManagerCorpus | None"] = relationship(back_populates="files")
    source_metadata: Mapped["FileManagerFileSourceMetadata | None"] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
    access_grants: Mapped[list["FileManagerFileAccessGrant"]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
    )


class FileManagerFileSourceMetadata(Base):
    """Private source identity and sync state for one externally managed file."""

    __tablename__ = "file_manager_file_source_metadata"
    __table_args__ = (
        UniqueConstraint(
            "corpus_id",
            "external_id_sha256",
            name="uq_file_manager_source_metadata_corpus_external",
        ),
        UniqueConstraint(
            "corpus_id",
            "source_kind",
            "source_id_sha256",
            name="uq_file_manager_source_metadata_corpus_source_identity",
        ),
        Index(
            "ix_file_manager_source_metadata_corpus_updated",
            "corpus_id",
            "source_updated_at",
        ),
    )

    file_id: Mapped[str] = mapped_column(
        ForeignKey("file_manager_files.id", ondelete="CASCADE"),
        primary_key=True,
    )
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("file_manager_corpora.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    external_id_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_id_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    author: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    department: Mapped[str | None] = mapped_column(String(512), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_metadata: Mapped[dict] = mapped_column(JSONB_COMPAT, default=dict, nullable=False)
    acl_resolved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    file: Mapped["FileManagerFile"] = relationship(back_populates="source_metadata")
    corpus: Mapped["FileManagerCorpus"] = relationship(back_populates="source_file_metadata")


class FileManagerFileAccessGrant(Base):
    """Resolved explicit grant; raw upstream ACL payloads never leave source metadata."""

    __tablename__ = "file_manager_file_access_grants"
    __table_args__ = (
        CheckConstraint(
            "grant_type IN ('company','workspace','user','org_unit','team')",
            name="ck_file_manager_file_access_grants_type",
        ),
        CheckConstraint(
            "(grant_type = 'company' AND target_id IS NULL) OR "
            "(grant_type <> 'company' AND target_id IS NOT NULL)",
            name="ck_file_manager_file_access_grants_target",
        ),
        UniqueConstraint(
            "file_id",
            "grant_key",
            name="uq_file_manager_file_access_grants_file_key",
        ),
        Index(
            "ix_file_manager_file_access_grants_target",
            "grant_type",
            "target_id",
            "file_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        ForeignKey("file_manager_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grant_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    grant_key: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    file: Mapped["FileManagerFile"] = relationship(back_populates="access_grants")


class FileManagerStorageCleanupJob(Base):
    __tablename__ = "file_manager_storage_cleanup_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','succeeded','failed')",
            name="ck_file_manager_storage_cleanup_jobs_status",
        ),
        Index(
            "ix_file_manager_storage_cleanup_jobs_status_retry",
            "status",
            "next_retry_at",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class FileManagerBulkIngestRun(Base):
    __tablename__ = "file_manager_bulk_ingest_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','ingesting','paused','completed','purging','purged','failed')",
            name="ck_file_manager_bulk_ingest_runs_status",
        ),
        CheckConstraint(
            "manifest_entry_count >= 0 AND manifest_total_bytes >= 0",
            name="ck_file_manager_bulk_ingest_runs_manifest_counts",
        ),
        UniqueConstraint(
            "corpus_id",
            "manifest_sha256",
            name="uq_file_manager_bulk_ingest_runs_corpus_manifest",
        ),
        UniqueConstraint(
            "root_folder_id",
            name="uq_file_manager_bulk_ingest_runs_root_folder",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key_sha256",
            name="uq_file_manager_bulk_ingest_runs_workspace_idempotency",
        ),
        Index(
            "ix_file_manager_bulk_ingest_runs_workspace_status",
            "workspace_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("file_manager_corpora.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    root_folder_id: Mapped[str] = mapped_column(
        ForeignKey("file_manager_folders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    idempotency_key_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_root_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="planned",
        server_default=text("'planned'"),
        nullable=False,
        index=True,
    )
    purge_after_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workspace = relationship("Workspace")
    corpus: Mapped[FileManagerCorpus] = relationship(back_populates="bulk_ingest_runs")
    root_folder: Mapped[FileManagerFolder] = relationship(foreign_keys=[root_folder_id])
    created_by = relationship("User")
    entries: Mapped[list["FileManagerBulkIngestEntry"]] = relationship(back_populates="run")


class FileManagerBulkIngestEntry(Base):
    __tablename__ = "file_manager_bulk_ingest_entries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','uploaded','failed','purged')",
            name="ck_file_manager_bulk_ingest_entries_status",
        ),
        CheckConstraint(
            "size_bytes >= 0 AND attempt_count >= 0",
            name="ck_file_manager_bulk_ingest_entries_counts",
        ),
        UniqueConstraint(
            "run_id",
            "source_path_sha256",
            name="uq_file_manager_bulk_ingest_entries_run_source",
        ),
        UniqueConstraint(
            "target_file_id",
            name="uq_file_manager_bulk_ingest_entries_target_file",
        ),
        Index(
            "ix_file_manager_bulk_ingest_entries_run_status_target",
            "run_id",
            "status",
            "target_file_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("file_manager_bulk_ingest_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_path_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    target_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="planned",
        server_default=text("'planned'"),
        nullable=False,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped[FileManagerBulkIngestRun] = relationship(back_populates="entries")
