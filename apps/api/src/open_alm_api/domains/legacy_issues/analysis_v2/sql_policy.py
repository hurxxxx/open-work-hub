from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from open_alm_api.domains.legacy_issues.analysis_v2.views import (
    ANALYSIS_VIEW_CONTRACTS,
    CHECKLIST_ITEMS_VIEW_V1,
    ISSUE_RECORDS_VIEW_V1,
    AnalysisViewContract,
)


MAX_SQL_CHARS = 20_000
_PARAMETER_NAME = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_SQL_COMMENT = re.compile(r"(--|/\*)")
_APPROVED_JOIN_KEY_PAIRS = frozenset(
    {
        frozenset(
            {
                (ISSUE_RECORDS_VIEW_V1, "stable_issue_id"),
                (CHECKLIST_ITEMS_VIEW_V1, "stable_issue_id"),
            }
        ),
    }
)

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
        "min",
        "nullif",
        "or",
        "percentile_cont",
        "percentile_disc",
        "rank",
        "replace",
        "round",
        "row_number",
        "stddev",
        "stddev_pop",
        "stddev_samp",
        "substring",
        "sum",
        "timestamp_trunc",
        "trim",
        "upper",
        "variance",
        "var_pop",
        "var_samp",
    }
)

_DISALLOWED_NODE_NAMES = (
    "Alter",
    "Attach",
    "Command",
    "Commit",
    "Copy",
    "Create",
    "Delete",
    "Detach",
    "Drop",
    "Execute",
    "Grant",
    "Insert",
    "Into",
    "Merge",
    "Pragma",
    "Revoke",
    "Set",
    "Transaction",
    "TruncateTable",
    "Update",
    "Use",
)
_DISALLOWED_NODES = tuple(
    node_type
    for name in _DISALLOWED_NODE_NAMES
    if (node_type := getattr(exp, name, None)) is not None
)


class SafeSqlPolicyError(ValueError):
    """SQL failed the versioned read-only analysis-view contract."""


@dataclass(frozen=True, slots=True)
class ValidatedSql:
    sql: str
    fingerprint: str
    referenced_views: tuple[str, ...]
    referenced_columns: tuple[str, ...]
    parameter_names: tuple[str, ...]


