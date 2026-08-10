"""add managed HR workforce categories and projection decisions

Revision ID: c2e6f9a3d5b7
Revises: b1d5e8f2c4a6
Create Date: 2026-07-29 20:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c2e6f9a3d5b7"
down_revision: str | Sequence[str] | None = "b1d5e8f2c4a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hr_workforce_categories",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(code)) > 0",
            name="ck_hr_workforce_categories_code",
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_hr_workforce_categories_name",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_hr_workforce_categories_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    op.execute(
        sa.text(
            "INSERT INTO hr_workforce_categories "
            "(code, name, description, is_system, is_active, sort_order, "
            "created_at, updated_at) VALUES "
            "('internal', '일반 인력', 'ERP와 그룹웨어가 연결된 일반 인력', "
            "true, true, 10, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
            "('field', '현장직', 'ERP에만 존재하는 현장 인력', "
            "true, true, 20, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
            "('external', '해외/외부', '그룹웨어의 해외 또는 외부 인력', "
            "true, true, 30, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
            "('unresolved', '확인 필요', '정합 또는 분류 확인이 필요한 인력', "
            "true, true, 40, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )
    for index_name, columns in (
        ("ix_hr_workforce_categories_is_active", ["is_active"]),
        ("ix_hr_workforce_categories_created_by_user_id", ["created_by_user_id"]),
        ("ix_hr_workforce_categories_created_at", ["created_at"]),
        ("ix_hr_workforce_categories_updated_by_user_id", ["updated_by_user_id"]),
        ("ix_hr_workforce_categories_updated_at", ["updated_at"]),
        (
            "ix_hr_workforce_categories_active_sort",
            ["is_active", "sort_order", "code"],
        ),
    ):
        op.create_index(index_name, "hr_workforce_categories", columns)

    op.create_table(
        "hr_workforce_category_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject_kind", sa.String(length=32), nullable=False),
        sa.Column("subject_key", sa.String(length=160), nullable=False),
        sa.Column("category_code", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("activated_revision", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_revision", sa.Integer(), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "subject_kind IN ('erp_employee','groupware_identity')",
            name="ck_hr_workforce_assignments_subject_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active','revoked')",
            name="ck_hr_workforce_assignments_status",
        ),
        sa.CheckConstraint(
            "length(trim(subject_key)) > 0",
            name="ck_hr_workforce_assignments_subject_key",
        ),
        sa.CheckConstraint(
            "activated_revision >= 0",
            name="ck_hr_workforce_assignments_activated_revision",
        ),
        sa.CheckConstraint(
            "revoked_revision IS NULL OR revoked_revision >= activated_revision",
            name="ck_hr_workforce_assignments_revoked_revision",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL AND revoked_revision IS NULL) "
            "OR (status = 'revoked' AND revoked_at IS NOT NULL "
            "AND revoked_revision IS NOT NULL)",
            name="ck_hr_workforce_assignments_revocation",
        ),
        sa.ForeignKeyConstraint(
            ["category_code"],
            ["hr_workforce_categories.code"],
            ondelete="RESTRICT",
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
    for index_name, columns in (
        ("ix_hr_workforce_category_assignments_subject_kind", ["subject_kind"]),
        ("ix_hr_workforce_category_assignments_subject_key", ["subject_key"]),
        ("ix_hr_workforce_category_assignments_category_code", ["category_code"]),
        ("ix_hr_workforce_category_assignments_status", ["status"]),
        (
            "ix_hr_workforce_category_assignments_created_by_user_id",
            ["created_by_user_id"],
        ),
        ("ix_hr_workforce_category_assignments_created_at", ["created_at"]),
        (
            "ix_hr_workforce_category_assignments_revoked_by_user_id",
            ["revoked_by_user_id"],
        ),
        ("ix_hr_workforce_category_assignments_revoked_at", ["revoked_at"]),
    ):
        op.create_index(index_name, "hr_workforce_category_assignments", columns)
    op.create_index(
        "uq_hr_workforce_assignments_active_subject",
        "hr_workforce_category_assignments",
        ["subject_kind", "subject_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.add_column(
        "hr_manual_identity_links",
        sa.Column("activated_revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "hr_manual_identity_links",
        sa.Column("revoked_revision", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE hr_manual_identity_links SET activated_revision = 0, "
            "revoked_revision = CASE WHEN status = 'revoked' THEN 0 ELSE NULL END"
        )
    )
    op.alter_column(
        "hr_manual_identity_links",
        "activated_revision",
        nullable=False,
    )
    op.drop_constraint(
        "ck_hr_manual_identity_links_revocation",
        "hr_manual_identity_links",
        type_="check",
    )
    op.create_check_constraint(
        "ck_hr_manual_identity_links_activated_revision",
        "hr_manual_identity_links",
        "activated_revision >= 0",
    )
    op.create_check_constraint(
        "ck_hr_manual_identity_links_revoked_revision",
        "hr_manual_identity_links",
        "revoked_revision IS NULL OR revoked_revision >= activated_revision",
    )
    op.create_check_constraint(
        "ck_hr_manual_identity_links_revocation",
        "hr_manual_identity_links",
        "(status = 'active' AND revoked_at IS NULL AND revoked_revision IS NULL) "
        "OR (status = 'revoked' AND revoked_at IS NOT NULL "
        "AND revoked_revision IS NOT NULL)",
    )

    op.drop_constraint(
        "ck_hr_master_person_rows_workforce_category",
        "hr_master_person_rows",
        type_="check",
    )
    op.alter_column(
        "hr_master_person_rows",
        "workforce_category",
        existing_type=sa.String(length=24),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.add_column(
        "hr_master_person_rows",
        sa.Column(
            "inferred_workforce_category",
            sa.String(length=64),
            server_default="unresolved",
            nullable=False,
        ),
    )
    op.add_column(
        "hr_master_person_rows",
        sa.Column(
            "workforce_category_resolution_kind",
            sa.String(length=24),
            server_default="inferred",
            nullable=False,
        ),
    )
    op.add_column(
        "hr_master_person_rows",
        sa.Column("workforce_assignment_id", sa.String(length=36), nullable=True),
    )
    op.execute(
        sa.text("UPDATE hr_master_person_rows SET inferred_workforce_category = workforce_category")
    )
    op.create_check_constraint(
        "ck_hr_master_person_rows_workforce_category_resolution_kind",
        "hr_master_person_rows",
        "workforce_category_resolution_kind IN ('inferred','manual')",
    )
    op.create_foreign_key(
        "fk_hr_master_person_rows_inferred_workforce_category",
        "hr_master_person_rows",
        "hr_workforce_categories",
        ["inferred_workforce_category"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_hr_master_person_rows_workforce_category",
        "hr_master_person_rows",
        "hr_workforce_categories",
        ["workforce_category"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_hr_master_person_rows_workforce_assignment_id",
        "hr_master_person_rows",
        "hr_workforce_category_assignments",
        ["workforce_assignment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_hr_master_person_rows_inferred_workforce_category",
        "hr_master_person_rows",
        ["inferred_workforce_category"],
    )
    op.create_index(
        "ix_hr_master_person_rows_workforce_category_resolution_kind",
        "hr_master_person_rows",
        ["workforce_category_resolution_kind"],
    )
    op.create_index(
        "ix_hr_master_person_rows_workforce_assignment_id",
        "hr_master_person_rows",
        ["workforce_assignment_id"],
    )

    op.add_column(
        "hr_master_external_person_rows",
        sa.Column(
            "inferred_workforce_category",
            sa.String(length=64),
            server_default="external",
            nullable=False,
        ),
    )
    op.add_column(
        "hr_master_external_person_rows",
        sa.Column(
            "workforce_category",
            sa.String(length=64),
            server_default="external",
            nullable=False,
        ),
    )
    op.add_column(
        "hr_master_external_person_rows",
        sa.Column(
            "workforce_category_resolution_kind",
            sa.String(length=24),
            server_default="inferred",
            nullable=False,
        ),
    )
    op.add_column(
        "hr_master_external_person_rows",
        sa.Column("workforce_assignment_id", sa.String(length=36), nullable=True),
    )
    op.create_check_constraint(
        "ck_hr_master_external_rows_workforce_category_resolution_kind",
        "hr_master_external_person_rows",
        "workforce_category_resolution_kind IN ('inferred','manual')",
    )
    op.create_foreign_key(
        "fk_hr_master_external_rows_inferred_workforce_category",
        "hr_master_external_person_rows",
        "hr_workforce_categories",
        ["inferred_workforce_category"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_hr_master_external_rows_workforce_category",
        "hr_master_external_person_rows",
        "hr_workforce_categories",
        ["workforce_category"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_hr_master_external_rows_workforce_assignment_id",
        "hr_master_external_person_rows",
        "hr_workforce_category_assignments",
        ["workforce_assignment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_hr_master_external_person_rows_inferred_workforce_category",
        "hr_master_external_person_rows",
        ["inferred_workforce_category"],
    )
    op.create_index(
        "ix_hr_master_external_person_rows_workforce_category",
        "hr_master_external_person_rows",
        ["workforce_category"],
    )
    op.create_index(
        "ix_hr_master_external_rows_category_resolution",
        "hr_master_external_person_rows",
        ["workforce_category_resolution_kind"],
    )
    op.create_index(
        "ix_hr_master_external_person_rows_workforce_assignment_id",
        "hr_master_external_person_rows",
        ["workforce_assignment_id"],
    )

    op.drop_constraint(
        "ck_hr_master_conflict_rows_workforce_category",
        "hr_master_conflict_rows",
        type_="check",
    )
    op.alter_column(
        "hr_master_conflict_rows",
        "workforce_category",
        existing_type=sa.String(length=24),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.create_foreign_key(
        "fk_hr_master_conflict_rows_workforce_category",
        "hr_master_conflict_rows",
        "hr_workforce_categories",
        ["workforce_category"],
        ["code"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # v3 cannot read v4 materialized decisions. Remove only v4 projections so
    # the previous immutable v3 head becomes current again; source snapshots
    # and older master runs remain intact.
    op.execute(sa.text("DELETE FROM hr_master_runs WHERE schema_version = 'hr-master-v4'"))
    # Links created under v4 may connect differently named users, which the v3
    # builder does not support. Revoke those links before dropping the revision
    # markers so a rolled-back v3 build cannot consume them.
    op.execute(
        sa.text(
            "UPDATE hr_manual_identity_links "
            "SET status = 'revoked', "
            "revoked_revision = activated_revision, "
            "revocation_reason = COALESCE(revocation_reason, 'schema_downgrade'), "
            "revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP) "
            "WHERE status = 'active' AND activated_revision > 0"
        )
    )

    op.drop_constraint(
        "fk_hr_master_conflict_rows_workforce_category",
        "hr_master_conflict_rows",
        type_="foreignkey",
    )
    op.alter_column(
        "hr_master_conflict_rows",
        "workforce_category",
        existing_type=sa.String(length=64),
        type_=sa.String(length=24),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_hr_master_conflict_rows_workforce_category",
        "hr_master_conflict_rows",
        "workforce_category IN ('internal','field','external','unresolved')",
    )

    for index_name in (
        "ix_hr_master_external_person_rows_workforce_assignment_id",
        "ix_hr_master_external_rows_category_resolution",
        "ix_hr_master_external_person_rows_workforce_category",
        "ix_hr_master_external_person_rows_inferred_workforce_category",
    ):
        op.drop_index(index_name, table_name="hr_master_external_person_rows")
    for constraint_name in (
        "fk_hr_master_external_rows_workforce_assignment_id",
        "fk_hr_master_external_rows_workforce_category",
        "fk_hr_master_external_rows_inferred_workforce_category",
    ):
        op.drop_constraint(
            constraint_name,
            "hr_master_external_person_rows",
            type_="foreignkey",
        )
    op.drop_constraint(
        "ck_hr_master_external_rows_workforce_category_resolution_kind",
        "hr_master_external_person_rows",
        type_="check",
    )
    op.drop_column("hr_master_external_person_rows", "workforce_assignment_id")
    op.drop_column(
        "hr_master_external_person_rows",
        "workforce_category_resolution_kind",
    )
    op.drop_column("hr_master_external_person_rows", "workforce_category")
    op.drop_column("hr_master_external_person_rows", "inferred_workforce_category")

    for index_name in (
        "ix_hr_master_person_rows_workforce_assignment_id",
        "ix_hr_master_person_rows_workforce_category_resolution_kind",
        "ix_hr_master_person_rows_inferred_workforce_category",
    ):
        op.drop_index(index_name, table_name="hr_master_person_rows")
    for constraint_name in (
        "fk_hr_master_person_rows_workforce_assignment_id",
        "fk_hr_master_person_rows_workforce_category",
        "fk_hr_master_person_rows_inferred_workforce_category",
    ):
        op.drop_constraint(
            constraint_name,
            "hr_master_person_rows",
            type_="foreignkey",
        )
    op.drop_constraint(
        "ck_hr_master_person_rows_workforce_category_resolution_kind",
        "hr_master_person_rows",
        type_="check",
    )
    op.drop_column("hr_master_person_rows", "workforce_assignment_id")
    op.drop_column(
        "hr_master_person_rows",
        "workforce_category_resolution_kind",
    )
    op.drop_column("hr_master_person_rows", "inferred_workforce_category")
    op.alter_column(
        "hr_master_person_rows",
        "workforce_category",
        existing_type=sa.String(length=64),
        type_=sa.String(length=24),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_hr_master_person_rows_workforce_category",
        "hr_master_person_rows",
        "workforce_category IN ('internal','field','external','unresolved')",
    )

    for constraint_name in (
        "ck_hr_manual_identity_links_revocation",
        "ck_hr_manual_identity_links_revoked_revision",
        "ck_hr_manual_identity_links_activated_revision",
    ):
        op.drop_constraint(
            constraint_name,
            "hr_manual_identity_links",
            type_="check",
        )
    op.create_check_constraint(
        "ck_hr_manual_identity_links_revocation",
        "hr_manual_identity_links",
        "(status = 'active' AND revoked_at IS NULL) "
        "OR (status = 'revoked' AND revoked_at IS NOT NULL)",
    )
    op.drop_column("hr_manual_identity_links", "revoked_revision")
    op.drop_column("hr_manual_identity_links", "activated_revision")

    op.drop_table("hr_workforce_category_assignments")
    op.drop_table("hr_workforce_categories")
