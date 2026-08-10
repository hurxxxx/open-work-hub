"""add legacy issue AI chunks

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-06-17 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "legacy_issue_ai_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("stable_record_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_key", sa.String(length=160), nullable=False),
        sa.Column("chunk_kind", sa.String(length=40), nullable=False),
        sa.Column("field_key", sa.String(length=160), nullable=True),
        sa.Column("field_label", sa.String(length=255), nullable=True),
        sa.Column("field_value", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("embedding_vector", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("embedding_status", sa.String(length=32), server_default="not_indexed", nullable=False),
        sa.Column("embedding_error", sa.Text(), nullable=True),
        sa.Column("evidence_metadata", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["legacy_issue_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["legacy_issue_data_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("record_id", "chunk_key", name="uq_legacy_issue_ai_chunks_record_chunk"),
    )
    for column in (
        "workspace_id",
        "dataset_key",
        "revision_id",
        "record_id",
        "stable_record_id",
        "chunk_kind",
        "field_key",
    ):
        op.create_index(op.f(f"ix_legacy_issue_ai_chunks_{column}"), "legacy_issue_ai_chunks", [column])
    op.create_index(
        "ix_legacy_issue_ai_chunks_workspace_dataset_revision",
        "legacy_issue_ai_chunks",
        ["workspace_id", "dataset_key", "revision_id"],
    )
    op.create_index(
        "ix_legacy_issue_ai_chunks_record",
        "legacy_issue_ai_chunks",
        ["record_id", "chunk_kind"],
    )
    op.create_index(
        "ix_legacy_issue_ai_chunks_workspace_dataset_stable",
        "legacy_issue_ai_chunks",
        ["workspace_id", "dataset_key", "stable_record_id"],
    )
    op.create_index(
        "ix_legacy_issue_ai_chunks_embedding_status",
        "legacy_issue_ai_chunks",
        ["embedding_status"],
    )
    _create_postgres_search_indexes()


def downgrade() -> None:
    op.drop_table("legacy_issue_ai_chunks")


def _create_postgres_search_indexes() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_legacy_issue_ai_chunks_search_text_fts
        ON legacy_issue_ai_chunks
        USING gin (to_tsvector('simple', coalesce(search_text, '')))
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm') THEN
            EXECUTE 'CREATE EXTENSION IF NOT EXISTS pg_trgm';
            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_legacy_issue_ai_chunks_search_text_trgm
              ON legacy_issue_ai_chunks
              USING gin (lower(search_text) gin_trgm_ops)';
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
          vector_ready boolean := false;
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
            BEGIN
              EXECUTE 'CREATE EXTENSION IF NOT EXISTS vector';
              vector_ready := true;
            EXCEPTION WHEN insufficient_privilege THEN
              vector_ready := false;
            END;
            IF vector_ready THEN
              BEGIN
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_legacy_issue_ai_chunks_embedding_hnsw
                  ON legacy_issue_ai_chunks
                  USING hnsw ((embedding_vector::vector(1024)) vector_cosine_ops)
                  WHERE embedding_status = ''embedded'' AND embedding_vector IS NOT NULL';
              EXCEPTION WHEN OTHERS THEN
                NULL;
              END;
            END IF;
          END IF;
        END $$;
        """
    )
