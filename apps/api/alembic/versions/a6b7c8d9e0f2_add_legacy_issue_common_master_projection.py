"""add legacy issue common master projection

Revision ID: a6b7c8d9e0f2
Revises: f3b7c2d9a6e1
Create Date: 2026-06-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a6b7c8d9e0f2"
down_revision: str | Sequence[str] | None = "f3b7c2d9a6e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FIELD_LABELS = {
    "row_no": "번호",
    "department": "부서",
    "registrant": "등록자",
    "legacy_issue_number": "과거차관리번호",
    "major_category": "대분류",
    "middle_category": "중분류",
    "region_zone": "권역",
    "occurrence_stage": "발생단계",
    "occurrence_type": "발생구분",
    "oem_open": "OEM오픈",
    "vehicle_model": "차종",
    "occurrence_date": "발생일",
    "received_date": "접수일",
    "issue_type": "유형",
    "cause_type": "원인구분",
    "supplier": "협력사",
    "part_number": "부품번호",
    "process_name": "공정명",
    "symptom": "현상",
    "cause": "원인",
    "countermeasure": "개선대책",
    "action": "조치",
    "severity_grade": "중요도/등급",
    "confirmation_content": "확인내용",
    "check_plan": "점검방안",
    "applied": "적용유무",
    "reflection_result": "반영/검토결과",
    "evidence_legacy_issue": "과거차문제점",
    "evidence_design_check_sheet": "설계체크시트",
    "evidence_design_fmea": "설계FMEA",
    "evidence_design_standard_guide": "설계표준·가이드",
    "evidence_quality_spec": "품질규격",
    "reflected_revision": "반영Rev.",
    "notes": "비고",
}

PROJECTION_COLUMNS = tuple(FIELD_LABELS)
TEXT_COLUMNS = (*PROJECTION_COLUMNS, "search_text")

COMPOSITE_INDEXES = {
    "ix_legacy_issue_records_workspace_dataset_department": (
        "workspace_id",
        "dataset_key",
        "department",
    ),
    "ix_legacy_issue_records_workspace_dataset_issue_no": (
        "workspace_id",
        "dataset_key",
        "legacy_issue_number",
    ),
    "ix_legacy_issue_records_workspace_dataset_vehicle": (
        "workspace_id",
        "dataset_key",
        "vehicle_model",
    ),
    "ix_legacy_issue_records_workspace_dataset_stage": (
        "workspace_id",
        "dataset_key",
        "occurrence_stage",
    ),
    "ix_legacy_issue_records_workspace_dataset_type": (
        "workspace_id",
        "dataset_key",
        "issue_type",
    ),
    "ix_legacy_issue_records_workspace_dataset_applied": (
        "workspace_id",
        "dataset_key",
        "applied",
    ),
}


def upgrade() -> None:
    for column_name in TEXT_COLUMNS:
        op.add_column("legacy_issue_records", sa.Column(column_name, sa.Text(), nullable=True))

    for index_name, columns in COMPOSITE_INDEXES.items():
        op.create_index(index_name, "legacy_issue_records", list(columns))

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _backfill_postgresql_projection()
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_legacy_issue_records_field_values_gin
            ON legacy_issue_records
            USING gin (field_values)
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_legacy_issue_records_search_text_fts
            ON legacy_issue_records
            USING gin (to_tsvector('simple', coalesce(search_text, '')))
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_legacy_issue_records_search_text_trgm
            ON legacy_issue_records
            USING gin ((lower(search_text)) gin_trgm_ops)
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_legacy_issue_records_search_text_trgm")
        op.execute("DROP INDEX IF EXISTS ix_legacy_issue_records_search_text_fts")
        op.execute("DROP INDEX IF EXISTS ix_legacy_issue_records_field_values_gin")

    for index_name in reversed(tuple(COMPOSITE_INDEXES)):
        op.drop_index(index_name, table_name="legacy_issue_records")

    for column_name in reversed(TEXT_COLUMNS):
        op.drop_column("legacy_issue_records", column_name)


def _backfill_postgresql_projection() -> None:
    assignments = ",\n                ".join(
        f"{column_name} = NULLIF(btrim(field_values ->> '{column_name}'), '')"
        for column_name in PROJECTION_COLUMNS
    )
    search_parts = ",\n                    ".join(
        (f"NULLIF('{label}: ' || btrim(field_values ->> '{column_name}'), '{label}: ')")
        for column_name, label in FIELD_LABELS.items()
    )
    op.execute(
        f"""
        UPDATE legacy_issue_records
        SET
            {assignments},
            search_text = NULLIF(concat_ws(E'\\n', {search_parts}), '')
        WHERE field_values IS NOT NULL
        """
    )
