"""repair unified HR master retry and provenance constraints

Revision ID: f9d2b5e8c3a7
Revises: e8c1a4d7b2f6
Create Date: 2026-07-29 13:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f9d2b5e8c3a7"
down_revision: str | Sequence[str] | None = "e8c1a4d7b2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LEGACY_UNIQUE_CONSTRAINTS = (
    "uq_hr_master_runs_source_pair_schema",
    "uq_hr_master_runs_idempotency_key",
)
_PROVENANCE_COLUMNS = {
    "hr_master_person_rows": (
        ("erp_snapshot_row_id", "hr_user_snapshot_rows"),
        ("groupware_snapshot_row_id", "hr_user_snapshot_rows"),
    ),
    "hr_master_group_rows": (("source_snapshot_row_id", "hr_org_snapshot_rows"),),
    "hr_master_conflict_rows": (("source_snapshot_row_id", "hr_user_snapshot_rows"),),
}
_SUCCEEDED_SOURCE_PAIR_INDEX = "uq_hr_master_runs_succeeded_source_pair_schema"
_SQLITE_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _foreign_keys_by_column(
    inspector: sa.Inspector,
    table_name: str,
) -> dict[str, dict[str, object]]:
    return {
        str(foreign_key["constrained_columns"][0]): foreign_key
        for foreign_key in inspector.get_foreign_keys(table_name)
        if len(foreign_key["constrained_columns"]) == 1
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    unique_names = {
        constraint["name"] for constraint in inspector.get_unique_constraints("hr_master_runs")
    }
    legacy_unique_names = [name for name in _LEGACY_UNIQUE_CONSTRAINTS if name in unique_names]
    if legacy_unique_names:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(
                "hr_master_runs",
                recreate="always",
            ) as batch_op:
                for name in legacy_unique_names:
                    batch_op.drop_constraint(name, type_="unique")
        else:
            for name in legacy_unique_names:
                op.drop_constraint(name, "hr_master_runs", type_="unique")

    for table_name, provenance_columns in _PROVENANCE_COLUMNS.items():
        inspector = sa.inspect(bind)
        foreign_keys = _foreign_keys_by_column(inspector, table_name)
        columns_to_drop = [
            (column_name, referred_table)
            for column_name, referred_table in provenance_columns
            if column_name in foreign_keys
        ]
        if not columns_to_drop:
            continue
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(
                table_name,
                recreate="always",
                naming_convention=_SQLITE_NAMING_CONVENTION,
            ) as batch_op:
                for column_name, referred_table in columns_to_drop:
                    batch_op.drop_constraint(
                        f"fk_{table_name}_{column_name}_{referred_table}",
                        type_="foreignkey",
                    )
        else:
            for column_name, _referred_table in columns_to_drop:
                constraint_name = foreign_keys[column_name]["name"]
                if constraint_name:
                    op.drop_constraint(
                        str(constraint_name),
                        table_name,
                        type_="foreignkey",
                    )

    inspector = sa.inspect(bind)
    index_names = {index["name"] for index in inspector.get_indexes("hr_master_runs")}
    if _SUCCEEDED_SOURCE_PAIR_INDEX not in index_names:
        op.create_index(
            _SUCCEEDED_SOURCE_PAIR_INDEX,
            "hr_master_runs",
            ["erp_run_id", "groupware_run_id", "schema_version"],
            unique=True,
            postgresql_where=sa.text("status = 'succeeded'"),
            sqlite_where=sa.text("status = 'succeeded'"),
        )


def downgrade() -> None:
    # Compatibility-only normalization: the preceding revision now creates the
    # repaired schema directly, so restoring the superseded constraints would
    # make the database diverge from that revision and may reject retained
    # failed/building attempts or provenance IDs whose raw rows have expired.
    pass
