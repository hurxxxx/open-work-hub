"""Rename the legacy issue registrant field label.

Revision ID: e7b9d1f3a5c8
Revises: a1c4e7f9b2d6
Create Date: 2026-07-30 09:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "e7b9d1f3a5c8"
down_revision: str | None = "a1c4e7f9b2d6"
branch_labels: str | None = None
depends_on: str | None = None

DATASET_KEY = "common-master"
FIELD_KEY = "registrant"
OLD_LABEL_KO = "등록자"
NEW_LABEL_KO = "대책 작성자"
OLD_LABEL_EN = "Registrant"
NEW_LABEL_EN = "Countermeasure Author"


def _rename_labels(
    *,
    source_ko: str,
    target_ko: str,
    source_en: str,
    target_en: str,
) -> None:
    op.execute(
        sa.text(
            """
            UPDATE legacy_issue_system_field_settings
            SET
                label_ko = CASE
                    WHEN label_ko = :source_ko THEN :target_ko
                    ELSE label_ko
                END,
                label_en = CASE
                    WHEN label_en = :source_en THEN :target_en
                    ELSE label_en
                END
            WHERE dataset_key = :dataset_key
              AND field_key = :field_key
              AND (
                  label_ko = :source_ko
                  OR label_en = :source_en
              )
            """
        ).bindparams(
            dataset_key=DATASET_KEY,
            field_key=FIELD_KEY,
            source_ko=source_ko,
            target_ko=target_ko,
            source_en=source_en,
            target_en=target_en,
        )
    )


def upgrade() -> None:
    _rename_labels(
        source_ko=OLD_LABEL_KO,
        target_ko=NEW_LABEL_KO,
        source_en=OLD_LABEL_EN,
        target_en=NEW_LABEL_EN,
    )


def downgrade() -> None:
    _rename_labels(
        source_ko=NEW_LABEL_KO,
        target_ko=OLD_LABEL_KO,
        source_en=NEW_LABEL_EN,
        target_en=OLD_LABEL_EN,
    )
