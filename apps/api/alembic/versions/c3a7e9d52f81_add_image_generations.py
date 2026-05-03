"""add image_generations

Revision ID: c3a7e9d52f81
Revises: b6d8a1f4c2e0
Create Date: 2026-05-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3a7e9d52f81"
down_revision: Union[str, Sequence[str], None] = "b6d8a1f4c2e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_generations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column("use_case_other", sa.String(length=200), nullable=False),
        sa.Column("style", sa.JSON(), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("context_refs", sa.JSON(), nullable=False),
        sa.Column("reference_image_keys", sa.JSON(), nullable=False),
        sa.Column("brief_versions", sa.JSON(), nullable=False),
        sa.Column("brief_status", sa.String(length=24), nullable=False),
        sa.Column("image_status", sa.String(length=24), nullable=False),
        sa.Column("image_storage_key", sa.String(length=512), nullable=True),
        sa.Column("image_model", sa.String(length=120), nullable=True),
        sa.Column("agent_trace_id", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("trashed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_image_generations_owner_id"),
        "image_generations",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_generations_workspace_id"),
        "image_generations",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_generations_brief_status"),
        "image_generations",
        ["brief_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_generations_image_status"),
        "image_generations",
        ["image_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_generations_trashed_at"),
        "image_generations",
        ["trashed_at"],
        unique=False,
    )
    op.create_index(
        "ix_image_generations_workspace_owner_created",
        "image_generations",
        ["workspace_id", "owner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_image_generations_workspace_image_status",
        "image_generations",
        ["workspace_id", "image_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_generations_workspace_image_status",
        table_name="image_generations",
    )
    op.drop_index(
        "ix_image_generations_workspace_owner_created",
        table_name="image_generations",
    )
    op.drop_index(
        op.f("ix_image_generations_trashed_at"), table_name="image_generations"
    )
    op.drop_index(
        op.f("ix_image_generations_image_status"), table_name="image_generations"
    )
    op.drop_index(
        op.f("ix_image_generations_brief_status"), table_name="image_generations"
    )
    op.drop_index(
        op.f("ix_image_generations_workspace_id"), table_name="image_generations"
    )
    op.drop_index(op.f("ix_image_generations_owner_id"), table_name="image_generations")
    op.drop_table("image_generations")
