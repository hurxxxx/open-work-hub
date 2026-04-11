"""workspace_rearchitecture_foundation

Revision ID: 2d4f6c9ab1ef
Revises: 6b21fc0a74c8
Create Date: 2026-04-11 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2d4f6c9ab1ef"
down_revision: Union[str, Sequence[str], None] = "6b21fc0a74c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ALL_APPS = ("ai", "docs", "pms", "planner", "meeting")
LEGACY_APP_WORKSPACES = set(ALL_APPS)


def upgrade() -> None:
    op.create_table(
        "workspace_enabled_apps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("app_code", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "app_code", name="uq_workspace_enabled_app"),
    )
    op.create_index(
        op.f("ix_workspace_enabled_apps_workspace_id"),
        "workspace_enabled_apps",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workspace_enabled_apps_app_code"),
        "workspace_enabled_apps",
        ["app_code"],
        unique=False,
    )

    op.add_column(
        "docs_native_docs",
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_docs_native_docs_workspace_id"),
        "docs_native_docs",
        ["workspace_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_docs_native_docs_workspace_id_workspaces",
        "docs_native_docs",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )

    connection = op.get_bind()
    workspaces = list(
        connection.execute(
            sa.text(
                """
                SELECT id, key
                FROM workspaces
                WHERE active IS TRUE
                ORDER BY created_at ASC, key ASC
                """
            )
        ).mappings()
    )
    if workspaces:
        default_workspace_id = workspaces[0]["id"]
        connection.execute(
            sa.text(
                """
                UPDATE docs_native_docs
                SET workspace_id = :workspace_id
                WHERE workspace_id IS NULL
                """
            ),
            {"workspace_id": default_workspace_id},
        )

    for row in workspaces:
        workspace_id = row["id"]
        workspace_key = row["key"]
        app_codes = [workspace_key] if workspace_key in LEGACY_APP_WORKSPACES else list(ALL_APPS)
        if workspace_key == "admin":
            app_codes = []
        for app_code in app_codes:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO workspace_enabled_apps (id, workspace_id, app_code, created_at)
                    VALUES (:id, :workspace_id, :app_code, CURRENT_TIMESTAMP)
                    ON CONFLICT (workspace_id, app_code) DO NOTHING
                    """
                ),
                {
                    "id": f"{workspace_id[:24]}-{app_code}"[:36],
                    "workspace_id": workspace_id,
                    "app_code": app_code,
                },
            )

    op.alter_column("docs_native_docs", "workspace_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint(
        "fk_docs_native_docs_workspace_id_workspaces",
        "docs_native_docs",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_docs_native_docs_workspace_id"), table_name="docs_native_docs")
    op.drop_column("docs_native_docs", "workspace_id")

    op.drop_index(op.f("ix_workspace_enabled_apps_app_code"), table_name="workspace_enabled_apps")
    op.drop_index(op.f("ix_workspace_enabled_apps_workspace_id"), table_name="workspace_enabled_apps")
    op.drop_table("workspace_enabled_apps")
