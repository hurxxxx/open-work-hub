"""Add organization directory and platform integrations.

Revision ID: a7c4e9f2b6d1
Revises: a9c3d2e1f4b5
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a7c4e9f2b6d1"
down_revision: str | Sequence[str] | None = "a9c3d2e1f4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_units",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column(
            "unit_type",
            sa.String(length=40),
            server_default=sa.text("'department'"),
            nullable=False,
        ),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_organization_units_name",
        ),
        sa.CheckConstraint(
            "length(trim(unit_type)) > 0",
            name="ck_organization_units_type",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["organization_units.id"],
            name="fk_organization_units_parent_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns, unique in (
        ("ix_organization_units_name", ["name"], False),
        ("ix_organization_units_slug", ["slug"], True),
        ("ix_organization_units_unit_type", ["unit_type"], False),
        ("ix_organization_units_parent_id", ["parent_id"], False),
        ("ix_organization_units_active", ["active"], False),
    ):
        op.create_index(index_name, "organization_units", columns, unique=unique)

    op.add_column("users", sa.Column("employee_code", sa.String(length=40), nullable=True))
    op.add_column("users", sa.Column("job_title", sa.String(length=120), nullable=True))
    op.add_column(
        "users",
        sa.Column("primary_organization_unit_id", sa.String(length=36), nullable=True),
    )
    op.add_column("users", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.execute(sa.text("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL"))
    op.alter_column("users", "updated_at", existing_type=sa.DateTime(), nullable=False)
    op.create_foreign_key(
        "fk_users_primary_organization_unit_id",
        "users",
        "organization_units",
        ["primary_organization_unit_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_employee_code", "users", ["employee_code"], unique=False)
    op.create_index(
        "ix_users_primary_organization_unit_id",
        "users",
        ["primary_organization_unit_id"],
        unique=False,
    )

    op.create_table(
        "platform_api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("key_prefix", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_platform_api_keys_status",
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_platform_api_keys_name",
        ),
        sa.CheckConstraint(
            "substr(key_prefix, 1, 7) = 'owh_pk_'",
            name="ck_platform_api_keys_prefix",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL AND revoked_by_user_id IS NULL) "
            "OR (status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_platform_api_keys_revocation",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns, unique in (
        ("ix_platform_api_keys_token_hash", ["token_hash"], True),
        ("ix_platform_api_keys_key_prefix", ["key_prefix"], True),
        ("ix_platform_api_keys_name", ["name"], False),
        ("ix_platform_api_keys_status", ["status"], False),
        ("ix_platform_api_keys_created_by_user_id", ["created_by_user_id"], False),
        ("ix_platform_api_keys_created_at", ["created_at"], False),
        ("ix_platform_api_keys_revoked_by_user_id", ["revoked_by_user_id"], False),
        ("ix_platform_api_keys_revoked_at", ["revoked_at"], False),
        ("ix_platform_api_keys_last_used_at", ["last_used_at"], False),
        ("ix_platform_api_keys_status_created", ["status", "created_at", "id"], False),
    ):
        op.create_index(index_name, "platform_api_keys", columns, unique=unique)


def downgrade() -> None:
    op.drop_table("platform_api_keys")
    op.drop_index("ix_users_primary_organization_unit_id", table_name="users")
    op.drop_index("ix_users_employee_code", table_name="users")
    op.drop_constraint(
        "fk_users_primary_organization_unit_id",
        "users",
        type_="foreignkey",
    )
    op.drop_column("users", "updated_at")
    op.drop_column("users", "primary_organization_unit_id")
    op.drop_column("users", "job_title")
    op.drop_column("users", "employee_code")
    op.drop_table("organization_units")
