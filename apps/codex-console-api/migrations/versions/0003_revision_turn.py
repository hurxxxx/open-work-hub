"""Record native document turn provenance for idempotent recovery."""

import sqlalchemy as sa
from alembic import op

revision = "console_0003"
down_revision = "console_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("console_tasks", sa.Column("current_operation_id", sa.String(36), nullable=True))
    op.execute("""UPDATE console_tasks AS task SET current_operation_id = (
        SELECT id FROM console_operations
        WHERE task_id = task.id AND kind <> 'steer'
        ORDER BY created_at DESC LIMIT 1
    )""")
    op.add_column("console_revisions", sa.Column("source_turn_id", sa.String(160), nullable=True))
    op.create_unique_constraint(
        "uq_console_revision_source_turn", "console_revisions", ["task_id", "source_turn_id"]
    )


def downgrade():
    op.drop_constraint("uq_console_revision_source_turn", "console_revisions", type_="unique")
    op.drop_column("console_revisions", "source_turn_id")
    op.drop_column("console_tasks", "current_operation_id")
