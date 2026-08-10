"""add ppt generator jobs

Revision ID: b3c4d5e6f8a9
Revises: e2b3c4d5e6f7
Create Date: 2026-06-23 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f8a9"
down_revision: str | Sequence[str] | None = "e2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _table_exists("ppt_jobs"):
        op.create_table(
            "ppt_jobs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("family", sa.String(length=40), nullable=False),
            sa.Column("aspect", sa.String(length=8), nullable=False),
            sa.Column("n_slides", sa.Integer(), nullable=False),
            sa.Column("params", sa.JSON(), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("slides_spec", sa.JSON(), nullable=True),
            sa.Column("pptx_key", sa.String(length=512), nullable=True),
            sa.Column("preview_count", sa.Integer(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("celery_task_id", sa.String(length=80), nullable=True),
            sa.Column("chat_result", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_ppt_jobs_celery_task_id",
        "ppt_jobs",
        ["celery_task_id"],
    )
    _create_index_if_missing("ix_ppt_jobs_status", "ppt_jobs", ["status"])
    _create_index_if_missing("ix_ppt_jobs_user_id", "ppt_jobs", ["user_id"])
    _create_index_if_missing("ix_ppt_jobs_workspace_id", "ppt_jobs", ["workspace_id"])
    _create_index_if_missing(
        "ix_ppt_jobs_workspace_status",
        "ppt_jobs",
        ["workspace_id", "status"],
    )
    _create_index_if_missing(
        "ix_ppt_jobs_workspace_user_created",
        "ppt_jobs",
        ["workspace_id", "user_id", "created_at"],
    )


def downgrade() -> None:
    if not _table_exists("ppt_jobs"):
        return
    for index_name in (
        "ix_ppt_jobs_workspace_user_created",
        "ix_ppt_jobs_workspace_status",
        "ix_ppt_jobs_workspace_id",
        "ix_ppt_jobs_user_id",
        "ix_ppt_jobs_status",
        "ix_ppt_jobs_celery_task_id",
    ):
        if _index_exists("ppt_jobs", index_name):
            op.drop_index(index_name, table_name="ppt_jobs")
    op.drop_table("ppt_jobs")
