"""add shared AI graph and immutable artifact control plane

Revision ID: a4e7c2f9d1b6
Revises: f3c9e1a5b7d2
Create Date: 2026-07-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a4e7c2f9d1b6"
down_revision: str | Sequence[str] | None = "f3c9e1a5b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(
    sa.JSON(),
    "sqlite",
)


def _create_langgraph_checkpoint_tables() -> None:
    """Materialize the schema expected by checkpoint-postgres 3.1.0."""

    op.create_table(
        "checkpoint_migrations",
        sa.Column("v", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("v"),
    )
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column(
            "checkpoint_ns",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("checkpoint", _JSONB_COMPAT, nullable=False),
        sa.Column(
            "metadata",
            _JSONB_COMPAT,
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
    )
    op.create_index("checkpoints_thread_id_idx", "checkpoints", ["thread_id"])
    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column(
            "checkpoint_ns",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint(
            "thread_id",
            "checkpoint_ns",
            "channel",
            "version",
        ),
    )
    op.create_index(
        "checkpoint_blobs_thread_id_idx",
        "checkpoint_blobs",
        ["thread_id"],
    )
    op.create_table(
        "checkpoint_writes",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column(
            "checkpoint_ns",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.Column(
            "task_path",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            "task_id",
            "idx",
        ),
    )
    op.create_index(
        "checkpoint_writes_thread_id_idx",
        "checkpoint_writes",
        ["thread_id"],
    )
    migration_table = sa.table(
        "checkpoint_migrations",
        sa.column("v", sa.Integer()),
    )
    op.bulk_insert(migration_table, [{"v": version} for version in range(10)])


def _create_graph_tables() -> None:
    op.create_table(
        "ai_graph_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=False),
        sa.Column("graph_version", sa.String(length=64), nullable=False),
        sa.Column("checkpoint_thread_id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_ns", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=128), nullable=True),
        sa.Column("current_step", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_steps", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "progress_percent",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("status_message_key", sa.String(length=160), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("execution_claim_token", sa.String(length=64), nullable=True),
        sa.Column("execution_claimed_at", sa.DateTime(), nullable=True),
        sa.Column("execution_lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("execution_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "visibility",
            sa.String(length=24),
            server_default=sa.text("'private'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_ai_graph_runs_status",
        ),
        sa.CheckConstraint(
            "visibility IN ('private','workspace')",
            name="ck_ai_graph_runs_visibility",
        ),
        sa.CheckConstraint(
            "current_step >= 0 AND total_steps >= 0 AND current_step <= total_steps",
            name="ck_ai_graph_runs_steps",
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_ai_graph_runs_progress",
        ),
        sa.CheckConstraint(
            "execution_attempts >= 0",
            name="ck_ai_graph_runs_execution_attempts",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_thread_id"),
    )
    op.create_index("ix_ai_graph_runs_workspace_id", "ai_graph_runs", ["workspace_id"])
    op.create_index(
        "ix_ai_graph_runs_requested_by_user_id",
        "ai_graph_runs",
        ["requested_by_user_id"],
    )
    op.create_index(
        "ix_ai_graph_runs_conversation_id",
        "ai_graph_runs",
        ["conversation_id"],
    )
    op.create_index("ix_ai_graph_runs_app_id", "ai_graph_runs", ["app_id"])
    op.create_index(
        "ix_ai_graph_runs_workspace_user_created",
        "ai_graph_runs",
        ["workspace_id", "requested_by_user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_graph_runs_workspace_status_created",
        "ai_graph_runs",
        ["workspace_id", "status", "created_at"],
    )
    op.create_index(
        "ix_ai_graph_runs_conversation_created",
        "ai_graph_runs",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_ai_graph_runs_status_lease",
        "ai_graph_runs",
        ["status", "execution_lease_expires_at"],
    )

    op.create_table(
        "ai_graph_run_inputs",
        sa.Column("graph_run_id", sa.String(length=36), nullable=False),
        sa.Column("payload_json", _JSONB_COMPAT, nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "schema_version >= 1",
            name="ck_ai_graph_run_inputs_schema_version",
        ),
        sa.ForeignKeyConstraint(
            ["graph_run_id"],
            ["ai_graph_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("graph_run_id"),
    )

    op.create_table(
        "ai_graph_run_node_progress",
        sa.Column("graph_run_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["graph_run_id"],
            ["ai_graph_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("graph_run_id", "node_id"),
    )

    op.create_table(
        "ai_graph_dispatch_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_run_id", sa.String(length=36), nullable=False),
        sa.Column("payload_ref", sa.String(length=512), nullable=False),
        sa.Column("queue_name", sa.String(length=128), nullable=False),
        sa.Column("task_name", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','claimed','dispatched','dead_letter')",
            name="ck_ai_graph_dispatch_outbox_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_ai_graph_dispatch_outbox_attempts"),
        sa.ForeignKeyConstraint(
            ["graph_run_id"],
            ["ai_graph_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_graph_dispatch_outbox_graph_run_id",
        "ai_graph_dispatch_outbox",
        ["graph_run_id"],
        unique=True,
    )
    op.create_index(
        "ix_ai_graph_dispatch_outbox_due",
        "ai_graph_dispatch_outbox",
        ["status", "available_at", "created_at"],
    )


def _create_index_generation_table() -> None:
    op.create_table(
        "ai_index_generations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("generation_key", sa.String(length=256), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'staging'"),
            nullable=False,
        ),
        sa.Column("backend", sa.String(length=64), nullable=False),
        sa.Column("source_namespace", sa.String(length=256), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=True),
        sa.Column("embedding_model", sa.String(length=256), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("source_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("document_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("corpus_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "validation_status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("validation_json", _JSONB_COMPAT, nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("cutover_at", sa.DateTime(), nullable=True),
        sa.Column("retired_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('staging','active','failed','retired')",
            name="ck_ai_index_generations_status",
        ),
        sa.CheckConstraint(
            "validation_status IN ('pending','passed','failed')",
            name="ck_ai_index_generations_validation_status",
        ),
        sa.CheckConstraint(
            "schema_version >= 1 AND source_count >= 0 AND document_count >= 0 "
            "AND chunk_count >= 0",
            name="ck_ai_index_generations_counts",
        ),
        sa.CheckConstraint(
            "embedding_dimensions IS NULL OR embedding_dimensions > 0",
            name="ck_ai_index_generations_dimensions",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "app_id",
            "backend",
            "source_namespace",
            "generation_key",
            name="uq_ai_index_generations_identity",
        ),
    )
    op.create_index(
        "ix_ai_index_generations_workspace_id",
        "ai_index_generations",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ai_index_generations_app_id",
        "ai_index_generations",
        ["app_id"],
    )
    op.create_index(
        "ix_ai_index_generations_workspace_app_status",
        "ai_index_generations",
        ["workspace_id", "app_id", "status"],
    )
    op.create_index(
        "ix_ai_index_generations_namespace_created",
        "ai_index_generations",
        ["source_namespace", "created_at"],
    )
    op.create_index(
        "uq_ai_index_generations_active_scope",
        "ai_index_generations",
        ["workspace_id", "app_id", "backend", "source_namespace"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def _create_artifact_tables() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute(sa.text("CREATE SEQUENCE ai_report_artifact_number_seq START WITH 1"))
        op.execute(sa.text("CREATE SEQUENCE ai_analysis_artifact_number_seq START WITH 1"))

    op.create_table(
        "ai_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("artifact_number", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("graph_run_id", sa.String(length=36), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("conversation_turn_id", sa.String(length=36), nullable=True),
        sa.Column("supersedes_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_type", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("payload_json", _JSONB_COMPAT, nullable=True),
        sa.Column("schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("content_size_bytes", sa.Integer(), nullable=True),
        sa.Column(
            "visibility",
            sa.String(length=24),
            server_default=sa.text("'private'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'building'"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "artifact_type IN ('report','analysis')",
            name="ck_ai_artifacts_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','building','completed','failed')",
            name="ck_ai_artifacts_status",
        ),
        sa.CheckConstraint(
            "visibility IN ('private','workspace')",
            name="ck_ai_artifacts_visibility",
        ),
        sa.CheckConstraint(
            "(artifact_type = 'report' AND artifact_number LIKE 'AIR-%') OR "
            "(artifact_type = 'analysis' AND artifact_number LIKE 'AIA-%')",
            name="ck_ai_artifacts_number_prefix",
        ),
        sa.CheckConstraint(
            "supersedes_artifact_id IS NULL OR supersedes_artifact_id <> id",
            name="ck_ai_artifacts_not_self_superseding",
        ),
        sa.CheckConstraint(
            "owner_user_id IS NOT NULL OR visibility = 'workspace'",
            name="ck_ai_artifacts_owner_or_workspace_visibility",
        ),
        sa.CheckConstraint(
            "(status <> 'completed' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL "
            "AND content_sha256 IS NOT NULL AND content_size_bytes IS NOT NULL "
            "AND (content_text IS NOT NULL OR payload_json IS NOT NULL))",
            name="ck_ai_artifacts_completion",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_turn_id"],
            ["conversation_turns.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["graph_run_id"],
            ["ai_graph_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["supersedes_artifact_id"],
            ["ai_artifacts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_artifacts_artifact_number",
        "ai_artifacts",
        ["artifact_number"],
        unique=True,
    )
    for column in (
        "workspace_id",
        "owner_user_id",
        "conversation_id",
        "conversation_turn_id",
        "supersedes_artifact_id",
        "app_id",
    ):
        op.create_index(f"ix_ai_artifacts_{column}", "ai_artifacts", [column])
    op.create_index("ix_ai_artifacts_graph_run", "ai_artifacts", ["graph_run_id"])
    op.create_index(
        "ix_ai_artifacts_workspace_owner_created",
        "ai_artifacts",
        ["workspace_id", "owner_user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_artifacts_workspace_type_created",
        "ai_artifacts",
        ["workspace_id", "artifact_type", "created_at"],
    )

    op.create_table(
        "ai_artifact_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=512), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("locator_json", _JSONB_COMPAT, nullable=True),
        sa.Column("metadata_json", _JSONB_COMPAT, nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("grid_columns_json", _JSONB_COMPAT, nullable=True),
        sa.Column("grid_rows_json", _JSONB_COMPAT, nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("truncated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_ai_artifact_sources_ordinal"),
        sa.CheckConstraint(
            "row_count IS NULL OR row_count >= 0",
            name="ck_ai_artifact_sources_row_count",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["ai_artifacts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id",
            "source_kind",
            "source_ref",
            "source_version",
            name="uq_ai_artifact_sources_identity",
        ),
        sa.UniqueConstraint(
            "artifact_id",
            "ordinal",
            name="uq_ai_artifact_sources_ordinal",
        ),
    )
    op.create_index(
        "ix_ai_artifact_sources_artifact_id",
        "ai_artifact_sources",
        ["artifact_id"],
    )

    op.create_table(
        "ai_artifact_queries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("query_kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("family_id", sa.String(length=128), nullable=True),
        sa.Column("query_spec_json", _JSONB_COMPAT, nullable=True),
        sa.Column("statement_text", sa.Text(), nullable=True),
        sa.Column("typed_params_json", _JSONB_COMPAT, nullable=True),
        sa.Column(
            "execution_status",
            sa.String(length=24),
            server_default=sa.text("'not_executed'"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("result_schema_json", _JSONB_COMPAT, nullable=True),
        sa.Column("result_rows_json", _JSONB_COMPAT, nullable=True),
        sa.Column("query_sha256", sa.String(length=64), nullable=False),
        sa.Column("result_sha256", sa.String(length=64), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("truncated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("payload_bytes", sa.Integer(), nullable=True),
        sa.Column(
            "exactness",
            sa.String(length=24),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_ai_artifact_queries_ordinal"),
        sa.CheckConstraint(
            "exactness IN ('exact','estimated','semantic','mixed','unknown')",
            name="ck_ai_artifact_queries_exactness",
        ),
        sa.CheckConstraint(
            "row_count IS NULL OR row_count >= 0",
            name="ck_ai_artifact_queries_row_count",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_ai_artifact_queries_duration",
        ),
        sa.CheckConstraint(
            "payload_bytes IS NULL OR payload_bytes >= 0",
            name="ck_ai_artifact_queries_payload_bytes",
        ),
        sa.CheckConstraint(
            "execution_status IN ('not_executed','completed','failed')",
            name="ck_ai_artifact_queries_execution_status",
        ),
        sa.CheckConstraint(
            "execution_status <> 'failed' OR error_code IS NOT NULL",
            name="ck_ai_artifact_queries_failed_error",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["ai_artifacts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id",
            "ordinal",
            name="uq_ai_artifact_queries_ordinal",
        ),
    )
    op.create_index(
        "ix_ai_artifact_queries_artifact_id",
        "ai_artifact_queries",
        ["artifact_id"],
    )

    op.create_table(
        "ai_artifact_index_generations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("index_generation_id", sa.String(length=36), nullable=False),
        sa.Column("metadata_json", _JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_ai_artifact_index_generations_ordinal",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["ai_artifacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["index_generation_id"],
            ["ai_index_generations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id",
            "index_generation_id",
            name="uq_ai_artifact_index_generations_identity",
        ),
        sa.UniqueConstraint(
            "artifact_id",
            "ordinal",
            name="uq_ai_artifact_index_generations_ordinal",
        ),
    )
    op.create_index(
        "ix_ai_artifact_index_generations_artifact_id",
        "ai_artifact_index_generations",
        ["artifact_id"],
    )
    op.create_index(
        "ix_ai_artifact_index_generations_index_generation_id",
        "ai_artifact_index_generations",
        ["index_generation_id"],
    )


def _create_immutability_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION ai_guard_completed_artifact() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'completed' THEN
                RAISE EXCEPTION 'completed AI artifacts are immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE FUNCTION ai_guard_graph_run_input_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'AI graph bootstrap input is immutable'
                USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_graph_run_inputs_immutable
        BEFORE UPDATE ON ai_graph_run_inputs
        FOR EACH ROW EXECUTE FUNCTION ai_guard_graph_run_input_update()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_artifacts_completed_immutable
        BEFORE UPDATE OR DELETE ON ai_artifacts
        FOR EACH ROW EXECUTE FUNCTION ai_guard_completed_artifact()
        """
    )
    op.execute(
        """
        CREATE FUNCTION ai_guard_completed_artifact_child() RETURNS trigger AS $$
        DECLARE
            candidate_artifact_id varchar(36);
        BEGIN
            IF TG_OP = 'DELETE' THEN
                candidate_artifact_id := OLD.artifact_id;
            ELSE
                candidate_artifact_id := NEW.artifact_id;
            END IF;
            IF EXISTS (
                SELECT 1 FROM ai_artifacts
                WHERE id = candidate_artifact_id AND status = 'completed'
            ) THEN
                RAISE EXCEPTION 'completed AI artifact children are immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'UPDATE'
               AND OLD.artifact_id <> NEW.artifact_id
               AND EXISTS (
                   SELECT 1 FROM ai_artifacts
                   WHERE id = OLD.artifact_id AND status = 'completed'
               ) THEN
                RAISE EXCEPTION 'completed AI artifact children are immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "ai_artifact_sources",
        "ai_artifact_queries",
        "ai_artifact_index_generations",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_completed_immutable
            BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION ai_guard_completed_artifact_child()
            """
        )


