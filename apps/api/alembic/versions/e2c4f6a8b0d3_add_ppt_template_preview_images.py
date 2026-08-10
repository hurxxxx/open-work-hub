"""add ppt template preview images

Revision ID: e2c4f6a8b0d3
Revises: c1d2e3f4a6b8
Create Date: 2026-06-23 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e2c4f6a8b0d3"
down_revision: str | Sequence[str] | None = "c1d2e3f4a6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    if not _table_exists("ppt_template_preview_images"):
        op.create_table(
            "ppt_template_preview_images",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("family_id", sa.String(length=40), nullable=False),
            sa.Column("media_id", sa.String(length=36), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("uploaded_by_id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["media_id"], ["media_files.id"]),
            sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("media_id"),
        )
    for index_name, columns in {
        "ix_ppt_template_preview_images_family_id": ["family_id"],
        "ix_ppt_template_preview_images_uploaded_by_id": ["uploaded_by_id"],
        "ix_ppt_template_preview_images_workspace_id": ["workspace_id"],
        "ix_ppt_template_preview_images_workspace_family_sort": [
            "workspace_id",
            "family_id",
            "deleted_at",
            "sort_order",
        ],
    }.items():
        if not _index_exists("ppt_template_preview_images", index_name):
            op.create_index(
                index_name,
                "ppt_template_preview_images",
                columns,
                unique=False,
            )


def downgrade() -> None:
    if not _table_exists("ppt_template_preview_images"):
        return
    for index_name in (
        "ix_ppt_template_preview_images_workspace_family_sort",
        "ix_ppt_template_preview_images_workspace_id",
        "ix_ppt_template_preview_images_uploaded_by_id",
        "ix_ppt_template_preview_images_family_id",
    ):
        if _index_exists("ppt_template_preview_images", index_name):
            op.drop_index(index_name, table_name="ppt_template_preview_images")
    op.drop_table("ppt_template_preview_images")
