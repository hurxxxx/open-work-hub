from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import Scope, traverse_scope

from open_alm_api.domains.legacy_issues.analysis_contracts import AnalysisCountingUnit


MAX_GENERATED_SQL_CHARS = 20_000
GENERATED_SQL_AGGREGATE_LIMIT = 100
GENERATED_SQL_DETAIL_LIMIT = 200
GENERATED_SQL_MAX_PLAN_COST = 100_000
GENERATED_SQL_MAX_PLAN_ROWS = 100_000
GENERATED_SQL_TIMEOUT_MS = 5_000

_ALLOWED_FUNCTIONS = frozenset(
    {
        "abs",
        "and",
        "avg",
        "case",
        "ceil",
        "ceiling",
        "coalesce",
        "concat",
        "count",
        "date_part",
        "date_trunc",
        "dense_rank",
        "extract",
        "floor",
        "greatest",
        "if",
        "lag",
        "lead",
        "least",
        "length",
        "lower",
        "max",
        "median",
        "min",
        "nullif",
        "percent_rank",
        "percentile_cont",
        "percentile_disc",
        "power",
        "rank",
        "replace",
        "round",
        "row_number",
        "substring",
        "sum",
        "sqrt",
        "stddev",
        "stddev_pop",
        "stddev_samp",
        "trim",
        "upper",
        "var_pop",
        "var_samp",
        "variance",
        "or",
    }
)

_DISALLOWED_NODES = (
    exp.Alter,
    exp.Command,
    exp.Commit,
    exp.Copy,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Into,
    exp.Merge,
    exp.Set,
    exp.Transaction,
    exp.TruncateTable,
    exp.Update,
    exp.Use,
)

_DISALLOWED_PSEUDO_COLUMNS = frozenset(
    {
        "current_role",
        "system_user",
        "user",
    }
)


class GeneratedSqlPolicyError(ValueError):
    """Generated SQL did not satisfy the read-only logical-schema contract."""


@dataclass(frozen=True, slots=True)
class ValidatedGeneratedSql:
    sql: str
    ast_fingerprint: str
    referenced_columns: tuple[str, ...]
    cte_names: tuple[str, ...]


def validate_generated_sql(
    sql: str,
    *,
    allowed_columns: set[str] | frozenset[str],
) -> ValidatedGeneratedSql:
    normalized_input = sql.strip()
    if not normalized_input:
        raise GeneratedSqlPolicyError("generated_sql_empty")
    if len(normalized_input) > MAX_GENERATED_SQL_CHARS:
        raise GeneratedSqlPolicyError("generated_sql_too_large")

    try:
        statements = parse(normalized_input, read="postgres")
    except ParseError as exc:
        raise GeneratedSqlPolicyError("generated_sql_parse_failed") from exc
    if len(statements) != 1:
        raise GeneratedSqlPolicyError("generated_sql_multiple_statements")
    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise GeneratedSqlPolicyError("generated_sql_not_select")
    if any(statement.find(node_type) is not None for node_type in _DISALLOWED_NODES):
        raise GeneratedSqlPolicyError("generated_sql_mutating_node")

    # User-defined CTEs are deliberately prohibited.  Resolving CTE names safely
    # requires lexical-scope analysis; treating aliases as one global allow-list can
    # let a nested CTE authorize an unrelated physical table in an outer query.
    # Inline derived tables retain the expressiveness needed for aggregate/window
    # analysis while every physical relation remains visible to this simple policy.
    if statement.find(exp.CTE) is not None or statement.find(exp.With) is not None:
        raise GeneratedSqlPolicyError("generated_sql_cte_not_allowed")
    if statement.find(exp.Star) is not None:
        raise GeneratedSqlPolicyError("generated_sql_wildcard_not_allowed")
    if statement.find(exp.Operator) is not None:
        raise GeneratedSqlPolicyError("generated_sql_custom_operator")
    if statement.find(exp.Having) is not None:
        raise GeneratedSqlPolicyError("generated_sql_having_not_allowed")
    for join in statement.find_all(exp.Join):
        if join.args.get("using") or join.args.get("method") == "NATURAL":
            raise GeneratedSqlPolicyError("generated_sql_implicit_join")
    if any(
        column.name.casefold() in _DISALLOWED_PSEUDO_COLUMNS
        for column in statement.find_all(exp.Column)
    ):
        raise GeneratedSqlPolicyError("generated_sql_system_value")

    cte_names: set[str] = set()
    allowed_relations = {"visible_records"}
    referenced_tables: set[str] = set()
    for table in statement.find_all(exp.Table):
        if table.catalog or table.db:
            raise GeneratedSqlPolicyError("generated_sql_physical_schema")
        if table.args.get("only") or table.args.get("sample") is not None:
            raise GeneratedSqlPolicyError("generated_sql_relation_modifier")
        name = table.name
        if name not in allowed_relations:
            raise GeneratedSqlPolicyError("generated_sql_unknown_relation")
        referenced_tables.add(name)
    if "visible_records" not in referenced_tables:
        raise GeneratedSqlPolicyError("generated_sql_scope_missing")

    normalized_allowed_columns = {value.strip() for value in allowed_columns if value.strip()}
    referenced_columns = _validate_scoped_columns(
        statement,
        allowed_columns=normalized_allowed_columns,
    )

    for function in statement.find_all(exp.Func):
        function_name = function.sql_name().lower()
        if function_name not in _ALLOWED_FUNCTIONS:
            raise GeneratedSqlPolicyError("generated_sql_unknown_function")

    for select_node in statement.find_all(exp.Select):
        if select_node.args.get("locks"):
            raise GeneratedSqlPolicyError("generated_sql_locking_select")

    canonical_sql = statement.sql(dialect="postgres", comments=False)
    fingerprint = hashlib.sha256(canonical_sql.encode("utf-8")).hexdigest()
    return ValidatedGeneratedSql(
        sql=canonical_sql,
        ast_fingerprint=fingerprint,
        referenced_columns=tuple(sorted(referenced_columns)),
        cte_names=tuple(sorted(cte_names)),
    )


