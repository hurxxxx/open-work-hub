"""Add the private workspace Hermes terminal application.

Revision ID: a7e3c1d9f5b2
Revises: c2d7e9f1a4b8
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a7e3c1d9f5b2"
down_revision: str | Sequence[str] | None = "c2d7e9f1a4b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB = postgresql.JSONB(astext_type=sa.Text())
APP_ID = "hermes-terminal"


def upgrade() -> None:
    op.create_table(
        "hermes_terminal_profile_states",
        sa.Column("profile_binding_id", sa.String(length=36), nullable=False),
        sa.Column("profile_name", sa.String(length=63), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=True),
        sa.Column("archive_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "archive_size_bytes",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("exported_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "revision >= 0 AND archive_size_bytes >= 0",
            name="ck_hermes_terminal_profile_states_size_revision",
        ),
        sa.ForeignKeyConstraint(
            ["profile_binding_id"],
            ["hermes_profile_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("profile_binding_id"),
        sa.UniqueConstraint("profile_name"),
    )

    op.create_table(
        "hermes_terminal_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_binding_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column(
            "mode",
            sa.String(length=16),
            server_default=sa.text("'standard'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'starting'"),
            nullable=False,
        ),
        sa.Column(
            "allowed_app_ids",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("runtime_handle", sa.String(length=128), nullable=True),
        sa.Column("broker_instance_id", sa.String(length=96), nullable=True),
        sa.Column("mcp_token_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "cols",
            sa.Integer(),
            server_default=sa.text("120"),
            nullable=False,
        ),
        sa.Column(
            "rows",
            sa.Integer(),
            server_default=sa.text("32"),
            nullable=False,
        ),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=160), nullable=True),
        sa.Column("archive_target_status", sa.String(length=24), nullable=True),
        sa.Column(
            "archive_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("archive_started_at", sa.DateTime(), nullable=True),
        sa.Column("archive_failure_code", sa.String(length=160), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "mode IN ('standard','yolo')",
            name="ck_hermes_terminal_sessions_mode",
        ),
        sa.CheckConstraint(
            "status IN ('starting','running','awaiting_approval','stopping',"
            "'archiving','exited','terminated','failed')",
            name="ck_hermes_terminal_sessions_status",
        ),
        sa.CheckConstraint(
            "cols >= 20 AND cols <= 500 AND rows >= 5 AND rows <= 300",
            name="ck_hermes_terminal_sessions_size",
        ),
        sa.CheckConstraint(
            "archive_attempts >= 0",
            name="ck_hermes_terminal_sessions_archive_attempts",
        ),
        sa.CheckConstraint(
            "archive_target_status IS NULL OR "
            "archive_target_status IN ('exited','terminated','failed')",
            name="ck_hermes_terminal_sessions_archive_target",
        ),
        sa.ForeignKeyConstraint(
            ["profile_binding_id"],
            ["hermes_profile_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mcp_token_digest"),
        sa.UniqueConstraint("runtime_handle"),
    )
    op.create_index(
        "ix_hermes_terminal_sessions_profile_binding_id",
        "hermes_terminal_sessions",
        ["profile_binding_id"],
    )
    op.create_index(
        "ix_hermes_terminal_sessions_workspace_id",
        "hermes_terminal_sessions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_hermes_terminal_sessions_user_id",
        "hermes_terminal_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_hermes_terminal_sessions_owner_created",
        "hermes_terminal_sessions",
        ["workspace_id", "user_id", "created_at"],
    )
    op.create_index(
        "ix_hermes_terminal_sessions_status_activity",
        "hermes_terminal_sessions",
        ["status", "last_activity_at"],
    )
    op.create_index(
        "ix_hermes_terminal_sessions_archive_recovery",
        "hermes_terminal_sessions",
        ["status", "archive_started_at", "archive_attempts"],
    )
    op.create_index(
        "uq_hermes_terminal_sessions_active_owner",
        "hermes_terminal_sessions",
        ["workspace_id", "user_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('starting','running','awaiting_approval','stopping','archiving')"
        ),
        sqlite_where=sa.text(
            "status IN ('starting','running','awaiting_approval','stopping','archiving')"
        ),
    )

    op.create_table(
        "hermes_terminal_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_hermes_terminal_artifacts_size",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["hermes_terminal_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint(
            "session_id",
            "relative_path",
            name="uq_hermes_terminal_artifacts_session_path",
        ),
    )
    op.create_index(
        "ix_hermes_terminal_artifacts_session_id",
        "hermes_terminal_artifacts",
        ["session_id"],
    )
    op.create_index(
        "ix_hermes_terminal_artifacts_workspace_id",
        "hermes_terminal_artifacts",
        ["workspace_id"],
    )
    op.create_index(
        "ix_hermes_terminal_artifacts_user_id",
        "hermes_terminal_artifacts",
        ["user_id"],
    )
    op.create_index(
        "ix_hermes_terminal_artifacts_expires_at",
        "hermes_terminal_artifacts",
        ["expires_at"],
    )
    op.create_index(
        "ix_hermes_terminal_artifacts_owner_expiry",
        "hermes_terminal_artifacts",
        ["workspace_id", "user_id", "expires_at"],
    )

    op.create_table(
        "hermes_terminal_tool_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=256), nullable=False),
        sa.Column("tool_name", sa.String(length=160), nullable=False),
        sa.Column("arguments_sha256", sa.String(length=64), nullable=False),
        sa.Column("request_payload", JSONB, nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("choice", sa.String(length=24), nullable=True),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("external_call_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','approved','denied','expired')",
            name="ck_hermes_terminal_tool_approvals_status",
        ),
        sa.CheckConstraint(
            "(consumed_at IS NULL AND external_call_id IS NULL) OR "
            "(consumed_at IS NOT NULL AND external_call_id IS NOT NULL)",
            name="ck_hermes_terminal_tool_approvals_consumption",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["hermes_terminal_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "request_id",
            name="uq_hermes_terminal_tool_approvals_session_request",
        ),
    )
    op.create_index(
        "ix_hermes_terminal_tool_approvals_session_id",
        "hermes_terminal_tool_approvals",
        ["session_id"],
    )
    op.create_index(
        "ix_hermes_terminal_tool_approvals_expires_at",
        "hermes_terminal_tool_approvals",
        ["expires_at"],
    )
    op.create_index(
        "ix_hermes_terminal_tool_approvals_session_status",
        "hermes_terminal_tool_approvals",
        ["session_id", "status", "created_at"],
    )
    op.create_index(
        "ix_hermes_terminal_tool_approvals_external_call_id",
        "hermes_terminal_tool_approvals",
        ["external_call_id"],
        unique=True,
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    company_controls = sa.table(
        "company_app_controls",
        sa.column("app_id", sa.String(length=64)),
        sa.column("enabled", sa.Boolean()),
        sa.column("updated_by_user_id", sa.String(length=36)),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    workspace_defaults = sa.table(
        "workspace_app_defaults",
        sa.column("app_id", sa.String(length=64)),
        sa.column("enabled", sa.Boolean()),
        sa.column("updated_by_user_id", sa.String(length=36)),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    row = {
        "app_id": APP_ID,
        "enabled": True,
        "updated_by_user_id": None,
        "created_at": now,
        "updated_at": now,
    }
    op.bulk_insert(company_controls, [row])
    op.bulk_insert(workspace_defaults, [row])


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM user_app_workspace_preferences WHERE app_id = :app_id").bindparams(
            app_id=APP_ID
        )
    )
    op.execute(
        sa.text("DELETE FROM workspace_app_overrides WHERE app_id = :app_id").bindparams(
            app_id=APP_ID
        )
    )
    op.execute(
        sa.text("DELETE FROM workspace_app_defaults WHERE app_id = :app_id").bindparams(
            app_id=APP_ID
        )
    )
    op.execute(
        sa.text("DELETE FROM company_app_controls WHERE app_id = :app_id").bindparams(
            app_id=APP_ID
        )
    )

    op.drop_index(
        "ix_hermes_terminal_tool_approvals_external_call_id",
        table_name="hermes_terminal_tool_approvals",
    )
    op.drop_index(
        "ix_hermes_terminal_tool_approvals_session_status",
        table_name="hermes_terminal_tool_approvals",
    )
    op.drop_index(
        "ix_hermes_terminal_tool_approvals_expires_at",
        table_name="hermes_terminal_tool_approvals",
    )
    op.drop_index(
        "ix_hermes_terminal_tool_approvals_session_id",
        table_name="hermes_terminal_tool_approvals",
    )
    op.drop_table("hermes_terminal_tool_approvals")

    op.drop_index(
        "ix_hermes_terminal_artifacts_owner_expiry",
        table_name="hermes_terminal_artifacts",
    )
    op.drop_index(
        "ix_hermes_terminal_artifacts_expires_at",
        table_name="hermes_terminal_artifacts",
    )
    op.drop_index(
        "ix_hermes_terminal_artifacts_user_id",
        table_name="hermes_terminal_artifacts",
    )
    op.drop_index(
        "ix_hermes_terminal_artifacts_workspace_id",
        table_name="hermes_terminal_artifacts",
    )
    op.drop_index(
        "ix_hermes_terminal_artifacts_session_id",
        table_name="hermes_terminal_artifacts",
    )
    op.drop_table("hermes_terminal_artifacts")

    op.drop_index(
        "uq_hermes_terminal_sessions_active_owner",
        table_name="hermes_terminal_sessions",
    )
    op.drop_index(
        "ix_hermes_terminal_sessions_archive_recovery",
        table_name="hermes_terminal_sessions",
    )
    op.drop_index(
        "ix_hermes_terminal_sessions_status_activity",
        table_name="hermes_terminal_sessions",
    )
    op.drop_index(
        "ix_hermes_terminal_sessions_owner_created",
        table_name="hermes_terminal_sessions",
    )
    op.drop_index(
        "ix_hermes_terminal_sessions_user_id",
        table_name="hermes_terminal_sessions",
    )
    op.drop_index(
        "ix_hermes_terminal_sessions_workspace_id",
        table_name="hermes_terminal_sessions",
    )
    op.drop_index(
        "ix_hermes_terminal_sessions_profile_binding_id",
        table_name="hermes_terminal_sessions",
    )
    op.drop_table("hermes_terminal_sessions")
    op.drop_table("hermes_terminal_profile_states")
