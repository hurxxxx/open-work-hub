from __future__ import annotations

import pytest

from ai_do_api.domains.legacy_issues.analysis_generated_sql import (
    GeneratedSqlPolicyError,
    validate_generated_counting_unit,
    validate_generated_sql,
)
from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisCountingUnit,
    AnalysisDataSource,
)
from ai_do_api.domains.legacy_issues.analysis_sql_fallback import _messages


ALLOWED_COLUMNS = frozenset(
    {
        "issue_id",
        "vehicle_model",
        "region_zone",
        "occurrence_date",
        "occurrence_date__date",
        "received_date__date",
        "issue_type",
    }
)


def test_checklist_generated_prompt_distinguishes_items_from_documents() -> None:
    messages = _messages(
        question="상태별 체크리스트 문서 수",
        logical_columns=[
            {"key": "stable_record_id"},
            {"key": "checklist_id"},
            {"key": "checklist_status"},
        ],
        family_id="generated_sql_fallback",
        data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
        counting_unit=AnalysisCountingUnit.CHECKLISTS,
    )

    assert "COUNT(DISTINCT checklist_id)" in messages[0]["content"]
    assert "Never label an item count as a checklist or document count" in messages[0]["content"]
    assert "grounded counting_unit is checklists" in messages[0]["content"]


@pytest.mark.parametrize(
    ("sql", "counting_unit"),
    [
        (
            "SELECT COUNT(DISTINCT stable_record_id) AS item_count FROM visible_records",
            AnalysisCountingUnit.CHECKLIST_ITEMS,
        ),
        (
            "SELECT checklist_status, COUNT(DISTINCT checklist_id) AS checklist_count "
            "FROM visible_records GROUP BY checklist_status",
            AnalysisCountingUnit.CHECKLISTS,
        ),
    ],
)
def test_generated_counting_unit_accepts_only_the_grounded_entity(
    sql: str,
    counting_unit: AnalysisCountingUnit,
) -> None:
    validate_generated_counting_unit(sql, counting_unit=counting_unit)


@pytest.mark.parametrize(
    ("sql", "counting_unit", "reason"),
    [
        (
            "SELECT COUNT(DISTINCT checklist_vehicle_code) AS count FROM visible_records",
            AnalysisCountingUnit.CHECKLIST_ITEMS,
            "generated_sql_counting_unit_mismatch",
        ),
        (
            "SELECT COUNT(DISTINCT checklist_vehicle_code) AS count FROM visible_records",
            AnalysisCountingUnit.CHECKLISTS,
            "generated_sql_counting_unit_mismatch",
        ),
        (
            "SELECT checklist_status FROM visible_records",
            AnalysisCountingUnit.CHECKLISTS,
            "generated_sql_counting_unit_missing",
        ),
    ],
)
def test_generated_counting_unit_rejects_wrong_or_missing_count_target(
    sql: str,
    counting_unit: AnalysisCountingUnit,
    reason: str,
) -> None:
    with pytest.raises(GeneratedSqlPolicyError, match=reason):
        validate_generated_counting_unit(sql, counting_unit=counting_unit)


@pytest.mark.parametrize(
    "sql",
    [
        (
            "SELECT COUNT(DISTINCT checklist_id) + SUM(1) AS checklist_count "
            "FROM visible_records"
        ),
        (
            "SELECT COUNT(DISTINCT checklist_id) AS checklist_count, "
            "SUM(1) AS item_rows FROM visible_records"
        ),
        (
            "SELECT COUNT(DISTINCT checklist_id) + 1 AS checklist_count "
            "FROM visible_records"
        ),
        (
            "SELECT COALESCE(COUNT(DISTINCT checklist_id), 0) AS checklist_count "
            "FROM visible_records"
        ),
        (
            "SELECT COUNT(DISTINCT checklist_id) OVER () AS checklist_count "
            "FROM visible_records"
        ),
        (
            "SELECT checklist_count + 1 AS checklist_count FROM ("
            "SELECT COUNT(DISTINCT checklist_id) AS checklist_count "
            "FROM visible_records"
            ") AS grouped"
        ),
        (
            "SELECT checklist_status FROM visible_records WHERE EXISTS ("
            "SELECT COUNT(DISTINCT checklist_id) FROM visible_records"
            ")"
        ),
    ],
)
def test_generated_document_count_rejects_manipulated_count_expression(sql: str) -> None:
    with pytest.raises(
        GeneratedSqlPolicyError,
        match="generated_sql_counting_unit_mismatch",
    ):
        validate_generated_counting_unit(
            sql,
            counting_unit=AnalysisCountingUnit.CHECKLISTS,
        )


