from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from ai_do_api.domains.ai.gateway import AiGatewayDecision
from ai_do_api.domains.legacy_issues import analysis_planner
from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisCountingUnit,
    AnalysisDataSource,
    AnalysisMode,
    AnalysisPlanV1,
    DimensionSpecV1,
    FilterConditionV1,
    FilterGroupV1,
    FilterJunction,
    FilterOperator,
    MetricOperator,
    QueryFamilyId,
    QueryRequestV1,
)
from ai_do_api.domains.legacy_issues.analysis_planner import (
    plan_legacy_issue_analysis,
)
from ai_do_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_FIELDS,
    DatasetFieldDefinition,
)
from ai_do_api.domains.legacy_issues.task_kinds import (
    LEGACY_ISSUE_ANALYSIS_PLAN_WORKLOAD_ID,
)


def test_analysis_planner_uses_registered_workload_and_runtime_catalog(monkeypatch) -> None:
    decision = cast(AiGatewayDecision, object())
    execute = _mock_execute(
        monkeypatch,
        [_result(_plan_json(query=_total_count_query()), decision)],
    )

    planning = _run_planner()
    plan, decisions = planning

    assert plan.mode == AnalysisMode.ANALYTICS
    assert plan.queries[0].family_ref == "total_count@1"
    assert decisions == [decision]
    call = execute.call_args
    assert call.args[0] == LEGACY_ISSUE_ANALYSIS_PLAN_WORKLOAD_ID
    assert call.args[1].app_id == "legacy-issues"
    assert call.args[1].source == "legacy_issues.analysis_plan"
    assert call.kwargs["temperature"] == 0
    assert call.kwargs["max_tokens"] == 4_096
    request = json.loads(call.kwargs["messages"][1]["content"])
    assert request["question"] == "권역별 전체 건수를 알려줘"
    assert len(request["analysis_catalog"]["family_index"]) == 62
    assert len(request["analysis_catalog"]["family_details"]) == 8
    assert request["analysis_catalog"]["fields"][0]["key"] == "region_zone"
    assert request["analysis_catalog"]["fields"][0]["options"] == ["국내", "해외"]
    assert request["response_json_schema"]["additionalProperties"] is False
    assert "sql" not in _collect_keys(request["response_json_schema"])
    system_prompt = call.kwargs["messages"][0]["content"]
    assert "family_index is complete" in system_prompt
    assert "exclude_seed_matches=true only when" in system_prompt
    assert "one global N across complete dimension tuples" in system_prompt
    assert "N inside every parent group" in system_prompt
    assert "grouped breakdown and its overall total" in system_prompt
    assert "Preserve every explicitly named population constraint" in system_prompt
    assert "not a reason to use generated SQL" in system_prompt
    assert "free-text filter values must be literals explicitly named" in system_prompt
    assert planning.diagnostics.status == "valid"
    assert planning.diagnostics.attempt_count == 1
    assert planning.diagnostics.candidate_family_count == 8
    assert planning.diagnostics.prompt_chars < 32_000


def test_analysis_planner_repairs_catalog_invalid_plan_once(monkeypatch) -> None:
    first_decision = cast(AiGatewayDecision, object())
    second_decision = cast(AiGatewayDecision, object())
    invalid_query = {
        "query_id": "q1",
        "family_id": "single_distribution",
        "dimensions": [{"field_key": "unknown_field"}],
    }
    valid_query = {
        "query_id": "q1",
        "family_id": "single_distribution",
        "dimensions": [{"field_key": "region_zone"}],
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(_plan_json(query=invalid_query), first_decision),
            _result(_plan_json(query=valid_query), second_decision),
        ],
    )

    planning = _run_planner()
    plan, decisions = planning

    assert plan.queries[0].dimensions[0].field_key == "region_zone"
    assert decisions == [first_decision, second_decision]
    assert execute.call_count == 2
    repair = json.loads(execute.call_args_list[1].kwargs["messages"][-1]["content"])
    assert repair["repair_required"] is True
    assert "unknown_field" in repair["validation_error"]
    repair_request = json.loads(execute.call_args_list[1].kwargs["messages"][1]["content"])
    assert len(repair_request["analysis_catalog"]["family_details"]) == 16
    assert planning.diagnostics.prompt_chars < 45_000


def test_analysis_planner_normalizes_split_between_operands(monkeypatch) -> None:
    decision = cast(AiGatewayDecision, object())
    query = {
        "query_id": "period_count",
        "family_id": "filtered_count",
        "filters": {
            "conditions": [
                {
                    "field_key": "occurrence_date",
                    "operator": "between",
                    "values": ["2023-01-01"],
                    "value": "2026-12-31",
                }
            ]
        },
    }
    execute = _mock_execute(
        monkeypatch,
        [_result(_plan_json(query=query), decision)],
    )

    planning = _run_planner(
        question="2023년부터 2026년까지 전체 건수",
        fields=(
            DatasetFieldDefinition(
                key="occurrence_date",
                label_ko="발생일",
                label_en="Occurrence date",
                field_type="date",
            ),
        ),
        routing_mode=AnalysisMode.ANALYTICS,
        family_categories=("time", "scalar"),
    )

    condition = planning.plan.queries[0].filters.conditions[0]
    assert condition.operator == FilterOperator.BETWEEN
    assert condition.values == ("2023-01-01", "2026-12-31")
    assert condition.value is None
    assert planning.diagnostics.status == "valid"
    execute.assert_called_once()


def test_analysis_planner_moves_sequence_value_container_to_values(monkeypatch) -> None:
    query = {
        "query_id": "period_count",
        "family_id": "filtered_count",
        "filters": {
            "conditions": [
                {
                    "field_key": "occurrence_date",
                    "operator": "between",
                    "value": ["2023-01-01", "2026-12-31"],
                }
            ]
        },
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=query),
                cast(AiGatewayDecision, object()),
            )
        ],
    )

    planning = _run_planner(
        question="2023년부터 2026년까지 전체 건수",
        fields=(
            DatasetFieldDefinition(
                key="occurrence_date",
                label_ko="발생일",
                label_en="Occurrence date",
                field_type="date",
            ),
        ),
        routing_mode=AnalysisMode.ANALYTICS,
    )

    condition = planning.plan.queries[0].filters.conditions[0]
    assert condition.values == ("2023-01-01", "2026-12-31")
    assert condition.value is None
    assert planning.diagnostics.status == "valid"
    execute.assert_called_once()


