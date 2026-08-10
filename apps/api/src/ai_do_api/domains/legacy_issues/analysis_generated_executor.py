from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import distinct, func, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from ai_do_api.domains.legacy_issues.analysis_generated_sql import (
    GENERATED_SQL_AGGREGATE_LIMIT,
    GENERATED_SQL_DETAIL_LIMIT,
    GENERATED_SQL_MAX_PLAN_COST,
    GENERATED_SQL_MAX_PLAN_ROWS,
    GENERATED_SQL_TIMEOUT_MS,
)
from ai_do_api.domains.legacy_issues.analysis_sql import (
    build_visible_records_relation,
    resolve_analysis_scope,
)
from ai_do_api.domains.legacy_issues.analysis_sql_fallback import (
    LegacyIssueGeneratedSqlPlan,
)
from ai_do_api.domains.legacy_issues.dataset_records import DatasetFieldDefinition


_MAX_RESULT_COLUMNS = 64
_MAX_CELL_CHARS = 2_000
_MAX_QUERY_ROW_CHARS = 250_000


class GeneratedAnalysisExecutionError(RuntimeError):
    """A validated generated query failed an independent runtime guard."""


def execute_generated_analysis(
    db: Session,
    *,
    workspace_id: str,
    enabled_module_keys: Iterable[str] | None,
    field_definitions: Iterable[DatasetFieldDefinition],
    generated_plan: LegacyIssueGeneratedSqlPlan,
    retrieval_partition_ids: Iterable[str] | None = None,
    family_id: str = "generated_sql",
) -> dict[str, Any]:
    """Execute generated SQL against only the scoped logical relation.

    Execution uses a fresh PostgreSQL connection and a read-only transaction. The
    validated query is rejected before execution when PostgreSQL's plan estimate
    exceeds either the cost or row cap.
    """

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        raise GeneratedAnalysisExecutionError("generated_sql_requires_postgresql")
    scope = resolve_analysis_scope(
        db,
        workspace_id=workspace_id,
        enabled_module_keys=enabled_module_keys,
        retrieval_partition_ids=retrieval_partition_ids,
        data_sources=(generated_plan.data_source,),
    )
    definitions = tuple(field_definitions)
    engine = _engine_for_bind(bind)
    with engine.connect() as connection, connection.begin():
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql(f"SET LOCAL statement_timeout = '{GENERATED_SQL_TIMEOUT_MS}ms'")
        visible_records = build_visible_records_relation(
            scope,
            field_definitions=definitions,
            dialect_name="postgresql",
            include_generated_helpers=True,
            data_source=generated_plan.data_source,
        )
        source_count = _source_count(connection, visible_records)
        statement = text(generated_plan.validated_sql.sql).columns().add_cte(visible_records)
        compiled = statement.compile(
            dialect=connection.dialect,
            compile_kwargs={"render_postcompile": True},
        )
        sql = str(compiled)
        params = dict(compiled.params)
        _enforce_explain_limits(connection, sql=sql, params=params)
        row_limit = (
            GENERATED_SQL_DETAIL_LIMIT
            if generated_plan.shape == "detail"
            else GENERATED_SQL_AGGREGATE_LIMIT
        )
        result = connection.exec_driver_sql(
            f"SELECT * FROM ({sql}) AS generated_result LIMIT {row_limit + 1}",
            params,
        )
        column_keys = tuple(str(key) for key in result.keys())
        if not column_keys or len(column_keys) > _MAX_RESULT_COLUMNS:
            raise GeneratedAnalysisExecutionError("generated_sql_result_column_limit")
        if len(set(column_keys)) != len(column_keys):
            raise GeneratedAnalysisExecutionError("generated_sql_duplicate_result_columns")
        raw_rows = result.fetchmany(row_limit + 1)

    truncated = len(raw_rows) > row_limit
    rows: list[dict[str, Any]] = []
    serialized_row_chars = 0
    for raw_row in raw_rows[:row_limit]:
        row = {key: _normalize_public_cell(value) for key, value in zip(column_keys, raw_row)}
        row_chars = len(json.dumps(row, ensure_ascii=False, default=str))
        if rows and serialized_row_chars + row_chars > _MAX_QUERY_ROW_CHARS:
            truncated = True
            break
        rows.append(row)
        serialized_row_chars += row_chars
    columns = _result_columns(
        column_keys=column_keys,
        rows=rows,
        shape=generated_plan.shape,
    )
    warnings = ["결과 행 또는 표시 용량 제한에 따라 일부 행만 표시합니다."] if truncated else []
    scope_payload: dict[str, Any] = {
        "dataset_key": scope.dataset_key,
        "data_sources": [generated_plan.data_source.value],
        "module_keys": list(scope.module_keys),
        "revision_ids": list(scope.revision_ids),
        "checklist_ids": list(getattr(scope, "checklist_ids", ())),
        "source_count": source_count,
        "source_counts": {generated_plan.data_source.value: source_count},
    }
    return {
        "version": 1,
        "mode": "generated",
        "data_source": generated_plan.data_source.value,
        "title": generated_plan.title,
        "exactness": "generated",
        "scope": scope_payload,
        "queries": [
            {
                "id": (f"generated-{generated_plan.validated_sql.ast_fingerprint[:12]}"),
                "title": generated_plan.title,
                "family_id": family_id,
                "family_version": 1,
                "data_source": generated_plan.data_source.value,
                "source_count": source_count,
                "shape": generated_plan.shape,
                "exactness": "generated",
                "columns": columns,
                "rows": rows,
                "totals": {},
                "coverage": [],
                "warnings": warnings,
                "truncated": truncated,
            }
        ],
        "warnings": warnings,
    }


