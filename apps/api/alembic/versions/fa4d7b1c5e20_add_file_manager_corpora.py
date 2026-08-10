"""Add source-owned File Manager corpora.

Revision ID: fa4d7b1c5e20
Revises: e9c3f6a0b4d8
Create Date: 2026-07-22 21:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "fa4d7b1c5e20"
down_revision = "e9c3f6a0b4d8"
branch_labels = None
depends_on = None


_CHILD_TABLES = ("file_manager_folders", "file_manager_files")
_POSTGRESQL_LOCK_TIMEOUT = "5s"


def upgrade() -> None:
    _set_postgresql_lock_timeout()
    op.create_table(
        "file_manager_corpora",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("managed_workspace_id", sa.String(length=36), nullable=False),
        sa.Column(
            "access_scope_kind",
            sa.String(length=16),
            server_default=sa.text("'workspace'"),
            nullable=False,
        ),
        sa.Column("retrieval_partition_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column(
            "metadata_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "access_scope_kind IN ('workspace','company')",
            name="ck_file_manager_corpora_access_scope_kind",
        ),
        sa.CheckConstraint(
            "metadata_version >= 1",
            name="ck_file_manager_corpora_metadata_version",
        ),
        sa.ForeignKeyConstraint(
            ["managed_workspace_id"],
            ["workspaces.id"],
            name="fk_file_corpora_managed_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_partition_id"],
            ["retrieval_partitions.id"],
            name="fk_file_corpora_partition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_file_corpora_created_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "retrieval_partition_id",
            name="uq_file_manager_corpora_retrieval_partition_id",
        ),
    )
    op.create_index(
        op.f("ix_file_manager_corpora_managed_workspace_id"),
        "file_manager_corpora",
        ["managed_workspace_id"],
    )
    op.create_index(
        op.f("ix_file_manager_corpora_access_scope_kind"),
        "file_manager_corpora",
        ["access_scope_kind"],
    )
    op.create_index(
        op.f("ix_file_manager_corpora_created_by_id"),
        "file_manager_corpora",
        ["created_by_id"],
    )
    op.create_index(
        "ix_file_manager_corpora_workspace_scope",
        "file_manager_corpora",
        ["managed_workspace_id", "access_scope_kind"],
    )

    for table_name in _CHILD_TABLES:
        _add_corpus_reference(table_name)

    op.create_table(
        "file_manager_corpus_transition_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("corpus_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("from_access_scope_kind", sa.String(length=16), nullable=False),
        sa.Column("to_access_scope_kind", sa.String(length=16), nullable=False),
        sa.Column("from_managed_workspace_id", sa.String(length=36), nullable=False),
        sa.Column("to_managed_workspace_id", sa.String(length=36), nullable=False),
        sa.Column("from_metadata_version", sa.Integer(), nullable=False),
        sa.Column("to_metadata_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "from_access_scope_kind IN ('workspace','company')",
            name="ck_file_manager_corpus_transition_audits_from_scope",
        ),
        sa.CheckConstraint(
            "to_access_scope_kind IN ('workspace','company')",
            name="ck_file_manager_corpus_transition_audits_to_scope",
        ),
        sa.CheckConstraint(
            "from_metadata_version >= 1 AND to_metadata_version > from_metadata_version",
            name="ck_file_manager_corpus_transition_audits_versions",
        ),
        sa.ForeignKeyConstraint(
            ["corpus_id"],
            ["file_manager_corpora.id"],
            name="fk_file_corpus_audits_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_file_corpus_audits_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["from_managed_workspace_id"],
            ["workspaces.id"],
            name="fk_file_corpus_audits_from_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_managed_workspace_id"],
            ["workspaces.id"],
            name="fk_file_corpus_audits_to_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_file_manager_corpus_transition_audits_corpus_id"),
        "file_manager_corpus_transition_audits",
        ["corpus_id"],
    )
    op.create_index(
        op.f("ix_file_manager_corpus_transition_audits_actor_id"),
        "file_manager_corpus_transition_audits",
        ["actor_id"],
    )
    op.create_index(
        op.f("ix_file_manager_corpus_transition_audits_request_id"),
        "file_manager_corpus_transition_audits",
        ["request_id"],
    )
    op.create_index(
        "ix_file_corpus_transition_audits_corpus_created",
        "file_manager_corpus_transition_audits",
        ["corpus_id", "created_at"],
    )


def downgrade() -> None:
    _set_postgresql_lock_timeout()
    op.drop_index(
        "ix_file_corpus_transition_audits_corpus_created",
        table_name="file_manager_corpus_transition_audits",
    )
    op.drop_index(
        op.f("ix_file_manager_corpus_transition_audits_request_id"),
        table_name="file_manager_corpus_transition_audits",
    )
    op.drop_index(
        op.f("ix_file_manager_corpus_transition_audits_actor_id"),
        table_name="file_manager_corpus_transition_audits",
    )
    op.drop_index(
        op.f("ix_file_manager_corpus_transition_audits_corpus_id"),
        table_name="file_manager_corpus_transition_audits",
    )
    op.drop_table("file_manager_corpus_transition_audits")
    for table_name in reversed(_CHILD_TABLES):
        _drop_corpus_reference(table_name)
    op.drop_index(
        "ix_file_manager_corpora_workspace_scope",
        table_name="file_manager_corpora",
    )
    op.drop_index(
        op.f("ix_file_manager_corpora_created_by_id"),
        table_name="file_manager_corpora",
    )
    op.drop_index(
        op.f("ix_file_manager_corpora_access_scope_kind"),
        table_name="file_manager_corpora",
    )
    op.drop_index(
        op.f("ix_file_manager_corpora_managed_workspace_id"),
        table_name="file_manager_corpora",
    )
    op.drop_table("file_manager_corpora")


def _add_corpus_reference(table_name: str) -> None:
    constraint_name = f"fk_{table_name}_corpus_id_file_manager_corpora"
    if op.get_bind().dialect.name == "postgresql":
        op.add_column(table_name, sa.Column("corpus_id", sa.String(length=36), nullable=True))
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
                "FOREIGN KEY (corpus_id) REFERENCES file_manager_corpora (id) "
                "ON DELETE RESTRICT NOT VALID"
            )
        )
        # Existing PostgreSQL tables receive these indexes concurrently in the
        # following fb5e revision.  Keeping the operation out of this
        # transaction prevents upload/browse writers from being blocked while
        # the index scans a populated Files table.
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(sa.Column("corpus_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            constraint_name,
            "file_manager_corpora",
            ["corpus_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(op.f(f"ix_{table_name}_corpus_id"), table_name, ["corpus_id"])


def _drop_corpus_reference(table_name: str) -> None:
    constraint_name = f"fk_{table_name}_corpus_id_file_manager_corpora"
    if op.get_bind().dialect.name == "postgresql":
        # fb5e normally removes the concurrent index first.  DROP COLUMN also
        # removes a leftover index from a partially completed fb5e attempt.
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
        op.drop_column(table_name, "corpus_id")
        return
    op.drop_index(op.f(f"ix_{table_name}_corpus_id"), table_name=table_name)
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_constraint(constraint_name, type_="foreignkey")
        batch_op.drop_column("corpus_id")


def _set_postgresql_lock_timeout() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"SET LOCAL lock_timeout = '{_POSTGRESQL_LOCK_TIMEOUT}'"))
