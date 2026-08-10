from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlglot import exp, parse_one
from sqlalchemy.engine import Connection, Engine

from ai_do_api.domains.legacy_issues.analysis_v2.contracts import (
    PublicCell,
    QueryColumn,
    QueryResult,
    RecipeReference,
)
from ai_do_api.domains.legacy_issues.analysis_v2.recipes import (
    FilterOperator,
    RenderedRecipe,
)
from ai_do_api.domains.legacy_issues.analysis_v2.sql_policy import (
    SafeSqlPolicy,
    ValidatedSql,
)


MAX_QUERY_TIMEOUT_MS = 5_000
MAX_QUERY_ROWS = 1_000
MAX_QUERY_PAYLOAD_BYTES = 250 * 1024
MAX_QUERY_COLUMNS = 64
MAX_CONTAINS_LITERAL_CHARS = 80
MAX_CONTAINS_LITERAL_TERMS = 4
_LITERAL_TERM_RE = re.compile(r"\w+", re.UNICODE)


class SafeQueryLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_ms: int = Field(default=MAX_QUERY_TIMEOUT_MS, ge=1, le=MAX_QUERY_TIMEOUT_MS)
    row_limit: int = Field(default=MAX_QUERY_ROWS, ge=1, le=MAX_QUERY_ROWS)
    payload_bytes: int = Field(
        default=MAX_QUERY_PAYLOAD_BYTES,
        ge=1024,
        le=MAX_QUERY_PAYLOAD_BYTES,
    )


