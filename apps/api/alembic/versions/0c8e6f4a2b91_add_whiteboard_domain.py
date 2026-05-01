"""add_whiteboard_domain

Revision ID: 0c8e6f4a2b91
Revises: f0a1b2c3d4e5
Create Date: 2026-05-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0c8e6f4a2b91"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "whiteboards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_app", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("generation_kind", sa.String(length=32), nullable=False),
        sa.Column("scene", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("trashed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_whiteboards_workspace_id"), "whiteboards", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_whiteboards_owner_id"), "whiteboards", ["owner_id"], unique=False)
    op.create_index(op.f("ix_whiteboards_source_app"), "whiteboards", ["source_app"], unique=False)
    op.create_index(op.f("ix_whiteboards_source_kind"), "whiteboards", ["source_kind"], unique=False)
    op.create_index(op.f("ix_whiteboards_source_ref"), "whiteboards", ["source_ref"], unique=False)
    op.create_index(op.f("ix_whiteboards_generation_kind"), "whiteboards", ["generation_kind"], unique=False)
    op.create_index(op.f("ix_whiteboards_trashed_at"), "whiteboards", ["trashed_at"], unique=False)

    op.create_table(
        "whiteboard_containers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("whiteboard_id", sa.String(length=36), nullable=False),
        sa.Column("container_app", sa.String(length=64), nullable=False),
        sa.Column("container_type", sa.String(length=64), nullable=False),
        sa.Column("container_id", sa.String(length=128), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["whiteboard_id"], ["whiteboards.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "whiteboard_id",
            "container_app",
            "container_type",
            "container_id",
            name="uq_whiteboard_containers_board_container",
        ),
    )
    op.create_index(
        op.f("ix_whiteboard_containers_whiteboard_id"),
        "whiteboard_containers",
        ["whiteboard_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whiteboard_containers_container_app"),
        "whiteboard_containers",
        ["container_app"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whiteboard_containers_container_type"),
        "whiteboard_containers",
        ["container_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whiteboard_containers_container_id"),
        "whiteboard_containers",
        ["container_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whiteboard_containers_is_primary"),
        "whiteboard_containers",
        ["is_primary"],
        unique=False,
    )
    op.create_index(
        "ix_whiteboard_containers_lookup",
        "whiteboard_containers",
        ["container_app", "container_type", "container_id"],
        unique=False,
    )
    op.create_index(
        "uq_whiteboard_containers_primary",
        "whiteboard_containers",
        ["whiteboard_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )

    op.create_table(
        "whiteboard_user_item_prefs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("whiteboard_id", sa.String(length=36), nullable=False),
        sa.Column("is_favorite", sa.Boolean(), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["whiteboard_id"], ["whiteboards.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "whiteboard_id", name="uq_whiteboard_user_item_pref"),
    )
    op.create_index(
        op.f("ix_whiteboard_user_item_prefs_user_id"),
        "whiteboard_user_item_prefs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whiteboard_user_item_prefs_whiteboard_id"),
        "whiteboard_user_item_prefs",
        ["whiteboard_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_whiteboard_user_item_prefs_whiteboard_id"), table_name="whiteboard_user_item_prefs")
    op.drop_index(op.f("ix_whiteboard_user_item_prefs_user_id"), table_name="whiteboard_user_item_prefs")
    op.drop_table("whiteboard_user_item_prefs")
    op.drop_index("uq_whiteboard_containers_primary", table_name="whiteboard_containers")
    op.drop_index("ix_whiteboard_containers_lookup", table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_is_primary"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_container_id"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_container_type"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_container_app"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_whiteboard_id"), table_name="whiteboard_containers")
    op.drop_table("whiteboard_containers")
    op.drop_index(op.f("ix_whiteboards_trashed_at"), table_name="whiteboards")
    op.drop_index(op.f("ix_whiteboards_generation_kind"), table_name="whiteboards")
    op.drop_index(op.f("ix_whiteboards_source_ref"), table_name="whiteboards")
    op.drop_index(op.f("ix_whiteboards_source_kind"), table_name="whiteboards")
    op.drop_index(op.f("ix_whiteboards_source_app"), table_name="whiteboards")
    op.drop_index(op.f("ix_whiteboards_owner_id"), table_name="whiteboards")
    op.drop_index(op.f("ix_whiteboards_workspace_id"), table_name="whiteboards")
    op.drop_table("whiteboards")

