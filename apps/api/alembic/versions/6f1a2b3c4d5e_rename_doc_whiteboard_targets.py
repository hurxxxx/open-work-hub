"""rename_doc_whiteboard_targets

Revision ID: 6f1a2b3c4d5e
Revises: 5c8e1a9d0b2f
Create Date: 2026-06-12 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "5c8e1a9d0b2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_docs_doc_containers_lookup", table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_container_id"), table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_container_type"), table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_container_app"), table_name="docs_doc_containers")
    op.drop_constraint(
        "uq_docs_doc_containers_doc_container",
        "docs_doc_containers",
        type_="unique",
    )
    op.alter_column(
        "docs_doc_containers",
        "container_app",
        new_column_name="target_app",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "docs_doc_containers",
        "container_type",
        new_column_name="target_type",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "docs_doc_containers",
        "container_id",
        new_column_name="target_id",
        existing_type=sa.String(length=128),
    )
    op.create_index(
        op.f("ix_docs_doc_containers_target_app"),
        "docs_doc_containers",
        ["target_app"],
        unique=False,
    )
    op.create_index(
        op.f("ix_docs_doc_containers_target_type"),
        "docs_doc_containers",
        ["target_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_docs_doc_containers_target_id"), "docs_doc_containers", ["target_id"], unique=False
    )
    op.create_index(
        "ix_docs_doc_containers_target_lookup",
        "docs_doc_containers",
        ["target_app", "target_type", "target_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_docs_doc_containers_doc_target",
        "docs_doc_containers",
        ["doc_id", "target_app", "target_type", "target_id"],
    )

    op.drop_index("uq_whiteboard_containers_pms_task_list_slot", table_name="whiteboard_containers")
    op.drop_index("uq_whiteboard_containers_meeting_slot", table_name="whiteboard_containers")
    op.drop_index("ix_whiteboard_containers_lookup", table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_container_id"), table_name="whiteboard_containers")
    op.drop_index(
        op.f("ix_whiteboard_containers_container_type"), table_name="whiteboard_containers"
    )
    op.drop_index(
        op.f("ix_whiteboard_containers_container_app"), table_name="whiteboard_containers"
    )
    op.drop_constraint(
        "uq_whiteboard_containers_board_container",
        "whiteboard_containers",
        type_="unique",
    )
    op.alter_column(
        "whiteboard_containers",
        "container_app",
        new_column_name="target_app",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "whiteboard_containers",
        "container_type",
        new_column_name="target_type",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "whiteboard_containers",
        "container_id",
        new_column_name="target_id",
        existing_type=sa.String(length=128),
    )
    op.create_index(
        op.f("ix_whiteboard_containers_target_app"),
        "whiteboard_containers",
        ["target_app"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whiteboard_containers_target_type"),
        "whiteboard_containers",
        ["target_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whiteboard_containers_target_id"),
        "whiteboard_containers",
        ["target_id"],
        unique=False,
    )
    op.create_index(
        "ix_whiteboard_containers_target_lookup",
        "whiteboard_containers",
        ["target_app", "target_type", "target_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_whiteboard_containers_board_target",
        "whiteboard_containers",
        ["whiteboard_id", "target_app", "target_type", "target_id"],
    )
    op.create_index(
        "uq_whiteboard_containers_meeting_target_slot",
        "whiteboard_containers",
        ["target_app", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("target_app = 'meeting' AND target_type = 'meeting'"),
        sqlite_where=sa.text("target_app = 'meeting' AND target_type = 'meeting'"),
    )
    op.create_index(
        "uq_whiteboard_containers_pms_task_list_target_slot",
        "whiteboard_containers",
        ["target_app", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("target_app = 'pms' AND target_type = 'task_list'"),
        sqlite_where=sa.text("target_app = 'pms' AND target_type = 'task_list'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_whiteboard_containers_pms_task_list_target_slot", table_name="whiteboard_containers"
    )
    op.drop_index(
        "uq_whiteboard_containers_meeting_target_slot", table_name="whiteboard_containers"
    )
    op.drop_constraint(
        "uq_whiteboard_containers_board_target",
        "whiteboard_containers",
        type_="unique",
    )
    op.drop_index("ix_whiteboard_containers_target_lookup", table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_target_id"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_target_type"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_target_app"), table_name="whiteboard_containers")
    op.alter_column(
        "whiteboard_containers",
        "target_id",
        new_column_name="container_id",
        existing_type=sa.String(length=128),
    )
    op.alter_column(
        "whiteboard_containers",
        "target_type",
        new_column_name="container_type",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "whiteboard_containers",
        "target_app",
        new_column_name="container_app",
        existing_type=sa.String(length=64),
    )
    op.create_unique_constraint(
        "uq_whiteboard_containers_board_container",
        "whiteboard_containers",
        ["whiteboard_id", "container_app", "container_type", "container_id"],
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
        "ix_whiteboard_containers_lookup",
        "whiteboard_containers",
        ["container_app", "container_type", "container_id"],
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

    op.drop_constraint(
        "uq_docs_doc_containers_doc_target",
        "docs_doc_containers",
        type_="unique",
    )
    op.drop_index("ix_docs_doc_containers_target_lookup", table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_target_id"), table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_target_type"), table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_target_app"), table_name="docs_doc_containers")
    op.alter_column(
        "docs_doc_containers",
        "target_id",
        new_column_name="container_id",
        existing_type=sa.String(length=128),
    )
    op.alter_column(
        "docs_doc_containers",
        "target_type",
        new_column_name="container_type",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "docs_doc_containers",
        "target_app",
        new_column_name="container_app",
        existing_type=sa.String(length=64),
    )
    op.create_unique_constraint(
        "uq_docs_doc_containers_doc_container",
        "docs_doc_containers",
        ["doc_id", "container_app", "container_type", "container_id"],
    )
    op.create_index(
        op.f("ix_docs_doc_containers_container_app"),
        "docs_doc_containers",
        ["container_app"],
        unique=False,
    )
    op.create_index(
        op.f("ix_docs_doc_containers_container_type"),
        "docs_doc_containers",
        ["container_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_docs_doc_containers_container_id"),
        "docs_doc_containers",
        ["container_id"],
        unique=False,
    )
    op.create_index(
        "ix_docs_doc_containers_lookup",
        "docs_doc_containers",
        ["container_app", "container_type", "container_id"],
        unique=False,
    )
