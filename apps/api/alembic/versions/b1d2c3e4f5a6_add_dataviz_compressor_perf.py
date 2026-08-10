"""add_dataviz_compressor_perf

Revision ID: b1d2c3e4f5a6
Revises: fa0b1c2d3e5f
Create Date: 2026-05-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1d2c3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "fa0b1c2d3e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataviz_perf_data",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("refrigerant", sa.String(length=16), nullable=False),
        sa.Column("capacity", sa.String(length=32), nullable=False),
        sa.Column("test_group", sa.String(length=40), nullable=False),
        sa.Column("comp_type", sa.String(length=120), nullable=False),
        sa.Column("serial_no", sa.String(length=120), nullable=False),
        sa.Column("test_date", sa.String(length=80), nullable=False),
        sa.Column("car_model", sa.String(length=80), nullable=False),
        sa.Column("engine_spec", sa.String(length=160), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=False),
        sa.Column("source_file", sa.String(length=512), nullable=False),
        sa.Column("rpm", sa.Float(), nullable=True),
        sa.Column("pd", sa.Float(), nullable=True),
        sa.Column("td", sa.Float(), nullable=True),
        sa.Column("ps", sa.Float(), nullable=True),
        sa.Column("ts", sa.Float(), nullable=True),
        sa.Column("pc", sa.Float(), nullable=True),
        sa.Column("mass_flow", sa.Float(), nullable=True),
        sa.Column("vol_eff", sa.Float(), nullable=True),
        sa.Column("ocr", sa.Float(), nullable=True),
        sa.Column("cooling_cap_a", sa.Float(), nullable=True),
        sa.Column("cooling_cap_f", sa.Float(), nullable=True),
        sa.Column("power_kw", sa.Float(), nullable=True),
        sa.Column("cop_sc", sa.Float(), nullable=True),
        sa.Column("heat_balance", sa.Float(), nullable=True),
        sa.Column("torque", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("category IN ('가변','전동')", name="ck_dataviz_perf_data_category"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataviz_perf_data_workspace_id", "dataviz_perf_data", ["workspace_id"])
    op.create_index("ix_dataviz_perf_data_owner_id", "dataviz_perf_data", ["owner_id"])
    op.create_index("ix_dataviz_perf_data_category", "dataviz_perf_data", ["category"])
    op.create_index("ix_dataviz_perf_data_refrigerant", "dataviz_perf_data", ["refrigerant"])
    op.create_index("ix_dataviz_perf_data_capacity", "dataviz_perf_data", ["capacity"])
    op.create_index("ix_dataviz_perf_data_test_group", "dataviz_perf_data", ["test_group"])
    op.create_index("ix_dataviz_perf_data_comp_type", "dataviz_perf_data", ["comp_type"])
    op.create_index("ix_dataviz_perf_data_serial_no", "dataviz_perf_data", ["serial_no"])
    op.create_index("ix_dataviz_perf_data_car_model", "dataviz_perf_data", ["car_model"])
    op.create_index("ix_dataviz_perf_data_source_file", "dataviz_perf_data", ["source_file"])
    op.create_index(
        "ix_dataviz_perf_data_workspace_filter",
        "dataviz_perf_data",
        ["workspace_id", "category", "refrigerant", "capacity", "source_file"],
    )
    op.create_index(
        "ix_dataviz_perf_data_workspace_created",
        "dataviz_perf_data",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "dataviz_perf_processed_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("refrigerant", sa.String(length=16), nullable=False),
        sa.Column("capacity", sa.String(length=32), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "filename",
            "category",
            "refrigerant",
            "capacity",
            name="uq_dataviz_perf_processed_file_scope",
        ),
    )
    op.create_index(
        "ix_dataviz_perf_processed_files_workspace_id",
        "dataviz_perf_processed_files",
        ["workspace_id"],
    )
    op.create_index(
        "ix_dataviz_perf_processed_files_filter",
        "dataviz_perf_processed_files",
        ["workspace_id", "category", "refrigerant", "capacity"],
    )

    op.create_table(
        "dataviz_car_model_refs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "code", name="uq_dataviz_car_model_ref_workspace_code"),
    )
    op.create_index("ix_dataviz_car_model_refs_workspace_id", "dataviz_car_model_refs", ["workspace_id"])
    op.create_index("ix_dataviz_car_model_refs_code", "dataviz_car_model_refs", ["code"])

    op.create_table(
        "dataviz_perf_tolerance",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("refrigerant", sa.String(length=16), nullable=False),
        sa.Column("capacity", sa.String(length=32), nullable=False),
        sa.Column("car_model", sa.String(length=80), nullable=False),
        sa.Column("test_group", sa.String(length=40), nullable=False),
        sa.Column("field_name", sa.String(length=60), nullable=False),
        sa.Column("ref_value", sa.Float(), nullable=True),
        sa.Column("tolerance", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
            "car_model",
            "test_group",
            "field_name",
            name="uq_dataviz_perf_tolerance_scope",
        ),
    )
    op.create_index("ix_dataviz_perf_tolerance_workspace_id", "dataviz_perf_tolerance", ["workspace_id"])
    op.create_index(
        "ix_dataviz_perf_tolerance_lookup",
        "dataviz_perf_tolerance",
        ["workspace_id", "category", "refrigerant", "capacity", "car_model"],
    )

    op.create_table(
        "dataviz_perf_tol_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("refrigerant", sa.String(length=16), nullable=False),
        sa.Column("capacity", sa.String(length=32), nullable=False),
        sa.Column("profile_name", sa.String(length=80), server_default=sa.text("'BASE'"), nullable=False),
        sa.Column("test_group", sa.String(length=40), nullable=False),
        sa.Column("field_name", sa.String(length=60), nullable=False),
        sa.Column("tol_value", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
            "profile_name",
            "test_group",
            "field_name",
            name="uq_dataviz_perf_tol_profile_scope",
        ),
    )
    op.create_index("ix_dataviz_perf_tol_profiles_workspace_id", "dataviz_perf_tol_profiles", ["workspace_id"])
    op.create_index(
        "ix_dataviz_perf_tol_profiles_lookup",
        "dataviz_perf_tol_profiles",
        ["workspace_id", "category", "refrigerant", "capacity", "profile_name"],
    )

    op.create_table(
        "dataviz_perf_tol_profile_cars",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("refrigerant", sa.String(length=16), nullable=False),
        sa.Column("capacity", sa.String(length=32), nullable=False),
        sa.Column("profile_name", sa.String(length=80), nullable=False),
        sa.Column("car_model", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
            "profile_name",
            "car_model",
            name="uq_dataviz_perf_tol_profile_car_scope",
        ),
    )
    op.create_index(
        "ix_dataviz_perf_tol_profile_cars_workspace_id",
        "dataviz_perf_tol_profile_cars",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dataviz_perf_tol_profile_cars_workspace_id", table_name="dataviz_perf_tol_profile_cars")
    op.drop_table("dataviz_perf_tol_profile_cars")
    op.drop_index("ix_dataviz_perf_tol_profiles_lookup", table_name="dataviz_perf_tol_profiles")
    op.drop_index("ix_dataviz_perf_tol_profiles_workspace_id", table_name="dataviz_perf_tol_profiles")
    op.drop_table("dataviz_perf_tol_profiles")
    op.drop_index("ix_dataviz_perf_tolerance_lookup", table_name="dataviz_perf_tolerance")
    op.drop_index("ix_dataviz_perf_tolerance_workspace_id", table_name="dataviz_perf_tolerance")
    op.drop_table("dataviz_perf_tolerance")
    op.drop_index("ix_dataviz_car_model_refs_code", table_name="dataviz_car_model_refs")
    op.drop_index("ix_dataviz_car_model_refs_workspace_id", table_name="dataviz_car_model_refs")
    op.drop_table("dataviz_car_model_refs")
    op.drop_index("ix_dataviz_perf_processed_files_filter", table_name="dataviz_perf_processed_files")
    op.drop_index("ix_dataviz_perf_processed_files_workspace_id", table_name="dataviz_perf_processed_files")
    op.drop_table("dataviz_perf_processed_files")
    op.drop_index("ix_dataviz_perf_data_workspace_created", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_workspace_filter", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_source_file", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_car_model", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_serial_no", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_comp_type", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_test_group", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_capacity", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_refrigerant", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_category", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_owner_id", table_name="dataviz_perf_data")
    op.drop_index("ix_dataviz_perf_data_workspace_id", table_name="dataviz_perf_data")
    op.drop_table("dataviz_perf_data")
