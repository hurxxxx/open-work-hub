"""Two modes, per-document turn provenance and persisted execution cwd."""

import sqlalchemy as sa
from alembic import op

revision = "console_0005"
down_revision = "console_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("console_tasks", sa.Column("last_execution_root", sa.Text(), nullable=True))
    op.execute("UPDATE console_tasks SET last_execution_root = root")
    op.execute("UPDATE console_tasks SET stage = 'plan' WHERE stage IN ('chat', 'requirements')")
    op.drop_constraint("uq_console_revision_source_turn", "console_revisions", type_="unique")
    op.create_unique_constraint(
        "uq_console_revision_kind_turn", "console_revisions", ["task_id", "kind", "source_turn_id"]
    )


def downgrade():
    # Retain both document histories when returning to the older single-document provenance.
    op.execute(
        "UPDATE console_revisions SET source_turn_id = NULL WHERE id IN ("
        "SELECT id FROM (SELECT id, row_number() OVER (PARTITION BY task_id, source_turn_id "
        "ORDER BY id) AS n FROM console_revisions WHERE source_turn_id IS NOT NULL) "
        "AS duplicates WHERE n > 1)"
    )
    op.drop_constraint("uq_console_revision_kind_turn", "console_revisions", type_="unique")
    op.create_unique_constraint(
        "uq_console_revision_source_turn", "console_revisions", ["task_id", "source_turn_id"]
    )
    op.drop_column("console_tasks", "last_execution_root")
