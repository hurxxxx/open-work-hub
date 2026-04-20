"""reset_docs_canonical_schema

Revision ID: e1f2a3b4c5d6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("fk_meetings_notes_page_id", "meetings", type_="foreignkey")
    op.drop_constraint("fk_meetings_notes_doc_id", "meetings", type_="foreignkey")
    op.execute("UPDATE meetings SET notes_doc_id = NULL, notes_page_id = NULL")
    op.execute("DELETE FROM meeting_doc_links")
    op.execute("UPDATE meeting_recordings SET linked_doc_id = NULL")
    op.execute("DELETE FROM media_files WHERE resource_type IN ('docs_native_page', 'space_doc_page')")

    op.execute("DROP TABLE IF EXISTS pms_user_doc_prefs CASCADE")
    op.execute("DROP TABLE IF EXISTS pms_space_doc_pages CASCADE")
    op.execute("DROP TABLE IF EXISTS pms_space_docs CASCADE")

    op.execute("DROP TABLE IF EXISTS docs_collab_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS docs_user_item_prefs CASCADE")
    op.execute("DROP TABLE IF EXISTS docs_meeting_access CASCADE")
    op.execute("DROP TABLE IF EXISTS docs_native_doc_link_shares CASCADE")
    op.execute("DROP TABLE IF EXISTS docs_native_doc_user_shares CASCADE")
    op.execute("DROP TABLE IF EXISTS docs_doc_containers CASCADE")
    op.execute("DROP TABLE IF EXISTS docs_native_doc_pages CASCADE")
    op.execute("DROP TABLE IF EXISTS docs_native_docs CASCADE")

    op.create_table(
        "docs_native_docs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_app", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("generation_kind", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("trashed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_docs_native_docs_workspace_id"), "docs_native_docs", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_docs_native_docs_owner_id"), "docs_native_docs", ["owner_id"], unique=False)
    op.create_index(op.f("ix_docs_native_docs_source_app"), "docs_native_docs", ["source_app"], unique=False)
    op.create_index(op.f("ix_docs_native_docs_source_kind"), "docs_native_docs", ["source_kind"], unique=False)
    op.create_index(op.f("ix_docs_native_docs_source_ref"), "docs_native_docs", ["source_ref"], unique=False)
    op.create_index(op.f("ix_docs_native_docs_generation_kind"), "docs_native_docs", ["generation_kind"], unique=False)
    op.create_index(op.f("ix_docs_native_docs_trashed_at"), "docs_native_docs", ["trashed_at"], unique=False)

    op.create_table(
        "docs_doc_containers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("container_app", sa.String(length=64), nullable=False),
        sa.Column("container_type", sa.String(length=64), nullable=False),
        sa.Column("container_id", sa.String(length=128), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["docs_native_docs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "doc_id",
            "container_app",
            "container_type",
            "container_id",
            name="uq_docs_doc_containers_doc_container",
        ),
    )
    op.create_index(op.f("ix_docs_doc_containers_doc_id"), "docs_doc_containers", ["doc_id"], unique=False)
    op.create_index(op.f("ix_docs_doc_containers_container_app"), "docs_doc_containers", ["container_app"], unique=False)
    op.create_index(op.f("ix_docs_doc_containers_container_type"), "docs_doc_containers", ["container_type"], unique=False)
    op.create_index(op.f("ix_docs_doc_containers_container_id"), "docs_doc_containers", ["container_id"], unique=False)
    op.create_index(op.f("ix_docs_doc_containers_is_primary"), "docs_doc_containers", ["is_primary"], unique=False)
    op.create_index(
        "ix_docs_doc_containers_lookup",
        "docs_doc_containers",
        ["container_app", "container_type", "container_id"],
        unique=False,
    )
    op.create_index(
        "uq_docs_doc_containers_primary",
        "docs_doc_containers",
        ["doc_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )

    op.create_table(
        "docs_native_doc_pages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_blocks", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("trashed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["doc_id"], ["docs_native_docs.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["docs_native_doc_pages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_docs_native_doc_pages_doc_id"), "docs_native_doc_pages", ["doc_id"], unique=False)
    op.create_index(op.f("ix_docs_native_doc_pages_parent_id"), "docs_native_doc_pages", ["parent_id"], unique=False)
    op.create_index(op.f("ix_docs_native_doc_pages_created_by_id"), "docs_native_doc_pages", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_docs_native_doc_pages_trashed_at"), "docs_native_doc_pages", ["trashed_at"], unique=False)

    op.create_table(
        "docs_native_doc_user_shares",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("access_level", sa.String(length=16), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["doc_id"], ["docs_native_docs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_id", "user_id", name="uq_docs_native_doc_user_share"),
    )
    op.create_index(op.f("ix_docs_native_doc_user_shares_doc_id"), "docs_native_doc_user_shares", ["doc_id"], unique=False)
    op.create_index(op.f("ix_docs_native_doc_user_shares_user_id"), "docs_native_doc_user_shares", ["user_id"], unique=False)
    op.create_index(op.f("ix_docs_native_doc_user_shares_created_by_id"), "docs_native_doc_user_shares", ["created_by_id"], unique=False)

    op.create_table(
        "docs_native_doc_link_shares",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("access_level", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["doc_id"], ["docs_native_docs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_id", name="uq_docs_native_doc_link_share_doc"),
    )
    op.create_index(op.f("ix_docs_native_doc_link_shares_doc_id"), "docs_native_doc_link_shares", ["doc_id"], unique=False)
    op.create_index(op.f("ix_docs_native_doc_link_shares_token"), "docs_native_doc_link_shares", ["token"], unique=True)
    op.create_index(op.f("ix_docs_native_doc_link_shares_active"), "docs_native_doc_link_shares", ["active"], unique=False)
    op.create_index(op.f("ix_docs_native_doc_link_shares_created_by_id"), "docs_native_doc_link_shares", ["created_by_id"], unique=False)

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
    op.create_index(op.f("ix_docs_meeting_access_doc_id"), "docs_meeting_access", ["doc_id"], unique=False)
    op.create_index(op.f("ix_docs_meeting_access_user_id"), "docs_meeting_access", ["user_id"], unique=False)
    op.create_index(op.f("ix_docs_meeting_access_granted_by_meeting_id"), "docs_meeting_access", ["granted_by_meeting_id"], unique=False)
    op.create_index(op.f("ix_docs_meeting_access_granted_by_user_id"), "docs_meeting_access", ["granted_by_user_id"], unique=False)
    op.create_index(op.f("ix_docs_meeting_access_revoked_by_user_id"), "docs_meeting_access", ["revoked_by_user_id"], unique=False)
    op.create_index("ix_docs_meeting_access_user_revoked", "docs_meeting_access", ["user_id", "revoked_at"], unique=False)
    op.create_index("ix_docs_meeting_access_meeting_revoked", "docs_meeting_access", ["granted_by_meeting_id", "revoked_at"], unique=False)
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

    op.create_table(
        "docs_user_item_prefs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_doc_id", sa.String(length=36), nullable=False),
        sa.Column("is_favorite", sa.Boolean(), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(), nullable=True),
        sa.Column("last_viewed_page_source_id", sa.String(length=36), nullable=True),
        sa.Column("last_viewed_page_title", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_type", "source_doc_id", name="uq_docs_user_item_pref"),
    )
    op.create_index(op.f("ix_docs_user_item_prefs_user_id"), "docs_user_item_prefs", ["user_id"], unique=False)
    op.create_index(op.f("ix_docs_user_item_prefs_source_type"), "docs_user_item_prefs", ["source_type"], unique=False)
    op.create_index(op.f("ix_docs_user_item_prefs_source_doc_id"), "docs_user_item_prefs", ["source_doc_id"], unique=False)

    op.create_table(
        "docs_collab_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_key", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_page_id", sa.String(length=36), nullable=False),
        sa.Column("yjs_state", sa.LargeBinary(), nullable=True),
        sa.Column("snapshot_content_blocks", sa.JSON(), nullable=True),
        sa.Column("last_snapshot_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_key", name="uq_docs_collab_documents_room_key"),
        sa.UniqueConstraint("source_type", "source_page_id", name="uq_docs_collab_documents_source_page"),
    )
    op.create_index("ix_docs_collab_documents_source_page", "docs_collab_documents", ["source_type", "source_page_id"], unique=False)

    op.create_foreign_key(
        "fk_meetings_notes_doc_id",
        "meetings",
        "docs_native_docs",
        ["notes_doc_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_meetings_notes_page_id",
        "meetings",
        "docs_native_doc_pages",
        ["notes_page_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_meeting_doc_links_doc_id",
        "meeting_doc_links",
        "docs_native_docs",
        ["doc_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_meeting_recordings_linked_doc_id",
        "meeting_recordings",
        "docs_native_docs",
        ["linked_doc_id"],
        ["id"],
    )


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported for the docs canonical reset.")
