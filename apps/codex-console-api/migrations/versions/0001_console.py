"""Initial independent console schema; never run against the OWH application DB."""

import sqlalchemy as sa
from alembic import op

revision = "console_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "console_owner",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.CheckConstraint("id = 1"),
    )
    op.create_table(
        "console_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_console_sessions_expires_at", "console_sessions", ["expires_at"])
    op.create_table(
        "console_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("thread_id", sa.String(160), unique=True),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("root", sa.Text(), nullable=False),
        sa.Column("worktree_owned", sa.Boolean(), nullable=False),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("model", sa.String(200)),
        sa.Column("turn_id", sa.String(160)),
        sa.Column("approved_revision", sa.Integer()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    def task_fk():
        return sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("console_tasks.id", ondelete="CASCADE"),
            nullable=False,
        )

    op.create_table(
        "console_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        task_fk(),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "kind", "version"),
    )
    op.create_table(
        "console_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        task_fk(),
        sa.Column("item_id", sa.String(200), nullable=False),
        sa.Column("turn_id", sa.String(160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("task_id", "item_id"),
    )
    op.create_table(
        "console_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        task_fk(),
        sa.Column("turn_id", sa.String(160), nullable=False),
        sa.Column("rpc_id", sa.Text(), nullable=False),
        sa.Column("generation", sa.String(36), nullable=False),
        sa.Column("method", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("answer", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "console_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        task_fk(),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "console_workspace_lease",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("console_tasks.id")),
        sa.CheckConstraint("id = 1"),
    )
    op.execute("INSERT INTO console_workspace_lease (id) VALUES (1)")
    op.create_table(
        "console_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        task_fk(),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_console_events_task_id_id", "console_events", ["task_id", "id"])


def downgrade():
    for table in (
        "console_events",
        "console_workspace_lease",
        "console_operations",
        "console_requests",
        "console_items",
        "console_revisions",
        "console_tasks",
        "console_sessions",
        "console_owner",
    ):
        op.drop_table(table)