def test_analysis_planner_rejects_uncontracted_sql_before_repair(monkeypatch) -> None:
    first_decision = cast(AiGatewayDecision, object())
    second_decision = cast(AiGatewayDecision, object())
    invalid_query = {
        **_total_count_query(),
        "sql": "SELECT 1",
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(_plan_json(query=invalid_query), first_decision),
            _result(_plan_json(query=_total_count_query()), second_decision),
        ],
    )

    planning = _run_planner()
    plan, decisions = planning

    assert plan.queries[0].family_ref == "total_count@1"
    assert decisions == [first_decision, second_decision]
    repair = json.loads(execute.call_args_list[1].kwargs["messages"][-1]["content"])
    assert "sql" in repair["validation_error"]
    assert "extra" in repair["validation_error"]


def test_analysis_planner_normalizes_common_json_drift(monkeypatch) -> None:
    query = {
        "query_id": "q1",
        "family_id": "conditional_rate",
        "metrics": [
            {
                "operator": "conditional_rate",
                "alias": "applied_rate",
                "condition": {
                    "conditions": [
                        {
                            "field_key": "applied",
                            "operator": "eq",
                            "value": "O",
                        }
                    ]
                },
            }
        ],
        "dimensions": [{"field_key": "region_zone"}],
        "comparisons": None,
        "windows": None,
        "detail_fields": None,
        "sort": [{"key": "metric:applied_rate", "direction": "desc"}],
        "limit": None,
    }
    execute = _mock_execute(
        monkeypatch,
        [_result(_plan_json(query=query), cast(AiGatewayDecision, object()))],
    )
    fields = (
        DatasetFieldDefinition(
            key="region_zone",
            label_ko="권역",
            label_en="Region",
            field_type="select",
        ),
        DatasetFieldDefinition(
            key="applied",
            label_ko="적용 여부",
            label_en="Applied",
            field_type="select",
        ),
    )

    planning = _run_planner(fields=fields)

    planned = planning.plan.queries[0]
    assert execute.call_count == 1
    assert planning.diagnostics.status == "valid"
    assert planned.metrics[0].field_key is None
    assert planned.comparisons == ()
    assert planned.windows == ()
    assert planned.detail_fields == ()
    assert planned.sort[0].key == "applied_rate"
    assert planned.limit == 10


def test_analysis_planner_normalizes_redundant_filter_operands(
    monkeypatch,
) -> None:
    query = {
        "query_id": "period",
        "family_id": "single_distribution",
        "metrics": [{"operator": "issue_count", "alias": "count"}],
        "dimensions": [{"field_key": "region_zone"}],
        "filters": {
            "conditions": [
                {
                    "field_key": "occurrence_date",
                    "operator": "between",
                    "value": "2025-01-01",
                    "values": ["2025-01-01", "2025-12-31"],
                }
            ]
        },
    }
    execute = _mock_execute(
        monkeypatch,
        [_result(_plan_json(query=query), cast(AiGatewayDecision, object()))],
    )
    fields = (
        DatasetFieldDefinition(
            key="region_zone",
            label_ko="권역",
            label_en="Region",
            field_type="select",
        ),
        DatasetFieldDefinition(
            key="occurrence_date",
            label_ko="발생일",
            label_en="Occurrence date",
            field_type="date",
        ),
    )

    planning = _run_planner(fields=fields)

    planned = planning.plan.queries[0]
    assert execute.call_count == 1
    assert planned.family_id == QueryFamilyId.SINGLE_DISTRIBUTION
    assert planned.filters is not None
    assert planned.filters.conditions[0].value is None
    assert planned.filters.conditions[0].values == (
        "2025-01-01",
        "2025-12-31",
    )


def test_analysis_planner_normalizes_one_dimension_breakdown_family(
    monkeypatch,
) -> None:
    query = {
        "query_id": "region-breakdown",
        "family_id": "multidim_breakdown",
        "metrics": [{"operator": "issue_count", "alias": "count"}],
        "dimensions": [{"field_key": "region_zone"}],
    }
    execute = _mock_execute(
        monkeypatch,
        [_result(_plan_json(query=query), cast(AiGatewayDecision, object()))],
    )

    planning = _run_planner()

    assert execute.call_count == 1
    assert planning.diagnostics.status == "valid"
    assert planning.plan.queries[0].family_id == QueryFamilyId.SINGLE_DISTRIBUTION
    assert planning.plan.queries[0].dimensions[0].field_key == "region_zone"


def test_analysis_planner_normalizes_histogram_sort_alias(monkeypatch) -> None:
    query = {
        "query_id": "histogram",
        "family_id": "histogram",
        "metrics": [{"operator": "issue_count", "alias": "count"}],
        "dimensions": [
            {
                "field_key": "introduced_revision_no",
                "alias": "revision_bucket",
                "numeric_bucket_size": 5,
            }
        ],
        "sort": [{"key": "dimension:revision_bucket", "direction": "asc"}],
    }
    execute = _mock_execute(
        monkeypatch,
        [_result(_plan_json(query=query), cast(AiGatewayDecision, object()))],
    )

    planning = _run_planner(
        fields=(
            DatasetFieldDefinition(
                key="introduced_revision_no",
                label_ko="반영 리비전",
                label_en="Introduced revision",
                field_type="number",
            ),
        ),
    )

    assert execute.call_count == 1
    assert planning.plan.queries[0].family_id == QueryFamilyId.HISTOGRAM
    assert planning.plan.queries[0].sort[0].key == "revision_bucket"