def validate_generated_counting_unit(
    sql: str,
    *,
    counting_unit: AnalysisCountingUnit | None,
) -> None:
    if counting_unit not in {
        AnalysisCountingUnit.CHECKLIST_ITEMS,
        AnalysisCountingUnit.CHECKLISTS,
    }:
        return
    try:
        statements = parse(sql, read="postgres")
    except (IndexError, ParseError) as exc:
        raise GeneratedSqlPolicyError("generated_sql_parse_failed") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise GeneratedSqlPolicyError("generated_sql_counting_unit_mismatch")
    statement = statements[0]
    if statement.find(exp.Subquery) is not None:
        raise GeneratedSqlPolicyError("generated_sql_counting_unit_mismatch")
    count_expressions = tuple(statement.find_all(exp.Count))
    if not count_expressions:
        raise GeneratedSqlPolicyError("generated_sql_counting_unit_missing")
    aggregate_expressions = tuple(statement.find_all(exp.AggFunc))
    if any(not isinstance(aggregate, exp.Count) for aggregate in aggregate_expressions):
        raise GeneratedSqlPolicyError("generated_sql_counting_unit_mismatch")
    allowed_fields = (
        {"stable_record_id", "record_id"}
        if counting_unit == AnalysisCountingUnit.CHECKLIST_ITEMS
        else {"checklist_id"}
    )
    if any(
        _distinct_count_field(count_expression) not in allowed_fields
        or not _is_direct_select_projection(count_expression, statement=statement)
        for count_expression in count_expressions
    ):
        raise GeneratedSqlPolicyError("generated_sql_counting_unit_mismatch")


def _distinct_count_field(count_expression: exp.Count) -> str | None:
    distinct = count_expression.this
    if not isinstance(distinct, exp.Distinct) or len(distinct.expressions) != 1:
        return None
    field = distinct.expressions[0]
    if not isinstance(field, exp.Column):
        return None
    return field.name


def _is_direct_select_projection(
    count_expression: exp.Count,
    *,
    statement: exp.Select,
) -> bool:
    parent = count_expression.parent
    if isinstance(parent, exp.Alias):
        return parent.parent is statement
    return parent is statement


def _validate_scoped_columns(
    statement: exp.Select,
    *,
    allowed_columns: set[str],
) -> set[str]:
    referenced_columns: set[str] = set()
    scopes = traverse_scope(statement)
    if not scopes:
        raise GeneratedSqlPolicyError("generated_sql_scope_missing")
    for scope in scopes:
        if not scope.selected_sources:
            raise GeneratedSqlPolicyError("generated_sql_unsourced_select")
        for _alias, (_node, source) in scope.selected_sources.items():
            if isinstance(source, exp.Table):
                if source.name != "visible_records":
                    raise GeneratedSqlPolicyError("generated_sql_unknown_relation")
            elif not isinstance(source, Scope):
                raise GeneratedSqlPolicyError("generated_sql_unknown_source")
        for column in scope.columns:
            name = column.name
            if name.casefold() in _DISALLOWED_PSEUDO_COLUMNS:
                raise GeneratedSqlPolicyError("generated_sql_system_value")
            source = _column_source(scope, column)
            if isinstance(source, exp.Table):
                if name not in allowed_columns:
                    raise GeneratedSqlPolicyError("generated_sql_unknown_column")
                referenced_columns.add(name)
                continue
            if isinstance(source, Scope):
                if name not in source.expression.named_selects:
                    raise GeneratedSqlPolicyError("generated_sql_unknown_derived_column")
                continue
            raise GeneratedSqlPolicyError("generated_sql_unresolved_column")
    return referenced_columns


def _column_source(scope: Scope, column: exp.Column) -> exp.Table | Scope | None:
    if column.table:
        return scope.sources.get(column.table)
    selected_sources = tuple(source for _node, source in scope.selected_sources.values())
    if len(selected_sources) == 1:
        return selected_sources[0]
    return None


__all__ = [
    "GENERATED_SQL_AGGREGATE_LIMIT",
    "GENERATED_SQL_DETAIL_LIMIT",
    "GENERATED_SQL_MAX_PLAN_COST",
    "GENERATED_SQL_MAX_PLAN_ROWS",
    "GENERATED_SQL_TIMEOUT_MS",
    "GeneratedSqlPolicyError",
    "ValidatedGeneratedSql",
    "validate_generated_counting_unit",
    "validate_generated_sql",
]
