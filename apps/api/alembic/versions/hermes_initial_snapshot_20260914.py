"""Give migrated latest files one coherent initial snapshot per session."""

from alembic import op
import sqlalchemy as sa

revision = "hermes_initial_snapshot_20260914"
down_revision = "hermes_file_versions_20260914"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only the original backfill reused the logical file ID as its revision ID.
    # Align its snapshot cutoff without changing catalog modification times or
    # any subsequently published immutable revision.
    op.execute(sa.text("""
        UPDATE hermes_file_revisions AS revision
        SET created_at = snapshot.cutoff
        FROM (
            SELECT session_id, MAX(created_at) AS cutoff
            FROM hermes_file_revisions
            WHERE id = file_id AND run_id IS NULL
            GROUP BY session_id
        ) AS snapshot
        WHERE revision.session_id = snapshot.session_id
          AND revision.id = revision.file_id AND revision.run_id IS NULL
    """))


def downgrade() -> None:
    # Snapshot repair remains compatible with the preceding schema. The
    # original per-file snapshot times cannot be reconstructed safely.
    pass
