"""Add administrator-managed Hermes research source settings.

Revision ID: d1f4a8c2e6b9
Revises: a7e3c1d9f5b2
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision: str = "d1f4a8c2e6b9"
down_revision: str | Sequence[str] | None = "a7e3c1d9f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = op.create_table(
        "hermes_research_source_settings",
        sa.Column("id", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "semantic_scholar_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "arxiv_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "openalex_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "crossref_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_hermes_research_source_settings_revision",
        ),
        sa.CheckConstraint(
            "id = 1",
            name="ck_hermes_research_source_settings_singleton",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(
        table,
        [
            {
                "id": 1,
                "semantic_scholar_enabled": False,
                "arxiv_enabled": True,
                "openalex_enabled": True,
                "crossref_enabled": True,
                "revision": 1,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("hermes_research_source_settings")
