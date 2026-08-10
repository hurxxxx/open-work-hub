"""add_knowledge_sources

Revision ID: e3f4a5b6c7d8
Revises: d2f3a4b5c6d7
Create Date: 2026-05-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "knowledge_connectors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'ready'"), nullable=False
        ),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "source_type",
            name="uq_knowledge_connector_workspace_source",
        ),
    )
    op.create_index(
        "ix_knowledge_connectors_workspace_enabled",
        "knowledge_connectors",
        ["workspace_id", "enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_connectors_workspace_id"),
        "knowledge_connectors",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_connectors_source_type"),
        "knowledge_connectors",
        ["source_type"],
        unique=False,
    )

    op.create_table(
        "knowledge_source_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("connector_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("storage_provider", sa.String(length=40), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("external_uri", sa.String(length=2048), nullable=True),
        sa.Column("version_ref", sa.String(length=256), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("acl_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("origin_ref_type", sa.String(length=80), nullable=True),
        sa.Column("origin_ref_id", sa.String(length=80), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("visibility_refs", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "ingest_status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "rag_status", sa.String(length=24), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connector_id"], ["knowledge_connectors.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "source_type",
            "external_id",
            name="uq_knowledge_doc_workspace_source_external",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_source_documents_workspace_id"),
        "knowledge_source_documents",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_source_documents_connector_id"),
        "knowledge_source_documents",
        ["connector_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_source_documents_source_type"),
        "knowledge_source_documents",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_source_documents_owner_id"),
        "knowledge_source_documents",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_source_documents_content_hash"),
        "knowledge_source_documents",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_source_documents_disabled_at"),
        "knowledge_source_documents",
        ["disabled_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_source_documents_deleted_at"),
        "knowledge_source_documents",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_docs_workspace_status",
        "knowledge_source_documents",
        ["workspace_id", "ingest_status", "rag_status"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_docs_origin",
        "knowledge_source_documents",
        ["origin_ref_type", "origin_ref_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_docs_source_updated",
        "knowledge_source_documents",
        ["workspace_id", "source_updated_at"],
        unique=False,
    )

    op.create_table(
        "knowledge_document_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_document_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_type", sa.String(length=40), nullable=False),
        sa.Column("storage_provider", sa.String(length=40), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("mime_type", sa.String(length=160), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["knowledge_source_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_artifacts_document_type",
        "knowledge_document_artifacts",
        ["source_document_id", "artifact_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_document_artifacts_source_document_id"),
        "knowledge_document_artifacts",
        ["source_document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_document_artifacts_artifact_type"),
        "knowledge_document_artifacts",
        ["artifact_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_document_artifacts_content_hash"),
        "knowledge_document_artifacts",
        ["content_hash"],
        unique=False,
    )

    op.create_table(
        "knowledge_ingest_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_document_id", sa.String(length=36), nullable=False),
        sa.Column(
            "operation", sa.String(length=24), server_default=sa.text("'upsert'"), nullable=False
        ),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["knowledge_source_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_ingest_jobs_workspace_status",
        "knowledge_ingest_jobs",
        ["workspace_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_ingest_jobs_document_status",
        "knowledge_ingest_jobs",
        ["source_document_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_ingest_jobs_workspace_id"),
        "knowledge_ingest_jobs",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_ingest_jobs_source_document_id"),
        "knowledge_ingest_jobs",
        ["source_document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_knowledge_ingest_jobs_source_document_id"), table_name="knowledge_ingest_jobs"
    )
    op.drop_index(op.f("ix_knowledge_ingest_jobs_workspace_id"), table_name="knowledge_ingest_jobs")
    op.drop_index("ix_knowledge_ingest_jobs_document_status", table_name="knowledge_ingest_jobs")
    op.drop_index("ix_knowledge_ingest_jobs_workspace_status", table_name="knowledge_ingest_jobs")
    op.drop_table("knowledge_ingest_jobs")

    op.drop_index(
        op.f("ix_knowledge_document_artifacts_content_hash"),
        table_name="knowledge_document_artifacts",
    )
    op.drop_index(
        op.f("ix_knowledge_document_artifacts_artifact_type"),
        table_name="knowledge_document_artifacts",
    )
    op.drop_index(
        op.f("ix_knowledge_document_artifacts_source_document_id"),
        table_name="knowledge_document_artifacts",
    )
    op.drop_index("ix_knowledge_artifacts_document_type", table_name="knowledge_document_artifacts")
    op.drop_table("knowledge_document_artifacts")

    op.drop_index("ix_knowledge_docs_source_updated", table_name="knowledge_source_documents")
    op.drop_index("ix_knowledge_docs_origin", table_name="knowledge_source_documents")
    op.drop_index("ix_knowledge_docs_workspace_status", table_name="knowledge_source_documents")
    op.drop_index(
        op.f("ix_knowledge_source_documents_deleted_at"), table_name="knowledge_source_documents"
    )
    op.drop_index(
        op.f("ix_knowledge_source_documents_disabled_at"), table_name="knowledge_source_documents"
    )
    op.drop_index(
        op.f("ix_knowledge_source_documents_content_hash"), table_name="knowledge_source_documents"
    )
    op.drop_index(
        op.f("ix_knowledge_source_documents_owner_id"), table_name="knowledge_source_documents"
    )
    op.drop_index(
        op.f("ix_knowledge_source_documents_source_type"), table_name="knowledge_source_documents"
    )
    op.drop_index(
        op.f("ix_knowledge_source_documents_connector_id"), table_name="knowledge_source_documents"
    )
    op.drop_index(
        op.f("ix_knowledge_source_documents_workspace_id"), table_name="knowledge_source_documents"
    )
    op.drop_table("knowledge_source_documents")

    op.drop_index(op.f("ix_knowledge_connectors_source_type"), table_name="knowledge_connectors")
    op.drop_index(op.f("ix_knowledge_connectors_workspace_id"), table_name="knowledge_connectors")
    op.drop_index("ix_knowledge_connectors_workspace_enabled", table_name="knowledge_connectors")
    op.drop_table("knowledge_connectors")
