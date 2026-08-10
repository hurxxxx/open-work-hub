from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import literal, select
from sqlalchemy.dialects import postgresql

from open_alm_api.domains.legacy_issues import analysis_generated_executor as executor
from open_alm_api.domains.legacy_issues.analysis_generated_executor import (
    GeneratedAnalysisExecutionError,
    execute_generated_analysis,
)
from open_alm_api.domains.legacy_issues.analysis_generated_sql import (
    GENERATED_SQL_AGGREGATE_LIMIT,
    GENERATED_SQL_DETAIL_LIMIT,
    GENERATED_SQL_MAX_PLAN_COST,
    GENERATED_SQL_MAX_PLAN_ROWS,
    GENERATED_SQL_TIMEOUT_MS,
    ValidatedGeneratedSql,
)
from open_alm_api.domains.legacy_issues.analysis_sql_fallback import (
    LegacyIssueGeneratedSqlPlan,
)


class _Transaction:
    def __init__(self, events: list[tuple[str, Any]]) -> None:
        self.events = events

    def __enter__(self) -> "_Transaction":
        self.events.append(("transaction_enter", None))
        return self

    def __exit__(self, *_args: object) -> None:
        self.events.append(("transaction_exit", None))


class _ExplainResult:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def scalar_one(self) -> object:
        return self.payload


class _RowsResult:
    def __init__(
        self,
        *,
        column_keys: tuple[str, ...],
        rows: list[tuple[object, ...]],
        fetch_sizes: list[int],
    ) -> None:
        self.column_keys = column_keys
        self.rows = rows
        self.fetch_sizes = fetch_sizes

    def keys(self) -> tuple[str, ...]:
        return self.column_keys

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        self.fetch_sizes.append(size)
        return self.rows[:size]


class _Connection:
    def __init__(
        self,
        *,
        events: list[tuple[str, Any]],
        explain_payload: object,
        column_keys: tuple[str, ...] = ("region_zone", "issue_count"),
        rows: list[tuple[object, ...]] | None = None,
        source_count: int = 7,
    ) -> None:
        self.events = events
        self.explain_payload = explain_payload
        self.column_keys = column_keys
        self.rows = rows or [("국내", 2)]
        self.source_count = source_count
        self.fetch_sizes: list[int] = []
        self.dialect = postgresql.dialect()

    def __enter__(self) -> "_Connection":
        self.events.append(("connection_enter", None))
        return self

    def __exit__(self, *_args: object) -> None:
        self.events.append(("connection_exit", None))

    def begin(self) -> _Transaction:
        self.events.append(("begin", None))
        return _Transaction(self.events)

    def scalar(self, _statement: object) -> int:
        self.events.append(("source_count", None))
        return self.source_count

    def exec_driver_sql(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> object:
        self.events.append(("exec_driver_sql", sql))
        if sql.startswith("EXPLAIN (FORMAT JSON)"):
            return _ExplainResult(self.explain_payload)
        if sql.startswith("SELECT * FROM ("):
            return _RowsResult(
                column_keys=self.column_keys,
                rows=self.rows,
                fetch_sizes=self.fetch_sizes,
            )
        return SimpleNamespace()


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def connect(self) -> _Connection:
        return self.connection


class _Session:
    def __init__(self, *, dialect_name: str, engine: _Engine | None = None) -> None:
        self.bind = SimpleNamespace(
            dialect=SimpleNamespace(name=dialect_name),
            engine=engine,
        )

    def get_bind(self) -> object:
        return self.bind


def _generated_plan(*, shape: str = "table") -> LegacyIssueGeneratedSqlPlan:
    return LegacyIssueGeneratedSqlPlan(
        title="권역별 문제 현황",
        shape=shape,
        validated_sql=ValidatedGeneratedSql(
            sql=(
                "SELECT region_zone, COUNT(*) AS issue_count "
                "FROM visible_records GROUP BY region_zone"
            ),
            ast_fingerprint="a" * 64,
            referenced_columns=("region_zone",),
            cte_names=(),
        ),
    )


def _runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    explain_payload: object | None = None,
    column_keys: tuple[str, ...] = ("region_zone", "issue_count"),
    rows: list[tuple[object, ...]] | None = None,
    source_count: int = 7,
) -> tuple[_Session, _Connection, list[tuple[str, Any]]]:
    events: list[tuple[str, Any]] = []
    connection = _Connection(
        events=events,
        explain_payload=explain_payload or {"Plan": {"Total Cost": 10, "Plan Rows": 10}},
        column_keys=column_keys,
        rows=rows,
        source_count=source_count,
    )
    session = _Session(dialect_name="postgresql", engine=_Engine(connection))
    scope = SimpleNamespace(
        dataset_key="common-master",
        module_keys=("aircon",),
        revision_ids=("revision-1",),
    )
    visible_records = select(
        literal("stable-1").label("stable_record_id"),
        literal("record-1").label("record_id"),
        literal("국내").label("region_zone"),
    ).cte("visible_records")
    monkeypatch.setattr(executor, "resolve_analysis_scope", lambda *_args, **_kwargs: scope)
    monkeypatch.setattr(
        executor,
        "build_visible_records_relation",
        lambda *_args, **_kwargs: visible_records,
    )
    return session, connection, events


