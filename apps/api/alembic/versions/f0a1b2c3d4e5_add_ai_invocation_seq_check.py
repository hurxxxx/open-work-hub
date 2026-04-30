"""add_ai_invocation_seq_check

Revision ID: f0a1b2c3d4e5
Revises: e7f8a9b0c1d2
Create Date: 2026-04-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_ai_agent_invocations_invocation_seq_nonnegative",
        "ai_agent_invocations",
        "invocation_seq >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ai_agent_invocations_invocation_seq_nonnegative",
        "ai_agent_invocations",
        type_="check",
    )
