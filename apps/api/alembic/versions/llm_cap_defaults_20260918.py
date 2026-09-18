"""Let untouched global output defaults inherit each registered workload's cap."""

from alembic import op
import sqlalchemy as sa

revision = "llm_cap_defaults_20260918"
down_revision = "llm_connections_20260918"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only machine-seeded defaults are implicit. Preserve every admin edit.
    op.execute(
        sa.text("""
        UPDATE ai_model_policy_defaults
        SET max_output_tokens = NULL
        WHERE app_id = '' AND version = 1 AND updated_by IS NULL
          AND ((route_mode = 'local' AND max_output_tokens = 32768)
            OR (route_mode = 'external' AND max_output_tokens = 65536))
    """)
    )


def downgrade() -> None:
    # NULL is supported by the preceding schema; retain the chosen inheritance.
    pass
