"""Guard retrieval projection event and head fences.

Revision ID: a9c3d2e1f4b5
Revises: f6d2a4c8e1b3
"""

from collections.abc import Sequence

from alembic import op


revision: str = "a9c3d2e1f4b5"
down_revision: str | Sequence[str] | None = "f6d2a4c8e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_retrieval_projection_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'retrieval projection events are immutable'
                USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_retrieval_projection_event_mutation
        BEFORE UPDATE OR DELETE ON retrieval_projection_events
        FOR EACH ROW
        EXECUTE FUNCTION reject_retrieval_projection_event_mutation();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_retrieval_projection_head_delete()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'retrieval projection heads must be tombstoned'
                USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_retrieval_projection_head_delete
        BEFORE DELETE ON retrieval_projection_heads
        FOR EACH ROW
        EXECUTE FUNCTION reject_retrieval_projection_head_delete();
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        "DROP TRIGGER IF EXISTS reject_retrieval_projection_head_delete "
        "ON retrieval_projection_heads"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_retrieval_projection_head_delete()")
    op.execute(
        "DROP TRIGGER IF EXISTS reject_retrieval_projection_event_mutation "
        "ON retrieval_projection_events"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_retrieval_projection_event_mutation()")
