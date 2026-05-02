"""add_meeting_recording_sequence

Revision ID: a3c9d8e7f6b5
Revises: 7c4e1a92d8b6
Create Date: 2026-05-02 16:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c9d8e7f6b5"
down_revision: Union[str, Sequence[str], None] = "7c4e1a92d8b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meeting_recordings", sa.Column("sequence_no", sa.Integer(), nullable=True))
    op.execute(
        """
        WITH ranked AS (
          SELECT
            id,
            row_number() OVER (
              PARTITION BY meeting_id
              ORDER BY created_at ASC, id ASC
            ) AS seq
          FROM meeting_recordings
        )
        UPDATE meeting_recordings
        SET sequence_no = ranked.seq
        FROM ranked
        WHERE meeting_recordings.id = ranked.id
        """
    )
    op.alter_column("meeting_recordings", "sequence_no", nullable=False)
    op.create_index(
        "ix_meeting_recordings_meeting_sequence",
        "meeting_recordings",
        ["meeting_id", "sequence_no"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_meeting_recordings_meeting_sequence",
        "meeting_recordings",
        ["meeting_id", "sequence_no"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_meeting_recordings_meeting_sequence",
        "meeting_recordings",
        type_="unique",
    )
    op.drop_index("ix_meeting_recordings_meeting_sequence", table_name="meeting_recordings")
    op.drop_column("meeting_recordings", "sequence_no")
