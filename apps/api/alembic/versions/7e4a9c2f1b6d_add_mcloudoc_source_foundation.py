"""Add the mcloudoc source foundation and explicit Files grants.

Revision ID: 7e4a9c2f1b6d
Revises: c5f8a1d2e3b4
Create Date: 2026-08-04 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7e4a9c2f1b6d"
down_revision: str | Sequence[str] | None = "c5f8a1d2e3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")

_DOWNGRADE_PROTECTED_TABLES = (
    "file_manager_file_access_grants",
    "file_manager_file_source_metadata",
    "mcloudoc_documents",
    "mcloudoc_ingest_runs",
    "mcloudoc_sources",
)


def upgrade() -> None:
    # Defaults retain the pre-existing corpus behavior. Explicit grants can be
    # enabled only for corpora that are deliberately marked source-managed.
    op.add_column(
        "file_manager_corpora",
        sa.Column(
            "source_managed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "file_manager_corpora",
        sa.Column(
            "authorization_mode",
            sa.String(length=24),
            server_default=sa.text("'cohort'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_file_manager_corpora_authorization_mode",
        "file_manager_corpora",
        "authorization_mode IN ('cohort','explicit_grants')",
    )
    op.create_check_constraint(
        "ck_file_manager_corpora_explicit_grants_source_managed",
        "file_manager_corpora",
        "authorization_mode = 'cohort' OR source_managed = true",
    )
    op.create_index(
        op.f("ix_file_manager_corpora_source_managed"),
        "file_manager_corpora",
        ["source_managed"],
    )
    op.create_index(
        op.f("ix_file_manager_corpora_authorization_mode"),
        "file_manager_corpora",
        ["authorization_mode"],
    )

    op.create_table(
        "file_manager_file_source_metadata",
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("corpus_id", sa.String(length=36), nullable=False),
        sa.Column("external_id", sa.String(length=1024), nullable=False),
        sa.Column("external_id_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=1024), nullable=False),
        sa.Column("source_id_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.String(length=4096), nullable=True),
        sa.Column("source_uri", sa.String(length=2048), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("author", sa.String(length=512), nullable=True),
        sa.Column("authored_at", sa.DateTime(), nullable=True),
        sa.Column("department", sa.String(length=512), nullable=True),
        sa.Column("document_type", sa.String(length=255), nullable=True),
        sa.Column("content_checksum", sa.String(length=64), nullable=False),
        sa.Column("raw_metadata", JSONB_COMPAT, nullable=False),
        sa.Column(
            "acl_resolved",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["file_manager_files.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["corpus_id"],
            ["file_manager_corpora.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("file_id"),
        sa.UniqueConstraint(
            "corpus_id",
            "external_id_sha256",
            name="uq_file_manager_source_metadata_corpus_external",
        ),
        sa.UniqueConstraint(
            "corpus_id",
            "source_kind",
            "source_id_sha256",
            name="uq_file_manager_source_metadata_corpus_source_identity",
        ),
    )
    op.create_index(
        op.f("ix_file_manager_file_source_metadata_corpus_id"),
        "file_manager_file_source_metadata",
        ["corpus_id"],
    )
    op.create_index(
        op.f("ix_file_manager_file_source_metadata_acl_resolved"),
        "file_manager_file_source_metadata",
        ["acl_resolved"],
    )
    op.create_index(
        "ix_file_manager_source_metadata_corpus_updated",
        "file_manager_file_source_metadata",
        ["corpus_id", "source_updated_at"],
    )

    op.create_table(
        "file_manager_file_access_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("grant_type", sa.String(length=24), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("grant_key", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "grant_type IN ('company','workspace','user','org_unit','team')",
            name="ck_file_manager_file_access_grants_type",
        ),
        sa.CheckConstraint(
            "(grant_type = 'company' AND target_id IS NULL) OR "
            "(grant_type <> 'company' AND target_id IS NOT NULL)",
            name="ck_file_manager_file_access_grants_target",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["file_manager_files.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "file_id",
            "grant_key",
            name="uq_file_manager_file_access_grants_file_key",
        ),
    )
    op.create_index(
        op.f("ix_file_manager_file_access_grants_file_id"),
        "file_manager_file_access_grants",
        ["file_id"],
    )
    op.create_index(
        "ix_file_manager_file_access_grants_target",
        "file_manager_file_access_grants",
        ["grant_type", "target_id", "file_id"],
    )

    op.create_table(
        "mcloudoc_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=36), nullable=False),
        sa.Column("corpus_id", sa.String(length=36), nullable=False),
        sa.Column("ingest_owner_id", sa.String(length=36), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("current_continuation", sa.Text(), nullable=True),
        sa.Column("active_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('workspace','company')",
            name="ck_mcloudoc_sources_scope_type",
        ),
        sa.ForeignKeyConstraint(
            ["corpus_id"],
            ["file_manager_corpora.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingest_owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope_type",
            "scope_id",
            "name",
            name="uq_mcloudoc_sources_scope_name",
        ),
        sa.UniqueConstraint(
            "corpus_id",
            name="uq_mcloudoc_sources_corpus",
        ),
    )
    op.create_index(
        op.f("ix_mcloudoc_sources_corpus_id"),
        "mcloudoc_sources",
        ["corpus_id"],
    )
    op.create_index(
        op.f("ix_mcloudoc_sources_ingest_owner_id"),
        "mcloudoc_sources",
        ["ingest_owner_id"],
    )
    op.create_index(
        op.f("ix_mcloudoc_sources_enabled"),
        "mcloudoc_sources",
        ["enabled"],
    )
    op.create_index(
        "ix_mcloudoc_sources_scope",
        "mcloudoc_sources",
        ["scope_type", "scope_id"],
    )

    op.create_table(
        "mcloudoc_ingest_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("delivery_id", sa.Text(), nullable=False),
        sa.Column("delivery_id_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column("continuation_from", sa.Text(), nullable=True),
        sa.Column("continuation_to", sa.Text(), nullable=True),
        sa.Column(
            "is_complete",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("received_count", sa.Integer(), nullable=False),
        sa.Column("upserted_count", sa.Integer(), nullable=False),
        sa.Column("deleted_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("quarantined_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("errors", JSONB_COMPAT, nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "mode IN ('incremental','snapshot')",
            name="ck_mcloudoc_ingest_runs_mode",
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','failed')",
            name="ck_mcloudoc_ingest_runs_status",
        ),
        sa.CheckConstraint(
            "received_count >= 0 AND upserted_count >= 0 AND deleted_count >= 0 "
            "AND unchanged_count >= 0 AND quarantined_count >= 0 AND failed_count >= 0",
            name="ck_mcloudoc_ingest_runs_counts_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["mcloudoc_sources.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "delivery_id_sha256",
            name="uq_mcloudoc_ingest_runs_source_delivery",
        ),
    )
    op.create_index(
        op.f("ix_mcloudoc_ingest_runs_source_id"),
        "mcloudoc_ingest_runs",
        ["source_id"],
    )
    op.create_index(
        "ix_mcloudoc_ingest_runs_source_status",
        "mcloudoc_ingest_runs",
        ["source_id", "status"],
    )

    op.create_table(
        "mcloudoc_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("external_id_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("opaque_revision", sa.Text(), nullable=True),
        sa.Column("opaque_checksum", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("quarantine_code", sa.String(length=80), nullable=True),
        sa.Column("quarantine_detail", sa.String(length=512), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("content_type", sa.String(length=160), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("author", sa.String(length=512), nullable=True),
        sa.Column("authored_at", sa.DateTime(), nullable=True),
        sa.Column("department", sa.String(length=512), nullable=True),
        sa.Column("document_type", sa.String(length=255), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column("source_uri", sa.String(length=2048), nullable=True),
        sa.Column("raw_metadata", JSONB_COMPAT, nullable=False),
        sa.Column("raw_acl", JSONB_COMPAT, nullable=True),
        sa.Column("resolved_grants", JSONB_COMPAT, nullable=False),
        sa.Column("last_delivery_id", sa.Text(), nullable=True),
        sa.Column("last_delivery_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("last_seen_run_id", sa.String(length=36), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','deleted','quarantined')",
            name="ck_mcloudoc_documents_status",
        ),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_mcloudoc_documents_size_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["mcloudoc_sources.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["file_manager_files.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"],
            ["mcloudoc_ingest_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "external_id_sha256",
            name="uq_mcloudoc_documents_source_external_id",
        ),
        sa.UniqueConstraint(
            "file_id",
            name="uq_mcloudoc_documents_file",
        ),
    )
    op.create_index(
        op.f("ix_mcloudoc_documents_source_id"),
        "mcloudoc_documents",
        ["source_id"],
    )
    op.create_index(
        op.f("ix_mcloudoc_documents_status"),
        "mcloudoc_documents",
        ["status"],
    )
    op.create_index(
        "ix_mcloudoc_documents_source_status",
        "mcloudoc_documents",
        ["source_id", "status"],
    )
    op.create_index(
        "ix_mcloudoc_documents_last_seen_run",
        "mcloudoc_documents",
        ["source_id", "last_seen_run_id"],
    )


def downgrade() -> None:
    _assert_downgrade_is_safe()
    # The previous schema has cohort-only Files authorization. Normalize the
    # remaining corpus rows before removing the explicit authorization columns.
    op.execute(
        sa.text(
            "UPDATE file_manager_corpora SET authorization_mode = 'cohort', source_managed = false"
        )
    )

    op.drop_index(
        "ix_mcloudoc_documents_last_seen_run",
        table_name="mcloudoc_documents",
    )
    op.drop_index(
        "ix_mcloudoc_documents_source_status",
        table_name="mcloudoc_documents",
    )
    op.drop_index(op.f("ix_mcloudoc_documents_status"), table_name="mcloudoc_documents")
    op.drop_index(op.f("ix_mcloudoc_documents_source_id"), table_name="mcloudoc_documents")
    op.drop_table("mcloudoc_documents")

    op.drop_index(
        "ix_mcloudoc_ingest_runs_source_status",
        table_name="mcloudoc_ingest_runs",
    )
    op.drop_index(
        op.f("ix_mcloudoc_ingest_runs_source_id"),
        table_name="mcloudoc_ingest_runs",
    )
    op.drop_table("mcloudoc_ingest_runs")

    op.drop_index("ix_mcloudoc_sources_scope", table_name="mcloudoc_sources")
    op.drop_index(op.f("ix_mcloudoc_sources_enabled"), table_name="mcloudoc_sources")
    op.drop_index(
        op.f("ix_mcloudoc_sources_ingest_owner_id"),
        table_name="mcloudoc_sources",
    )
    op.drop_index(op.f("ix_mcloudoc_sources_corpus_id"), table_name="mcloudoc_sources")
    op.drop_table("mcloudoc_sources")

    op.drop_index(
        "ix_file_manager_file_access_grants_target",
        table_name="file_manager_file_access_grants",
    )
    op.drop_index(
        op.f("ix_file_manager_file_access_grants_file_id"),
        table_name="file_manager_file_access_grants",
    )
    op.drop_table("file_manager_file_access_grants")

    op.drop_index(
        "ix_file_manager_source_metadata_corpus_updated",
        table_name="file_manager_file_source_metadata",
    )
    op.drop_index(
        op.f("ix_file_manager_file_source_metadata_acl_resolved"),
        table_name="file_manager_file_source_metadata",
    )
    op.drop_index(
        op.f("ix_file_manager_file_source_metadata_corpus_id"),
        table_name="file_manager_file_source_metadata",
    )
    op.drop_table("file_manager_file_source_metadata")

    op.drop_index(
        op.f("ix_file_manager_corpora_authorization_mode"),
        table_name="file_manager_corpora",
    )
    op.drop_index(
        op.f("ix_file_manager_corpora_source_managed"),
        table_name="file_manager_corpora",
    )
    op.drop_constraint(
        "ck_file_manager_corpora_explicit_grants_source_managed",
        "file_manager_corpora",
        type_="check",
    )
    op.drop_constraint(
        "ck_file_manager_corpora_authorization_mode",
        "file_manager_corpora",
        type_="check",
    )
    op.drop_column("file_manager_corpora", "authorization_mode")
    op.drop_column("file_manager_corpora", "source_managed")


def _assert_downgrade_is_safe() -> None:
    bind = op.get_bind()
    blockers: list[str] = []
    explicit_corpus_exists = bind.scalar(
        sa.text("SELECT 1 FROM file_manager_corpora WHERE authorization_mode <> 'cohort' LIMIT 1")
    )
    if explicit_corpus_exists is not None:
        blockers.append("file_manager_corpora.authorization_mode")

    for table_name in _DOWNGRADE_PROTECTED_TABLES:
        row_exists = bind.scalar(sa.text(f'SELECT 1 FROM "{table_name}" LIMIT 1'))
        if row_exists is not None:
            blockers.append(table_name)

    if blockers:
        raise RuntimeError(
            "mcloudoc downgrade refused because explicit ACL or source state exists: "
            + ", ".join(blockers)
        )
