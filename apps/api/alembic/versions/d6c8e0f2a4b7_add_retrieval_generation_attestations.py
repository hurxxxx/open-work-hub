"""Add append-only retrieval generation attestations.

Revision ID: d6c8e0f2a4b7
Revises: c5b7d9e1f3a6
Create Date: 2026-07-29 15:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d6c8e0f2a4b7"
down_revision: str | None = "c5b7d9e1f3a6"
branch_labels: str | None = None
depends_on: str | None = None

_JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(
    sa.JSON(),
    "sqlite",
)


def upgrade() -> None:
    op.create_table(
        "retrieval_projection_generation_attestations",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("generation_key", sa.String(length=64), nullable=False),
        sa.Column("opensearch_generation_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("qdrant_generation_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column(
            "attestation_kind",
            sa.String(length=32),
            server_default=sa.text("'quality'"),
            nullable=False,
        ),
        sa.Column("source_files_event_watermark", sa.BigInteger(), nullable=False),
        sa.Column("source_resource_count", sa.BigInteger(), nullable=False),
        sa.Column("quality_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("quality_corpus_id", sa.String(length=255), nullable=False),
        sa.Column("quality_corpus_sha256", sa.String(length=64), nullable=False),
        sa.Column("scope_coverage", _JSONB_COMPAT, nullable=False),
        sa.Column("quality_details", _JSONB_COMPAT, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "attestation_kind = 'quality'",
            name="ck_retrieval_projection_generation_attestations_kind",
        ),
        sa.CheckConstraint(
            "source_files_event_watermark >= 0 AND source_resource_count > 0",
            name="ck_retrieval_projection_generation_attestations_source",
        ),
        sa.ForeignKeyConstraint(
            ["opensearch_generation_id"],
            ["retrieval_projection_generations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["qdrant_generation_id"],
            ["retrieval_projection_generations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generation_key",
            "source_files_event_watermark",
            name="uq_retrieval_projection_generation_attestations_watermark",
        ),
    )
    op.create_index(
        "ix_retrieval_gen_attestations_generation_created",
        "retrieval_projection_generation_attestations",
        ["generation_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrieval_gen_attestations_generation_created",
        table_name="retrieval_projection_generation_attestations",
    )
    op.drop_table("retrieval_projection_generation_attestations")
