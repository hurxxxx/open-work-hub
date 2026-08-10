"""add legacy issue record module key

Revision ID: f6a7b8c9d0e1
Revises: e1a2b3c4d5f7
Create Date: 2026-07-02
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e1a2b3c4d5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MODULE_DEPARTMENT_LABELS = {
    "샤시(ACON)": "aircon",
    "의장(HVAC)": "interior",
    "쿨링모듈": "cooling-module",
    "전장(기구)": "electrical-mechanical",
    "전장(제어-HW)": "electrical-control-hw",
    "전장(제어-SW)": "electrical-control-sw",
}


def upgrade() -> None:
    op.add_column(
        "legacy_issue_records",
        sa.Column("module_key", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "ix_legacy_issue_records_workspace_dataset_module",
        "legacy_issue_records",
        ["workspace_id", "dataset_key", "module_key"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for department, module_key in MODULE_DEPARTMENT_LABELS.items():
            department_filter = """
                  AND (
                    department = :department
                    OR field_values ->> 'department' = :department
                    OR raw_fields ->> '부서' = :department
                  )
                """
            bind.execute(
                sa.text(
                    f"""
                    UPDATE legacy_issue_records
                    SET module_key = :module_key
                    WHERE module_key IS NULL
                    {department_filter}
                    """
                ),
                {"module_key": module_key, "department": department},
            )
        _clear_module_department_values_postgresql()
    else:
        _backfill_and_clear_module_department_values_portable()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _restore_module_department_values_postgresql()
    else:
        _restore_module_department_values_portable()
    op.drop_index(
        "ix_legacy_issue_records_workspace_dataset_module",
        table_name="legacy_issue_records",
    )
    op.drop_column("legacy_issue_records", "module_key")


def _clear_module_department_values_postgresql() -> None:
    op.execute(
        """
        UPDATE legacy_issue_records
        SET
            field_values = CASE
                WHEN field_values ->> 'department' IN (
                    '샤시(ACON)',
                    '의장(HVAC)',
                    '쿨링모듈',
                    '전장(기구)',
                    '전장(제어-HW)',
                    '전장(제어-SW)'
                )
                THEN field_values - 'department'
                ELSE field_values
            END,
            raw_fields = CASE
                WHEN raw_fields ->> '부서' IN (
                    '샤시(ACON)',
                    '의장(HVAC)',
                    '쿨링모듈',
                    '전장(기구)',
                    '전장(제어-HW)',
                    '전장(제어-SW)'
                )
                THEN raw_fields - '부서'
                ELSE raw_fields
            END,
            search_text = NULLIF(
                trim(
                    both E'\n' from regexp_replace(
                        coalesce(search_text, ''),
                        E'(^|\\n)부서: (샤시\\(ACON\\)|의장\\(HVAC\\)|쿨링모듈|전장\\(기구\\)|전장\\(제어-HW\\)|전장\\(제어-SW\\))(\\n|$)',
                        E'\\1',
                        'g'
                    )
                ),
                ''
            ),
            department = CASE
                WHEN department IN (
                    '샤시(ACON)',
                    '의장(HVAC)',
                    '쿨링모듈',
                    '전장(기구)',
                    '전장(제어-HW)',
                    '전장(제어-SW)'
                )
                THEN NULL
                ELSE department
            END
        WHERE department IN (
            '샤시(ACON)',
            '의장(HVAC)',
            '쿨링모듈',
            '전장(기구)',
            '전장(제어-HW)',
            '전장(제어-SW)'
        )
        OR field_values ->> 'department' IN (
            '샤시(ACON)',
            '의장(HVAC)',
            '쿨링모듈',
            '전장(기구)',
            '전장(제어-HW)',
            '전장(제어-SW)'
        )
        OR raw_fields ->> '부서' IN (
            '샤시(ACON)',
            '의장(HVAC)',
            '쿨링모듈',
            '전장(기구)',
            '전장(제어-HW)',
            '전장(제어-SW)'
        )
        OR search_text LIKE '%부서: 샤시(ACON)%'
        OR search_text LIKE '%부서: 의장(HVAC)%'
        OR search_text LIKE '%부서: 쿨링모듈%'
        OR search_text LIKE '%부서: 전장(기구)%'
        OR search_text LIKE '%부서: 전장(제어-HW)%'
        OR search_text LIKE '%부서: 전장(제어-SW)%'
        """
    )


def _restore_module_department_values_postgresql() -> None:
    bind = op.get_bind()
    for department, module_key in MODULE_DEPARTMENT_LABELS.items():
        bind.execute(
            sa.text(
                """
                UPDATE legacy_issue_records
                SET
                    department = coalesce(department, :department),
                    field_values = CASE
                        WHEN field_values ? 'department' THEN field_values
                        ELSE jsonb_set(
                            coalesce(field_values, '{}'::jsonb),
                            '{department}',
                            to_jsonb(CAST(:department AS text)),
                            true
                        )
                    END,
                    raw_fields = CASE
                        WHEN raw_fields ? '부서' THEN raw_fields
                        ELSE jsonb_set(
                            coalesce(raw_fields, '{}'::jsonb),
                            '{부서}',
                            to_jsonb(CAST(:department AS text)),
                            true
                        )
                    END,
                    search_text = CASE
                        WHEN coalesce(search_text, '') LIKE :search_pattern THEN search_text
                        WHEN coalesce(search_text, '') = '' THEN :search_line
                        ELSE :search_line || E'\n' || search_text
                    END
                WHERE module_key = :module_key
                """
            ),
            {
                "department": department,
                "module_key": module_key,
                "search_line": f"부서: {department}",
                "search_pattern": f"%부서: {department}%",
            },
        )


def _restore_module_department_values_portable() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, module_key, department, field_values, raw_fields, search_text
            FROM legacy_issue_records
            WHERE module_key IS NOT NULL
            """
        )
    ).mappings()
    module_labels = {module_key: label for label, module_key in MODULE_DEPARTMENT_LABELS.items()}
    for row in rows:
        department = module_labels.get(row["module_key"])
        if not department:
            continue
        field_values = _json_mapping(row["field_values"])
        raw_fields = _json_mapping(row["raw_fields"])
        field_values.setdefault("department", department)
        raw_fields.setdefault("부서", department)
        bind.execute(
            sa.text(
                """
                UPDATE legacy_issue_records
                SET
                    department = coalesce(department, :department),
                    field_values = :field_values,
                    raw_fields = :raw_fields,
                    search_text = :search_text
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "department": department,
                "field_values": json.dumps(field_values, ensure_ascii=False),
                "raw_fields": json.dumps(raw_fields, ensure_ascii=False),
                "search_text": _prepend_module_department_search_text(
                    row["search_text"], department
                ),
            },
        )


def _backfill_and_clear_module_department_values_portable() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, department, field_values, raw_fields, search_text
            FROM legacy_issue_records
            """
        )
    ).mappings()
    for row in rows:
        field_values = _json_mapping(row["field_values"])
        raw_fields = _json_mapping(row["raw_fields"])
        label = _module_department_label(
            row["department"],
            field_values.get("department"),
            raw_fields.get("부서"),
            raw_fields.get("department"),
        )
        if not label:
            continue
        if field_values.get("department") in MODULE_DEPARTMENT_LABELS:
            field_values.pop("department", None)
        if raw_fields.get("부서") in MODULE_DEPARTMENT_LABELS:
            raw_fields.pop("부서", None)
        if raw_fields.get("department") in MODULE_DEPARTMENT_LABELS:
            raw_fields.pop("department", None)
        bind.execute(
            sa.text(
                """
                UPDATE legacy_issue_records
                SET
                    module_key = coalesce(module_key, :module_key),
                    department = NULL,
                    field_values = :field_values,
                    raw_fields = :raw_fields,
                    search_text = :search_text
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "module_key": MODULE_DEPARTMENT_LABELS[label],
                "field_values": json.dumps(field_values, ensure_ascii=False),
                "raw_fields": json.dumps(raw_fields, ensure_ascii=False),
                "search_text": _remove_module_department_search_text(row["search_text"]),
            },
        )


def _json_mapping(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _module_department_label(*values) -> str | None:
    for value in values:
        normalized = str(value).strip() if value is not None else ""
        if normalized in MODULE_DEPARTMENT_LABELS:
            return normalized
    return None


def _remove_module_department_search_text(value: str | None) -> str | None:
    if not value:
        return None
    labels = {f"부서: {label}" for label in MODULE_DEPARTMENT_LABELS}
    lines = [line for line in value.splitlines() if line.strip() not in labels]
    return "\n".join(lines) or None


def _prepend_module_department_search_text(value: str | None, department: str) -> str:
    search_line = f"부서: {department}"
    if not value:
        return search_line
    if search_line in value:
        return value
    return f"{search_line}\n{value}"