def _engine_for_bind(bind: Engine | Connection) -> Engine:
    if isinstance(bind, Engine):
        return bind
    return bind.engine


def _source_count(connection: Connection, visible_records: Any) -> int:
    identity = func.coalesce(
        visible_records.c.stable_record_id,
        visible_records.c.record_id,
    )
    statement = select(func.count(distinct(identity))).select_from(visible_records)
    return int(connection.scalar(statement) or 0)


def _enforce_explain_limits(
    connection: Connection,
    *,
    sql: str,
    params: dict[str, Any],
) -> None:
    explained = connection.exec_driver_sql(
        f"EXPLAIN (FORMAT JSON) {sql}",
        params,
    ).scalar_one()
    payload = _explain_payload(explained)
    plan = payload.get("Plan")
    if not isinstance(plan, dict):
        raise GeneratedAnalysisExecutionError("generated_sql_explain_invalid")
    try:
        total_cost = float(plan["Total Cost"])
        plan_rows = float(plan["Plan Rows"])
    except (KeyError, TypeError, ValueError) as error:
        raise GeneratedAnalysisExecutionError("generated_sql_explain_invalid") from error
    if total_cost > GENERATED_SQL_MAX_PLAN_COST:
        raise GeneratedAnalysisExecutionError("generated_sql_plan_cost_limit")
    if plan_rows > GENERATED_SQL_MAX_PLAN_ROWS:
        raise GeneratedAnalysisExecutionError("generated_sql_plan_row_limit")


def _explain_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, dict):
        return value
    raise GeneratedAnalysisExecutionError("generated_sql_explain_invalid")


def _result_columns(
    *,
    column_keys: tuple[str, ...],
    rows: list[dict[str, Any]],
    shape: str,
) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for index, key in enumerate(column_keys):
        values = [row.get(key) for row in rows if row.get(key) is not None]
        value_type = _public_value_type(values)
        if shape == "scalar":
            role = "metric"
        elif value_type in {"number", "percent"}:
            role = "metric"
        elif index == 0 or shape in {"detail", "table", "crosstab"}:
            role = "dimension"
        else:
            role = "dimension"
        columns.append(
            {
                "key": key,
                "label": key,
                "type": value_type,
                "role": role,
            }
        )
    return columns


def _public_value_type(values: list[Any]) -> str:
    if values and all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in values
    ):
        return "number"
    if values and all(_is_iso_date(value) for value in values):
        return "date"
    return "text"


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _normalize_public_cell(value: Any) -> str | int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (dict, list, tuple)):
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    else:
        rendered = str(value)
    return rendered[:_MAX_CELL_CHARS]


__all__ = [
    "GeneratedAnalysisExecutionError",
    "execute_generated_analysis",
]
