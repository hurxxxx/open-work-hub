"""allow completed artifact visibility changes and FK lineage cleanup

Revision ID: d7b2e4f6a8c1
Revises: c6a9e2f4b8d1
Create Date: 2026-07-27 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "d7b2e4f6a8c1"
down_revision: str | Sequence[str] | None = "c6a9e2f4b8d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_completed_artifact_guard() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ai_guard_completed_artifact() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'completed' THEN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'completed AI artifacts are immutable'
                        USING ERRCODE = '55000';
                END IF;

                IF (to_jsonb(NEW) - 'visibility')
                   IS NOT DISTINCT FROM
                   (to_jsonb(OLD) - 'visibility') THEN
                    RETURN NEW;
                END IF;

                IF pg_trigger_depth() > 1
                   AND (
                       NEW.conversation_id IS DISTINCT FROM OLD.conversation_id
                       OR NEW.conversation_turn_id
                          IS DISTINCT FROM OLD.conversation_turn_id
                   )
                   AND (
                       NEW.conversation_id IS NOT DISTINCT FROM OLD.conversation_id
                       OR NEW.conversation_id IS NULL
                   )
                   AND (
                       NEW.conversation_turn_id
                           IS NOT DISTINCT FROM OLD.conversation_turn_id
                       OR NEW.conversation_turn_id IS NULL
                   )
                   AND (
                       to_jsonb(NEW)
                           - ARRAY['conversation_id', 'conversation_turn_id']
                   ) IS NOT DISTINCT FROM (
                       to_jsonb(OLD)
                           - ARRAY['conversation_id', 'conversation_turn_id']
                   ) THEN
                    RETURN NEW;
                END IF;

                RAISE EXCEPTION 'completed AI artifacts are immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )


def _restore_strict_completed_artifact_guard() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ai_guard_completed_artifact() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'completed' THEN
                RAISE EXCEPTION 'completed AI artifacts are immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _replace_completed_artifact_guard()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _restore_strict_completed_artifact_guard()
