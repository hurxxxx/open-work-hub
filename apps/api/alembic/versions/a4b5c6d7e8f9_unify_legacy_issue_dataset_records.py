"""unify legacy issue dataset records

Revision ID: a4b5c6d7e8f9
Revises: e9a0b1c2d3f5
Create Date: 2026-06-17 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a4b5c6d7e8f9"
down_revision: str | Sequence[str] | None = "e9a0b1c2d3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")

AIRCON_TABLE = "legacy_issue_aircon_records"
AIRCON_ATTACHMENT_TABLE = "legacy_issue_aircon_attachments"
MODULE_ATTACHMENT_TABLE = "legacy_issue_module_attachments"
MODULE_TABLES = (
    ("legacy_issue_electrical_mechanical_records", "electrical-mechanical"),
    ("legacy_issue_electrical_control_hw_records", "electrical-control-hw"),
    ("legacy_issue_electrical_control_sw_records", "electrical-control-sw"),
    ("legacy_issue_interior_records", "interior"),
    ("legacy_issue_cooling_module_records", "cooling-module"),
)
OLD_RECORD_TABLES = (AIRCON_TABLE, *(table_name for table_name, _dataset_key in MODULE_TABLES))
AIRCON_FIELD_KEYS = (
    "row_no",
    "legacy_issue_number",
    "occurrence_stage",
    "occurrence_type",
    "vehicle_model",
    "item",
    "sub_item",
    "occurrence_source",
    "defect_type",
    "supplier",
    "problem",
    "cause",
    "countermeasure",
    "attachment_note",
    "check_legacy_master",
    "check_design_check_sheet",
    "check_design_fmea",
    "check_design_standard",
    "design_reflect_spec_diff",
    "design_reflect_process",
    "design_reflect_under_review",
    "design_reflected",
    "notes",
)


def upgrade() -> None:
    _create_common_tables()
    _copy_aircon_records()
    _copy_module_records()
    _copy_attachments()
    _normalize_revision_dataset_keys()
    _normalize_record_history()
    _drop_legacy_tables()


def downgrade() -> None:
    # The previous mixed schema split one fixed aircon table from several JSON
    # module tables. Reconstructing that shape without losing updates made after
    # this migration would require dataset-specific column decisions that are no
    # longer canonical.
    pass


def _create_common_tables() -> None:
    op.create_table(
        "legacy_issue_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("stable_record_id", sa.String(length=36), nullable=True),
        sa.Column("field_values", JSONB_COMPAT, nullable=True),
        sa.Column("raw_fields", JSONB_COMPAT, nullable=True),
        sa.Column("imported_source_filename", sa.String(length=512), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["legacy_issue_data_revisions.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legacy_issue_records_workspace_dataset_revision",
        "legacy_issue_records",
        ["workspace_id", "dataset_key", "revision_id"],
    )
    op.create_index(
        "ix_legacy_issue_records_workspace_dataset_updated",
        "legacy_issue_records",
        ["workspace_id", "dataset_key", "updated_at"],
    )
    op.create_index(
        "ix_legacy_issue_records_workspace_dataset_stable",
        "legacy_issue_records",
        ["workspace_id", "dataset_key", "stable_record_id"],
    )
    for column in ("workspace_id", "dataset_key", "revision_id", "stable_record_id", "created_by_id"):
        op.create_index(op.f(f"ix_legacy_issue_records_{column}"), "legacy_issue_records", [column])

    op.create_table(
        "legacy_issue_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("stable_record_id", sa.String(length=36), nullable=True),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=160),
            server_default="application/octet-stream",
            nullable=False,
        ),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("uploaded_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["legacy_issue_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["legacy_issue_data_revisions.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legacy_issue_attachments_record",
        "legacy_issue_attachments",
        ["record_id", "created_at"],
    )
    op.create_index(
        "ix_legacy_issue_attachments_workspace",
        "legacy_issue_attachments",
        ["workspace_id", "dataset_key", "created_at"],
    )
    for column in (
        "workspace_id",
        "dataset_key",
        "revision_id",
        "stable_record_id",
        "record_id",
        "uploaded_by_id",
    ):
        op.create_index(op.f(f"ix_legacy_issue_attachments_{column}"), "legacy_issue_attachments", [column])


def _copy_aircon_records() -> None:
    bind = op.get_bind()
    if not _table_exists(AIRCON_TABLE):
        return
    field_values_expr = _aircon_field_values_expr(bind.dialect.name)
    bind.execute(
        sa.text(
            f"""
            INSERT INTO legacy_issue_records (
                id,
                workspace_id,
                dataset_key,
                revision_id,
                stable_record_id,
                field_values,
                raw_fields,
                imported_source_filename,
                imported_at,
                created_by_id,
                created_at,
                updated_at
            )
            SELECT
                id,
                workspace_id,
                'aircon',
                revision_id,
                stable_record_id,
                {field_values_expr},
                raw_fields,
                imported_source_filename,
                imported_at,
                created_by_id,
                created_at,
                updated_at
            FROM {AIRCON_TABLE}
            """
        )
    )


def _copy_module_records() -> None:
    bind = op.get_bind()
    for table_name, dataset_key in MODULE_TABLES:
        if not _table_exists(table_name):
            continue
        bind.execute(
            sa.text(
                f"""
                INSERT INTO legacy_issue_records (
                    id,
                    workspace_id,
                    dataset_key,
                    revision_id,
                    stable_record_id,
                    field_values,
                    raw_fields,
                    imported_source_filename,
                    imported_at,
                    created_by_id,
                    created_at,
                    updated_at
                )
                SELECT
                    id,
                    workspace_id,
                    :dataset_key,
                    revision_id,
                    stable_record_id,
                    field_values,
                    raw_fields,
                    imported_source_filename,
                    imported_at,
                    created_by_id,
                    created_at,
                    updated_at
                FROM {table_name}
                """
            ),
            {"dataset_key": dataset_key},
        )


def _copy_attachments() -> None:
    bind = op.get_bind()
    if _table_exists(AIRCON_ATTACHMENT_TABLE):
        bind.execute(
            sa.text(
                f"""
                INSERT INTO legacy_issue_attachments (
                    id,
                    workspace_id,
                    dataset_key,
                    revision_id,
                    stable_record_id,
                    record_id,
                    filename,
                    content_type,
                    size_bytes,
                    storage_key,
                    is_primary,
                    uploaded_by_id,
                    created_at
                )
                SELECT
                    id,
                    workspace_id,
                    'aircon',
                    revision_id,
                    stable_record_id,
                    record_id,
                    filename,
                    content_type,
                    size_bytes,
                    storage_key,
                    is_primary,
                    uploaded_by_id,
                    created_at
                FROM {AIRCON_ATTACHMENT_TABLE}
                WHERE record_id IN (SELECT id FROM legacy_issue_records WHERE dataset_key = 'aircon')
                """
            )
        )
    if _table_exists(MODULE_ATTACHMENT_TABLE):
        bind.execute(
            sa.text(
                f"""
                INSERT INTO legacy_issue_attachments (
                    id,
                    workspace_id,
                    dataset_key,
                    revision_id,
                    stable_record_id,
                    record_id,
                    filename,
                    content_type,
                    size_bytes,
                    storage_key,
                    is_primary,
                    uploaded_by_id,
                    created_at
                )
                SELECT
                    id,
                    workspace_id,
                    module_key,
                    revision_id,
                    stable_record_id,
                    record_id,
                    filename,
                    content_type,
                    size_bytes,
                    storage_key,
                    is_primary,
                    uploaded_by_id,
                    created_at
                FROM {MODULE_ATTACHMENT_TABLE}
                WHERE record_id IN (SELECT id FROM legacy_issue_records WHERE dataset_key = module_key)
                """
            )
        )


def _normalize_revision_dataset_keys() -> None:
    bind = op.get_bind()
    for table_name in ("legacy_issue_data_revisions", "legacy_issue_data_revision_events"):
        bind.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET dataset_key = replace(dataset_key, 'legacy_issue.module.', 'legacy_issue.')
                WHERE dataset_key LIKE 'legacy_issue.module.%'
                """
            )
        )


