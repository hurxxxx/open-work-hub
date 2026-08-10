"""add_file_manager

Revision ID: 2f4c6d8e1a90
Revises: e3f4a5b6c7d8
Create Date: 2026-05-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2f4c6d8e1a90"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "file_manager_folders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("visibility", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "visibility IN ('private','workspace')",
            name="ck_file_manager_folders_visibility",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["file_manager_folders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_file_manager_folders_workspace_parent",
        "file_manager_folders",
        ["workspace_id", "parent_id"],
    )
    op.create_index(
        "ix_file_manager_folders_workspace_owner",
        "file_manager_folders",
        ["workspace_id", "owner_id"],
    )
    op.create_index(
        "ix_file_manager_folders_workspace_visibility",
        "file_manager_folders",
        ["workspace_id", "visibility"],
    )
    op.create_index(
        op.f("ix_file_manager_folders_workspace_id"),
        "file_manager_folders",
        ["workspace_id"],
    )
    op.create_index(op.f("ix_file_manager_folders_parent_id"), "file_manager_folders", ["parent_id"])
    op.create_index(op.f("ix_file_manager_folders_owner_id"), "file_manager_folders", ["owner_id"])
    op.create_index(
        op.f("ix_file_manager_folders_deleted_at"),
        "file_manager_folders",
        ["deleted_at"],
    )

    op.create_table(
        "file_manager_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("folder_id", sa.String(length=36), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("visibility", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "visibility IN ('private','workspace')",
            name="ck_file_manager_files_visibility",
        ),
        sa.ForeignKeyConstraint(["folder_id"], ["file_manager_folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_file_manager_files_workspace_folder",
        "file_manager_files",
        ["workspace_id", "folder_id"],
    )
    op.create_index(
        "ix_file_manager_files_workspace_owner",
        "file_manager_files",
        ["workspace_id", "owner_id"],
    )
    op.create_index(
        "ix_file_manager_files_workspace_visibility",
        "file_manager_files",
        ["workspace_id", "visibility"],
    )
    op.create_index(
        op.f("ix_file_manager_files_workspace_id"),
        "file_manager_files",
        ["workspace_id"],
    )
    op.create_index(op.f("ix_file_manager_files_folder_id"), "file_manager_files", ["folder_id"])
    op.create_index(op.f("ix_file_manager_files_owner_id"), "file_manager_files", ["owner_id"])
    op.create_index(
        op.f("ix_file_manager_files_deleted_at"),
        "file_manager_files",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_file_manager_files_deleted_at"), table_name="file_manager_files")
    op.drop_index(op.f("ix_file_manager_files_owner_id"), table_name="file_manager_files")
    op.drop_index(op.f("ix_file_manager_files_folder_id"), table_name="file_manager_files")
    op.drop_index(op.f("ix_file_manager_files_workspace_id"), table_name="file_manager_files")
    op.drop_index("ix_file_manager_files_workspace_visibility", table_name="file_manager_files")
    op.drop_index("ix_file_manager_files_workspace_owner", table_name="file_manager_files")
    op.drop_index("ix_file_manager_files_workspace_folder", table_name="file_manager_files")
    op.drop_table("file_manager_files")

    op.drop_index(op.f("ix_file_manager_folders_deleted_at"), table_name="file_manager_folders")
    op.drop_index(op.f("ix_file_manager_folders_owner_id"), table_name="file_manager_folders")
    op.drop_index(op.f("ix_file_manager_folders_parent_id"), table_name="file_manager_folders")
    op.drop_index(op.f("ix_file_manager_folders_workspace_id"), table_name="file_manager_folders")
    op.drop_index(
        "ix_file_manager_folders_workspace_visibility",
        table_name="file_manager_folders",
    )
    op.drop_index("ix_file_manager_folders_workspace_owner", table_name="file_manager_folders")
    op.drop_index("ix_file_manager_folders_workspace_parent", table_name="file_manager_folders")
    op.drop_table("file_manager_folders")
