"""add retrieval partition directory and nullable bindings

Revision ID: c7a1d4e8f2b6
Revises: b6d9e2f4a7c1
Create Date: 2026-07-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c7a1d4e8f2b6"
down_revision: str | Sequence[str] | None = "b6d9e2f4a7c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PARTITION_REFERENCE_TABLES = (
    "docs_native_docs",
    "file_manager_folders",
    "file_manager_files",
    "meetings",
    "pms_tasks",
    "planner_events",
    "qna_documents",
    "knowledge_source_documents",
    "legacy_issue_records",
    "legacy_issue_data_revisions",
    "legacy_issue_attachments",
    "legacy_issue_ai_chunks",
    "rag_sync_jobs",
    "search_index_jobs",
    "legacy_issue_attachment_index_jobs",
)
_POSTGRESQL_LOCK_TIMEOUT = "5s"


def upgrade() -> None:
    _set_postgresql_lock_timeout()
    op.create_table(
        "retrieval_partitions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_namespace", sa.String(length=80), nullable=False),
        sa.Column("managed_workspace_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_scope_kind", sa.String(length=16), nullable=False),
        sa.Column("candidate_workspace_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "state",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "metadata_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "is_default_ingest",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "candidate_scope_kind IN ('company','workspace','personal')",
            name="ck_retrieval_partitions_candidate_scope_kind",
        ),
        sa.CheckConstraint(
            "state IN ('active','transitioning','retired')",
            name="ck_retrieval_partitions_state",
        ),
        sa.CheckConstraint(
            "metadata_version >= 1",
            name="ck_retrieval_partitions_metadata_version",
        ),
        sa.CheckConstraint(
            "(candidate_scope_kind = 'company' "
            "AND candidate_workspace_id IS NULL AND candidate_user_id IS NULL) "
            "OR (candidate_scope_kind = 'workspace' "
            "AND candidate_workspace_id IS NOT NULL AND candidate_user_id IS NULL) "
            "OR (candidate_scope_kind = 'personal' "
            "AND candidate_workspace_id IS NULL AND candidate_user_id IS NOT NULL)",
            name="ck_retrieval_partitions_candidate_target",
        ),
        sa.CheckConstraint(
            "state <> 'retired' OR is_default_ingest IS FALSE",
            name="ck_retrieval_partitions_retired_not_default",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_workspace_id"],
            ["workspaces.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["managed_workspace_id"],
            ["workspaces.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "source_namespace",
        "managed_workspace_id",
        "candidate_scope_kind",
        "candidate_workspace_id",
        "candidate_user_id",
        "state",
    ):
        op.create_index(
            op.f(f"ix_retrieval_partitions_{column}"),
            "retrieval_partitions",
            [column],
        )
    op.create_index(
        "ix_retrieval_partitions_namespace_state",
        "retrieval_partitions",
        ["source_namespace", "state"],
    )
    op.create_index(
        "ix_retrieval_partitions_candidate_workspace",
        "retrieval_partitions",
        ["candidate_scope_kind", "candidate_workspace_id", "state"],
    )
    op.create_index(
        "ix_retrieval_partitions_candidate_user",
        "retrieval_partitions",
        ["candidate_scope_kind", "candidate_user_id", "state"],
    )
    op.create_index(
        "uq_retrieval_partitions_default_managed_workspace",
        "retrieval_partitions",
        ["source_namespace", "managed_workspace_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_default_ingest IS TRUE AND state <> 'retired' "
            "AND managed_workspace_id IS NOT NULL AND candidate_user_id IS NULL"
        ),
        sqlite_where=sa.text(
            "is_default_ingest = 1 AND state <> 'retired' "
            "AND managed_workspace_id IS NOT NULL AND candidate_user_id IS NULL"
        ),
    )
    op.create_index(
        "uq_retrieval_partitions_default_company",
        "retrieval_partitions",
        ["source_namespace"],
        unique=True,
        postgresql_where=sa.text(
            "is_default_ingest IS TRUE AND state <> 'retired' "
            "AND managed_workspace_id IS NULL AND candidate_scope_kind = 'company'"
        ),
        sqlite_where=sa.text(
            "is_default_ingest = 1 AND state <> 'retired' "
            "AND managed_workspace_id IS NULL AND candidate_scope_kind = 'company'"
        ),
    )
    op.create_index(
        "uq_retrieval_partitions_default_personal",
        "retrieval_partitions",
        ["source_namespace", "candidate_user_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_default_ingest IS TRUE AND state <> 'retired' "
            "AND candidate_scope_kind = 'personal' AND candidate_user_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "is_default_ingest = 1 AND state <> 'retired' "
            "AND candidate_scope_kind = 'personal' AND candidate_user_id IS NOT NULL"
        ),
    )
    _create_partition_id_immutability_trigger()

    # Expand-only: old API/worker binaries keep writing while this migration runs.
    # Backfill, index creation, FK validation, and NOT NULL enforcement belong to
    # later resumable backfill/contract releases.
    for table_name in _PARTITION_REFERENCE_TABLES:
        _add_partition_reference(table_name)


def downgrade() -> None:
    _set_postgresql_lock_timeout()
    for table_name in reversed(_PARTITION_REFERENCE_TABLES):
        _drop_partition_reference(table_name)
    _drop_partition_id_immutability_trigger()
    op.drop_table("retrieval_partitions")


def _add_partition_reference(table_name: str) -> None:
    constraint_name = f"fk_{table_name}_retrieval_partition_id"
    op.add_column(
        table_name,
        sa.Column(
            "retrieval_partition_id",
            sa.Uuid(as_uuid=False),
            nullable=True,
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
                "FOREIGN KEY (retrieval_partition_id) "
                "REFERENCES retrieval_partitions (id) ON DELETE RESTRICT NOT VALID"
            )
        )
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.create_foreign_key(
            constraint_name,
            "retrieval_partitions",
            ["retrieval_partition_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def _drop_partition_reference(table_name: str) -> None:
    constraint_name = f"fk_{table_name}_retrieval_partition_id"
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
        op.drop_column(table_name, "retrieval_partition_id")
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_constraint(constraint_name, type_="foreignkey")
        batch_op.drop_column("retrieval_partition_id")


def _create_partition_id_immutability_trigger() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION reject_retrieval_partition_id_update()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF NEW.id IS DISTINCT FROM OLD.id THEN
                        RAISE EXCEPTION 'retrieval partition id is immutable'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_retrieval_partitions_immutable_id
                BEFORE UPDATE OF id ON retrieval_partitions
                FOR EACH ROW
                EXECUTE FUNCTION reject_retrieval_partition_id_update()
                """
            )
        )
        return
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_retrieval_partitions_immutable_id
            BEFORE UPDATE OF id ON retrieval_partitions
            FOR EACH ROW WHEN NEW.id <> OLD.id
            BEGIN
                SELECT RAISE(ABORT, 'retrieval partition id is immutable');
            END
            """
        )
    )


def _drop_partition_id_immutability_trigger() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_retrieval_partitions_immutable_id "
                "ON retrieval_partitions"
            )
        )
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_retrieval_partition_id_update()"))
        return
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_retrieval_partitions_immutable_id"))


def _set_postgresql_lock_timeout() -> None:
    """Fail the transaction instead of waiting indefinitely on active writers."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"SET LOCAL lock_timeout = '{_POSTGRESQL_LOCK_TIMEOUT}'"))
