from __future__ import annotations

from datetime import date
from typing import Any

from ai_do_api.domains.legacy_issues.analysis_v2.execution import (
    MAX_QUERY_PAYLOAD_BYTES,
    MAX_QUERY_ROWS,
    MAX_QUERY_TIMEOUT_MS,
    AuthorizedQueryRequest,
    AnalysisSqlScope,
    RawQueryResult,
    SafeAnalysisQueryService,
    postgres_scope_binder,
)
from ai_do_api.domains.legacy_issues.analysis_v2.recipes import (
    default_recipe_catalog,
)


class _Gateway:
    gateway_id = "test"

    def __init__(
        self,
        *,
        rows: tuple[tuple[Any, ...], ...] = (("A", 2),),
        fail: bool = False,
    ) -> None:
        self.rows = rows
        self.fail = fail
        self.requests: list[AuthorizedQueryRequest] = []

    def execute(self, request: AuthorizedQueryRequest) -> RawQueryResult:
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("database detail must not escape")
        return RawQueryResult(
            column_names=("vehicle_model", "issue_count"),
            rows=self.rows,
            elapsed_ms=13,
        )


class _ScopeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def exec_driver_sql(
        self,
        statement: str,
        parameters: dict[str, str] | None = None,
    ) -> None:
        self.calls.append((statement, parameters))


def test_postgres_scope_binder_enters_reader_role_before_binding_scope() -> None:
    connection = _ScopeConnection()
    binder = postgres_scope_binder(
        AnalysisSqlScope(
            workspace_id="workspace-1",
            partition_ids=("partition-1",),
            module_keys=("global-chassis",),
            revision_ids=("revision-1",),
            checklist_ids=("checklist-1",),
        )
    )

    binder(connection)  # type: ignore[arg-type]

    assert connection.calls[0] == ("SET LOCAL ROLE ai_do_analysis_reader", None)
    assert [call[1]["setting_name"] for call in connection.calls[1:]] == [
        "ai_do.legacy_issue_workspace_id",
        "ai_do.legacy_issue_partition_ids",
        "ai_do.legacy_issue_module_keys",
        "ai_do.legacy_issue_revision_ids",
        "ai_do.legacy_issue_checklist_ids",
    ]


def test_execution_enforces_fixed_limits_and_persists_full_lineage() -> None:
    gateway = _Gateway()
    service = SafeAnalysisQueryService(gateway=gateway)

    result = service.run_safe_sql(
        "SELECT i.vehicle_model, COUNT(DISTINCT i.issue_id) AS issue_count "
        "FROM legacy_issue_analysis.issue_records_v1 AS i "
        "WHERE i.occurrence_date >= :date_from GROUP BY i.vehicle_model",
        parameters={"date_from": date(2026, 1, 1)},
    )

    request = gateway.requests[0]
    assert request.limits.timeout_ms == MAX_QUERY_TIMEOUT_MS == 5_000
    assert request.limits.row_limit == MAX_QUERY_ROWS == 1_000
    assert request.limits.payload_bytes == MAX_QUERY_PAYLOAD_BYTES == 250 * 1024
    assert result.status == "succeeded"
    assert result.error_code is None
    assert result.parameterized_sql
    assert result.parameters == {"date_from": date(2026, 1, 1)}
    assert result.row_count == 1
    assert result.columns[1].value_type == "integer"
    assert result.elapsed_ms == 13


def test_recipe_execution_preserves_identifiers_defaults_and_filters() -> None:
    gateway = _Gateway()
    rendered = default_recipe_catalog().render(
        "issue_matrix",
        1,
        {
            "row_dimension": "occurrence_stage",
            "column_dimension": "process_name",
            "regions": ["테스트-국내"],
            "limit": 25,
        },
    )

    result = SafeAnalysisQueryService(gateway=gateway).run_recipe(rendered)

    assert result.parameters == {
        "limit": 25,
        "regions_0": "테스트-국내",
    }
    assert result.recipe_arguments == {
        "row_dimension": "occurrence_stage",
        "column_dimension": "process_name",
        "limit": 25,
        "regions": ["테스트-국내"],
    }


def test_recipe_execution_rejects_module_filter_outside_server_scope() -> None:
    gateway = _Gateway()
    rendered = default_recipe_catalog().render(
        "issue_total",
        1,
        {
            "module_keys": ["evaporator"],
            "query_text": "에바 증발기 결빙",
        },
    )
    service = SafeAnalysisQueryService(
        gateway=gateway,
        scope=AnalysisSqlScope(
            workspace_id="workspace-1",
            module_keys=("aircon", "compressor"),
        ),
    )

    result = service.run_recipe(rendered)

    assert result.status == "failed"
    assert result.error_code == "analysis_v2.invalid_module_filter"
    assert result.recipe_arguments["module_keys"] == ["evaporator"]
    assert gateway.requests == []


