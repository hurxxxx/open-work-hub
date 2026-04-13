"""add_meeting_access_grants

Revision ID: 8b1b7fa4b72b
Revises: 5f2f47dc2d11
Create Date: 2026-04-13 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b1b7fa4b72b"
down_revision: Union[str, Sequence[str], None] = "5f2f47dc2d11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pms_issue_user_access",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issue_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("access_level", sa.String(length=16), nullable=False),
        sa.Column("granted_by_meeting_id", sa.String(length=36), nullable=True),
        sa.Column("granted_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revoke_reason", sa.String(length=24), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["granted_by_meeting_id"], ["meetings.id"]),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["issue_id"], ["pms_issues.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pms_issue_user_access_issue_id"),
        "pms_issue_user_access",
        ["issue_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pms_issue_user_access_user_id"),
        "pms_issue_user_access",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pms_issue_user_access_granted_by_meeting_id"),
        "pms_issue_user_access",
        ["granted_by_meeting_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pms_issue_user_access_granted_by_user_id"),
        "pms_issue_user_access",
        ["granted_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pms_issue_user_access_revoked_by_user_id"),
        "pms_issue_user_access",
        ["revoked_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_pms_issue_user_access_user_revoked",
        "pms_issue_user_access",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_pms_issue_user_access_meeting_revoked",
        "pms_issue_user_access",
        ["granted_by_meeting_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_pms_issue_user_access_expires_active",
        "pms_issue_user_access",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "uq_pms_issue_user_access_active",
        "pms_issue_user_access",
        ["issue_id", "user_id", "granted_by_meeting_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "docs_meeting_access",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("access_level", sa.String(length=16), nullable=False),
        sa.Column("granted_by_meeting_id", sa.String(length=36), nullable=True),
        sa.Column("granted_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revoke_reason", sa.String(length=24), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["docs_native_docs.id"]),
        sa.ForeignKeyConstraint(["granted_by_meeting_id"], ["meetings.id"]),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_docs_meeting_access_doc_id"),
        "docs_meeting_access",
        ["doc_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_docs_meeting_access_user_id"),
        "docs_meeting_access",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_docs_meeting_access_granted_by_meeting_id"),
        "docs_meeting_access",
        ["granted_by_meeting_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_docs_meeting_access_granted_by_user_id"),
        "docs_meeting_access",
        ["granted_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_docs_meeting_access_revoked_by_user_id"),
        "docs_meeting_access",
        ["revoked_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_docs_meeting_access_user_revoked",
        "docs_meeting_access",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_docs_meeting_access_meeting_revoked",
        "docs_meeting_access",
        ["granted_by_meeting_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_docs_meeting_access_expires_active",
        "docs_meeting_access",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "uq_docs_meeting_access_active",
        "docs_meeting_access",
        ["doc_id", "user_id", "granted_by_meeting_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_docs_meeting_access_active", table_name="docs_meeting_access")
    op.drop_index("ix_docs_meeting_access_expires_active", table_name="docs_meeting_access")
    op.drop_index("ix_docs_meeting_access_meeting_revoked", table_name="docs_meeting_access")
    op.drop_index("ix_docs_meeting_access_user_revoked", table_name="docs_meeting_access")
    op.drop_index(op.f("ix_docs_meeting_access_revoked_by_user_id"), table_name="docs_meeting_access")
    op.drop_index(op.f("ix_docs_meeting_access_granted_by_user_id"), table_name="docs_meeting_access")
    op.drop_index(op.f("ix_docs_meeting_access_granted_by_meeting_id"), table_name="docs_meeting_access")
    op.drop_index(op.f("ix_docs_meeting_access_user_id"), table_name="docs_meeting_access")
    op.drop_index(op.f("ix_docs_meeting_access_doc_id"), table_name="docs_meeting_access")
    op.drop_table("docs_meeting_access")

    op.drop_index("uq_pms_issue_user_access_active", table_name="pms_issue_user_access")
    op.drop_index("ix_pms_issue_user_access_expires_active", table_name="pms_issue_user_access")
    op.drop_index("ix_pms_issue_user_access_meeting_revoked", table_name="pms_issue_user_access")
    op.drop_index("ix_pms_issue_user_access_user_revoked", table_name="pms_issue_user_access")
    op.drop_index(op.f("ix_pms_issue_user_access_revoked_by_user_id"), table_name="pms_issue_user_access")
    op.drop_index(op.f("ix_pms_issue_user_access_granted_by_user_id"), table_name="pms_issue_user_access")
    op.drop_index(op.f("ix_pms_issue_user_access_granted_by_meeting_id"), table_name="pms_issue_user_access")
    op.drop_index(op.f("ix_pms_issue_user_access_user_id"), table_name="pms_issue_user_access")
    op.drop_index(op.f("ix_pms_issue_user_access_issue_id"), table_name="pms_issue_user_access")
    op.drop_table("pms_issue_user_access")
