"""add_groupware_hr_identity

Revision ID: b8d9e0f1a2c3
Revises: a2b4c6d8e0f1
Create Date: 2026-06-01 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b8d9e0f1a2c3"
down_revision: str | Sequence[str] | None = "a2b4c6d8e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.add_column("org_units", sa.Column("hr_source_system", sa.String(length=32), nullable=True))
    op.add_column("org_units", sa.Column("hr_domain_num", sa.Integer(), nullable=True))
    op.add_column("org_units", sa.Column("hr_depart_num", sa.Integer(), nullable=True))
    op.add_column("org_units", sa.Column("hr_org_code", sa.String(length=80), nullable=True))
    op.add_column("org_units", sa.Column("hr_parent_org_code", sa.String(length=80), nullable=True))
    op.add_column("org_units", sa.Column("hr_org_level", sa.Integer(), nullable=True))
    op.add_column("org_units", sa.Column("hr_last_synced_at", sa.DateTime(), nullable=True))
    op.create_index("ix_org_units_hr_source_system", "org_units", ["hr_source_system"])
    op.create_index("ix_org_units_hr_domain_num", "org_units", ["hr_domain_num"])
    op.create_index("ix_org_units_hr_depart_num", "org_units", ["hr_depart_num"])
    op.create_index("ix_org_units_hr_org_code", "org_units", ["hr_org_code"])
    op.create_index("ix_org_units_hr_parent_org_code", "org_units", ["hr_parent_org_code"])
    op.create_index("ix_org_units_hr_last_synced_at", "org_units", ["hr_last_synced_at"])
    op.create_unique_constraint(
        "uq_org_units_hr_source_identity",
        "org_units",
        ["hr_source_system", "hr_domain_num", "hr_depart_num"],
    )
    op.create_unique_constraint(
        "uq_org_units_hr_org_code",
        "org_units",
        ["hr_source_system", "hr_domain_num", "hr_org_code"],
    )

    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=32),
            nullable=False,
            server_default="local",
        ),
    )
    op.add_column("users", sa.Column("hr_source_system", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("hr_domain_num", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("hr_user_num", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("hr_com_state", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("hr_last_synced_at", sa.DateTime(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "login_blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("users", "login_blocked", server_default=None)
    op.alter_column("users", "auth_provider", server_default=None)
    op.create_check_constraint(
        "ck_users_auth_provider",
        "users",
        "auth_provider IN ('local', 'groupware')",
    )
    op.create_index("ix_users_auth_provider", "users", ["auth_provider"])
    op.create_index("ix_users_hr_source_system", "users", ["hr_source_system"])
    op.create_index("ix_users_hr_domain_num", "users", ["hr_domain_num"])
    op.create_index("ix_users_hr_user_num", "users", ["hr_user_num"])
    op.create_index("ix_users_hr_com_state", "users", ["hr_com_state"])
    op.create_index("ix_users_hr_last_synced_at", "users", ["hr_last_synced_at"])
    op.create_index("ix_users_login_blocked", "users", ["login_blocked"])
    op.create_unique_constraint(
        "uq_users_hr_source_identity",
        "users",
        ["hr_source_system", "hr_domain_num", "hr_user_num"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_hr_source_identity", "users", type_="unique")
    op.drop_index("ix_users_login_blocked", table_name="users")
    op.drop_index("ix_users_hr_last_synced_at", table_name="users")
    op.drop_index("ix_users_hr_com_state", table_name="users")
    op.drop_index("ix_users_hr_user_num", table_name="users")
    op.drop_index("ix_users_hr_domain_num", table_name="users")
    op.drop_index("ix_users_hr_source_system", table_name="users")
    op.drop_index("ix_users_auth_provider", table_name="users")
    op.drop_constraint("ck_users_auth_provider", "users", type_="check")
    op.drop_column("users", "hr_last_synced_at")
    op.drop_column("users", "hr_com_state")
    op.drop_column("users", "hr_user_num")
    op.drop_column("users", "hr_domain_num")
    op.drop_column("users", "hr_source_system")
    op.drop_column("users", "login_blocked")
    op.drop_column("users", "auth_provider")

    op.drop_constraint("uq_org_units_hr_org_code", "org_units", type_="unique")
    op.drop_constraint("uq_org_units_hr_source_identity", "org_units", type_="unique")
    op.drop_index("ix_org_units_hr_last_synced_at", table_name="org_units")
    op.drop_index("ix_org_units_hr_parent_org_code", table_name="org_units")
    op.drop_index("ix_org_units_hr_org_code", table_name="org_units")
    op.drop_index("ix_org_units_hr_depart_num", table_name="org_units")
    op.drop_index("ix_org_units_hr_domain_num", table_name="org_units")
    op.drop_index("ix_org_units_hr_source_system", table_name="org_units")
    op.drop_column("org_units", "hr_last_synced_at")
    op.drop_column("org_units", "hr_org_level")
    op.drop_column("org_units", "hr_parent_org_code")
    op.drop_column("org_units", "hr_org_code")
    op.drop_column("org_units", "hr_depart_num")
    op.drop_column("org_units", "hr_domain_num")
    op.drop_column("org_units", "hr_source_system")

    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