def test_analysis_planner_removes_redundant_semantic_hybrid_node(
    monkeypatch,
) -> None:
    payload = json.dumps(
        {
            "schema_version": 1,
            "mode": "hybrid",
            "queries": [
                _total_count_query(),
                {
                    "query_id": "representatives",
                    "family_id": "representative_records",
                    "metrics": [],
                    "detail_fields": ["region_zone"],
                },
            ],
            "clarification": None,
        }
    )
    execute = _mock_execute(
        monkeypatch,
        [_result(payload, cast(AiGatewayDecision, object()))],
    )

    planning = _run_planner(
        routing_mode=AnalysisMode.HYBRID,
        family_categories=("scalar", "semantic", "hybrid"),
    )

    assert execute.call_count == 1
    assert planning.plan.mode == AnalysisMode.HYBRID
    assert [query.family_id for query in planning.plan.queries] == [
        QueryFamilyId.TOTAL_COUNT
    ]


def test_analysis_planner_repairs_zero_dimension_distribution(
    monkeypatch,
) -> None:
    query = {
        "query_id": "checklist-total",
        "family_id": "single_distribution",
        "metrics": [{"operator": "issue_count", "alias": "count"}],
        "dimensions": [],
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(_plan_json(query=query), cast(AiGatewayDecision, object())),
            _result(
                _plan_json(query=_total_count_query()),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner(
        routing_mode=AnalysisMode.ANALYTICS,
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
        counting_unit=AnalysisCountingUnit.CHECKLIST_ITEMS,
    )

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.plan.queries[0].family_id == QueryFamilyId.TOTAL_COUNT


def test_analysis_planner_repairs_instead_of_dropping_invalid_filter(
    monkeypatch,
) -> None:
    invalid_query = {
        "query_id": "filtered",
        "family_id": "filtered_count",
        "filters": ["invalid-group"],
    }
    repaired_query = {
        "query_id": "filtered",
        "family_id": "filtered_count",
        "filters": {
            "conditions": [
                {
                    "field_key": "region_zone",
                    "operator": "eq",
                    "value": "국내",
                }
            ]
        },
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=invalid_query),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=repaired_query),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner()

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.plan.queries[0].family_id == QueryFamilyId.FILTERED_COUNT
    assert planning.plan.queries[0].filters is not None


def test_analysis_planner_repairs_missing_adjacent_code_constraint(
    monkeypatch,
) -> None:
    unscoped_query = _total_count_query()
    scoped_query = {
        "query_id": "filtered",
        "family_id": "filtered_count",
        "filters": {
            "conditions": [
                {
                    "field_key": "vehicle_model",
                    "operator": "eq",
                    "value": "CV",
                }
            ]
        },
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=unscoped_query),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=scoped_query),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner(
        question="CV 차종 문제는 총 몇 건이야?",
        fields=(
            DatasetFieldDefinition(
                key="vehicle_model",
                label_ko="차종",
                label_en="Vehicle Model",
            ),
        ),
    )

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.diagnostics.validation_error_code == (
        "question_constraint_unrepresented"
    )
    assert planning.plan.queries[0].filters is not None
    repair = json.loads(execute.call_args_list[1].kwargs["messages"][-1]["content"])
    assert "vehicle_model='CV'" in repair["validation_error"]


def test_analysis_planner_fails_closed_when_code_constraint_stays_missing(
    monkeypatch,
) -> None:
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=_total_count_query()),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=_total_count_query()),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner(
        question="CV 차종 문제 건수",
        routing_mode=AnalysisMode.HYBRID,
        fields=(
            DatasetFieldDefinition(
                key="vehicle_model",
                label_ko="차종",
                label_en="Vehicle Model",
            ),
        ),
    )

    assert execute.call_count == 2
    assert planning.diagnostics.status == "fallback"
    assert planning.diagnostics.validation_error_code == (
        "question_constraint_unrepresented"
    )
    assert planning.plan.mode == AnalysisMode.GENERATED
    assert planning.plan.delegated_family_id == QueryFamilyId.GENERATED_SQL_FALLBACK


def test_adjacent_code_grounding_avoids_ranking_and_english_overmatch() -> None:
    fields = (
        DatasetFieldDefinition(
            key="vehicle_model",
            label_ko="차종",
            label_en="Vehicle Model",
        ),
    )

    assert analysis_planner._grounded_code_constraints(
        "TOP 10 차종",
        fields=fields,
    ) == ()
    assert analysis_planner._grounded_code_constraints(
        "상위 10 차종",
        fields=fields,
    ) == ()
    assert analysis_planner._grounded_code_constraints(
        "차종별 전체 건수",
        fields=fields,
    ) == ()
    assert analysis_planner._grounded_code_constraints(
        "Show Vehicle Model CV counts",
        fields=fields,
    ) == (("vehicle_model", ("CV",)),)
    assert analysis_planner._grounded_code_constraints(
        "Count KA4 PE Vehicle Model issues",
        fields=fields,
    ) == (("vehicle_model", ("KA4 PE",)),)


def test_grounded_code_validation_rejects_broad_or_partial_query_scope() -> None:
    broad_filter = FilterGroupV1(
        junction=FilterJunction.ANY,
        conditions=(
            FilterConditionV1(
                field_key="vehicle_model",
                operator=FilterOperator.EQ,
                value="CV",
            ),
            FilterConditionV1(
                field_key="region_zone",
                operator=FilterOperator.EQ,
                value="유럽",
            ),
        ),
    )
    broad_plan = AnalysisPlanV1(
        mode=AnalysisMode.ANALYTICS,
        queries=(
            QueryRequestV1(
                query_id="broad",
                family_id=QueryFamilyId.FILTERED_COUNT,
                filters=broad_filter,
            ),
        ),
    )
    partial_plan = AnalysisPlanV1(
        mode=AnalysisMode.ANALYTICS,
        queries=(
            QueryRequestV1(
                query_id="cv-total",
                family_id=QueryFamilyId.FILTERED_COUNT,
                filters=FilterGroupV1(
                    conditions=(
                        FilterConditionV1(
                            field_key="vehicle_model",
                            operator=FilterOperator.EQ,
                            value="CV",
                        ),
                    ),
                ),
            ),
            QueryRequestV1(
                query_id="unscoped-breakdown",
                family_id=QueryFamilyId.SINGLE_DISTRIBUTION,
                dimensions=(
                    DimensionSpecV1(field_key="region_zone"),
                ),
            ),
        ),
    )

    assert not analysis_planner._plan_represents_code_constraint(
        broad_plan,
        field_key="vehicle_model",
        values=("CV",),
    )
    assert not analysis_planner._plan_represents_code_constraint(
        partial_plan,
        field_key="vehicle_model",
        values=("CV",),
    )


