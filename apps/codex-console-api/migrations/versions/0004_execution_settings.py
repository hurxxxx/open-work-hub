"""Persist effective execution settings and native plan progress."""

import sqlalchemy as sa
from alembic import op

revision = "console_0004"
down_revision = "console_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("console_tasks", sa.Column("effort", sa.String(40), nullable=True))
    op.add_column(
        "console_tasks",
        sa.Column("permissions", sa.String(24), nullable=False, server_default="read-only"),
    )
    op.execute("UPDATE console_tasks SET permissions = 'ask' WHERE approved_revision IS NOT NULL")
    op.add_column("console_tasks", sa.Column("progress", sa.JSON(), nullable=True))
    op.add_column("console_tasks", sa.Column("runtime_generation", sa.String(36), nullable=True))


def downgrade():
    for name in ("runtime_generation", "progress", "permissions", "effort"):
        op.drop_column("console_tasks", name)