def upgrade() -> None:
    _create_langgraph_checkpoint_tables()
    _create_graph_tables()
    _create_index_generation_table()
    _create_artifact_tables()
    if op.get_context().dialect.name == "postgresql":
        _create_immutability_triggers()


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        for table in (
            "ai_artifact_index_generations",
            "ai_artifact_queries",
            "ai_artifact_sources",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_completed_immutable ON {table}")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_ai_artifacts_completed_immutable ON ai_artifacts"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_ai_graph_run_inputs_immutable "
            "ON ai_graph_run_inputs"
        )
        op.execute("DROP FUNCTION IF EXISTS ai_guard_completed_artifact_child()")
        op.execute("DROP FUNCTION IF EXISTS ai_guard_completed_artifact()")
        op.execute("DROP FUNCTION IF EXISTS ai_guard_graph_run_input_update()")

    op.drop_index(
        "ix_ai_artifact_index_generations_index_generation_id",
        table_name="ai_artifact_index_generations",
    )
    op.drop_index(
        "ix_ai_artifact_index_generations_artifact_id",
        table_name="ai_artifact_index_generations",
    )
    op.drop_table("ai_artifact_index_generations")
    op.drop_index("ix_ai_artifact_queries_artifact_id", table_name="ai_artifact_queries")
    op.drop_table("ai_artifact_queries")
    op.drop_index("ix_ai_artifact_sources_artifact_id", table_name="ai_artifact_sources")
    op.drop_table("ai_artifact_sources")
    op.drop_index(
        "ix_ai_artifacts_workspace_type_created",
        table_name="ai_artifacts",
    )
    op.drop_index(
        "ix_ai_artifacts_workspace_owner_created",
        table_name="ai_artifacts",
    )
    op.drop_index("ix_ai_artifacts_graph_run", table_name="ai_artifacts")
    for column in reversed(
        (
            "artifact_number",
            "workspace_id",
            "owner_user_id",
            "conversation_id",
            "conversation_turn_id",
            "supersedes_artifact_id",
            "app_id",
        )
    ):
        op.drop_index(f"ix_ai_artifacts_{column}", table_name="ai_artifacts")
    op.drop_table("ai_artifacts")
    if op.get_context().dialect.name == "postgresql":
        op.execute(sa.text("DROP SEQUENCE IF EXISTS ai_analysis_artifact_number_seq"))
        op.execute(sa.text("DROP SEQUENCE IF EXISTS ai_report_artifact_number_seq"))

    op.drop_index(
        "uq_ai_index_generations_active_scope",
        table_name="ai_index_generations",
    )
    op.drop_index(
        "ix_ai_index_generations_namespace_created",
        table_name="ai_index_generations",
    )
    op.drop_index(
        "ix_ai_index_generations_workspace_app_status",
        table_name="ai_index_generations",
    )
    op.drop_index("ix_ai_index_generations_app_id", table_name="ai_index_generations")
    op.drop_index("ix_ai_index_generations_workspace_id", table_name="ai_index_generations")
    op.drop_table("ai_index_generations")

    op.drop_index(
        "ix_ai_graph_dispatch_outbox_due",
        table_name="ai_graph_dispatch_outbox",
    )
    op.drop_index(
        "ix_ai_graph_dispatch_outbox_graph_run_id",
        table_name="ai_graph_dispatch_outbox",
    )
    op.drop_table("ai_graph_dispatch_outbox")
    op.drop_table("ai_graph_run_node_progress")
    op.drop_table("ai_graph_run_inputs")
    op.drop_index(
        "ix_ai_graph_runs_status_lease",
        table_name="ai_graph_runs",
    )
    op.drop_index(
        "ix_ai_graph_runs_conversation_created",
        table_name="ai_graph_runs",
    )
    op.drop_index(
        "ix_ai_graph_runs_workspace_status_created",
        table_name="ai_graph_runs",
    )
    op.drop_index(
        "ix_ai_graph_runs_workspace_user_created",
        table_name="ai_graph_runs",
    )
    op.drop_index("ix_ai_graph_runs_app_id", table_name="ai_graph_runs")
    op.drop_index("ix_ai_graph_runs_conversation_id", table_name="ai_graph_runs")
    op.drop_index("ix_ai_graph_runs_requested_by_user_id", table_name="ai_graph_runs")
    op.drop_index("ix_ai_graph_runs_workspace_id", table_name="ai_graph_runs")
    op.drop_table("ai_graph_runs")
    op.drop_index(
        "checkpoint_writes_thread_id_idx",
        table_name="checkpoint_writes",
    )
    op.drop_table("checkpoint_writes")
    op.drop_index(
        "checkpoint_blobs_thread_id_idx",
        table_name="checkpoint_blobs",
    )
    op.drop_table("checkpoint_blobs")
    op.drop_index("checkpoints_thread_id_idx", table_name="checkpoints")
    op.drop_table("checkpoints")
    op.drop_table("checkpoint_migrations")