def test_analysis_planner_repairs_instead_of_dropping_metric_condition(
    monkeypatch,
) -> None:
    invalid_query = {
        **_total_count_query(),
        "metrics": [
            {
                "operator": "issue_count",
                "alias": "count",
                "condition": {
                    "conditions": [
                        {
                            "field_key": "region_zone",
                            "operator": "eq",
                            "value": "국내",
                        }
                    ]
                },
            }
        ],
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=invalid_query),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=_total_count_query()),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner()

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"


def test_analysis_planner_repairs_instead_of_dropping_nested_filter_group(
    monkeypatch,
) -> None:
    valid_condition = {
        "field_key": "region_zone",
        "operator": "eq",
        "value": "국내",
    }
    invalid_query = {
        "query_id": "filtered",
        "family_id": "filtered_count",
        "filters": {
            "conditions": [valid_condition],
            "groups": ["invalid-child"],
        },
    }
    repaired_query = {
        **invalid_query,
        "filters": {"conditions": [valid_condition]},
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=invalid_query),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=repaired_query),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner()

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.plan.queries[0].filters is not None


def test_analysis_planner_repairs_without_dropping_filtered_grouping(
    monkeypatch,
) -> None:
    filter_group = {
        "conditions": [
            {
                "field_key": "region_zone",
                "operator": "in",
                "values": ["국내", "해외"],
            }
        ]
    }
    invalid_query = {
        "query_id": "regions",
        "family_id": "filtered_count",
        "dimensions": [{"field_key": "region_zone"}],
        "filters": filter_group,
    }
    repaired_query = {
        **invalid_query,
        "family_id": "single_distribution",
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=invalid_query),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=repaired_query),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner()

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.plan.queries[0].dimensions[0].field_key == "region_zone"
    assert planning.plan.queries[0].filters is not None


