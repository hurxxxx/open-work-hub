"""widen_extension_resource_keys

Revision ID: f9a0b1c2d3e4
Revises: e5f6a7b8c9d0
Create Date: 2026-06-02 20:24:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f9a0b1c2d3e4"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "conversations",
        "scope_ref",
        existing_type=sa.String(length=24),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.alter_column(
        "conversations",
        "scope_resource_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "search_index_jobs",
        "entity_type",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.alter_column(
        "search_index_jobs",
        "entity_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "rag_sync_jobs",
        "resource_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "rag_visibility_recompute_jobs",
        "scope_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.execute(
        "DELETE FROM rag_visibility_recompute_jobs "
        "WHERE length(scope_id) > 64"
    )
    op.alter_column(
        "rag_visibility_recompute_jobs",
        "scope_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.execute("DELETE FROM rag_sync_jobs WHERE length(resource_id) > 36")
    op.alter_column(
        "rag_sync_jobs",
        "resource_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
    op.execute(
        "DELETE FROM search_index_jobs "
        "WHERE length(entity_id) > 36 OR length(entity_type) > 32"
    )
    op.alter_column(
        "search_index_jobs",
        "entity_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
    op.alter_column(
        "search_index_jobs",
        "entity_type",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE conversations SET scope_ref = NULL, scope_resource_id = NULL "
        "WHERE length(scope_ref) > 24 OR length(scope_resource_id) > 36"
    )
    op.alter_column(
        "conversations",
        "scope_resource_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=36),
        existing_nullable=True,
    )
    op.alter_column(
        "conversations",
        "scope_ref",
        existing_type=sa.String(length=64),
        type_=sa.String(length=24),
        existing_nullable=True,
    )
