"""add system performance (sysperf_*) tables

Revision ID: b7d3f1a9c5e2
Revises: a1f7c3e9d2b4
Create Date: 2026-06-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d3f1a9c5e2"
down_revision: Union[str, Sequence[str], None] = "a1f7c3e9d2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sysperf_standard_columns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("standard_name", sa.Text(), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_refrigerant_master",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "name",
            name="uq_sysperf_refrigerant_master_ws_name",
        ),
    )
    op.create_table(
        "sysperf_refrigerant_props",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("refrigerant_id", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("sat_pressure_kgcm2", sa.Float(), nullable=True),
        sa.Column("sat_pressure_kpa", sa.Float(), nullable=True),
        sa.Column("sat_pressure_bar", sa.Float(), nullable=True),
        sa.Column("liq_enthalpy", sa.Float(), nullable=True),
        sa.Column("vap_enthalpy", sa.Float(), nullable=True),
        sa.Column("liq_entropy", sa.Float(), nullable=True),
        sa.Column("vap_entropy", sa.Float(), nullable=True),
        sa.Column("liq_specific_vol", sa.Float(), nullable=True),
        sa.Column("vap_specific_vol", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_refrigerant_state_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("refrigerant_id", sa.Integer(), nullable=True),
        sa.Column("pressure_kpa", sa.Float(), nullable=True),
        sa.Column("pressure_kgcm2", sa.Float(), nullable=True),
        sa.Column("sat_temperature", sa.Float(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("enthalpy", sa.Float(), nullable=True),
        sa.Column("entropy", sa.Float(), nullable=True),
        sa.Column("specific_vol", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_item_keywords",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("item_n", sa.Integer(), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "item_n",
            name="uq_sysperf_item_keywords_ws_item",
        ),
    )
    op.create_table(
        "sysperf_car_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("era", sa.Text(), nullable=False),
        sa.Column("year", sa.Text(), nullable=False),
        sa.Column("car_name", sa.Text(), nullable=False),
        sa.Column("model_code", sa.Text(), nullable=False),
        sa.Column("segment_code", sa.Text(), nullable=False),
        sa.Column("segment_name", sa.Text(), nullable=False),
        sa.Column("refrigerant", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_parts_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("drive_type", sa.Text(), nullable=False),
        sa.Column("sub_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_parts_spec",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("car_code", sa.Text(), nullable=False),
        sa.Column("comp", sa.Text(), nullable=False),
        sa.Column("comp_prod", sa.Integer(), nullable=False),
        sa.Column("condenser", sa.Text(), nullable=False),
        sa.Column("cond_prod", sa.Integer(), nullable=False),
        sa.Column("txv", sa.Text(), nullable=False),
        sa.Column("txv_prod", sa.Integer(), nullable=False),
        sa.Column("hvac", sa.Text(), nullable=False),
        sa.Column("hvac_prod", sa.Integer(), nullable=False),
        sa.Column("pipe", sa.Text(), nullable=False),
        sa.Column("pipe_prod", sa.Integer(), nullable=False),
        sa.Column("refrigerant_charge", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_file_master",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("upload_date", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("sheet_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_test_master",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("sheet_name", sa.Text(), nullable=False),
        sa.Column("saved_at", sa.Text(), nullable=False),
        sa.Column("car_code", sa.Text(), nullable=False),
        sa.Column("car_type", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("car_number", sa.Text(), nullable=False),
        sa.Column("test_item", sa.Text(), nullable=False),
        sa.Column("test_date", sa.Text(), nullable=False),
        sa.Column("refrigerant_charge", sa.Text(), nullable=False),
        sa.Column("comp", sa.Text(), nullable=False),
        sa.Column("indoor_condenser", sa.Text(), nullable=False),
        sa.Column("condenser", sa.Text(), nullable=False),
        sa.Column("cooling_fan", sa.Text(), nullable=False),
        sa.Column("radiator", sa.Text(), nullable=False),
        sa.Column("ihx", sa.Text(), nullable=False),
        sa.Column("txv", sa.Text(), nullable=False),
        sa.Column("battery_chiller", sa.Text(), nullable=False),
        sa.Column("eva", sa.Text(), nullable=False),
        sa.Column("hvac", sa.Text(), nullable=False),
        sa.Column("heater_core", sa.Text(), nullable=False),
        sa.Column("ptc", sa.Text(), nullable=False),
        sa.Column("csv_path", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("col_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_sheet_header",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.Text(), nullable=False),
        sa.Column("header_row", sa.Integer(), nullable=False),
        sa.Column("info_row", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "file_id",
            "sheet_name",
            name="uq_sysperf_sheet_header_scope",
        ),
    )
    op.create_table(
        "sysperf_test_info",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.Text(), nullable=False),
        sa.Column("car_code", sa.Text(), nullable=False),
        sa.Column("car_model", sa.Text(), nullable=False),
        sa.Column("spec", sa.Text(), nullable=False),
        sa.Column("test_item", sa.Text(), nullable=False),
        sa.Column("test_date", sa.Text(), nullable=False),
        sa.Column("lot_no", sa.Text(), nullable=False),
        sa.Column("refrigerant", sa.Text(), nullable=False),
        sa.Column("refrigerant_charge", sa.Text(), nullable=False),
        sa.Column("parts_spec_id", sa.Integer(), nullable=False),
        sa.Column("comp", sa.Text(), nullable=False),
        sa.Column("condenser", sa.Text(), nullable=False),
        sa.Column("txv", sa.Text(), nullable=False),
        sa.Column("hvac", sa.Text(), nullable=False),
        sa.Column("pipe", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_column_mapping",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.Text(), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("standard_name", sa.Text(), nullable=False),
        sa.Column("col_index", sa.Integer(), nullable=True),
        sa.Column("confirmed", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sysperf_system_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("admin_only", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "key",
            name="uq_sysperf_system_config_ws_key",
        ),
    )

    for table_name in [
        "sysperf_standard_columns",
        "sysperf_refrigerant_master",
        "sysperf_refrigerant_props",
        "sysperf_refrigerant_state_points",
        "sysperf_item_keywords",
        "sysperf_car_models",
        "sysperf_parts_catalog",
        "sysperf_parts_spec",
        "sysperf_file_master",
        "sysperf_test_master",
        "sysperf_sheet_header",
        "sysperf_test_info",
        "sysperf_column_mapping",
        "sysperf_system_config",
    ]:
        op.create_index(
            f"ix_{table_name}_workspace_id",
            table_name,
            ["workspace_id"],
            unique=False,
        )
    op.create_index(
        "ix_sysperf_refrigerant_props_refrigerant_id",
        "sysperf_refrigerant_props",
        ["refrigerant_id"],
        unique=False,
    )
    op.create_index(
        "ix_sysperf_refrigerant_state_points_refrigerant_id",
        "sysperf_refrigerant_state_points",
        ["refrigerant_id"],
        unique=False,
    )
    op.create_index(
        "ix_sysperf_test_master_file_id",
        "sysperf_test_master",
        ["file_id"],
        unique=False,
    )
    op.create_index(
        "ix_sysperf_test_info_file_id",
        "sysperf_test_info",
        ["file_id"],
        unique=False,
    )
    op.create_index(
        "ix_sysperf_column_mapping_file_id",
        "sysperf_column_mapping",
        ["file_id"],
        unique=False,
    )


def downgrade() -> None:
    for table_name in [
        "sysperf_system_config",
        "sysperf_column_mapping",
        "sysperf_test_info",
        "sysperf_sheet_header",
        "sysperf_test_master",
        "sysperf_file_master",
        "sysperf_parts_spec",
        "sysperf_parts_catalog",
        "sysperf_car_models",
        "sysperf_item_keywords",
        "sysperf_refrigerant_state_points",
        "sysperf_refrigerant_props",
        "sysperf_refrigerant_master",
        "sysperf_standard_columns",
    ]:
        op.drop_table(table_name)