def test_analysis_planner_repairs_mixed_exact_and_generated_nodes(
    monkeypatch,
) -> None:
    mixed_payload = json.dumps(
        {
            "schema_version": 1,
            "mode": "hybrid",
            "queries": [
                _total_count_query(),
                {
                    "query_id": "duration",
                    "family_id": "duration_summary",
                },
            ],
            "clarification": None,
        }
    )
    generated_query = {
        "query_id": "generated",
        "family_id": "generated_sql_fallback",
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(mixed_payload, cast(AiGatewayDecision, object())),
            _result(
                _plan_json(query=generated_query, mode="generated"),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner(routing_mode=AnalysisMode.HYBRID)

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.plan.mode == AnalysisMode.GENERATED
    assert (
        planning.plan.delegated_family_id
        == QueryFamilyId.GENERATED_SQL_FALLBACK
    )


def test_analysis_payload_normalizer_does_not_truncate_quality_metrics() -> None:
    metrics = [
        {
            "operator": "present_count",
            "field_key": f"field_{index}",
            "alias": f"present_{index}",
        }
        for index in range(7)
    ]
    payload = {
        "schema_version": 1,
        "mode": "metadata",
        "queries": [
            {
                "query_id": "coverage",
                "family_id": "field_coverage_cardinality",
                "metrics": metrics,
            }
        ],
    }

    normalized = analysis_planner._normalize_plan_payload(payload)

    assert len(normalized["queries"]) == 1
    assert normalized["queries"][0]["metrics"] == metrics


def test_analysis_payload_normalizer_preserves_unsupported_window_and_sort() -> None:
    window = {
        "operator": "rank",
        "metric_alias": "metric:count",
        "alias": "rank",
        "order_by": ["metric:count"],
    }
    sort = {"key": "metric:missing_alias", "direction": "asc"}
    payload = {
        "schema_version": 1,
        "mode": "analytics",
        "queries": [
            {
                **_total_count_query(),
                "metrics": [{"operator": "issue_count", "alias": "count"}],
                "windows": [window],
                "sort": [sort],
            }
        ],
    }

    normalized = analysis_planner._normalize_plan_payload(payload)
    normalized_query = normalized["queries"][0]

    assert len(normalized_query["windows"]) == 1
    assert normalized_query["windows"][0]["operator"] == "rank"
    assert normalized_query["sort"] == [
        {"key": "missing_alias", "direction": "asc"}
    ]


def test_analysis_payload_normalizer_does_not_override_contradictory_mode() -> None:
    payload = {
        "schema_version": 1,
        "mode": "clarify",
        "clarification": "비교 기간을 알려주세요.",
        "queries": [
            {
                "query_id": "generated",
                "family_id": "generated_sql_fallback",
            }
        ],
    }

    normalized = analysis_planner._normalize_plan_payload(payload)

    assert normalized["mode"] == "clarify"
    assert normalized["queries"][0]["family_id"] == "generated_sql_fallback"
    assert "delegated_family_id" not in normalized


def test_analysis_planner_repairs_non_clarify_plan_with_clarification(
    monkeypatch,
) -> None:
    invalid_payload = json.dumps(
        {
            "schema_version": 1,
            "mode": "analytics",
            "queries": [_total_count_query()],
            "clarification": "기간을 알려주세요.",
        }
    )
    execute = _mock_execute(
        monkeypatch,
        [
            _result(invalid_payload, cast(AiGatewayDecision, object())),
            _result(
                _plan_json(query=_total_count_query()),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner()

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.plan.clarification is None


def test_analysis_planner_enforces_generic_record_set_routing_hint(monkeypatch) -> None:
    decision = cast(AiGatewayDecision, object())
    repaired_decision = cast(AiGatewayDecision, object())
    base_query = {
        "query_id": "q1",
        "family_id": "single_distribution",
        "dimensions": [{"field_key": "region_zone"}],
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(_plan_json(query=base_query), decision),
            _result(
                _plan_json(
                    query={
                        **base_query,
                        "record_set": {
                            "kind": "cohort_reentry",
                            "key_fields": ["region_zone"],
                            "seed_filters": {
                                "conditions": [
                                    {
                                        "field_key": "region_zone",
                                        "operator": "eq",
                                        "value": "국내",
                                    }
                                ]
                            },
                        },
                    }
                ),
                repaired_decision,
            ),
        ],
    )

    planning = _run_planner(record_set_required=True)

    assert planning.plan.queries[0].record_set is not None
    assert planning.diagnostics.status == "repaired"
    repair = json.loads(execute.call_args_list[1].kwargs["messages"][-1]["content"])
    assert "routing hint suggests" in repair["validation_error"]


def test_record_set_routing_hint_can_be_overridden_by_repaired_plan(
    monkeypatch,
) -> None:
    query = {
        "query_id": "q1",
        "family_id": "single_distribution",
        "dimensions": [{"field_key": "region_zone"}],
    }
    _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=query),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=query),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner(record_set_required=True)

    assert planning.plan.mode == AnalysisMode.ANALYTICS
    assert planning.plan.queries[0].record_set is None
    assert planning.diagnostics.status == "repaired"
    assert planning.diagnostics.validation_error_code == "catalog_validation_failed"


def test_analysis_planner_falls_back_to_semantic_after_one_failed_repair(
    monkeypatch,
) -> None:
    first_decision = cast(AiGatewayDecision, object())
    second_decision = cast(AiGatewayDecision, object())
    execute = _mock_execute(
        monkeypatch,
        [
            _result('{"schema_version":1,"mode":"analytics","queries":[]}', first_decision),
            _result("not-json", second_decision),
        ],
    )

    planning = _run_planner()
    plan, decisions = planning

    assert plan.mode == AnalysisMode.SEMANTIC
    assert plan.queries == ()
    assert decisions == [first_decision, second_decision]
    assert execute.call_count == 2
    assert planning.diagnostics.status == "fallback"
    assert planning.diagnostics.fallback_reason == "attempts_exhausted"
    assert planning.diagnostics.validation_error_code == "response_json_invalid"
    assert planning.diagnostics.plan_fingerprint is not None
    assert "not-json" not in planning.diagnostics.model_dump_json()


def test_analysis_planner_structured_failure_uses_guarded_generated_sql(
    monkeypatch,
) -> None:
    execute = _mock_execute(
        monkeypatch,
        [
            _result("not-json", cast(AiGatewayDecision, object())),
            _result("still-not-json", cast(AiGatewayDecision, object())),
        ],
    )

    planning = _run_planner(
        routing_mode=AnalysisMode.ANALYTICS,
        family_categories=("scalar",),
    )

    assert planning.plan.mode == AnalysisMode.GENERATED
    assert planning.plan.delegated_family_id == QueryFamilyId.GENERATED_SQL_FALLBACK
    assert planning.plan.delegated_data_source == AnalysisDataSource.LEGACY_ISSUES
    assert planning.diagnostics.status == "fallback"
    assert execute.call_count == 2


def test_analysis_planner_salvages_valid_queries_after_repair_exhausted(
    monkeypatch,
) -> None:
    valid_query = {
        "query_id": "period_count",
        "family_id": "filtered_count",
        "filters": {
            "conditions": [
                {
                    "field_key": "occurrence_date",
                    "operator": "between",
                    "values": ["2023-01-01", "2026-12-31"],
                }
            ]
        },
    }
    invalid_query = {
        "query_id": "quality",
        "family_id": "missing_populated_rate",
        "metrics": [
            {
                "operator": "present_count",
                "alias": "present_count",
            },
            {
                "operator": "missing_count",
                "alias": "missing_count",
            },
        ],
    }
    invalid_plan = json.dumps(
        {
            "schema_version": 1,
            "mode": "analytics",
            "queries": [valid_query, invalid_query],
            "clarification": None,
        }
    )
    execute = _mock_execute(
        monkeypatch,
        [
            _result(invalid_plan, cast(AiGatewayDecision, object())),
            _result(invalid_plan, cast(AiGatewayDecision, object())),
        ],
    )

    planning = _run_planner(
        question="2023년부터 2026년까지 전체 건수와 입력 품질",
        fields=(
            DatasetFieldDefinition(
                key="occurrence_date",
                label_ko="발생일",
                label_en="Occurrence date",
                field_type="date",
            ),
        ),
        routing_mode=AnalysisMode.ANALYTICS,
        family_categories=("time", "quality"),
    )

    assert planning.plan.mode == AnalysisMode.ANALYTICS
    assert [query.query_id for query in planning.plan.queries] == ["period_count"]
    assert planning.diagnostics.status == "fallback"
    assert planning.diagnostics.fallback_reason == "partial_plan_salvaged"
    assert planning.diagnostics.validation_error_code == "plan_schema_invalid"
    assert execute.call_count == 2


def test_analysis_planner_report_failure_uses_standard_catalog_bundle(
    monkeypatch,
) -> None:
    execute = _mock_execute(
        monkeypatch,
        [
            _result("not-json", cast(AiGatewayDecision, object())),
            _result("still-not-json", cast(AiGatewayDecision, object())),
        ],
    )

    planning = _run_planner(
        question="경영진 검토용 전체 현황 보고서를 작성해줘",
        fields=COMMON_MASTER_FIELDS,
        routing_mode=AnalysisMode.HYBRID,
        family_categories=("composite", "scalar", "distribution", "time"),
        report_requested=True,
        data_sources=(AnalysisDataSource.LEGACY_ISSUES,),
    )

    assert planning.plan.mode == AnalysisMode.HYBRID
    assert [query.family_id for query in planning.plan.queries] == [
        QueryFamilyId.TOTAL_COUNT,
        QueryFamilyId.SEVERITY,
        QueryFamilyId.TOP_BOTTOM_N,
        QueryFamilyId.TIME_SERIES,
        QueryFamilyId.MISSING_POPULATED_RATE,
        QueryFamilyId.MISSING_POPULATED_RATE,
    ]
    assert planning.plan.queries[2].limit == 10
    assert "limit" in planning.plan.queries[2].model_fields_set
    assert "limit" not in planning.plan.queries[3].model_fields_set
    assert planning.plan.delegated_family_id is None
    assert planning.diagnostics.status == "fallback"
    assert execute.call_count == 2


def test_analysis_planner_multi_source_report_failure_uses_primary_guarded_sql(
    monkeypatch,
) -> None:
    execute = _mock_execute(
        monkeypatch,
        [
            _result("not-json", cast(AiGatewayDecision, object())),
            _result("still-not-json", cast(AiGatewayDecision, object())),
        ],
    )

    planning = _run_planner(
        question="과거차 문제와 체크리스트를 비교한 보고서를 작성해줘",
        fields=COMMON_MASTER_FIELDS,
        routing_mode=AnalysisMode.HYBRID,
        family_categories=("composite", "comparison"),
        report_requested=True,
        data_sources=(
            AnalysisDataSource.LEGACY_ISSUES,
            AnalysisDataSource.VEHICLE_CHECKLISTS,
        ),
    )

    assert planning.plan.mode == AnalysisMode.GENERATED
    assert planning.plan.delegated_family_id == QueryFamilyId.GENERATED_SQL_FALLBACK
    assert planning.plan.delegated_data_source == AnalysisDataSource.LEGACY_ISSUES
    assert planning.diagnostics.status == "fallback"
    assert execute.call_count == 2


def test_metadata_planner_failure_does_not_delegate_to_row_sql(
    monkeypatch,
) -> None:
    execute = _mock_execute(
        monkeypatch,
        [
            _result("not-json", cast(AiGatewayDecision, object())),
            _result("still-not-json", cast(AiGatewayDecision, object())),
        ],
    )

    planning = _run_planner(
        routing_mode=AnalysisMode.METADATA,
        family_categories=("metadata",),
    )

    assert planning.plan.mode == AnalysisMode.SEMANTIC
    assert planning.plan.delegated_family_id == QueryFamilyId.SEMANTIC_SIMILAR
    assert planning.diagnostics.status == "fallback"
    assert execute.call_count == 2


def test_analysis_planner_does_not_retransmit_provider_error_details(
    monkeypatch,
) -> None:
    secret_error = "provider https://private.example/token/secret failed"
    execute = _mock_execute(
        monkeypatch,
        [
            RuntimeError(secret_error),
            _result(
                _plan_json(query=_total_count_query()),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )

    planning = _run_planner()

    assert planning.plan.mode == AnalysisMode.ANALYTICS
    repair = execute.call_args_list[1].kwargs["messages"][-1]["content"]
    assert "llm_execution_failed" in repair
    assert secret_error not in repair


def test_analysis_planner_falls_back_without_calling_llm_for_oversized_question(
    monkeypatch,
) -> None:
    execute = _mock_execute(monkeypatch, [])

    planning = _run_planner(question="x" * 12_001)
    plan, decisions = planning

    assert plan.mode == AnalysisMode.SEMANTIC
    assert plan.queries == ()
    assert decisions == []
    assert planning.diagnostics.fallback_reason == "input_invalid"
    execute.assert_not_called()


def test_oversized_checklist_question_never_falls_back_to_legacy_semantic(
    monkeypatch,
) -> None:
    execute = _mock_execute(monkeypatch, [])

    planning = _run_planner(
        question="x" * 12_001,
        routing_mode=AnalysisMode.SEMANTIC,
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
    )

    assert planning.plan.mode == AnalysisMode.CLARIFY
    assert planning.plan.delegated_data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
    assert planning.plan.delegated_family_id is None
    execute.assert_not_called()


def test_semantic_cohort_hint_is_promoted_to_hybrid_planning(monkeypatch) -> None:
    query = {
        "query_id": "q1",
        "family_id": "detail_list",
        "detail_fields": ["region_zone"],
        "record_set": {
            "kind": "cohort_reentry",
            "key_fields": ["region_zone"],
            "seed_filters": {
                "conditions": [
                    {
                        "field_key": "region_zone",
                        "operator": "eq",
                        "value": "국내",
                    }
                ]
            },
        },
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mode": "hybrid",
                        "queries": [query],
                        "clarification": None,
                    }
                ),
                cast(AiGatewayDecision, object()),
            )
        ],
    )

    planning = _run_planner(
        routing_mode=AnalysisMode.SEMANTIC,
        family_categories=("semantic", "detail"),
        record_set_required=True,
    )

    request = json.loads(execute.call_args.kwargs["messages"][1]["content"])
    assert request["routing_hint"]["mode"] == "hybrid"
    assert planning.plan.mode == AnalysisMode.HYBRID
    assert planning.plan.queries[0].record_set is not None


