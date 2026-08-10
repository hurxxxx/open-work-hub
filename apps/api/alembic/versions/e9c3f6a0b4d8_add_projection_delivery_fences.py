"""Add nullable projection event fences to Search and RAG delivery jobs.

Revision ID: e9c3f6a0b4d8
Revises: d8b2e5f9a3c7
Create Date: 2026-07-22 20:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e9c3f6a0b4d8"
down_revision = "d8b2e5f9a3c7"
branch_labels = None
depends_on = None


_DELIVERY_TABLES = ("search_index_jobs", "rag_sync_jobs")
_POSTGRESQL_LOCK_TIMEOUT = "5s"


def upgrade() -> None:
    _set_postgresql_lock_timeout()
    for table_name in _DELIVERY_TABLES:
        if op.get_bind().dialect.name == "postgresql":
            _upgrade_postgresql_table(table_name)
        else:
            _upgrade_batch_table(table_name)


def downgrade() -> None:
    _set_postgresql_lock_timeout()
    for table_name in reversed(_DELIVERY_TABLES):
        if op.get_bind().dialect.name == "postgresql":
            _downgrade_postgresql_table(table_name)
        else:
            _downgrade_batch_table(table_name)


def _upgrade_postgresql_table(table_name: str) -> None:
    if table_name == "search_index_jobs":
        op.add_column(
            table_name,
            sa.Column("resource_type", sa.String(length=64), nullable=True),
        )
    op.add_column(
        table_name,
        sa.Column("projection_event_sequence", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("projection_version", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("desired_state", sa.String(length=16), nullable=True),
    )
    constraint_name = f"ck_{table_name}_desired_state"
    op.execute(
        sa.text(
            f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
            "CHECK (desired_state IS NULL OR desired_state IN ('active','deleted')) "
            "NOT VALID"
        )
    )
    constraint_name = f"fk_{table_name}_projection_event_sequence"
    op.execute(
        sa.text(
            f'ALTER TABLE "{table_name}" '
            f'ADD CONSTRAINT "{constraint_name}" '
            "FOREIGN KEY (projection_event_sequence) "
            "REFERENCES retrieval_projection_events(event_sequence) "
            "ON DELETE RESTRICT NOT VALID"
        )
    )


def _upgrade_batch_table(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        if table_name == "search_index_jobs":
            batch_op.add_column(sa.Column("resource_type", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("projection_event_sequence", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("projection_version", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("desired_state", sa.String(length=16), nullable=True))
        batch_op.create_check_constraint(
            f"ck_{table_name}_desired_state",
            "desired_state IS NULL OR desired_state IN ('active','deleted')",
        )
        batch_op.create_foreign_key(
            f"fk_{table_name}_projection_event_sequence",
            "retrieval_projection_events",
            ["projection_event_sequence"],
            ["event_sequence"],
            ondelete="RESTRICT",
        )


def _downgrade_postgresql_table(table_name: str) -> None:
    op.drop_constraint(
        f"fk_{table_name}_projection_event_sequence",
        table_name,
        type_="foreignkey",
    )
    op.drop_constraint(
        f"ck_{table_name}_desired_state",
        table_name,
        type_="check",
    )
    op.drop_column(table_name, "desired_state")
    op.drop_column(table_name, "projection_version")
    op.drop_column(table_name, "projection_event_sequence")
    if table_name == "search_index_jobs":
        op.drop_column(table_name, "resource_type")


def _downgrade_batch_table(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_constraint(
            f"fk_{table_name}_projection_event_sequence",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            f"ck_{table_name}_desired_state",
            type_="check",
        )
        batch_op.drop_column("desired_state")
        batch_op.drop_column("projection_version")
        batch_op.drop_column("projection_event_sequence")
        if table_name == "search_index_jobs":
            batch_op.drop_column("resource_type")


def _set_postgresql_lock_timeout() -> None:
    """Keep expand/contract DDL transactional while bounding lock waits."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"SET LOCAL lock_timeout = '{_POSTGRESQL_LOCK_TIMEOUT}'"))