class SafeSqlPolicy:
    """Validate model-authored SQL without resolving authorization itself."""

    def __init__(
        self,
        *,
        view_contracts: Mapping[str, AnalysisViewContract] = ANALYSIS_VIEW_CONTRACTS,
        allowed_functions: frozenset[str] = _ALLOWED_FUNCTIONS,
    ) -> None:
        self._views = dict(view_contracts)
        self._allowed_functions = allowed_functions

    @property
    def view_contracts(self) -> Mapping[str, AnalysisViewContract]:
        return self._views

    def validate(
        self,
        sql: str,
        *,
        parameters: Mapping[str, Any] | None = None,
    ) -> ValidatedSql:
        normalized = str(sql or "").strip()
        if not normalized:
            raise SafeSqlPolicyError("safe_sql_empty")
        if len(normalized) > MAX_SQL_CHARS:
            raise SafeSqlPolicyError("safe_sql_too_large")
        if _SQL_COMMENT.search(normalized):
            raise SafeSqlPolicyError("safe_sql_comment_not_allowed")

        try:
            statements = parse(normalized, read="postgres")
        except ParseError as exc:
            raise SafeSqlPolicyError("safe_sql_parse_failed") from exc
        if len(statements) != 1:
            raise SafeSqlPolicyError("safe_sql_multiple_statements")
        statement = statements[0]
        if not isinstance(statement, exp.Select):
            raise SafeSqlPolicyError("safe_sql_select_only")
        if any(statement.find(node_type) is not None for node_type in _DISALLOWED_NODES):
            raise SafeSqlPolicyError("safe_sql_mutation_not_allowed")
        if statement.find(exp.With) is not None or statement.find(exp.CTE) is not None:
            raise SafeSqlPolicyError("safe_sql_cte_not_allowed")
        if statement.find(exp.Subquery) is not None:
            raise SafeSqlPolicyError("safe_sql_subquery_not_allowed")
        if any(
            statement.find(node_type) is not None
            for node_type in (exp.Union, exp.Intersect, exp.Except)
        ):
            raise SafeSqlPolicyError("safe_sql_set_operation_not_allowed")
        if any(
            star.parent is None or not isinstance(star.parent, exp.Count)
            for star in statement.find_all(exp.Star)
        ):
            raise SafeSqlPolicyError("safe_sql_wildcard_not_allowed")
        if statement.args.get("locks"):
            raise SafeSqlPolicyError("safe_sql_lock_not_allowed")

        aliases, referenced_views = self._validate_tables(statement)
        referenced_columns = self._validate_columns(statement, aliases=aliases)
        self._validate_functions(statement)
        self._validate_joins(statement, aliases=aliases)
        self._validate_projections(statement)
        parameter_names = self._validate_parameters(statement, parameters=parameters or {})

        canonical = statement.sql(dialect="postgres", comments=False)
        return ValidatedSql(
            sql=canonical,
            fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            referenced_views=tuple(sorted(referenced_views)),
            referenced_columns=tuple(sorted(referenced_columns)),
            parameter_names=tuple(sorted(parameter_names)),
        )

    def _validate_tables(
        self,
        statement: exp.Select,
    ) -> tuple[dict[str, AnalysisViewContract], set[str]]:
        aliases: dict[str, AnalysisViewContract] = {}
        referenced_views: set[str] = set()
        for table in statement.find_all(exp.Table):
            if table.catalog:
                raise SafeSqlPolicyError("safe_sql_catalog_not_allowed")
            schema = table.db
            if not schema:
                raise SafeSqlPolicyError("safe_sql_qualified_view_required")
            qualified_name = f"{schema}.{table.name}"
            contract = self._views.get(qualified_name)
            if contract is None:
                raise SafeSqlPolicyError("safe_sql_view_not_allowed")
            alias = table.alias_or_name
            if alias in aliases and aliases[alias].name != qualified_name:
                raise SafeSqlPolicyError("safe_sql_duplicate_relation_alias")
            aliases[alias] = contract
            aliases[table.name] = contract
            referenced_views.add(qualified_name)
        if not referenced_views:
            raise SafeSqlPolicyError("safe_sql_view_required")
        return aliases, referenced_views

    def _validate_columns(
        self,
        statement: exp.Select,
        *,
        aliases: Mapping[str, AnalysisViewContract],
    ) -> set[str]:
        output_aliases = {
            projection.alias
            for projection in statement.expressions
            if projection.alias
        }
        contracts = {contract.name: contract for contract in aliases.values()}
        referenced: set[str] = set()
        for column in statement.find_all(exp.Column):
            name = column.name
            if not name:
                raise SafeSqlPolicyError("safe_sql_column_invalid")
            if column.table:
                contract = aliases.get(column.table)
                if contract is None or name not in contract.columns:
                    raise SafeSqlPolicyError("safe_sql_column_not_allowed")
                referenced.add(f"{contract.name}.{name}")
                continue
            if name in output_aliases:
                continue
            matches = [
                contract
                for contract in contracts.values()
                if name in contract.columns
            ]
            if len(matches) != 1:
                reason = (
                    "safe_sql_ambiguous_column"
                    if len(matches) > 1
                    else "safe_sql_column_not_allowed"
                )
                raise SafeSqlPolicyError(reason)
            referenced.add(f"{matches[0].name}.{name}")
        return referenced

    def _validate_functions(self, statement: exp.Select) -> None:
        for function in statement.find_all(exp.Func):
            name = function.sql_name().casefold()
            if name not in self._allowed_functions:
                raise SafeSqlPolicyError("safe_sql_function_not_allowed")

    @staticmethod
    def _validate_joins(
        statement: exp.Select,
        *,
        aliases: Mapping[str, AnalysisViewContract],
    ) -> None:
        from_clause = statement.args.get("from_")
        first_relation = getattr(from_clause, "this", None)
        if not isinstance(first_relation, exp.Table):
            raise SafeSqlPolicyError("safe_sql_view_required")
        introduced_aliases = {first_relation.alias_or_name}
        for join in statement.find_all(exp.Join):
            if join.args.get("using") or join.args.get("method") == "NATURAL":
                raise SafeSqlPolicyError("safe_sql_implicit_join_not_allowed")
            if join.args.get("kind") == "CROSS" or join.args.get("on") is None:
                raise SafeSqlPolicyError("safe_sql_unbounded_join_not_allowed")
            joined_relation = join.this
            if not isinstance(joined_relation, exp.Table):
                raise SafeSqlPolicyError("safe_sql_join_condition_not_allowed")
            joined_alias = joined_relation.alias_or_name
            on_expression = join.args["on"]
            if not isinstance(on_expression, exp.EQ):
                raise SafeSqlPolicyError("safe_sql_join_condition_not_allowed")
            left = on_expression.this
            right = on_expression.expression
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                raise SafeSqlPolicyError("safe_sql_join_condition_not_allowed")
            if not left.table or not right.table or left.table == right.table:
                raise SafeSqlPolicyError("safe_sql_join_condition_not_allowed")
            if joined_alias not in {left.table, right.table}:
                raise SafeSqlPolicyError("safe_sql_join_condition_not_allowed")
            prior_alias = right.table if left.table == joined_alias else left.table
            if prior_alias not in introduced_aliases:
                raise SafeSqlPolicyError("safe_sql_join_condition_not_allowed")
            left_contract = aliases.get(left.table)
            right_contract = aliases.get(right.table)
            if left_contract is None or right_contract is None:
                raise SafeSqlPolicyError("safe_sql_join_condition_not_allowed")
            key_pair = frozenset(
                {
                    (left_contract.name, left.name),
                    (right_contract.name, right.name),
                }
            )
            if key_pair not in _APPROVED_JOIN_KEY_PAIRS:
                raise SafeSqlPolicyError("safe_sql_join_key_not_allowed")
            introduced_aliases.add(joined_alias)

    @staticmethod
    def _validate_projections(statement: exp.Select) -> None:
        for projection in statement.expressions:
            expression = projection.this if isinstance(projection, exp.Alias) else projection
            has_column = expression.find(exp.Column) is not None
            has_count_star = any(
                count.find(exp.Star) is not None for count in expression.find_all(exp.Count)
            )
            if not has_column and not has_count_star:
                raise SafeSqlPolicyError("safe_sql_unsourced_projection")

    @staticmethod
    def _validate_parameters(
        statement: exp.Select,
        *,
        parameters: Mapping[str, Any],
    ) -> set[str]:
        names = {placeholder.name for placeholder in statement.find_all(exp.Placeholder)}
        if any(not name or not _PARAMETER_NAME.fullmatch(name) for name in names):
            raise SafeSqlPolicyError("safe_sql_parameter_invalid")
        supplied = {str(name) for name in parameters}
        if any(not _PARAMETER_NAME.fullmatch(name) for name in supplied):
            raise SafeSqlPolicyError("safe_sql_parameter_invalid")
        if names.difference(supplied):
            raise SafeSqlPolicyError("safe_sql_parameter_missing")
        if supplied.difference(names):
            raise SafeSqlPolicyError("safe_sql_parameter_unused")
        return names


__all__ = [
    "MAX_SQL_CHARS",
    "SafeSqlPolicy",
    "SafeSqlPolicyError",
    "ValidatedSql",
]