def test_analysis_planner_semantic_routing_hint_uses_fast_path(monkeypatch) -> None:
    execute = _mock_execute(monkeypatch, [])

    planning = _run_planner(
        question="유사한 과거 사례와 원인을 보여줘",
        routing_mode=AnalysisMode.SEMANTIC,
        family_categories=("semantic",),
    )
    plan, decisions = planning

    assert plan.mode == AnalysisMode.SEMANTIC
    assert plan.delegated_family_id == QueryFamilyId.SEMANTIC_SIMILAR
    assert decisions == []
    assert planning.diagnostics.status == "fast_path"
    assert planning.diagnostics.attempt_count == 0
    execute.assert_not_called()


def test_checklist_source_disables_semantic_fast_path_and_plans_typed_query(
    monkeypatch,
) -> None:
    checklist_query = {
        **_total_count_query(),
        "data_source": "vehicle_checklists",
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=checklist_query),
                cast(AiGatewayDecision, object()),
            )
        ],
    )

    planning = _run_planner(
        question="차량 체크리스트 항목 건수",
        routing_mode=AnalysisMode.SEMANTIC,
        family_categories=("semantic",),
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
    )

    request = json.loads(execute.call_args.kwargs["messages"][1]["content"])
    assert request["routing_hint"]["mode"] == "analytics"
    assert request["routing_hint"]["data_sources"] == ["vehicle_checklists"]
    assert planning.plan.mode == AnalysisMode.ANALYTICS
    assert planning.plan.queries[0].data_source == AnalysisDataSource.VEHICLE_CHECKLISTS


