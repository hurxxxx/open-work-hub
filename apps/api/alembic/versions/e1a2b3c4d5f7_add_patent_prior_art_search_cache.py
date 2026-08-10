"""add patent prior art search cache

Revision ID: e1a2b3c4d5f7
Revises: d5e6f7a8b9d1
Create Date: 2026-07-02 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e1a2b3c4d5f7"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "patent_prior_art_source_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_document_id", sa.String(length=160), nullable=True),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("representative_number", sa.String(length=160), nullable=True),
        sa.Column("application_number", sa.String(length=160), nullable=True),
        sa.Column("publication_number", sa.String(length=160), nullable=True),
        sa.Column("grant_number", sa.String(length=160), nullable=True),
        sa.Column("family_id", sa.String(length=160), nullable=True),
        sa.Column("priority_number", sa.String(length=160), nullable=True),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("claims_text", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("assignees", JSONB_COMPAT, nullable=True),
        sa.Column("ipc", JSONB_COMPAT, nullable=True),
        sa.Column("cpc", JSONB_COMPAT, nullable=True),
        sa.Column("dates", JSONB_COMPAT, nullable=True),
        sa.Column("legal_status", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("raw_payload", JSONB_COMPAT, nullable=True),
        sa.Column("embedding_vector", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column(
            "embedding_status",
            sa.String(length=32),
            server_default=sa.text("'not_indexed'"),
            nullable=False,
        ),
        sa.Column("embedding_error", sa.Text(), nullable=True),
        sa.Column("embedding_updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_ppaa_docs_country_repno",
        "patent_prior_art_source_documents",
        ["country", "representative_number"],
        unique=True,
        postgresql_where=sa.text(
            "representative_number IS NOT NULL AND representative_number <> ''"
        ),
    )
    op.create_index(
        "ux_ppaa_docs_country_pubno",
        "patent_prior_art_source_documents",
        ["country", "publication_number"],
        unique=True,
        postgresql_where=sa.text("publication_number IS NOT NULL AND publication_number <> ''"),
    )
    op.create_index(
        "ux_ppaa_docs_country_appno",
        "patent_prior_art_source_documents",
        ["country", "application_number"],
        unique=True,
        postgresql_where=sa.text("application_number IS NOT NULL AND application_number <> ''"),
    )
    op.create_index(
        "ux_ppaa_docs_country_grantno",
        "patent_prior_art_source_documents",
        ["country", "grant_number"],
        unique=True,
        postgresql_where=sa.text("grant_number IS NOT NULL AND grant_number <> ''"),
    )
    op.create_index(
        "ix_ppaa_docs_country_family",
        "patent_prior_art_source_documents",
        ["country", "family_id"],
    )
    op.create_index(
        "ix_ppaa_docs_source_id",
        "patent_prior_art_source_documents",
        ["source", "source_document_id"],
    )
    op.create_index(
        "ix_ppaa_docs_updated",
        "patent_prior_art_source_documents",
        ["updated_at"],
    )

    op.create_table(
        "patent_prior_art_source_aliases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("alias_type", sa.String(length=40), nullable=False),
        sa.Column("raw_value", sa.String(length=180), nullable=False),
        sa.Column("normalized_value", sa.String(length=180), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["patent_prior_art_source_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "country",
            "alias_type",
            "normalized_value",
            name="ux_ppaa_alias_country_type_norm",
        ),
    )
    op.create_index("ix_ppaa_alias_document", "patent_prior_art_source_aliases", ["document_id"])
    op.create_index(
        "ix_ppaa_alias_normalized",
        "patent_prior_art_source_aliases",
        ["normalized_value"],
    )

    op.create_table(
        "patent_prior_art_query_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("search_field", sa.String(length=80), nullable=False),
        sa.Column("query_id", sa.String(length=120), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("failure", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("raw_payload", JSONB_COMPAT, nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["patent_prior_art_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "round_no",
            "country",
            "provider",
            "search_field",
            "query_hash",
            name="ux_ppaa_query_job_round_hash",
        ),
    )
    op.create_index(
        op.f("ix_patent_prior_art_query_executions_workspace_id"),
        "patent_prior_art_query_executions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ppaa_query_job_round",
        "patent_prior_art_query_executions",
        ["job_id", "round_no"],
    )
    op.create_index(
        "ix_ppaa_query_country_provider_status",
        "patent_prior_art_query_executions",
        ["country", "provider", "status"],
    )
    op.create_index("ix_ppaa_query_hash", "patent_prior_art_query_executions", ["query_hash"])

    op.create_table(
        "patent_prior_art_query_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("query_execution_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("result_rank", sa.Integer(), nullable=True),
        sa.Column("raw_payload", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["patent_prior_art_source_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_execution_id"],
            ["patent_prior_art_query_executions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "query_execution_id",
            "document_id",
            name="ux_ppaa_query_result_query_document",
        ),
    )
    op.create_index(
        "ix_ppaa_query_result_query",
        "patent_prior_art_query_results",
        ["query_execution_id"],
    )
    op.create_index(
        "ix_ppaa_query_result_document",
        "patent_prior_art_query_results",
        ["document_id"],
    )

    op.create_table(
        "patent_prior_art_job_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("excluded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("exclude_reason", sa.Text(), nullable=False),
        sa.Column("matched_exclusion_terms", JSONB_COMPAT, nullable=True),
        sa.Column("candidate_stage", sa.String(length=40), nullable=False),
        sa.Column("raw_rank", sa.Integer(), nullable=True),
        sa.Column("active_rank", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("bm25_score", sa.Float(), nullable=True),
        sa.Column("vector_score", sa.Float(), nullable=True),
        sa.Column("rerank_score", sa.Float(), nullable=True),
        sa.Column("llm_decision", sa.String(length=80), nullable=False),
        sa.Column("score_reasons", JSONB_COMPAT, nullable=True),
        sa.Column("candidate_search_text", sa.Text(), nullable=False),
        sa.Column("raw_payload", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["patent_prior_art_source_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["patent_prior_art_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "document_id", name="ux_ppaa_job_candidate_job_document"),
    )
    op.create_index(
        op.f("ix_patent_prior_art_job_candidates_workspace_id"),
        "patent_prior_art_job_candidates",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ppaa_job_candidate_job_active_score",
        "patent_prior_art_job_candidates",
        ["job_id", "active", "score"],
    )
    op.create_index(
        "ix_ppaa_job_candidate_job_excluded",
        "patent_prior_art_job_candidates",
        ["job_id", "excluded"],
    )
    op.create_index(
        "ix_ppaa_job_candidate_exclude_reason",
        "patent_prior_art_job_candidates",
        ["job_id", "exclude_reason"],
    )

    op.create_table(
        "patent_prior_art_refinement_rounds",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("continue_refinement", sa.Boolean(), nullable=True),
        sa.Column("stop_reason", sa.Text(), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=False),
        sa.Column("additional_queries", JSONB_COMPAT, nullable=True),
        sa.Column("local_exclusion_terms", JSONB_COMPAT, nullable=True),
        sa.Column("response_payload", JSONB_COMPAT, nullable=True),
        sa.Column("token_usage", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["patent_prior_art_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "round_no", name="ux_ppaa_refinement_round_job_round"),
    )
    op.create_index(
        op.f("ix_patent_prior_art_refinement_rounds_workspace_id"),
        "patent_prior_art_refinement_rounds",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ppaa_refinement_round_job_created",
        "patent_prior_art_refinement_rounds",
        ["job_id", "created_at"],
    )

    _create_postgres_search_indexes()


def downgrade() -> None:
    op.drop_table("patent_prior_art_refinement_rounds")
    op.drop_table("patent_prior_art_job_candidates")
    op.drop_table("patent_prior_art_query_results")
    op.drop_table("patent_prior_art_query_executions")
    op.drop_table("patent_prior_art_source_aliases")
    op.drop_table("patent_prior_art_source_documents")


def _create_postgres_search_indexes() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ppaa_docs_raw_payload_gin
        ON patent_prior_art_source_documents
        USING gin (raw_payload)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ppaa_docs_search_fts
        ON patent_prior_art_source_documents
        USING gin (to_tsvector('simple', coalesce(search_text, '')))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ppaa_job_candidate_search_fts
        ON patent_prior_art_job_candidates
        USING gin (to_tsvector('simple', coalesce(candidate_search_text, '')))
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm') THEN
            EXECUTE 'CREATE EXTENSION IF NOT EXISTS pg_trgm';
            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ppaa_docs_search_trgm
              ON patent_prior_art_source_documents
              USING gin (lower(search_text) gin_trgm_ops)';
            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ppaa_job_candidate_search_trgm
              ON patent_prior_art_job_candidates
              USING gin (lower(candidate_search_text) gin_trgm_ops)';
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
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ppaa_docs_embedding_hnsw
                  ON patent_prior_art_source_documents
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
