"""Add the operator-managed Files bulk-ingest control plane.

Revision ID: c5b7d9e1f3a6
Revises: e4a8c2d6f0b3
Create Date: 2026-07-29 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "c5b7d9e1f3a6"
down_revision: str | None = "e4a8c2d6f0b3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "file_manager_corpora",
        sa.Column(
            "operator_managed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_file_manager_corpora_operator_managed"),
        "file_manager_corpora",
        ["operator_managed"],
    )

    op.create_table(
        "file_manager_bulk_ingest_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("corpus_id", sa.String(length=36), nullable=False),
        sa.Column("root_folder_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_root_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_entry_count", sa.Integer(), nullable=False),
        sa.Column("manifest_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column("purge_after_file_id", sa.String(length=36), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("purged_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN "
            "('planned','ingesting','paused','completed','purging','purged','failed')",
            name="ck_file_manager_bulk_ingest_runs_status",
        ),
        sa.CheckConstraint(
            "manifest_entry_count >= 0 AND manifest_total_bytes >= 0",
            name="ck_file_manager_bulk_ingest_runs_manifest_counts",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_file_bulk_ingest_runs_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["corpus_id"],
            ["file_manager_corpora.id"],
            name="fk_file_bulk_ingest_runs_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["root_folder_id"],
            ["file_manager_folders.id"],
            name="fk_file_bulk_ingest_runs_root_folder",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_file_bulk_ingest_runs_created_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "corpus_id",
            "manifest_sha256",
            name="uq_file_manager_bulk_ingest_runs_corpus_manifest",
        ),
        sa.UniqueConstraint(
            "root_folder_id",
            name="uq_file_manager_bulk_ingest_runs_root_folder",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key_sha256",
            name="uq_file_manager_bulk_ingest_runs_workspace_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_file_manager_bulk_ingest_runs_workspace_id"),
        "file_manager_bulk_ingest_runs",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_file_manager_bulk_ingest_runs_corpus_id"),
        "file_manager_bulk_ingest_runs",
        ["corpus_id"],
    )
    op.create_index(
        op.f("ix_file_manager_bulk_ingest_runs_created_by_id"),
        "file_manager_bulk_ingest_runs",
        ["created_by_id"],
    )
    op.create_index(
        op.f("ix_file_manager_bulk_ingest_runs_status"),
        "file_manager_bulk_ingest_runs",
        ["status"],
    )
    op.create_index(
        "ix_file_manager_bulk_ingest_runs_workspace_status",
        "file_manager_bulk_ingest_runs",
        ["workspace_id", "status"],
    )

    op.create_table(
        "file_manager_bulk_ingest_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_path", sa.String(length=2048), nullable=False),
        sa.Column("source_path_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("target_file_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("purged_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('planned','uploaded','failed','purged')",
            name="ck_file_manager_bulk_ingest_entries_status",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0 AND attempt_count >= 0",
            name="ck_file_manager_bulk_ingest_entries_counts",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["file_manager_bulk_ingest_runs.id"],
            name="fk_file_bulk_ingest_entries_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "source_path_sha256",
            name="uq_file_manager_bulk_ingest_entries_run_source",
        ),
        sa.UniqueConstraint(
            "target_file_id",
            name="uq_file_manager_bulk_ingest_entries_target_file",
        ),
    )
    op.create_index(
        op.f("ix_file_manager_bulk_ingest_entries_run_id"),
        "file_manager_bulk_ingest_entries",
        ["run_id"],
    )
    op.create_index(
        op.f("ix_file_manager_bulk_ingest_entries_status"),
        "file_manager_bulk_ingest_entries",
        ["status"],
    )
    op.create_index(
        "ix_file_manager_bulk_ingest_entries_run_status_target",
        "file_manager_bulk_ingest_entries",
        ["run_id", "status", "target_file_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_file_manager_bulk_ingest_entries_run_status_target",
        table_name="file_manager_bulk_ingest_entries",
    )
    op.drop_index(
        op.f("ix_file_manager_bulk_ingest_entries_status"),
        table_name="file_manager_bulk_ingest_entries",
    )
    op.drop_index(
        op.f("ix_file_manager_bulk_ingest_entries_run_id"),
        table_name="file_manager_bulk_ingest_entries",
    )
    op.drop_table("file_manager_bulk_ingest_entries")

    op.drop_index(
        "ix_file_manager_bulk_ingest_runs_workspace_status",
        table_name="file_manager_bulk_ingest_runs",
    )
    op.drop_index(
        op.f("ix_file_manager_bulk_ingest_runs_status"),
        table_name="file_manager_bulk_ingest_runs",
    )
    op.drop_index(
        op.f("ix_file_manager_bulk_ingest_runs_created_by_id"),
        table_name="file_manager_bulk_ingest_runs",
    )
    op.drop_index(
        op.f("ix_file_manager_bulk_ingest_runs_corpus_id"),
        table_name="file_manager_bulk_ingest_runs",
    )
    op.drop_index(
        op.f("ix_file_manager_bulk_ingest_runs_workspace_id"),
        table_name="file_manager_bulk_ingest_runs",
    )
    op.drop_table("file_manager_bulk_ingest_runs")

    op.drop_index(
        op.f("ix_file_manager_corpora_operator_managed"),
        table_name="file_manager_corpora",
    )
    op.drop_column("file_manager_corpora", "operator_managed")
