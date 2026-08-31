"""Replace global workspace selection and app visibility with app controls.

Revision ID: c5f8a2d1e7b4
Revises: b4e7c1d9a2f6
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision: str = "c5f8a2d1e7b4"
down_revision: str | Sequence[str] | None = "b4e7c1d9a2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ALL_APP_IDS = (
    "home",
    "agent-terminal",
    "chatbot",
    "web-search",
    "pms",
    "docs",
    "files",
    "mail",
    "community",
    "whiteboard",
    "diagrams",
    "bento",
    "planner",
    "meeting",
    "video-chat",
    "recording",
    "retrieval-search",
)

_WORKSPACE_APP_IDS = (
    "home",
    "chatbot",
    "web-search",
    "pms",
    "docs",
    "files",
    "whiteboard",
    "diagrams",
    "bento",
    "meeting",
    "video-chat",
    "recording",
    "retrieval-search",
)


def upgrade() -> None:
    op.drop_table("workspace_app_entitlements")
    op.drop_table("platform_app_visibility")
    op.drop_index("ix_users_default_workspace_id", table_name="users")
    op.drop_constraint("users_default_workspace_id_fkey", "users", type_="foreignkey")
    op.drop_column("users", "default_workspace_id")

    company_controls = op.create_table(
        "company_app_controls",
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("app_id"),
    )
    op.create_index(
        "ix_company_app_controls_enabled",
        "company_app_controls",
        ["enabled"],
    )
    op.create_index(
        "ix_company_app_controls_updated_by_user_id",
        "company_app_controls",
        ["updated_by_user_id"],
    )

    workspace_defaults = op.create_table(
        "workspace_app_defaults",
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("app_id"),
    )
    op.create_index(
        "ix_workspace_app_defaults_enabled",
        "workspace_app_defaults",
        ["enabled"],
    )
    op.create_index(
        "ix_workspace_app_defaults_updated_by_user_id",
        "workspace_app_defaults",
        ["updated_by_user_id"],
    )

    op.create_table(
        "workspace_app_overrides",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "app_id"),
    )
    op.create_index(
        "ix_workspace_app_overrides_app_id",
        "workspace_app_overrides",
        ["app_id"],
    )
    op.create_index(
        "ix_workspace_app_overrides_enabled",
        "workspace_app_overrides",
        ["enabled"],
    )
    op.create_index(
        "ix_workspace_app_overrides_updated_by_user_id",
        "workspace_app_overrides",
        ["updated_by_user_id"],
    )

    op.create_table(
        "user_app_workspace_preferences",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspace_user_bindings.workspace_id", "workspace_user_bindings.user_id"],
            name="fk_user_app_workspace_preference_membership",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "app_id"),
    )
    op.create_index(
        "ix_user_app_workspace_preferences_workspace_user",
        "user_app_workspace_preferences",
        ["workspace_id", "user_id"],
    )
    op.create_index(
        "ix_user_app_workspace_preferences_workspace_id",
        "user_app_workspace_preferences",
        ["workspace_id"],
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(
        company_controls,
        [
            {
                "app_id": app_id,
                "enabled": True,
                "updated_by_user_id": None,
                "created_at": now,
                "updated_at": now,
            }
            for app_id in _ALL_APP_IDS
        ],
    )
    op.bulk_insert(
        workspace_defaults,
        [
            {
                "app_id": app_id,
                "enabled": True,
                "updated_by_user_id": None,
                "created_at": now,
                "updated_at": now,
            }
            for app_id in _WORKSPACE_APP_IDS
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_app_workspace_preferences_workspace_user",
        table_name="user_app_workspace_preferences",
    )
    op.drop_index(
        "ix_user_app_workspace_preferences_workspace_id",
        table_name="user_app_workspace_preferences",
    )
    op.drop_table("user_app_workspace_preferences")
    op.drop_index(
        "ix_workspace_app_overrides_app_id",
        table_name="workspace_app_overrides",
    )
    op.drop_index(
        "ix_workspace_app_overrides_updated_by_user_id",
        table_name="workspace_app_overrides",
    )
    op.drop_index(
        "ix_workspace_app_overrides_enabled",
        table_name="workspace_app_overrides",
    )
    op.drop_table("workspace_app_overrides")
    op.drop_index(
        "ix_workspace_app_defaults_updated_by_user_id",
        table_name="workspace_app_defaults",
    )
    op.drop_index("ix_workspace_app_defaults_enabled", table_name="workspace_app_defaults")
    op.drop_table("workspace_app_defaults")
    op.drop_index(
        "ix_company_app_controls_updated_by_user_id",
        table_name="company_app_controls",
    )
    op.drop_index("ix_company_app_controls_enabled", table_name="company_app_controls")
    op.drop_table("company_app_controls")

    op.add_column("users", sa.Column("default_workspace_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "users_default_workspace_id_fkey",
        "users",
        "workspaces",
        ["default_workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_users_default_workspace_id",
        "users",
        ["default_workspace_id"],
    )

    op.create_table(
        "platform_app_visibility",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_app_visibility_app_id",
        "platform_app_visibility",
        ["app_id"],
        unique=True,
    )
    op.create_index(
        "ix_platform_app_visibility_visible",
        "platform_app_visibility",
        ["visible"],
    )

    op.create_table(
        "workspace_app_entitlements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("visibility_override", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "app_id",
            name="uq_workspace_app_entitlement",
        ),
    )
    op.create_index(
        "ix_workspace_app_entitlements_app_id",
        "workspace_app_entitlements",
        ["app_id"],
    )
    op.create_index(
        "ix_workspace_app_entitlements_visibility_override",
        "workspace_app_entitlements",
        ["visibility_override"],
    )
    op.create_index(
        "ix_workspace_app_entitlements_workspace_id",
        "workspace_app_entitlements",
        ["workspace_id"],
    )
