"""ensure legacy issue pgvector index

Revision ID: c4d5e6f7a8b0
Revises: b9e3f4a5c6d7
Create Date: 2026-06-18 00:00:00.000000

"""

from alembic import op


revision = "c4d5e6f7a8b0"
down_revision = "b9e3f4a5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
          vector_ready boolean := false;
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
            BEGIN
              EXECUTE 'CREATE EXTENSION IF NOT EXISTS vector';
              vector_ready := true;
            EXCEPTION WHEN insufficient_privilege THEN
              vector_ready := false;
            END;
            IF vector_ready THEN
              BEGIN
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_legacy_issue_ai_chunks_embedding_hnsw
                  ON legacy_issue_ai_chunks
                  USING hnsw ((embedding_vector::vector(1024)) vector_cosine_ops)
                  WHERE embedding_status = ''embedded'' AND embedding_vector IS NOT NULL';
              EXCEPTION WHEN OTHERS THEN
                NULL;
              END;
            END IF;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_legacy_issue_ai_chunks_embedding_hnsw
        """
    )
