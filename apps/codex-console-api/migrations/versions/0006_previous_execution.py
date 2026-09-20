"""Keep the last verified native sandbox across an uncertain permission transition."""

import sqlalchemy as sa
from alembic import op

revision = "console_0006"
down_revision = "console_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("console_tasks", sa.Column("previous_execution_root", sa.Text(), nullable=True))
    op.add_column("console_tasks", sa.Column("previous_permissions", sa.String(24), nullable=True))


def downgrade():
    op.drop_column("console_tasks", "previous_permissions")
    op.drop_column("console_tasks", "previous_execution_root")