def test_recipe_execution_rejects_natural_language_question_as_literal_filter() -> None:
    gateway = _Gateway()
    rendered = default_recipe_catalog().render(
        "issue_total",
        1,
        {
            "query_text": "에바(증발기)가 얼어서 문제된 이력이 있어?",
        },
    )

    result = SafeAnalysisQueryService(gateway=gateway).run_recipe(rendered)

    assert result.status == "failed"
    assert result.error_code == "analysis_v2.invalid_literal_filter"
    assert gateway.requests == []


def test_contains_filter_uses_generic_literal_phrase_bounds() -> None:
    gateway = _Gateway()
    catalog = default_recipe_catalog()
    sentence = catalog.render(
        "issue_total",
        1,
        {
            "query_text": "에바 증발기가 얼어서 문제된 이력이 있는지 확인",
        },
    )
    short_literal = catalog.render(
        "issue_total",
        1,
        {
            "query_text": "EVA FREEZE?",
        },
    )
    service = SafeAnalysisQueryService(gateway=gateway)

    rejected = service.run_recipe(sentence)
    accepted = service.run_recipe(short_literal)

    assert rejected.error_code == "analysis_v2.invalid_literal_filter"
    assert accepted.status == "succeeded"
    assert len(gateway.requests) == 1


def test_safe_sql_rejects_module_filter_outside_server_scope() -> None:
    gateway = _Gateway()
    service = SafeAnalysisQueryService(
        gateway=gateway,
        scope=AnalysisSqlScope(
            workspace_id="workspace-1",
            module_keys=("aircon", "compressor"),
        ),
    )

    result = service.run_safe_sql(
        "SELECT COUNT(DISTINCT i.issue_id) AS issue_count "
        "FROM legacy_issue_analysis.issue_records_v1 AS i "
        "WHERE i.module_key = :requested_module",
        parameters={"requested_module": "evaporator"},
    )

    assert result.status == "failed"
    assert result.error_code == "analysis_v2.invalid_module_filter"
    assert result.parameters == {"requested_module": "evaporator"}
    assert gateway.requests == []


def test_safe_sql_accepts_module_filter_inside_server_scope() -> None:
    gateway = _Gateway()
    service = SafeAnalysisQueryService(
        gateway=gateway,
        scope=AnalysisSqlScope(
            workspace_id="workspace-1",
            module_keys=("aircon", "compressor"),
        ),
    )

    result = service.run_safe_sql(
        "SELECT COUNT(DISTINCT i.issue_id) AS issue_count "
        "FROM legacy_issue_analysis.issue_records_v1 AS i "
        "WHERE i.module_key IN (:module_a, :module_b)",
        parameters={"module_a": "aircon", "module_b": "compressor"},
    )

    assert result.status == "succeeded"
    assert len(gateway.requests) == 1


def test_execution_marks_row_and_payload_truncation() -> None:
    gateway = _Gateway(
        rows=tuple((f"차종-{index}", index) for index in range(MAX_QUERY_ROWS + 1))
    )

    result = SafeAnalysisQueryService(gateway=gateway).run_safe_sql(
        "SELECT i.vehicle_model, i.revision_no AS issue_count "
        "FROM legacy_issue_analysis.issue_records_v1 AS i",
    )

    assert result.row_count == MAX_QUERY_ROWS
    assert result.truncated is True
    assert result.payload_bytes <= MAX_QUERY_PAYLOAD_BYTES


def test_execution_returns_sanitized_typed_failure_for_artifact_persistence() -> None:
    gateway = _Gateway(fail=True)

    result = SafeAnalysisQueryService(gateway=gateway).run_safe_sql(
        "SELECT COUNT(DISTINCT i.issue_id) AS issue_count "
        "FROM legacy_issue_analysis.issue_records_v1 AS i",
    )

    assert result.status == "failed"
    assert result.error_code == "analysis_v2.query_execution_failed"
    assert result.columns == ()
    assert result.rows == ()
    assert result.parameterized_sql
    assert "database detail" not in result.model_dump_json()


def test_execution_never_coerces_binary_or_json_values_to_null() -> None:
    gateway = _Gateway(
        rows=((b"\x00\x01", {"z": 2, "a": ["B", 1]}),),
    )

    result = SafeAnalysisQueryService(gateway=gateway).run_safe_sql(
        "SELECT i.vehicle_model, i.issue_type AS issue_count "
        "FROM legacy_issue_analysis.issue_records_v1 AS i "
        "WHERE i.vehicle_model <> :binary_value "
        "AND i.issue_type <> :json_value",
        parameters={
            "binary_value": b"abc",
            "json_value": {"z": 2, "a": ["B", 1]},
        },
    )

    assert result.status == "succeeded"
    assert result.parameters == {
        "binary_value": "<binary:3 bytes>",
        "json_value": '{"a":["B",1],"z":2}',
    }
    assert result.rows == (
        {
            "vehicle_model": "<binary:2 bytes>",
            "issue_count": '{"a":["B",1],"z":2}',
        },
    )
    assert all(value is not None for value in result.rows[0].values())