class AnalysisSqlScope(BaseModel):
    """Trusted scope resolved by the application before opening the SQL tools."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=80)
    partition_ids: tuple[str, ...] = Field(default=(), max_length=500)
    module_keys: tuple[str, ...] = Field(default=(), max_length=100)
    revision_ids: tuple[str, ...] = Field(default=(), max_length=500)
    checklist_ids: tuple[str, ...] = Field(default=(), max_length=1000)

    @field_validator(
        "workspace_id",
        "partition_ids",
        "module_keys",
        "revision_ids",
        "checklist_ids",
    )
    @classmethod
    def _reject_scope_delimiters(cls, value: Any) -> Any:
        values = (value,) if isinstance(value, str) else value
        if any(not str(item).strip() or "," in str(item) for item in values):
            raise ValueError("analysis SQL scope values cannot be blank or contain commas")
        return value


@dataclass(frozen=True, slots=True)
class AuthorizedQueryRequest:
    """Request passed only to a server-bound, ACL-aware SQL gateway."""

    validated_sql: ValidatedSql
    parameters: Mapping[str, Any]
    limits: SafeQueryLimits


@dataclass(frozen=True, slots=True)
class RawQueryResult:
    column_names: tuple[str, ...]
    rows: tuple[Sequence[Any] | Mapping[str, Any], ...]
    elapsed_ms: int


class BoundReadOnlySqlGateway(Protocol):
    """Execute against a connection already bound to trusted analysis scope."""

    gateway_id: str

    def execute(self, request: AuthorizedQueryRequest) -> RawQueryResult: ...


class QueryExecutionError(RuntimeError):
    pass


ScopeBinder = Callable[[Connection], None]


class SqlAlchemyReadOnlyGateway:
    """PostgreSQL implementation with transaction, timeout, and outer row caps."""

    gateway_id = "sqlalchemy-postgresql-readonly-v1"

    def __init__(
        self,
        *,
        engine: Engine,
        scope_binder: ScopeBinder,
    ) -> None:
        self._engine = engine
        self._scope_binder = scope_binder

    def execute(self, request: AuthorizedQueryRequest) -> RawQueryResult:
        if self._engine.dialect.name != "postgresql":
            raise QueryExecutionError("analysis_v2_requires_postgresql")
        started = time.perf_counter()
        with self._engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql(
                f"SET LOCAL statement_timeout = '{request.limits.timeout_ms}ms'"
            )
            self._scope_binder(connection)
            bounded_sql = (
                "SELECT * FROM ("
                f"{request.validated_sql.sql}"
                ") AS bounded_analysis_result "
                f"LIMIT {request.limits.row_limit + 1}"
            )
            result = connection.exec_driver_sql(
                bounded_sql,
                dict(request.parameters),
            )
            column_names = tuple(str(name) for name in result.keys())
            rows = tuple(result.fetchmany(request.limits.row_limit + 1))
        return RawQueryResult(
            column_names=column_names,
            rows=rows,
            elapsed_ms=max(int((time.perf_counter() - started) * 1000), 0),
        )


def postgres_scope_binder(scope: AnalysisSqlScope) -> ScopeBinder:
    """Build the only supported binder for the v1 security-barrier views."""

    settings = (
        ("ai_do.legacy_issue_workspace_id", scope.workspace_id),
        ("ai_do.legacy_issue_partition_ids", ",".join(scope.partition_ids)),
        ("ai_do.legacy_issue_module_keys", ",".join(scope.module_keys)),
        ("ai_do.legacy_issue_revision_ids", ",".join(scope.revision_ids)),
        ("ai_do.legacy_issue_checklist_ids", ",".join(scope.checklist_ids)),
    )

    def _bind(connection: Connection) -> None:
        connection.exec_driver_sql("SET LOCAL ROLE ai_do_analysis_reader")
        for name, value in settings:
            connection.exec_driver_sql(
                "SELECT set_config(%(setting_name)s, %(setting_value)s, true)",
                {"setting_name": name, "setting_value": value},
            )

    return _bind


class SafeAnalysisQueryService:
    def __init__(
        self,
        *,
        gateway: BoundReadOnlySqlGateway,
        policy: SafeSqlPolicy | None = None,
        limits: SafeQueryLimits | None = None,
        scope: AnalysisSqlScope | None = None,
    ) -> None:
        self._gateway = gateway
        self._policy = policy or SafeSqlPolicy()
        self._limits = limits or SafeQueryLimits()
        self._scope = scope

    @property
    def allowed_module_keys(self) -> tuple[str, ...]:
        return self._scope.module_keys if self._scope is not None else ()

    @property
    def authorized_revision_ids(self) -> tuple[str, ...]:
        return self._scope.revision_ids if self._scope is not None else ()

    def run_recipe(self, rendered: RenderedRecipe) -> QueryResult:
        requested_modules = rendered.arguments.get("module_keys")
        if (
            self._scope is not None
            and isinstance(requested_modules, (list, tuple))
            and not set(str(value) for value in requested_modules).issubset(
                self._scope.module_keys
            )
        ):
            return _blocked_recipe_result(
                rendered,
                error_code="analysis_v2.invalid_module_filter",
            )
        if not _contains_filters_are_literal_phrases(rendered):
            return _blocked_recipe_result(
                rendered,
                error_code="analysis_v2.invalid_literal_filter",
            )
        return self._execute(
            validated_sql=rendered.validated_sql,
            parameters=rendered.bindings,
            recipe_arguments=rendered.arguments,
            source="recipe",
            recipe=rendered.recipe.reference,
        )

    def run_safe_sql(
        self,
        sql: str,
        *,
        parameters: Mapping[str, Any] | None = None,
    ) -> QueryResult:
        bindings = dict(parameters or {})
        validated = self._policy.validate(sql, parameters=bindings)
        if self._scope is not None and not _module_filters_within_scope(
            validated.sql,
            parameters=bindings,
            allowed_module_keys=frozenset(self._scope.module_keys),
        ):
            return _blocked_safe_sql_result(
                validated,
                parameters=bindings,
                error_code="analysis_v2.invalid_module_filter",
            )
        return self._execute(
            validated_sql=validated,
            parameters=bindings,
            recipe_arguments={},
            source="safe_sql",
            recipe=None,
        )

    def _execute(
        self,
        *,
        validated_sql: ValidatedSql,
        parameters: Mapping[str, Any],
        recipe_arguments: Mapping[str, Any],
        source: Literal["recipe", "safe_sql"],
        recipe: RecipeReference | None,
    ) -> QueryResult:
        normalized_parameters = {
            str(name): _normalize_parameter(value)
            for name, value in parameters.items()
        }
        normalized_recipe_arguments = {
            str(name): _normalize_recipe_argument(value)
            for name, value in recipe_arguments.items()
        }
        started = time.perf_counter()
        try:
            raw = self._gateway.execute(
                AuthorizedQueryRequest(
                    validated_sql=validated_sql,
                    parameters=parameters,
                    limits=self._limits,
                )
            )
        except Exception:
            return QueryResult(
                query_id=f"analysis-{validated_sql.fingerprint[:16]}",
                source=source,
                recipe=recipe,
                parameterized_sql=validated_sql.sql,
                parameters=normalized_parameters,
                recipe_arguments=normalized_recipe_arguments,
                status="failed",
                error_code="analysis_v2.query_execution_failed",
                columns=(),
                rows=(),
                row_count=0,
                truncated=False,
                payload_bytes=0,
                elapsed_ms=max(int((time.perf_counter() - started) * 1000), 0),
                referenced_views=validated_sql.referenced_views,
            )
        if not raw.column_names or len(raw.column_names) > MAX_QUERY_COLUMNS:
            raise QueryExecutionError("analysis_v2_result_column_limit")
        if len(set(raw.column_names)) != len(raw.column_names):
            raise QueryExecutionError("analysis_v2_duplicate_result_columns")

        raw_rows = raw.rows
        truncated = len(raw_rows) > self._limits.row_limit
        rows: list[dict[str, PublicCell]] = []
        payload_bytes = 0
        for raw_row in raw_rows[: self._limits.row_limit]:
            row = _normalize_row(raw_row, column_names=raw.column_names)
            serialized = json.dumps(
                row,
                ensure_ascii=False,
                default=_json_default,
                separators=(",", ":"),
            ).encode("utf-8")
            if payload_bytes + len(serialized) > self._limits.payload_bytes:
                truncated = True
                break
            rows.append(row)
            payload_bytes += len(serialized)
        columns = tuple(
            QueryColumn(
                name=name,
                value_type=_infer_column_type(
                    [row.get(name) for row in rows if row.get(name) is not None]
                ),
            )
            for name in raw.column_names
        )
        return QueryResult(
            query_id=f"analysis-{validated_sql.fingerprint[:16]}",
            source=source,
            recipe=recipe,
            parameterized_sql=validated_sql.sql,
            parameters=normalized_parameters,
            recipe_arguments=normalized_recipe_arguments,
            status="succeeded",
            error_code=None,
            columns=columns,
            rows=tuple(rows),
            row_count=len(rows),
            truncated=truncated,
            payload_bytes=payload_bytes,
            elapsed_ms=raw.elapsed_ms,
            referenced_views=validated_sql.referenced_views,
        )


def _blocked_recipe_result(
    rendered: RenderedRecipe,
    *,
    error_code: str,
) -> QueryResult:
    return QueryResult(
        query_id=f"analysis-{rendered.validated_sql.fingerprint[:16]}",
        source="recipe",
        recipe=rendered.recipe.reference,
        parameterized_sql=rendered.validated_sql.sql,
        parameters={
            str(name): _normalize_parameter(value)
            for name, value in rendered.bindings.items()
        },
        recipe_arguments={
            str(name): _normalize_recipe_argument(value)
            for name, value in rendered.arguments.items()
        },
        status="failed",
        error_code=error_code,
        columns=(),
        rows=(),
        row_count=0,
        truncated=False,
        payload_bytes=0,
        elapsed_ms=0,
        referenced_views=rendered.validated_sql.referenced_views,
    )


def _contains_filters_are_literal_phrases(rendered: RenderedRecipe) -> bool:
    """Validate CONTAINS as a bounded literal operator, independent of question text."""

    for parameter in rendered.recipe.parameters:
        if parameter.operator != FilterOperator.CONTAINS:
            continue
        value = rendered.arguments.get(parameter.name)
        if value is None:
            continue
        if not isinstance(value, str):
            return False
        normalized = " ".join(value.split())
        if (
            not normalized
            or len(normalized) > MAX_CONTAINS_LITERAL_CHARS
            or len(_LITERAL_TERM_RE.findall(normalized))
            > MAX_CONTAINS_LITERAL_TERMS
        ):
            return False
    return True


def _blocked_safe_sql_result(
    validated_sql: ValidatedSql,
    *,
    parameters: Mapping[str, Any],
    error_code: str,
) -> QueryResult:
    return QueryResult(
        query_id=f"analysis-{validated_sql.fingerprint[:16]}",
        source="safe_sql",
        recipe=None,
        parameterized_sql=validated_sql.sql,
        parameters={
            str(name): _normalize_parameter(value)
            for name, value in parameters.items()
        },
        recipe_arguments={},
        status="failed",
        error_code=error_code,
        columns=(),
        rows=(),
        row_count=0,
        truncated=False,
        payload_bytes=0,
        elapsed_ms=0,
        referenced_views=validated_sql.referenced_views,
    )


def _module_filters_within_scope(
    sql: str,
    *,
    parameters: Mapping[str, Any],
    allowed_module_keys: frozenset[str],
) -> bool:
    statement = parse_one(sql, read="postgres")
    handled_columns: set[int] = set()
    requested: set[str] = set()
    for predicate in statement.find_all(exp.EQ):
        column, value_expression = _module_filter_operands(
            predicate.this,
            predicate.expression,
        )
        if column is None:
            continue
        handled_columns.add(id(column))
        value = _sql_filter_value(value_expression, parameters=parameters)
        if value is None:
            return False
        requested.add(value)
    for predicate in statement.find_all(exp.In):
        column = predicate.this
        if not isinstance(column, exp.Column) or column.name != "module_key":
            continue
        handled_columns.add(id(column))
        if not predicate.expressions:
            return False
        for value_expression in predicate.expressions:
            value = _sql_filter_value(value_expression, parameters=parameters)
            if value is None:
                return False
            requested.add(value)
    for column in statement.find_all(exp.Column):
        if (
            column.name == "module_key"
            and _has_ancestor(column, exp.Predicate)
            and id(column) not in handled_columns
        ):
            return False
    return requested.issubset(allowed_module_keys)


def _module_filter_operands(
    left: exp.Expression,
    right: exp.Expression,
) -> tuple[exp.Column | None, exp.Expression]:
    if isinstance(left, exp.Column) and left.name == "module_key":
        return left, right
    if isinstance(right, exp.Column) and right.name == "module_key":
        return right, left
    return None, right


def _sql_filter_value(
    expression: exp.Expression,
    *,
    parameters: Mapping[str, Any],
) -> str | None:
    if isinstance(expression, exp.Placeholder):
        value = parameters.get(str(expression.name))
    elif isinstance(expression, exp.Literal) and expression.is_string:
        value = expression.this
    else:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _has_ancestor(
    expression: exp.Expression,
    ancestor_type: type[exp.Expression],
) -> bool:
    parent = expression.parent
    while parent is not None:
        if isinstance(parent, ancestor_type):
            return True
        parent = parent.parent
    return False


def _normalize_row(
    raw_row: Sequence[Any] | Mapping[str, Any],
    *,
    column_names: tuple[str, ...],
) -> dict[str, PublicCell]:
    if isinstance(raw_row, Mapping):
        values = [raw_row.get(name) for name in column_names]
    else:
        values = list(raw_row)
    if len(values) != len(column_names):
        raise QueryExecutionError("analysis_v2_result_shape_mismatch")
    return {
        name: _normalize_cell(value)
        for name, value in zip(column_names, values, strict=True)
    }


def _normalize_cell(value: Any) -> PublicCell:
    if value is None or isinstance(value, (str, int, float, bool, date, datetime)):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return f"<binary:{len(value)} bytes>"
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        return str(value)


def _normalize_parameter(value: Any) -> PublicCell:
    normalized = _normalize_cell(value)
    if isinstance(normalized, str) and len(normalized) > 2_000:
        return normalized[:2_000]
    return normalized


def _normalize_recipe_argument(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_normalize_recipe_argument(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _normalize_recipe_argument(item)
            for key, item in value.items()
        }
    return _normalize_parameter(value)


def _infer_column_type(values: Iterable[PublicCell]) -> str:
    values = tuple(values)
    if not values:
        return "null"
    if all(isinstance(value, bool) for value in values):
        return "boolean"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return "integer"
    if all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in values
    ):
        return "number"
    if all(isinstance(value, datetime) for value in values):
        return "datetime"
    if all(isinstance(value, date) and not isinstance(value, datetime) for value in values):
        return "date"
    return "text"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


__all__ = [
    "MAX_QUERY_PAYLOAD_BYTES",
    "MAX_QUERY_ROWS",
    "MAX_QUERY_TIMEOUT_MS",
    "AnalysisSqlScope",
    "AuthorizedQueryRequest",
    "BoundReadOnlySqlGateway",
    "QueryExecutionError",
    "RawQueryResult",
    "SafeAnalysisQueryService",
    "SafeQueryLimits",
    "SqlAlchemyReadOnlyGateway",
    "postgres_scope_binder",
]
