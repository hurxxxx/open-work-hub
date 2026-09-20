"""Task file library and explicit per-message references."""

import sqlalchemy as sa
from alembic import op

revision = "console_0002"
down_revision = "console_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("console_operations", sa.Column("display_text", sa.Text()))
    op.create_table(
        "console_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("console_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_console_attachments_task_id", "console_attachments", ["task_id"])
    op.create_table(
        "console_message_attachments",
        sa.Column(
            "operation_id",
            sa.String(36),
            sa.ForeignKey("console_operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "attachment_id",
            sa.String(36),
            sa.ForeignKey("console_attachments.id"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("console_message_attachments")
    op.drop_table("console_attachments")
    op.drop_column("console_operations", "display_text")