def test_single_grounded_source_is_server_bound_when_model_omits_data_source(
    monkeypatch,
) -> None:
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=_total_count_query()),
                cast(AiGatewayDecision, object()),
            )
        ],
    )

    planning = _run_planner(
        question="차량 체크리스트 전체 항목 건수",
        routing_mode=AnalysisMode.ANALYTICS,
        family_categories=("scalar",),
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
    )

    assert execute.call_count == 1
    assert planning.diagnostics.status == "valid"
    assert planning.plan.queries[0].data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
    assert planning.plan.delegated_data_source == AnalysisDataSource.VEHICLE_CHECKLISTS


def test_checklist_item_counting_unit_repairs_document_count_metric(
    monkeypatch,
) -> None:
    wrong_query = {
        "query_id": "q1",
        "family_id": "single_distribution",
        "metrics": [
            {
                "operator": "distinct_count",
                "field_key": "checklist_id",
                "alias": "count",
            }
        ],
        "dimensions": [{"field_key": "region_zone"}],
    }
    repaired_query = {
        "query_id": "q1",
        "family_id": "single_distribution",
        "metrics": [{"operator": "issue_count", "alias": "count"}],
        "dimensions": [{"field_key": "region_zone"}],
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=wrong_query),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=repaired_query),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )
    fields = (
        DatasetFieldDefinition(
            key="region_zone",
            label_ko="권역",
            label_en="Region",
            field_type="select",
        ),
        DatasetFieldDefinition(
            key="checklist_id",
            label_ko="체크리스트 ID",
            label_en="Checklist ID",
            field_type="text",
        ),
    )

    planning = _run_planner(
        question="차량 체크리스트 항목을 권역별로 집계",
        fields=fields,
        routing_mode=AnalysisMode.ANALYTICS,
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
        counting_unit=AnalysisCountingUnit.CHECKLIST_ITEMS,
    )

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.plan.queries[0].metrics[0].operator.value == "issue_count"
    repair = json.loads(execute.call_args_list[1].kwargs["messages"][-1]["content"])
    assert "checklist_items counting_unit" in repair["validation_error"]


def test_checklist_document_counting_unit_rejects_distinct_vehicle_metric(
    monkeypatch,
) -> None:
    wrong_query = {
        "query_id": "q1",
        "family_id": "single_distribution",
        "metrics": [
            {
                "operator": "distinct_count",
                "field_key": "checklist_vehicle_code",
                "alias": "count",
            }
        ],
        "dimensions": [{"field_key": "region_zone"}],
    }
    repaired_query = {
        "query_id": "q1",
        "family_id": "single_distribution",
        "metrics": [
            {
                "operator": "distinct_count",
                "field_key": "checklist_id",
                "alias": "count",
            }
        ],
        "dimensions": [{"field_key": "region_zone"}],
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=wrong_query),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=repaired_query),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )
    fields = (
        DatasetFieldDefinition(
            key="region_zone",
            label_ko="권역",
            label_en="Region",
            field_type="select",
        ),
        DatasetFieldDefinition(
            key="checklist_id",
            label_ko="체크리스트 ID",
            label_en="Checklist ID",
            field_type="text",
        ),
        DatasetFieldDefinition(
            key="checklist_vehicle_code",
            label_ko="차종 코드",
            label_en="Vehicle Code",
            field_type="text",
        ),
    )

    planning = _run_planner(
        question="권역별 체크리스트 문서 수",
        fields=fields,
        routing_mode=AnalysisMode.ANALYTICS,
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
        counting_unit=AnalysisCountingUnit.CHECKLISTS,
    )

    assert execute.call_count == 2
    assert planning.plan.queries[0].metrics[0].field_key == "checklist_id"
    repair = json.loads(execute.call_args_list[1].kwargs["messages"][-1]["content"])
    assert "distinct_count(checklist_id)" in repair["validation_error"]


def test_checklist_document_counting_unit_rejects_item_weighted_rate(
    monkeypatch,
) -> None:
    wrong_query = {
        "query_id": "q1",
        "family_id": "conditional_rate",
        "metrics": [
            {
                "operator": "conditional_rate",
                "alias": "rate",
                "condition": {
                    "junction": "all",
                    "conditions": [
                        {
                            "field_key": "checklist_status",
                            "operator": "eq",
                            "value": "completed",
                        }
                    ],
                },
            }
        ],
        "dimensions": [{"field_key": "checklist_status"}],
    }
    repaired_query = {
        "query_id": "q1",
        "family_id": "single_distribution",
        "metrics": [
            {
                "operator": "distinct_count",
                "field_key": "checklist_id",
                "alias": "count",
            }
        ],
        "dimensions": [{"field_key": "checklist_status"}],
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=wrong_query),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=repaired_query),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )
    fields = (
        DatasetFieldDefinition(
            key="checklist_id",
            label_ko="체크리스트 ID",
            label_en="Checklist ID",
            field_type="text",
        ),
        DatasetFieldDefinition(
            key="checklist_status",
            label_ko="체크리스트 상태",
            label_en="Checklist Status",
            field_type="select",
        ),
    )

    planning = _run_planner(
        question="체크리스트 문서 완료 비율",
        fields=fields,
        routing_mode=AnalysisMode.ANALYTICS,
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
        counting_unit=AnalysisCountingUnit.CHECKLISTS,
    )

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.plan.queries[0].metrics[0].operator == MetricOperator.DISTINCT_COUNT
    repair = json.loads(execute.call_args_list[1].kwargs["messages"][-1]["content"])
    assert "distinct_count(checklist_id)" in repair["validation_error"]


