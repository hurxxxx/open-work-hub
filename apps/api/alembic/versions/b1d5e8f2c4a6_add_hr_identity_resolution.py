"""add integrated HR workforce classification and manual identity resolution

Revision ID: b1d5e8f2c4a6
Revises: a0c4e7f1b6d9
Create Date: 2026-07-29 18:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b1d5e8f2c4a6"
down_revision: str | Sequence[str] | None = "a0c4e7f1b6d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY_RESOLUTION_HASH = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"


def upgrade() -> None:
    op.create_table(
        "hr_identity_resolution_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_hr_identity_resolution_state_singleton"),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_hr_identity_resolution_state_revision_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO hr_identity_resolution_state (id, revision, updated_at) "
            "VALUES (1, 0, CURRENT_TIMESTAMP)"
        )
    )

    op.create_table(
        "hr_manual_identity_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("groupware_source_identity", sa.String(length=160), nullable=False),
        sa.Column("groupware_employee_code", sa.String(length=40), nullable=False),
        sa.Column("erp_employee_code", sa.String(length=40), nullable=False),
        sa.Column("matched_name", sa.String(length=160), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active','revoked')",
            name="ck_hr_manual_identity_links_status",
        ),
        sa.CheckConstraint(
            "length(trim(groupware_source_identity)) > 0",
            name="ck_hr_manual_identity_links_groupware_identity",
        ),
        sa.CheckConstraint(
            "erp_employee_code = upper(trim(erp_employee_code)) AND length(erp_employee_code) > 0",
            name="ck_hr_manual_identity_links_erp_code",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) "
            "OR (status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_hr_manual_identity_links_revocation",
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
    op.create_index(
        "ix_hr_manual_identity_links_groupware_source_identity",
        "hr_manual_identity_links",
        ["groupware_source_identity"],
    )
    op.create_index(
        "ix_hr_manual_identity_links_erp_employee_code",
        "hr_manual_identity_links",
        ["erp_employee_code"],
    )
    op.create_index(
        "ix_hr_manual_identity_links_status",
        "hr_manual_identity_links",
        ["status"],
    )
    op.create_index(
        "ix_hr_manual_identity_links_created_by_user_id",
        "hr_manual_identity_links",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_hr_manual_identity_links_created_at",
        "hr_manual_identity_links",
        ["created_at"],
    )
    op.create_index(
        "ix_hr_manual_identity_links_revoked_by_user_id",
        "hr_manual_identity_links",
        ["revoked_by_user_id"],
    )
    op.create_index(
        "ix_hr_manual_identity_links_revoked_at",
        "hr_manual_identity_links",
        ["revoked_at"],
    )
    op.create_index(
        "uq_hr_manual_identity_links_active_groupware",
        "hr_manual_identity_links",
        ["groupware_source_identity"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_hr_manual_identity_links_active_erp",
        "hr_manual_identity_links",
        ["erp_employee_code"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.add_column(
        "hr_master_runs",
        sa.Column("identity_resolution_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "hr_master_runs",
        sa.Column(
            "identity_resolution_hash",
            sa.String(length=64),
            server_default=_EMPTY_RESOLUTION_HASH,
            nullable=False,
        ),
    )
    op.add_column(
        "hr_master_runs",
        sa.Column("external_row_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_hr_master_runs_external_count_nonnegative",
        "hr_master_runs",
        "external_row_count >= 0",
    )
    op.drop_index(
        "uq_hr_master_runs_succeeded_source_pair_schema",
        table_name="hr_master_runs",
    )
    op.create_index(
        "uq_hr_master_runs_succeeded_source_pair_schema",
        "hr_master_runs",
        [
            "erp_run_id",
            "groupware_run_id",
            "schema_version",
            "identity_resolution_revision",
        ],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
        sqlite_where=sa.text("status = 'succeeded'"),
    )

    op.add_column(
        "hr_master_person_rows",
        sa.Column("workforce_category", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "hr_master_person_rows",
        sa.Column("identity_resolution_kind", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "hr_master_person_rows",
        sa.Column("groupware_source_identity", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "hr_master_person_rows",
        sa.Column("manual_identity_link_id", sa.String(length=36), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE hr_master_person_rows SET workforce_category = CASE "
            "WHEN reconciliation_status = 'matched' THEN 'internal' "
            "WHEN reconciliation_status = 'erp_only' THEN 'field' "
            "ELSE 'unresolved' END"
        )
    )
    op.execute(
        sa.text(
            "UPDATE hr_master_person_rows SET identity_resolution_kind = CASE "
            "WHEN reconciliation_status = 'matched' THEN 'employee_code' "
            "ELSE 'none' END"
        )
    )
    op.alter_column(
        "hr_master_person_rows",
        "workforce_category",
        nullable=False,
        server_default="unresolved",
    )
    op.alter_column(
        "hr_master_person_rows",
        "identity_resolution_kind",
        nullable=False,
        server_default="none",
    )
    op.create_check_constraint(
        "ck_hr_master_person_rows_workforce_category",
        "hr_master_person_rows",
        "workforce_category IN ('internal','field','external','unresolved')",
    )
    op.create_check_constraint(
        "ck_hr_master_person_rows_identity_resolution_kind",
        "hr_master_person_rows",
        "identity_resolution_kind IN ('employee_code','manual','none')",
    )
    op.create_foreign_key(
        "fk_hr_master_person_rows_manual_identity_link_id",
        "hr_master_person_rows",
        "hr_manual_identity_links",
        ["manual_identity_link_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_hr_master_person_rows_workforce_category",
        "hr_master_person_rows",
        ["workforce_category"],
    )
    op.create_index(
        "ix_hr_master_person_rows_identity_resolution_kind",
        "hr_master_person_rows",
        ["identity_resolution_kind"],
    )
    op.create_index(
        "ix_hr_master_person_rows_groupware_source_identity",
        "hr_master_person_rows",
        ["groupware_source_identity"],
    )
    op.create_index(
        "ix_hr_master_person_rows_manual_identity_link_id",
        "hr_master_person_rows",
        ["manual_identity_link_id"],
    )

    op.add_column(
        "hr_master_conflict_rows",
        sa.Column("workforce_category", sa.String(length=24), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE hr_master_conflict_rows SET workforce_category = CASE "
            "WHEN source_system = 'groupware' AND "
            "(reason_code = 'missing_employee_code' "
            "OR normalized_employee_code IN ('Z0000','Z00000')) "
            "THEN 'external' ELSE 'unresolved' END"
        )
    )
    op.alter_column(
        "hr_master_conflict_rows",
        "workforce_category",
        nullable=False,
        server_default="unresolved",
    )
    op.create_check_constraint(
        "ck_hr_master_conflict_rows_workforce_category",
        "hr_master_conflict_rows",
        "workforce_category IN ('internal','field','external','unresolved')",
    )
    op.create_index(
        "ix_hr_master_conflict_rows_workforce_category",
        "hr_master_conflict_rows",
        ["workforce_category"],
    )

    op.create_table(
        "hr_master_external_person_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("master_run_id", sa.String(length=36), nullable=False),
        sa.Column("groupware_source_identity", sa.String(length=160), nullable=False),
        sa.Column("employee_code", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("position", sa.String(length=160), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("login_id", sa.String(length=120), nullable=True),
        sa.Column("group_code", sa.String(length=80), nullable=True),
        sa.Column("group_name", sa.String(length=255), nullable=True),
        sa.Column("groupware_snapshot_row_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(groupware_source_identity)) > 0",
            name="ck_hr_master_external_rows_groupware_identity",
        ),
        sa.CheckConstraint(
            "employee_code IS NULL OR "
            "(employee_code = upper(trim(employee_code)) AND length(employee_code) > 0)",
            name="ck_hr_master_external_rows_employee_code",
        ),
        sa.ForeignKeyConstraint(
            ["master_run_id"],
            ["hr_master_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "master_run_id",
            "groupware_source_identity",
            name="uq_hr_master_external_rows_run_identity",
        ),
    )
    for index_name, columns in (
        ("ix_hr_master_external_person_rows_master_run_id", ["master_run_id"]),
        (
            "ix_hr_master_external_person_rows_groupware_source_identity",
            ["groupware_source_identity"],
        ),
        ("ix_hr_master_external_person_rows_employee_code", ["employee_code"]),
        ("ix_hr_master_external_person_rows_name", ["name"]),
        ("ix_hr_master_external_person_rows_email", ["email"]),
        ("ix_hr_master_external_person_rows_login_id", ["login_id"]),
        ("ix_hr_master_external_person_rows_group_code", ["group_code"]),
        ("ix_hr_master_external_person_rows_group_name", ["group_name"]),
        (
            "ix_hr_master_external_person_rows_groupware_snapshot_row_id",
            ["groupware_snapshot_row_id"],
        ),
        ("ix_hr_master_external_person_rows_created_at", ["created_at"]),
        ("ix_hr_master_external_rows_run_code", ["master_run_id", "employee_code"]),
        ("ix_hr_master_external_rows_run_group", ["master_run_id", "group_code"]),
    ):
        op.create_index(index_name, "hr_master_external_person_rows", columns)


def downgrade() -> None:
    op.drop_table("hr_master_external_person_rows")

    op.drop_index(
        "ix_hr_master_conflict_rows_workforce_category",
        table_name="hr_master_conflict_rows",
    )
    op.drop_constraint(
        "ck_hr_master_conflict_rows_workforce_category",
        "hr_master_conflict_rows",
        type_="check",
    )
    op.drop_column("hr_master_conflict_rows", "workforce_category")

    for index_name in (
        "ix_hr_master_person_rows_manual_identity_link_id",
        "ix_hr_master_person_rows_groupware_source_identity",
        "ix_hr_master_person_rows_identity_resolution_kind",
        "ix_hr_master_person_rows_workforce_category",
    ):
        op.drop_index(index_name, table_name="hr_master_person_rows")
    op.drop_constraint(
        "fk_hr_master_person_rows_manual_identity_link_id",
        "hr_master_person_rows",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_hr_master_person_rows_identity_resolution_kind",
        "hr_master_person_rows",
        type_="check",
    )
    op.drop_constraint(
        "ck_hr_master_person_rows_workforce_category",
        "hr_master_person_rows",
        type_="check",
    )
    op.drop_column("hr_master_person_rows", "manual_identity_link_id")
    op.drop_column("hr_master_person_rows", "groupware_source_identity")
    op.drop_column("hr_master_person_rows", "identity_resolution_kind")
    op.drop_column("hr_master_person_rows", "workforce_category")

    op.drop_index(
        "uq_hr_master_runs_succeeded_source_pair_schema",
        table_name="hr_master_runs",
    )
    op.create_index(
        "uq_hr_master_runs_succeeded_source_pair_schema",
        "hr_master_runs",
        ["erp_run_id", "groupware_run_id", "schema_version"],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
        sqlite_where=sa.text("status = 'succeeded'"),
    )
    op.drop_constraint(
        "ck_hr_master_runs_external_count_nonnegative",
        "hr_master_runs",
        type_="check",
    )
    op.drop_column("hr_master_runs", "external_row_count")
    op.drop_column("hr_master_runs", "identity_resolution_hash")
    op.drop_column("hr_master_runs", "identity_resolution_revision")

    op.drop_table("hr_manual_identity_links")
    op.drop_table("hr_identity_resolution_state")
