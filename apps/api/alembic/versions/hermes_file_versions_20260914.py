"""Retain immutable Hermes workspace versions and trusted generating runs."""

from alembic import op
import sqlalchemy as sa

revision = "hermes_file_versions_20260914"
down_revision = "hermes_runtime_20260912"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hermes_file_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("hermes_session_bindings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("hermes_run_projections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("size_bytes >= 0", name="ck_hermes_file_revisions_size"),
    )
    for field in ("file_id", "session_id", "user_id", "run_id", "expires_at"):
        op.create_index(f"ix_hermes_file_revisions_{field}", "hermes_file_revisions", [field])
    # Existing bytes are a known snapshot, but their generating run is unknown.
    op.execute(
        sa.text("""
        INSERT INTO hermes_file_revisions
          (id, file_id, session_id, user_id, run_id, relative_path, size_bytes,
           sha256, object_key, media_type, expires_at, created_at)
        SELECT id, id, session_id, user_id, NULL, relative_path, size_bytes,
          sha256, object_key, media_type, expires_at, updated_at
        FROM hermes_session_files
    """)
    )


def downgrade() -> None:
    op.drop_table("hermes_file_revisions")