def test_checklist_document_counting_unit_applies_to_hybrid_family(
    monkeypatch,
) -> None:
    wrong_query = {
        "query_id": "q1",
        "family_id": "exact_aggregate_plus_semantic",
        "metrics": [{"operator": "issue_count", "alias": "count"}],
    }
    repaired_query = {
        "query_id": "q1",
        "family_id": "exact_aggregate_plus_semantic",
        "metrics": [
            {
                "operator": "distinct_count",
                "field_key": "checklist_id",
                "alias": "count",
            }
        ],
    }
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=wrong_query, mode="hybrid"),
                cast(AiGatewayDecision, object()),
            ),
            _result(
                _plan_json(query=repaired_query, mode="hybrid"),
                cast(AiGatewayDecision, object()),
            ),
        ],
    )
    fields = (
        DatasetFieldDefinition(
            key="checklist_id",
            label_ko="체크리스트 ID",
            label_en="Checklist ID",
            field_type="text",
        ),
    )

    planning = _run_planner(
        question="체크리스트 문서 수와 근거",
        fields=fields,
        routing_mode=AnalysisMode.HYBRID,
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
        counting_unit=AnalysisCountingUnit.CHECKLISTS,
    )

    assert execute.call_count == 2
    assert planning.diagnostics.status == "repaired"
    assert planning.plan.queries[0].metrics[0].operator == MetricOperator.DISTINCT_COUNT
    repair = json.loads(execute.call_args_list[1].kwargs["messages"][-1]["content"])
    assert "distinct_count(checklist_id)" in repair["validation_error"]


def test_analysis_planner_clarify_routing_hint_is_revalidated(monkeypatch) -> None:
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                _plan_json(query=_total_count_query()),
                cast(AiGatewayDecision, object()),
            )
        ],
    )

    planning = _run_planner(
        question="2023년부터 2026년까지 연도별 건수를 비교해줘",
        routing_mode=AnalysisMode.CLARIFY,
        family_categories=("comparison",),
    )

    assert planning.plan.mode == AnalysisMode.ANALYTICS
    assert planning.plan.clarification is None
    assert planning.diagnostics.status == "valid"
    execute.assert_called_once()


def test_analysis_planner_accepts_clarification_after_revalidation(monkeypatch) -> None:
    execute = _mock_execute(
        monkeypatch,
        [
            _result(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mode": "clarify",
                        "queries": [],
                        "clarification": "비교할 두 기간을 알려주세요.",
                    }
                ),
                cast(AiGatewayDecision, object()),
            )
        ],
    )

    planning = _run_planner(
        question="두 기간을 비교해줘",
        routing_mode=AnalysisMode.CLARIFY,
        family_categories=("comparison",),
    )

    assert planning.plan.mode == AnalysisMode.CLARIFY
    assert planning.plan.clarification == "비교할 두 기간을 알려주세요."
    assert planning.diagnostics.status == "valid"
    execute.assert_called_once()


def test_family_ranking_is_generic_and_keeps_complete_catalog_discoverable() -> None:
    total_candidates = analysis_planner._rank_candidate_family_ids(
        question="전체 문제 건수를 알려줘",
        recent_messages=[],
        family_categories=("scalar",),
    )
    trend_candidates = analysis_planner._rank_candidate_family_ids(
        question="차종별 전년 대비 변화 추이",
        recent_messages=[],
        family_categories=("time", "distribution"),
    )

    assert len(total_candidates) == len(trend_candidates) == 8
    assert QueryFamilyId.TOTAL_COUNT in total_candidates
    assert QueryFamilyId.YOY_MOM in trend_candidates


def test_plan_shape_fingerprint_excludes_filter_values() -> None:
    def plan_for(value: str) -> AnalysisPlanV1:
        return AnalysisPlanV1(
            mode=AnalysisMode.ANALYTICS,
            queries=(
                QueryRequestV1(
                    query_id="filtered",
                    family_id=QueryFamilyId.FILTERED_COUNT,
                    filters=FilterGroupV1(
                        conditions=(
                            FilterConditionV1(
                                field_key="region_zone",
                                operator=FilterOperator.EQ,
                                value=value,
                            ),
                        ),
                    ),
                ),
            ),
        )

    first = analysis_planner._plan_shape_fingerprint(plan_for("서울"))
    second = analysis_planner._plan_shape_fingerprint(plan_for("유럽"))

    assert first == second
    assert "서울" not in first
    assert "유럽" not in second


def test_common_master_primary_prompt_stays_bounded(monkeypatch) -> None:
    decision = cast(AiGatewayDecision, object())
    execute = _mock_execute(
        monkeypatch,
        [_result(_plan_json(query=_total_count_query()), decision)],
    )

    planning = _run_planner(fields=COMMON_MASTER_FIELDS)

    assert planning.diagnostics.prompt_chars < 32_000
    request = json.loads(execute.call_args.kwargs["messages"][1]["content"])
    assert len(request["analysis_catalog"]["fields"]) == len(COMMON_MASTER_FIELDS)


def _run_planner(
    *,
    question: str = "권역별 전체 건수를 알려줘",
    fields: tuple[DatasetFieldDefinition, ...] | None = None,
    routing_mode: AnalysisMode | None = None,
    family_categories: tuple[str, ...] = (),
    record_set_required: bool = False,
    data_sources: tuple[AnalysisDataSource, ...] = (),
    counting_unit: AnalysisCountingUnit | None = None,
    report_requested: bool = False,
) -> Any:
    return plan_legacy_issue_analysis(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question=question,
        fields=fields
        or (
            DatasetFieldDefinition(
                key="region_zone",
                label_ko="권역",
                label_en="Region",
                field_type="select",
                options=("국내", "해외"),
            ),
        ),
        audit_entity_id="run-1",
        routing_mode=routing_mode,
        family_categories=family_categories,
        record_set_required=record_set_required,
        data_sources=data_sources,
        counting_unit=counting_unit,
        report_requested=report_requested,
    )


def _plan_json(*, query: dict[str, Any], mode: str = "analytics") -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "mode": mode,
            "queries": [query],
            "clarification": None,
        }
    )


def _total_count_query() -> dict[str, Any]:
    return {
        "query_id": "q1",
        "family_id": "total_count",
    }


def _result(text: str, decision: AiGatewayDecision) -> SimpleNamespace:
    return SimpleNamespace(
        completion=SimpleNamespace(text=text),
        decision=decision,
    )


def _mock_execute(monkeypatch, results: list[SimpleNamespace]):
    from unittest.mock import Mock

    execute = Mock(side_effect=results)
    monkeypatch.setattr(
        "ai_do_api.domains.legacy_issues.analysis_planner.execute_llm",
        execute,
    )
    return execute


def _collect_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested in value.values():
            keys.update(_collect_keys(nested))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for nested in value:
            keys.update(_collect_keys(nested))
        return keys
    return set()
