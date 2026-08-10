"""add file search extraction artifacts

Revision ID: ba2c4d6e8f10
Revises: b9d1f3a5c7e9
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "ba2c4d6e8f10"
down_revision: str | Sequence[str] | None = "b9d1f3a5c7e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "file_manager_files",
        sa.Column(
            "extraction_status",
            sa.String(length=24),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "file_manager_files",
        sa.Column("extraction_content_checksum", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "file_manager_files",
        sa.Column("extraction_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "file_manager_files",
        sa.Column(
            "extraction_blocks",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "file_manager_files",
        sa.Column(
            "extraction_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "file_manager_files",
        sa.Column("extraction_error_code", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "file_manager_files",
        sa.Column("extracted_at", sa.DateTime(), nullable=True),
    )
    for column_name, column_type in (
        ("extraction_status", sa.String(length=24)),
        ("extraction_blocks", postgresql.JSONB(astext_type=sa.Text())),
        ("extraction_metadata", postgresql.JSONB(astext_type=sa.Text())),
    ):
        op.alter_column(
            "file_manager_files",
            column_name,
            existing_type=column_type,
            existing_nullable=False,
            server_default=None,
        )
    op.create_check_constraint(
        "ck_file_manager_files_extraction_status",
        "file_manager_files",
        "extraction_status IN ('pending','ready','unsupported','failed')",
    )
    op.create_index(
        op.f("ix_file_manager_files_extraction_status"),
        "file_manager_files",
        ["extraction_status"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_file_manager_files_extraction_status"),
        table_name="file_manager_files",
    )
    op.drop_constraint(
        "ck_file_manager_files_extraction_status",
        "file_manager_files",
        type_="check",
    )
    op.drop_column("file_manager_files", "extracted_at")
    op.drop_column("file_manager_files", "extraction_error_code")
    op.drop_column("file_manager_files", "extraction_metadata")
    op.drop_column("file_manager_files", "extraction_blocks")
    op.drop_column("file_manager_files", "extraction_text")
    op.drop_column("file_manager_files", "extraction_content_checksum")
    op.drop_column("file_manager_files", "extraction_status")
