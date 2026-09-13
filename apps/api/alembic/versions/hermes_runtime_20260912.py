"""Partition Hermes model policy and persist workload execution contracts.

Revision ID: hermes_runtime_20260912
Revises: group_sources_20260912
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "hermes_runtime_20260912"
down_revision = "group_sources_20260912"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only enabled audiences participate. Preserve group grants as groups so
    # future membership changes retain the existing admission semantics.
    op.execute(
        sa.text("""
        DO $$
        DECLARE terminal_enabled boolean; chat_enabled boolean; merged_audience text;
        BEGIN
          SELECT enabled INTO terminal_enabled FROM company_app_controls WHERE app_id = 'hermes-terminal';
          SELECT enabled INTO chat_enabled FROM company_app_controls WHERE app_id = 'chatbot';
          IF COALESCE(terminal_enabled, false) THEN
            SELECT CASE WHEN EXISTS (
              SELECT 1 FROM app_access_policies p JOIN company_app_controls c USING (app_id)
              WHERE p.app_id IN ('chatbot', 'hermes-terminal') AND c.enabled AND p.audience = 'all'
            ) THEN 'all' ELSE 'selected' END INTO merged_audience;
            IF NOT COALESCE(chat_enabled, false) THEN
              DELETE FROM app_user_grants WHERE app_id = 'chatbot';
              DELETE FROM app_group_grants WHERE app_id = 'chatbot';
            END IF;
            INSERT INTO company_app_controls (app_id, enabled, created_at, updated_at)
              VALUES ('chatbot', true, now(), now())
              ON CONFLICT (app_id) DO UPDATE SET enabled = true, updated_at = now();
            INSERT INTO app_access_policies (app_id, audience) VALUES ('chatbot', merged_audience)
              ON CONFLICT (app_id) DO UPDATE SET audience = EXCLUDED.audience;
            INSERT INTO app_user_grants (app_id, user_id)
              SELECT 'chatbot', user_id FROM app_user_grants WHERE app_id = 'hermes-terminal'
              ON CONFLICT DO NOTHING;
            INSERT INTO app_group_grants (app_id, group_id)
              SELECT 'chatbot', group_id FROM app_group_grants WHERE app_id = 'hermes-terminal'
              ON CONFLICT DO NOTHING;
          END IF;
          UPDATE company_app_controls SET enabled = false, updated_at = now() WHERE app_id = 'hermes-terminal';
          UPDATE platform_app_bar_category_apps SET app_id = 'chatbot'
            WHERE app_id = 'hermes-terminal' AND NOT EXISTS (
              SELECT 1 FROM platform_app_bar_category_apps WHERE app_id = 'chatbot'
            );
          DELETE FROM platform_app_bar_category_apps WHERE app_id = 'hermes-terminal';
        END $$;
    """)
    )
    op.create_table(
        "hermes_file_objects",
        sa.Column("object_key", sa.String(1024), primary_key=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_hermes_file_objects_expires_at", "hermes_file_objects", ["expires_at"])
    op.create_table(
        "hermes_session_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("hermes_session_bindings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("session_id", "relative_path", name="uq_hermes_session_files_path"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_hermes_session_files_size"),
    )
    for column in ("session_id", "user_id", "expires_at"):
        op.create_index(f"ix_hermes_session_files_{column}", "hermes_session_files", [column])
    op.add_column(
        "hermes_profile_bindings",
        sa.Column(
            "route",
            sa.String(16),
            nullable=False,
            server_default="external",
        ),
    )
    op.drop_constraint("uq_hermes_profile_bindings_user", "hermes_profile_bindings", type_="unique")
    op.create_unique_constraint(
        "uq_hermes_profile_bindings_user_route",
        "hermes_profile_bindings",
        ["user_id", "route"],
    )
    op.add_column(
        "hermes_run_projections",
        sa.Column(
            "owner_app_id",
            sa.String(80),
            nullable=False,
            server_default="chatbot",
        ),
    )
    op.add_column(
        "hermes_run_projections",
        sa.Column(
            "runtime_options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    for name in ("output_schema", "output_payload"):
        op.add_column("hermes_run_projections", sa.Column(name, postgresql.JSONB(), nullable=True))
    op.execute(
        sa.text("""
        UPDATE ai_model_route_overrides SET runtime_adapter_id = 'hermes', version = version + 1
        WHERE workload_id IN ('bento.edit_presentation', 'bento.generate_presentation')
          AND runtime_adapter_id IN ('fixed_bento_pipeline', 'codex_sdk')
    """)
    )


def downgrade() -> None:
    # Separate policy partitions may now contain private conversations. An
    # automatic downgrade would discard or merge those owners' data.
    raise RuntimeError("Archive policy-partitioned Hermes sessions before schema rollback.")
