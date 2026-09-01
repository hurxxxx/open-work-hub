"""Bind Hermes approvals to one exact Open Work Hub tool call.

Revision ID: c2d7e9f1a4b8
Revises: f4a8c2d6e1b9
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c2d7e9f1a4b8"
down_revision: str | Sequence[str] | None = "f4a8c2d6e1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hermes_tool_approvals",
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "hermes_tool_approvals",
        sa.Column("consumed_tool_name", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "hermes_tool_approvals",
        sa.Column(
            "consumed_arguments_sha256",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "hermes_tool_approvals",
        sa.Column("external_call_id", sa.String(length=36), nullable=True),
    )
    op.create_check_constraint(
        "ck_hermes_tool_approvals_consumption",
        "hermes_tool_approvals",
        "(consumed_at IS NULL AND consumed_tool_name IS NULL "
        "AND consumed_arguments_sha256 IS NULL AND external_call_id IS NULL) "
        "OR (consumed_at IS NOT NULL AND consumed_tool_name IS NOT NULL "
        "AND consumed_arguments_sha256 IS NOT NULL AND external_call_id IS NOT NULL)",
    )
    op.create_index(
        "ix_hermes_tool_approvals_external_call_id",
        "hermes_tool_approvals",
        ["external_call_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hermes_tool_approvals_external_call_id",
        table_name="hermes_tool_approvals",
    )
    op.drop_constraint(
        "ck_hermes_tool_approvals_consumption",
        "hermes_tool_approvals",
        type_="check",
    )
    op.drop_column("hermes_tool_approvals", "external_call_id")
    op.drop_column("hermes_tool_approvals", "consumed_arguments_sha256")
    op.drop_column("hermes_tool_approvals", "consumed_tool_name")
    op.drop_column("hermes_tool_approvals", "consumed_at")