def _normalize_record_history() -> None:
    bind = op.get_bind()
    if not _table_exists("legacy_issue_record_history"):
        return
    op.add_column("legacy_issue_record_history", sa.Column("dataset_key", sa.String(length=80), nullable=True))
    bind.execute(
        sa.text(
            """
            UPDATE legacy_issue_record_history
            SET dataset_key = COALESCE(module_key, CASE WHEN record_kind = 'aircon' THEN 'aircon' ELSE NULL END)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE legacy_issue_record_history
            SET record_kind = 'legacy_issue'
            WHERE record_kind IN ('aircon', 'module')
            """
        )
    )
    op.drop_index("ix_legacy_issue_history_module_record", table_name="legacy_issue_record_history")
    op.drop_index(op.f("ix_legacy_issue_record_history_module_key"), table_name="legacy_issue_record_history")
    op.create_index(
        "ix_legacy_issue_history_dataset_record",
        "legacy_issue_record_history",
        ["workspace_id", "dataset_key", "record_id", "created_at"],
    )
    op.create_index(
        op.f("ix_legacy_issue_record_history_dataset_key"),
        "legacy_issue_record_history",
        ["dataset_key"],
    )
    op.drop_column("legacy_issue_record_history", "module_key")


def _drop_legacy_tables() -> None:
    for table_name in (AIRCON_ATTACHMENT_TABLE, MODULE_ATTACHMENT_TABLE, *OLD_RECORD_TABLES):
        if _table_exists(table_name):
            op.drop_table(table_name)


def _aircon_field_values_expr(dialect_name: str) -> str:
    if dialect_name == "postgresql":
        pairs = ", ".join(f"'{key}', {key}" for key in AIRCON_FIELD_KEYS)
        return f"jsonb_strip_nulls(jsonb_build_object({pairs}))"
    pairs = ", ".join(f"'{key}', {key}" for key in AIRCON_FIELD_KEYS)
    return f"json_object({pairs})"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in set(inspector.get_table_names())