def test_generated_sql_accepts_scoped_aggregate_and_window() -> None:
    validated = validate_generated_sql(
        """
        SELECT
          region_zone,
          issue_count,
          DENSE_RANK() OVER (ORDER BY issue_count DESC) AS issue_rank
        FROM (
          SELECT region_zone, COUNT(DISTINCT issue_id) AS issue_count
          FROM visible_records
          GROUP BY region_zone
        ) AS grouped
        ORDER BY issue_rank
        """,
        allowed_columns=ALLOWED_COLUMNS,
    )

    assert validated.ast_fingerprint
    assert validated.referenced_columns == ("issue_id", "region_zone")
    assert validated.cte_names == ()


def test_generated_sql_accepts_duration_over_server_validated_date_helpers() -> None:
    validated = validate_generated_sql(
        """
        SELECT
          AVG(received_date__date - occurrence_date__date) AS average_days,
          MIN(received_date__date - occurrence_date__date) AS minimum_days,
          MAX(received_date__date - occurrence_date__date) AS maximum_days
        FROM visible_records
        WHERE received_date__date IS NOT NULL
          AND occurrence_date__date IS NOT NULL
        """,
        allowed_columns=ALLOWED_COLUMNS,
    )

    assert validated.ast_fingerprint
    assert validated.referenced_columns == (
        "occurrence_date__date",
        "received_date__date",
    )


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("SELECT issue_type FROM legacy_issue_records", "generated_sql_unknown_relation"),
        ("SELECT pg_sleep(1) FROM visible_records", "generated_sql_unknown_function"),
        ("SELECT secret FROM visible_records", "generated_sql_unknown_column"),
        (
            "WITH visible_records AS (SELECT 1) SELECT * FROM visible_records",
            "generated_sql_cte_not_allowed",
        ),
        (
            "WITH RECURSIVE x AS (SELECT 1 UNION ALL SELECT 1 FROM x) "
            "SELECT * FROM visible_records",
            "generated_sql_cte_not_allowed",
        ),
        (
            "SELECT u.email FROM users AS u CROSS JOIN "
            "(WITH users AS ("
            "SELECT issue_type AS email FROM visible_records LIMIT 1"
            ") SELECT 1) AS nested",
            "generated_sql_cte_not_allowed",
        ),
        ("DELETE FROM visible_records", "generated_sql_not_select"),
        ("SELECT * FROM visible_records; SELECT 1", "generated_sql_multiple_statements"),
        ("SELECT schemaname FROM pg_catalog.pg_tables", "generated_sql_physical_schema"),
        ("SELECT issue_type FROM visible_records FOR UPDATE", "generated_sql_locking_select"),
        ("SELECT * FROM visible_records", "generated_sql_wildcard_not_allowed"),
        ("SELECT issue_type FROM ONLY visible_records", "generated_sql_relation_modifier"),
        (
            "SELECT issue_type FROM visible_records TABLESAMPLE SYSTEM (10)",
            "generated_sql_relation_modifier",
        ),
        (
            "SELECT USER AS who, issue_type AS USER FROM visible_records",
            "generated_sql_system_value",
        ),
        (
            "SELECT issue_type FROM visible_records UNION SELECT 'fabricated'",
            "generated_sql_not_select",
        ),
        (
            "SELECT issue_type, (SELECT 1) AS fabricated FROM visible_records",
            "generated_sql_unsourced_select",
        ),
        (
            "SELECT COUNT(record_id) AS n FROM visible_records "
            "HAVING MAX(retrieval_partition_id) LIKE 'a%'",
            "generated_sql_having_not_allowed",
        ),
        (
            "SELECT COUNT(record_id) AS n FROM visible_records HAVING USER LIKE 'a%'",
            "generated_sql_having_not_allowed",
        ),
        (
            "SELECT a.issue_type FROM visible_records AS a "
            "JOIN visible_records AS b USING (retrieval_partition_id)",
            "generated_sql_implicit_join",
        ),
        (
            "SELECT a.issue_type FROM visible_records AS a NATURAL JOIN visible_records AS b",
            "generated_sql_implicit_join",
        ),
    ],
)
def test_generated_sql_rejects_unsafe_shapes(sql: str, reason: str) -> None:
    with pytest.raises(GeneratedSqlPolicyError, match=reason):
        validate_generated_sql(sql, allowed_columns=ALLOWED_COLUMNS)