def _execute(
    session: _Session,
    *,
    shape: str = "table",
) -> dict[str, Any]:
    return execute_generated_analysis(
        session,  # type: ignore[arg-type]
        workspace_id="workspace-1",
        enabled_module_keys=("aircon",),
        field_definitions=(),
        generated_plan=_generated_plan(shape=shape),
    )


def test_generated_executor_sets_read_only_and_timeout_before_explain_and_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _connection, events = _runtime(monkeypatch)

    _execute(session)

    executed_sql = [value for event, value in events if event == "exec_driver_sql"]
    assert executed_sql[0] == "SET TRANSACTION READ ONLY"
    assert executed_sql[1] == (f"SET LOCAL statement_timeout = '{GENERATED_SQL_TIMEOUT_MS}ms'")
    assert executed_sql[2].startswith("EXPLAIN (FORMAT JSON)")
    assert executed_sql[3].startswith("SELECT * FROM (")
    assert events.index(("transaction_enter", None)) < events.index(
        ("exec_driver_sql", "SET TRANSACTION READ ONLY")
    )


@pytest.mark.parametrize(
    ("plan", "reason"),
    [
        (
            {
                "Plan": {
                    "Total Cost": GENERATED_SQL_MAX_PLAN_COST + 1,
                    "Plan Rows": 1,
                }
            },
            "generated_sql_plan_cost_limit",
        ),
        (
            {
                "Plan": {
                    "Total Cost": 1,
                    "Plan Rows": GENERATED_SQL_MAX_PLAN_ROWS + 1,
                }
            },
            "generated_sql_plan_row_limit",
        ),
    ],
)
def test_generated_executor_rejects_expensive_plan_before_query(
    monkeypatch: pytest.MonkeyPatch,
    plan: dict[str, object],
    reason: str,
) -> None:
    session, _connection, events = _runtime(
        monkeypatch,
        explain_payload=plan,
    )

    with pytest.raises(GeneratedAnalysisExecutionError, match=reason):
        _execute(session)

    executed_sql = [value for event, value in events if event == "exec_driver_sql"]
    assert any(sql.startswith("EXPLAIN (FORMAT JSON)") for sql in executed_sql)
    assert not any(sql.startswith("SELECT * FROM (") for sql in executed_sql)


@pytest.mark.parametrize(
    ("shape", "row_limit"),
    [
        ("table", GENERATED_SQL_AGGREGATE_LIMIT),
        ("detail", GENERATED_SQL_DETAIL_LIMIT),
    ],
)
def test_generated_executor_applies_outer_row_cap_and_marks_truncation(
    monkeypatch: pytest.MonkeyPatch,
    shape: str,
    row_limit: int,
) -> None:
    rows = [(f"권역-{index}", index) for index in range(row_limit + 1)]
    session, connection, events = _runtime(monkeypatch, rows=rows)

    payload = _execute(session, shape=shape)

    query = payload["queries"][0]
    assert connection.fetch_sizes == [row_limit + 1]
    assert len(query["rows"]) == row_limit
    assert query["truncated"] is True
    assert query["warnings"] == ["결과 행 또는 표시 용량 제한에 따라 일부 행만 표시합니다."]
    assert payload["warnings"] == query["warnings"]
    outer_sql = next(
        value
        for event, value in events
        if event == "exec_driver_sql" and value.startswith("SELECT * FROM (")
    )
    assert outer_sql.endswith(f"LIMIT {row_limit + 1}")


def test_generated_executor_returns_public_v1_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _connection, _events = _runtime(
        monkeypatch,
        column_keys=("region_zone", "issue_count"),
        rows=[("국내", 2)],
        source_count=7,
    )

    payload = _execute(session, shape="bar")

    assert payload == {
        "version": 1,
        "mode": "generated",
        "data_source": "legacy_issues",
        "title": "권역별 문제 현황",
        "exactness": "generated",
        "scope": {
            "dataset_key": "common-master",
            "data_sources": ["legacy_issues"],
            "module_keys": ["aircon"],
            "revision_ids": ["revision-1"],
            "checklist_ids": [],
            "source_count": 7,
            "source_counts": {"legacy_issues": 7},
        },
        "queries": [
            {
                "id": "generated-aaaaaaaaaaaa",
                "title": "권역별 문제 현황",
                "family_id": "generated_sql",
                "family_version": 1,
                "data_source": "legacy_issues",
                "source_count": 7,
                "shape": "bar",
                "exactness": "generated",
                "columns": [
                    {
                        "key": "region_zone",
                        "label": "region_zone",
                        "type": "text",
                        "role": "dimension",
                    },
                    {
                        "key": "issue_count",
                        "label": "issue_count",
                        "type": "number",
                        "role": "metric",
                    },
                ],
                "rows": [{"region_zone": "국내", "issue_count": 2}],
                "totals": {},
                "coverage": [],
                "warnings": [],
                "truncated": False,
            }
        ],
        "warnings": [],
    }


def test_generated_executor_rejects_unsupported_dialect_before_scope_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope_resolved = False

    def _resolve_scope(*_args: object, **_kwargs: object) -> object:
        nonlocal scope_resolved
        scope_resolved = True
        return object()

    monkeypatch.setattr(executor, "resolve_analysis_scope", _resolve_scope)
    session = _Session(dialect_name="sqlite")

    with pytest.raises(
        GeneratedAnalysisExecutionError,
        match="generated_sql_requires_postgresql",
    ):
        _execute(session)

    assert scope_resolved is False
