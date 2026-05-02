"""extend_whiteboard_collaboration

Revision ID: 2a9f4d6c8e10
Revises: 0c8e6f4a2b91
Create Date: 2026-05-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2a9f4d6c8e10"
down_revision: Union[str, Sequence[str], None] = "0c8e6f4a2b91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "whiteboard_containers",
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_whiteboard_containers_created_by_id_users",
        "whiteboard_containers",
        "users",
        ["created_by_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_whiteboard_containers_created_by_id"),
        "whiteboard_containers",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        "uq_whiteboard_containers_meeting_slot",
        "whiteboard_containers",
        ["container_app", "container_type", "container_id"],
        unique=True,
        postgresql_where=sa.text("container_app = 'meeting' AND container_type = 'meeting'"),
        sqlite_where=sa.text("container_app = 'meeting' AND container_type = 'meeting'"),
    )
    op.create_index(
        "uq_whiteboard_containers_pms_task_list_slot",
        "whiteboard_containers",
        ["container_app", "container_type", "container_id"],
        unique=True,
        postgresql_where=sa.text("container_app = 'pms' AND container_type = 'task_list'"),
        sqlite_where=sa.text("container_app = 'pms' AND container_type = 'task_list'"),
    )

    op.create_table(
        "whiteboard_user_shares",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("whiteboard_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("access_level", sa.String(length=16), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["whiteboard_id"], ["whiteboards.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("whiteboard_id", "user_id", name="uq_whiteboard_user_share"),
    )
    op.create_index(op.f("ix_whiteboard_user_shares_created_by_id"), "whiteboard_user_shares", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_whiteboard_user_shares_user_id"), "whiteboard_user_shares", ["user_id"], unique=False)
    op.create_index(op.f("ix_whiteboard_user_shares_whiteboard_id"), "whiteboard_user_shares", ["whiteboard_id"], unique=False)

    op.create_table(
        "whiteboard_link_shares",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("whiteboard_id", sa.String(length=36), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("access_level", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["whiteboard_id"], ["whiteboards.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("whiteboard_id", name="uq_whiteboard_link_share_board"),
    )
    op.create_index(op.f("ix_whiteboard_link_shares_active"), "whiteboard_link_shares", ["active"], unique=False)
    op.create_index(op.f("ix_whiteboard_link_shares_created_by_id"), "whiteboard_link_shares", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_whiteboard_link_shares_token"), "whiteboard_link_shares", ["token"], unique=True)
    op.create_index(op.f("ix_whiteboard_link_shares_whiteboard_id"), "whiteboard_link_shares", ["whiteboard_id"], unique=False)

    op.create_table(
        "whiteboard_collab_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_key", sa.String(length=128), nullable=False),
        sa.Column("whiteboard_id", sa.String(length=36), nullable=False),
        sa.Column("yjs_state", sa.LargeBinary(), nullable=True),
        sa.Column("snapshot_scene", sa.JSON(), nullable=True),
        sa.Column("last_snapshot_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["whiteboard_id"], ["whiteboards.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_key", name="uq_whiteboard_collab_documents_room_key"),
        sa.UniqueConstraint("whiteboard_id", name="uq_whiteboard_collab_documents_board"),
    )
    op.create_index(op.f("ix_whiteboard_collab_documents_whiteboard_id"), "whiteboard_collab_documents", ["whiteboard_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_whiteboard_collab_documents_whiteboard_id"), table_name="whiteboard_collab_documents")
    op.drop_table("whiteboard_collab_documents")
    op.drop_index(op.f("ix_whiteboard_link_shares_whiteboard_id"), table_name="whiteboard_link_shares")
    op.drop_index(op.f("ix_whiteboard_link_shares_token"), table_name="whiteboard_link_shares")
    op.drop_index(op.f("ix_whiteboard_link_shares_created_by_id"), table_name="whiteboard_link_shares")
    op.drop_index(op.f("ix_whiteboard_link_shares_active"), table_name="whiteboard_link_shares")
    op.drop_table("whiteboard_link_shares")
    op.drop_index(op.f("ix_whiteboard_user_shares_whiteboard_id"), table_name="whiteboard_user_shares")
    op.drop_index(op.f("ix_whiteboard_user_shares_user_id"), table_name="whiteboard_user_shares")
    op.drop_index(op.f("ix_whiteboard_user_shares_created_by_id"), table_name="whiteboard_user_shares")
    op.drop_table("whiteboard_user_shares")
    op.drop_index("uq_whiteboard_containers_pms_task_list_slot", table_name="whiteboard_containers")
    op.drop_index("uq_whiteboard_containers_meeting_slot", table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_created_by_id"), table_name="whiteboard_containers")
    op.drop_constraint("fk_whiteboard_containers_created_by_id_users", "whiteboard_containers", type_="foreignkey")
    op.drop_column("whiteboard_containers", "created_by_id")
