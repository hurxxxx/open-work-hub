"""add ai security mask and send effect

Revision ID: ce56df78ab90
Revises: bd45ce67fa89
Create Date: 2026-06-25 08:55:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "ce56df78ab90"
down_revision: Union[str, Sequence[str], None] = "bd45ce67fa89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_EFFECTS = "'inherit', 'local_only', 'external_allowed', 'deny', 'audit_only'"
_NEW_EFFECTS = (
    "'inherit', 'local_only', 'mask_and_send', 'external_allowed', 'deny', 'audit_only'"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_ai_security_policy_rules_effect",
        "ai_security_policy_rules",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ai_security_policy_rules_effect",
        "ai_security_policy_rules",
        f"effect IN ({_NEW_EFFECTS})",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ai_security_policy_rules "
        "SET effect = 'local_only' "
        "WHERE effect = 'mask_and_send'"
    )
    op.drop_constraint(
        "ck_ai_security_policy_rules_effect",
        "ai_security_policy_rules",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ai_security_policy_rules_effect",
        "ai_security_policy_rules",
        f"effect IN ({_OLD_EFFECTS})",
    )
