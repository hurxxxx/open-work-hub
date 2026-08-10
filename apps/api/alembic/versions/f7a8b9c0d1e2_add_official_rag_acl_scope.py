"""add_official_rag_acl_scope

Revision ID: f7a8b9c0d1e2
Revises: e4b7c9d1a2f3
Create Date: 2026-05-25 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "e4b7c9d1a2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "org_units",
        sa.Column(
            "unit_type",
            sa.String(length=24),
            nullable=False,
            server_default="division",
        ),
    )
    op.create_check_constraint(
        "ck_org_units_unit_type",
        "org_units",
        "unit_type IN ('group', 'division')",
    )
    op.create_index(op.f("ix_org_units_unit_type"), "org_units", ["unit_type"], unique=False)
    op.alter_column("org_units", "unit_type", server_default=None)

    op.add_column("teams", sa.Column("org_unit_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_teams_org_unit_id_org_units",
        "teams",
        "org_units",
        ["org_unit_id"],
        ["id"],
    )
    op.create_index(op.f("ix_teams_org_unit_id"), "teams", ["org_unit_id"], unique=False)

    op.add_column(
        "docs_native_docs",
        sa.Column(
            "rag_scope",
            sa.String(length=24),
            nullable=False,
            server_default="official",
        ),
    )
    op.create_check_constraint(
        "ck_docs_native_docs_rag_scope",
        "docs_native_docs",
        "rag_scope IN ('official', 'personal', 'excluded')",
    )
    op.create_index(
        op.f("ix_docs_native_docs_rag_scope"),
        "docs_native_docs",
        ["rag_scope"],
        unique=False,
    )
    op.execute(
        sa.text(
            "UPDATE docs_native_docs SET rag_scope = 'personal' "
            "WHERE source_app = 'learning' "
            "OR source_kind IN ('lesson_note_public', 'lesson_note_private')"
        )
    )
    op.alter_column("docs_native_docs", "rag_scope", server_default=None)

    op.add_column(
        "knowledge_source_documents",
        sa.Column("access_scope_kind", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "knowledge_source_documents",
        sa.Column("access_scope_id", sa.String(length=80), nullable=True),
    )
    op.create_check_constraint(
        "ck_knowledge_docs_access_scope_kind",
        "knowledge_source_documents",
        "access_scope_kind IS NULL OR access_scope_kind IN ('workspace', 'org_unit', 'team', 'user')",
    )
    op.create_index(
        op.f("ix_knowledge_source_documents_access_scope_kind"),
        "knowledge_source_documents",
        ["access_scope_kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_source_documents_access_scope_id"),
        "knowledge_source_documents",
        ["access_scope_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_docs_access_scope",
        "knowledge_source_documents",
        ["workspace_id", "access_scope_kind", "access_scope_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_docs_access_scope", table_name="knowledge_source_documents")
    op.drop_index(
        op.f("ix_knowledge_source_documents_access_scope_id"),
        table_name="knowledge_source_documents",
    )
    op.drop_index(
        op.f("ix_knowledge_source_documents_access_scope_kind"),
        table_name="knowledge_source_documents",
    )
    op.drop_constraint(
        "ck_knowledge_docs_access_scope_kind",
        "knowledge_source_documents",
        type_="check",
    )
    op.drop_column("knowledge_source_documents", "access_scope_id")
    op.drop_column("knowledge_source_documents", "access_scope_kind")

    op.drop_index(op.f("ix_docs_native_docs_rag_scope"), table_name="docs_native_docs")
    op.drop_constraint("ck_docs_native_docs_rag_scope", "docs_native_docs", type_="check")
    op.drop_column("docs_native_docs", "rag_scope")

    op.drop_index(op.f("ix_teams_org_unit_id"), table_name="teams")
    op.drop_constraint("fk_teams_org_unit_id_org_units", "teams", type_="foreignkey")
    op.drop_column("teams", "org_unit_id")

    op.drop_index(op.f("ix_org_units_unit_type"), table_name="org_units")
    op.drop_constraint("ck_org_units_unit_type", "org_units", type_="check")
    op.drop_column("org_units", "unit_type")
