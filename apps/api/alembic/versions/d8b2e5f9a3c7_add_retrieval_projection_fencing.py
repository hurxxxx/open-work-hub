"""add canonical retrieval projection heads and immutable events

Revision ID: d8b2e5f9a3c7
Revises: c7a1d4e8f2b6
Create Date: 2026-07-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8b2e5f9a3c7"
down_revision: str | Sequence[str] | None = "c7a1d4e8f2b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
_BIGINT_IDENTITY_COMPAT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "retrieval_projection_heads",
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "retrieval_partition_id",
            sa.Uuid(as_uuid=False),
            nullable=False,
        ),
        sa.Column("desired_state", sa.String(length=16), nullable=False),
        sa.Column("content_checksum", sa.String(length=128), nullable=True),
        sa.Column("visibility_checksum", sa.String(length=128), nullable=True),
        sa.Column("diagnostic_workspace_id", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "projection_version >= 1",
            name="ck_retrieval_projection_heads_version",
        ),
        sa.CheckConstraint(
            "desired_state IN ('active','deleted')",
            name="ck_retrieval_projection_heads_desired_state",
        ),
        sa.ForeignKeyConstraint(
            ["diagnostic_workspace_id"],
            ["workspaces.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_partition_id"],
            ["retrieval_partitions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("resource_type", "resource_id"),
    )
    op.create_index(
        "ix_retrieval_projection_heads_partition",
        "retrieval_projection_heads",
        ["retrieval_partition_id"],
    )

    op.create_table(
        "retrieval_projection_events",
        sa.Column(
            "event_sequence",
            _BIGINT_IDENTITY_COMPAT,
            sa.Identity(),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "retrieval_partition_id",
            sa.Uuid(as_uuid=False),
            nullable=False,
        ),
        sa.Column("change_kind", sa.String(length=16), nullable=False),
        sa.Column("desired_state", sa.String(length=16), nullable=False),
        sa.Column("content_checksum", sa.String(length=128), nullable=True),
        sa.Column("visibility_checksum", sa.String(length=128), nullable=True),
        sa.Column("diagnostic_workspace_id", sa.String(length=36), nullable=True),
        sa.Column("trace_context", _JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "projection_version >= 1",
            name="ck_retrieval_projection_events_version",
        ),
        sa.CheckConstraint(
            "change_kind IN ('content','visibility','delete','repair')",
            name="ck_retrieval_projection_events_change_kind",
        ),
        sa.CheckConstraint(
            "desired_state IN ('active','deleted')",
            name="ck_retrieval_projection_events_desired_state",
        ),
        sa.ForeignKeyConstraint(
            ["diagnostic_workspace_id"],
            ["workspaces.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_partition_id"],
            ["retrieval_partitions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_sequence"),
        sa.UniqueConstraint(
            "resource_type",
            "resource_id",
            "projection_version",
            name="uq_retrieval_projection_events_resource_version",
        ),
    )
    op.create_index(
        "ix_retrieval_projection_events_partition",
        "retrieval_projection_events",
        ["retrieval_partition_id"],
    )
    _create_projection_retention_triggers()


def downgrade() -> None:
    _drop_projection_retention_triggers()
    op.drop_index(
        "ix_retrieval_projection_events_partition",
        table_name="retrieval_projection_events",
    )
    op.drop_table("retrieval_projection_events")
    op.drop_index(
        "ix_retrieval_projection_heads_partition",
        table_name="retrieval_projection_heads",
    )
    op.drop_table("retrieval_projection_heads")


def _create_projection_retention_triggers() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION reject_retrieval_projection_head_delete()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'retrieval projection heads are permanent'
                        USING ERRCODE = '23514';
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_retrieval_projection_heads_reject_delete
                BEFORE DELETE ON retrieval_projection_heads
                FOR EACH ROW
                EXECUTE FUNCTION reject_retrieval_projection_head_delete()
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE FUNCTION reject_retrieval_projection_event_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'retrieval projection events are immutable'
                        USING ERRCODE = '23514';
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_retrieval_projection_events_immutable
                BEFORE UPDATE OR DELETE ON retrieval_projection_events
                FOR EACH ROW
                EXECUTE FUNCTION reject_retrieval_projection_event_mutation()
                """
            )
        )
        return

    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_retrieval_projection_heads_reject_delete
            BEFORE DELETE ON retrieval_projection_heads
            FOR EACH ROW
            BEGIN
                SELECT RAISE(ABORT, 'retrieval projection heads are permanent');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_retrieval_projection_events_reject_update
            BEFORE UPDATE ON retrieval_projection_events
            FOR EACH ROW
            BEGIN
                SELECT RAISE(ABORT, 'retrieval projection events are immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_retrieval_projection_events_reject_delete
            BEFORE DELETE ON retrieval_projection_events
            FOR EACH ROW
            BEGIN
                SELECT RAISE(ABORT, 'retrieval projection events are immutable');
            END
            """
        )
    )


def _drop_projection_retention_triggers() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_retrieval_projection_events_immutable "
                "ON retrieval_projection_events"
            )
        )
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_retrieval_projection_event_mutation()"))
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_retrieval_projection_heads_reject_delete "
                "ON retrieval_projection_heads"
            )
        )
        op.execute(sa.text("DROP FUNCTION IF EXISTS reject_retrieval_projection_head_delete()"))
        return

    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_retrieval_projection_events_reject_delete"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_retrieval_projection_events_reject_update"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_retrieval_projection_heads_reject_delete"))
