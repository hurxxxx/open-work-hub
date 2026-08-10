"""add retrieval projection generation control plane

Revision ID: fc6d8b2e0a31
Revises: fb5e7a1c9d20
Create Date: 2026-07-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "fc6d8b2e0a31"
down_revision: str | Sequence[str] | None = "fb5e7a1c9d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "retrieval_projection_generations",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("backend", sa.String(length=16), nullable=False),
        sa.Column("generation_key", sa.String(length=64), nullable=False),
        sa.Column("physical_name", sa.String(length=255), nullable=False),
        sa.Column("alias_name", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            sa.String(length=32),
            server_default=sa.text("'preparing'"),
            nullable=False,
        ),
        sa.Column(
            "baseline_event_sequence",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "replay_event_sequence",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "validation_state",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("validation_details", _JSONB_COMPAT, nullable=True),
        sa.Column("expected_projection_count", sa.BigInteger(), nullable=True),
        sa.Column("content_checksum", sa.String(length=128), nullable=True),
        sa.Column("config_checksum", sa.String(length=128), nullable=True),
        sa.Column("previous_generation_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("rollback_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "backend IN ('opensearch','qdrant')",
            name="ck_retrieval_projection_generations_backend",
        ),
        sa.CheckConstraint(
            "state IN ('preparing','baselining','replaying','validating','ready',"
            "'activating','active','rollback','compensation_required','failed','retired')",
            name="ck_retrieval_projection_generations_state",
        ),
        sa.CheckConstraint(
            "validation_state IN ('pending','passed','failed')",
            name="ck_retrieval_projection_generations_validation_state",
        ),
        sa.CheckConstraint(
            "schema_version >= 1",
            name="ck_retrieval_projection_generations_schema_version",
        ),
        sa.CheckConstraint(
            "baseline_event_sequence >= 0 AND replay_event_sequence >= baseline_event_sequence",
            name="ck_retrieval_projection_generations_watermark",
        ),
        sa.ForeignKeyConstraint(
            ["previous_generation_id"],
            ["retrieval_projection_generations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "backend",
            "generation_key",
            name="uq_retrieval_projection_generations_backend_key",
        ),
        sa.UniqueConstraint(
            "backend",
            "physical_name",
            name="uq_retrieval_projection_generations_backend_physical",
        ),
    )
    op.create_index(
        "ix_retrieval_projection_generations_backend_state",
        "retrieval_projection_generations",
        ["backend", "state"],
    )
    op.create_index(
        "uq_retrieval_projection_generations_active_backend",
        "retrieval_projection_generations",
        ["backend"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
        sqlite_where=sa.text("state = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_retrieval_projection_generations_active_backend",
        table_name="retrieval_projection_generations",
    )
    op.drop_index(
        "ix_retrieval_projection_generations_backend_state",
        table_name="retrieval_projection_generations",
    )
    op.drop_table("retrieval_projection_generations")
