"""rename_target_tables_and_recording_targets

Revision ID: 7a8b9c0d1e2f
Revises: 6f1a2b3c4d5e
Create Date: 2026-06-12 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "6f1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    _rename_docs_targets()
    _rename_whiteboard_targets()
    _rename_recording_targets()


def downgrade() -> None:
    _restore_recording_containers()
    _restore_whiteboard_containers()
    _restore_docs_containers()


def _rename_docs_targets() -> None:
    op.drop_index("ix_docs_doc_containers_target_lookup", table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_target_app"), table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_target_type"), table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_target_id"), table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_doc_id"), table_name="docs_doc_containers")
    op.drop_index(op.f("ix_docs_doc_containers_is_primary"), table_name="docs_doc_containers")
    op.drop_index("uq_docs_doc_containers_primary", table_name="docs_doc_containers")
    op.drop_constraint(
        "uq_docs_doc_containers_doc_target",
        "docs_doc_containers",
        type_="unique",
    )
    op.rename_table("docs_doc_containers", "docs_doc_targets")
    op.create_index(op.f("ix_docs_doc_targets_doc_id"), "docs_doc_targets", ["doc_id"])
    op.create_index(
        op.f("ix_docs_doc_targets_target_app"), "docs_doc_targets", ["target_app"]
    )
    op.create_index(
        op.f("ix_docs_doc_targets_target_type"), "docs_doc_targets", ["target_type"]
    )
    op.create_index(op.f("ix_docs_doc_targets_target_id"), "docs_doc_targets", ["target_id"])
    op.create_index(
        op.f("ix_docs_doc_targets_is_primary"), "docs_doc_targets", ["is_primary"]
    )
    op.create_index(
        "ix_docs_doc_targets_target_lookup",
        "docs_doc_targets",
        ["target_app", "target_type", "target_id"],
    )
    op.create_index(
        "uq_docs_doc_targets_primary",
        "docs_doc_targets",
        ["doc_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_unique_constraint(
        "uq_docs_doc_targets_doc_target",
        "docs_doc_targets",
        ["doc_id", "target_app", "target_type", "target_id"],
    )


def _restore_docs_containers() -> None:
    op.drop_constraint("uq_docs_doc_targets_doc_target", "docs_doc_targets", type_="unique")
    op.drop_index("uq_docs_doc_targets_primary", table_name="docs_doc_targets")
    op.drop_index("ix_docs_doc_targets_target_lookup", table_name="docs_doc_targets")
    op.drop_index(op.f("ix_docs_doc_targets_is_primary"), table_name="docs_doc_targets")
    op.drop_index(op.f("ix_docs_doc_targets_target_id"), table_name="docs_doc_targets")
    op.drop_index(op.f("ix_docs_doc_targets_target_type"), table_name="docs_doc_targets")
    op.drop_index(op.f("ix_docs_doc_targets_target_app"), table_name="docs_doc_targets")
    op.drop_index(op.f("ix_docs_doc_targets_doc_id"), table_name="docs_doc_targets")
    op.rename_table("docs_doc_targets", "docs_doc_containers")
    op.create_index(op.f("ix_docs_doc_containers_doc_id"), "docs_doc_containers", ["doc_id"])
    op.create_index(
        op.f("ix_docs_doc_containers_target_app"), "docs_doc_containers", ["target_app"]
    )
    op.create_index(
        op.f("ix_docs_doc_containers_target_type"), "docs_doc_containers", ["target_type"]
    )
    op.create_index(
        op.f("ix_docs_doc_containers_target_id"), "docs_doc_containers", ["target_id"]
    )
    op.create_index(
        op.f("ix_docs_doc_containers_is_primary"), "docs_doc_containers", ["is_primary"]
    )
    op.create_index(
        "ix_docs_doc_containers_target_lookup",
        "docs_doc_containers",
        ["target_app", "target_type", "target_id"],
    )
    op.create_index(
        "uq_docs_doc_containers_primary",
        "docs_doc_containers",
        ["doc_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_unique_constraint(
        "uq_docs_doc_containers_doc_target",
        "docs_doc_containers",
        ["doc_id", "target_app", "target_type", "target_id"],
    )


def _rename_whiteboard_targets() -> None:
    op.drop_index(
        "uq_whiteboard_containers_pms_task_list_target_slot",
        table_name="whiteboard_containers",
    )
    op.drop_index("uq_whiteboard_containers_meeting_target_slot", table_name="whiteboard_containers")
    op.drop_index("ix_whiteboard_containers_target_lookup", table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_target_app"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_target_type"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_target_id"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_whiteboard_id"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_is_primary"), table_name="whiteboard_containers")
    op.drop_index(op.f("ix_whiteboard_containers_created_by_id"), table_name="whiteboard_containers")
    op.drop_index("uq_whiteboard_containers_primary", table_name="whiteboard_containers")
    op.drop_constraint(
        "uq_whiteboard_containers_board_target",
        "whiteboard_containers",
        type_="unique",
    )
    op.drop_constraint(
        "fk_whiteboard_containers_created_by_id_users",
        "whiteboard_containers",
        type_="foreignkey",
    )
    op.rename_table("whiteboard_containers", "whiteboard_targets")
    op.create_foreign_key(
        "fk_whiteboard_targets_created_by_id_users",
        "whiteboard_targets",
        "users",
        ["created_by_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_whiteboard_targets_whiteboard_id"), "whiteboard_targets", ["whiteboard_id"]
    )
    op.create_index(
        op.f("ix_whiteboard_targets_target_app"), "whiteboard_targets", ["target_app"]
    )
    op.create_index(
        op.f("ix_whiteboard_targets_target_type"), "whiteboard_targets", ["target_type"]
    )
    op.create_index(op.f("ix_whiteboard_targets_target_id"), "whiteboard_targets", ["target_id"])
    op.create_index(
        op.f("ix_whiteboard_targets_is_primary"), "whiteboard_targets", ["is_primary"]
    )
    op.create_index(
        op.f("ix_whiteboard_targets_created_by_id"), "whiteboard_targets", ["created_by_id"]
    )
    op.create_index(
        "ix_whiteboard_targets_target_lookup",
        "whiteboard_targets",
        ["target_app", "target_type", "target_id"],
    )
    op.create_index(
        "uq_whiteboard_targets_primary",
        "whiteboard_targets",
        ["whiteboard_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
        sqlite_where=sa.text("is_primary IS TRUE"),
    )
    op.create_unique_constraint(
        "uq_whiteboard_targets_board_target",
        "whiteboard_targets",
        ["whiteboard_id", "target_app", "target_type", "target_id"],
    )
    op.create_index(
        "uq_whiteboard_targets_meeting_target_slot",
        "whiteboard_targets",
        ["target_app", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("target_app = 'meeting' AND target_type = 'meeting'"),
        sqlite_where=sa.text("target_app = 'meeting' AND target_type = 'meeting'"),
    )
    op.create_index(
        "uq_whiteboard_targets_pms_task_list_target_slot",
        "whiteboard_targets",
        ["target_app", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("target_app = 'pms' AND target_type = 'task_list'"),
        sqlite_where=sa.text("target_app = 'pms' AND target_type = 'task_list'"),
    )


def _restore_whiteboard_containers() -> None:
    op.drop_index("uq_whiteboard_targets_pms_task_list_target_slot", table_name="whiteboard_targets")
    op.drop_index("uq_whiteboard_targets_meeting_target_slot", table_name="whiteboard_targets")
    op.drop_constraint("uq_whiteboard_targets_board_target", "whiteboard_targets", type_="unique")
    op.drop_index("uq_whiteboard_targets_primary", table_name="whiteboard_targets")
    op.drop_index("ix_whiteboard_targets_target_lookup", table_name="whiteboard_targets")
    op.drop_index(op.f("ix_whiteboard_targets_created_by_id"), table_name="whiteboard_targets")
    op.drop_index(op.f("ix_whiteboard_targets_is_primary"), table_name="whiteboard_targets")
    op.drop_index(op.f("ix_whiteboard_targets_target_id"), table_name="whiteboard_targets")
    op.drop_index(op.f("ix_whiteboard_targets_target_type"), table_name="whiteboard_targets")
    op.drop_index(op.f("ix_whiteboard_targets_target_app"), table_name="whiteboard_targets")
    op.drop_index(op.f("ix_whiteboard_targets_whiteboard_id"), table_name="whiteboard_targets")
    op.drop_constraint(
        "fk_whiteboard_targets_created_by_id_users",
        "whiteboard_targets",
        type_="foreignkey",
    )
    op.rename_table("whiteboard_targets", "whiteboard_containers")
    op.create_foreign_key(
        "fk_whiteboard_containers_created_by_id_users",
        "whiteboard_containers",
        "users",
        ["created_by_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_whiteboard_containers_whiteboard_id"),
        "whiteboard_containers",
        ["whiteboard_id"],
    )
    op.create_index(
        op.f("ix_whiteboard_containers_target_app"), "whiteboard_containers", ["target_app"]
    )
    op.create_index(
        op.f("ix_whiteboard_containers_target_type"), "whiteboard_containers", ["target_type"]
    )
    op.create_index(
        op.f("ix_whiteboard_containers_target_id"), "whiteboard_containers", ["target_id"]
    )
    op.create_index(
        op.f("ix_whiteboard_containers_is_primary"), "whiteboard_containers", ["is_primary"]
    )
    op.create_index(
        op.f("ix_whiteboard_containers_created_by_id"),
        "whiteboard_containers",
        ["created_by_id"],
    )
    op.create_index(
        "ix_whiteboard_containers_target_lookup",
        "whiteboard_containers",
        ["target_app", "target_type", "target_id"],
    )
    op.create_index(
        "uq_whiteboard_containers_primary",
        "whiteboard_containers",
        ["whiteboard_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
        sqlite_where=sa.text("is_primary IS TRUE"),
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


def _rename_recording_targets() -> None:
    op.drop_index("ix_recording_staging_initial_container", table_name="recording_staging")
    op.alter_column(
        "recording_staging",
        "initial_container_app",
        new_column_name="initial_target_app",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "recording_staging",
        "initial_container_type",
        new_column_name="initial_target_type",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "recording_staging",
        "initial_container_id",
        new_column_name="initial_target_id",
        existing_type=sa.String(length=128),
    )
    op.create_index(
        "ix_recording_staging_initial_target",
        "recording_staging",
        ["workspace_id", "initial_target_app", "initial_target_type", "initial_target_id", "completed_at"],
    )

    op.drop_index("ix_recording_containers_lookup", table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_container_app"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_container_type"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_container_id"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_recording_id"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_is_primary"), table_name="recording_containers")
    op.drop_index(op.f("ix_recording_containers_added_by_id"), table_name="recording_containers")
    op.drop_index("uq_recording_containers_primary", table_name="recording_containers")
    op.drop_constraint(
        "uq_recording_containers_recording_container",
        "recording_containers",
        type_="unique",
    )
    op.alter_column(
        "recording_containers",
        "container_app",
        new_column_name="target_app",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "recording_containers",
        "container_type",
        new_column_name="target_type",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "recording_containers",
        "container_id",
        new_column_name="target_id",
        existing_type=sa.String(length=128),
    )
    op.rename_table("recording_containers", "recording_targets")
    op.create_index(op.f("ix_recording_targets_recording_id"), "recording_targets", ["recording_id"])
    op.create_index(op.f("ix_recording_targets_target_app"), "recording_targets", ["target_app"])
    op.create_index(op.f("ix_recording_targets_target_type"), "recording_targets", ["target_type"])
    op.create_index(op.f("ix_recording_targets_target_id"), "recording_targets", ["target_id"])
    op.create_index(op.f("ix_recording_targets_is_primary"), "recording_targets", ["is_primary"])
    op.create_index(op.f("ix_recording_targets_added_by_id"), "recording_targets", ["added_by_id"])
    op.create_index(
        "ix_recording_targets_lookup",
        "recording_targets",
        ["target_app", "target_type", "target_id"],
    )
    op.create_index(
        "uq_recording_targets_primary",
        "recording_targets",
        ["recording_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_unique_constraint(
        "uq_recording_targets_recording_target",
        "recording_targets",
        ["recording_id", "target_app", "target_type", "target_id"],
    )


def _restore_recording_containers() -> None:
    op.drop_constraint("uq_recording_targets_recording_target", "recording_targets", type_="unique")
    op.drop_index("uq_recording_targets_primary", table_name="recording_targets")
    op.drop_index("ix_recording_targets_lookup", table_name="recording_targets")
    op.drop_index(op.f("ix_recording_targets_added_by_id"), table_name="recording_targets")
    op.drop_index(op.f("ix_recording_targets_is_primary"), table_name="recording_targets")
    op.drop_index(op.f("ix_recording_targets_target_id"), table_name="recording_targets")
    op.drop_index(op.f("ix_recording_targets_target_type"), table_name="recording_targets")
    op.drop_index(op.f("ix_recording_targets_target_app"), table_name="recording_targets")
    op.drop_index(op.f("ix_recording_targets_recording_id"), table_name="recording_targets")
    op.rename_table("recording_targets", "recording_containers")
    op.alter_column(
        "recording_containers",
        "target_id",
        new_column_name="container_id",
        existing_type=sa.String(length=128),
    )
    op.alter_column(
        "recording_containers",
        "target_type",
        new_column_name="container_type",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "recording_containers",
        "target_app",
        new_column_name="container_app",
        existing_type=sa.String(length=64),
    )
    op.create_index(
        op.f("ix_recording_containers_recording_id"), "recording_containers", ["recording_id"]
    )
    op.create_index(
        op.f("ix_recording_containers_container_app"),
        "recording_containers",
        ["container_app"],
    )
    op.create_index(
        op.f("ix_recording_containers_container_type"),
        "recording_containers",
        ["container_type"],
    )
    op.create_index(
        op.f("ix_recording_containers_container_id"),
        "recording_containers",
        ["container_id"],
    )
    op.create_index(
        op.f("ix_recording_containers_is_primary"), "recording_containers", ["is_primary"]
    )
    op.create_index(
        op.f("ix_recording_containers_added_by_id"), "recording_containers", ["added_by_id"]
    )
    op.create_index(
        "ix_recording_containers_lookup",
        "recording_containers",
        ["container_app", "container_type", "container_id"],
    )
    op.create_index(
        "uq_recording_containers_primary",
        "recording_containers",
        ["recording_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_unique_constraint(
        "uq_recording_containers_recording_container",
        "recording_containers",
        ["recording_id", "container_app", "container_type", "container_id"],
    )

    op.drop_index("ix_recording_staging_initial_target", table_name="recording_staging")
    op.alter_column(
        "recording_staging",
        "initial_target_id",
        new_column_name="initial_container_id",
        existing_type=sa.String(length=128),
    )
    op.alter_column(
        "recording_staging",
        "initial_target_type",
        new_column_name="initial_container_type",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "recording_staging",
        "initial_target_app",
        new_column_name="initial_container_app",
        existing_type=sa.String(length=64),
    )
    op.create_index(
        "ix_recording_staging_initial_container",
        "recording_staging",
        [
            "workspace_id",
            "initial_container_app",
            "initial_container_type",
            "initial_container_id",
            "completed_at",
        ],
    )
