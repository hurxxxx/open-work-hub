from __future__ import annotations

import pytest

from open_alm_api.domains.legacy_issues.analysis_graph.contracts import (
    AnalysisInterpretation,
)
from open_alm_api.domains.legacy_issues.analysis_graph.data_provider import (
    _agent_result_to_bundle,
    _has_query_result,
    _requested_capability_limitations,
    _supplement_required_sources,
)
from open_alm_api.domains.legacy_issues.analysis_v2.agent import AnalysisAgentResult


class _EvidenceToolset:
    def __init__(self) -> None:
        self.queries: list[tuple[str, int]] = []

    def search_legacy_evidence(self, query: str, limit: int) -> dict:
        self.queries.append((query, limit))
        return {
            "query": query,
            "backend_id": "llamaindex-pgvector",
            "hits": [
                {
                    "hit_id": "hit-1",
                    "text": "저온 조건의 결빙 사례",
                    "score": 0.9,
                    "resource_type": "legacy_issue_record",
                    "resource_id": "issue-1",
                    "partition_id": "partition-1",
                    "metadata": {},
                }
            ],
        }


class _ChecklistToolset(_EvidenceToolset):
    def __init__(self) -> None:
        super().__init__()
        self.recipes: list[tuple[str, int, dict]] = []

    def run_recipe(
        self,
        recipe_id: str,
        version: int,
        parameters: dict,
    ) -> dict:
        self.recipes.append((recipe_id, version, parameters))
        rows = []
        if recipe_id == "issue_breakdown" and parameters.get("dimension") == "region_zone":
            rows = [
                {"dimension_value": "국내", "issue_count": 65},
                {"dimension_value": "테스트-국내", "issue_count": 36},
                {"dimension_value": "테스트-유럽", "issue_count": 32},
                {"dimension_value": "테스트-북미", "issue_count": 28},
                {"dimension_value": "테스트-중국", "issue_count": 24},
            ]
        return {
            "result": {
                "recipe": {"recipe_id": recipe_id, "version": version},
                "parameters": parameters,
                "status": "succeeded",
                "rows": rows,
            }
        }


class _FailingEvidenceToolset(_EvidenceToolset):
    def search_legacy_evidence(self, query: str, limit: int) -> dict:
        self.queries.append((query, limit))
        raise RuntimeError("backend unavailable")


def _successful_query_tool_result() -> dict:
    return {
        "result": {
            "query_id": "query-grounded-1",
            "source": "recipe",
            "recipe": {"recipe_id": "issue_total", "version": 1},
            "parameterized_sql": "SELECT COUNT(*) AS issue_count FROM scoped_records",
            "parameters": {},
            "recipe_arguments": {},
            "status": "succeeded",
            "error_code": None,
            "columns": [{"name": "issue_count", "value_type": "integer"}],
            "rows": [{"issue_count": 5}],
            "row_count": 1,
            "truncated": False,
            "payload_bytes": 32,
            "elapsed_ms": 5,
            "referenced_views": ["legacy_issue_analysis.records_v1"],
        }
    }


def _semantic_evidence_tool_result() -> dict:
    return {
        "query": "에바 동결 이력과 대책",
        "backend_id": "llamaindex-pgvector",
        "hits": [
            {
                "hit_id": "hit-grounded-1",
                "text": "에바 동결 원인과 재발 방지 대책이 기록된 사례",
                "score": 0.92,
                "resource_type": "legacy_issue_record",
                "resource_id": "issue-grounded-1",
                "partition_id": "partition-1",
                "metadata": {},
            }
        ],
    }


def _failed_query_tool_result() -> dict:
    return {
        "result": {
            "query_id": "query-failed-1",
            "source": "recipe",
            "recipe": {"recipe_id": "issue_details", "version": 1},
            "parameterized_sql": "SELECT issue_id FROM scoped_records",
            "parameters": {},
            "recipe_arguments": {},
            "status": "failed",
            "error_code": "analysis_v2.query_execution_failed",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "payload_bytes": 0,
            "elapsed_ms": 5,
            "referenced_views": ["legacy_issue_analysis.records_v1"],
        }
    }


@pytest.mark.parametrize("status", ["max_steps", "model_error"])
def test_incomplete_agent_with_required_grounded_sources_is_degraded_not_failed(
    status: str,
) -> None:
    interpretation = AnalysisInterpretation(
        needs_statistics=True,
        needs_semantic_evidence=True,
    )
    result = AnalysisAgentResult(
        status=status,
        final_text="",
        transcript=(),
        tool_results=(
            _successful_query_tool_result(),
            _semantic_evidence_tool_result(),
        ),
        steps=8 if status == "max_steps" else 1,
    )

    bundle = _agent_result_to_bundle(
        result,
        interpretation=interpretation,
    )

    assert bundle.limitations == []
    assert bundle.execution_warnings == [f"analysis_agent:{status}"]
    assert len(bundle.query_results) == 1
    assert len(bundle.evidence) == 1


def test_incomplete_agent_without_a_required_source_remains_failed() -> None:
    result = AnalysisAgentResult(
        status="model_error",
        final_text="",
        transcript=(),
        tool_results=(_semantic_evidence_tool_result(),),
        steps=1,
    )

    bundle = _agent_result_to_bundle(
        result,
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=True,
        ),
    )

    assert bundle.limitations == ["analysis_agent:model_error"]
    assert bundle.execution_warnings == []


def test_recovered_agent_never_hides_a_failed_query() -> None:
    result = AnalysisAgentResult(
        status="max_steps",
        final_text="",
        transcript=(),
        tool_results=(
            _successful_query_tool_result(),
            _failed_query_tool_result(),
            _semantic_evidence_tool_result(),
        ),
        steps=8,
    )

    bundle = _agent_result_to_bundle(
        result,
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=True,
        ),
    )

    assert bundle.execution_warnings == ["analysis_agent:max_steps"]
    assert bundle.limitations == ["one_or_more_queries_failed"]


def test_required_semantic_evidence_is_supplemented_after_bounded_agent_stops() -> None:
    toolset = _EvidenceToolset()
    result = AnalysisAgentResult(
        status="max_steps",
        final_text="",
        transcript=(),
        tool_results=(
            {
                "result": {
                    "status": "succeeded",
                    "rows": [{"issue_count": 0}],
                }
            },
        ),
        steps=8,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,
        result=result,
        question="결빙·저온 관련 사례를 보고해줘",
        interpretation=AnalysisInterpretation(needs_semantic_evidence=True),
    )

    assert toolset.queries == [("결빙·저온 관련 사례를 보고해줘", 12)]
    assert supplemented.status == "max_steps"
    assert len(supplemented.tool_results) == 2
    assert supplemented.tool_results[1]["hits"][0]["resource_id"] == "issue-1"


def test_model_error_recovers_after_deterministic_semantic_supplement() -> None:
    interpretation = AnalysisInterpretation(needs_semantic_evidence=True)
    result = AnalysisAgentResult(
        status="model_error",
        final_text="",
        transcript=(),
        tool_results=(),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=_EvidenceToolset(),
        result=result,
        question="에바(증발기) 동결발생한 과거 이력 및 대책은 뭐야?",
        interpretation=interpretation,
    )
    bundle = _agent_result_to_bundle(
        supplemented,
        interpretation=interpretation,
    )

    assert len(bundle.evidence) == 1
    assert bundle.limitations == []
    assert bundle.execution_warnings == ["analysis_agent:model_error"]


def test_required_semantic_retrieval_failure_is_preserved_as_limitation() -> None:
    toolset = _FailingEvidenceToolset()
    result = AnalysisAgentResult(
        status="completed",
        final_text="done",
        transcript=(),
        tool_results=(),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,
        result=result,
        question="결빙 관련 사례",
        interpretation=AnalysisInterpretation(needs_semantic_evidence=True),
    )
    bundle = _agent_result_to_bundle(
        supplemented,
        interpretation=AnalysisInterpretation(needs_semantic_evidence=True),
    )

    assert toolset.queries == [("결빙 관련 사례", 12)]
    assert "semantic_retrieval_failed" in bundle.limitations


def test_failed_query_does_not_satisfy_required_structured_result() -> None:
    assert (
        _has_query_result(
            (
                {
                    "result": {
                        "status": "failed",
                        "error_code": "analysis_v2.invalid_module_filter",
                    }
                },
            )
        )
        is False
    )


def test_rejected_planner_filter_is_removed_when_authorized_evidence_is_available() -> None:
    toolset = _EvidenceToolset()
    result = AnalysisAgentResult(
        status="completed",
        final_text="done",
        transcript=(),
        tool_results=(
            {
                "result": {
                    "query_id": "analysis-rejected",
                    "source": "recipe",
                    "recipe": {"recipe_id": "issue_total", "version": 1},
                    "parameterized_sql": "SELECT COUNT(*)",
                    "parameters": {"query_text": "%question%"},
                    "recipe_arguments": {"query_text": "question?"},
                    "status": "failed",
                    "error_code": "analysis_v2.invalid_literal_filter",
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "truncated": False,
                    "payload_bytes": 0,
                    "elapsed_ms": 0,
                    "referenced_views": [],
                }
            },
        ),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,
        result=result,
        question="에바(증발기)가 얼어서 문제된 이력이 있어?",
        interpretation=AnalysisInterpretation(needs_semantic_evidence=True),
    )
    bundle = _agent_result_to_bundle(
        supplemented,
        interpretation=AnalysisInterpretation(needs_semantic_evidence=True),
    )

    assert len(supplemented.tool_results) == 1
    assert supplemented.tool_results[0]["backend_id"] == "llamaindex-pgvector"
    assert bundle.limitations == []
    assert len(bundle.evidence) == 1


def test_rejected_structured_scope_never_falls_back_to_unfiltered_statistics() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="completed",
        final_text="done",
        transcript=(),
        tool_results=(
            {
                "result": {
                    "status": "failed",
                    "error_code": "analysis_v2.invalid_module_filter",
                }
            },
        ),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,
        result=result,
        question="2026년 에바 결빙 문제 건수?",
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=False,
        ),
    )
    bundle = _agent_result_to_bundle(
        supplemented,
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=False,
        ),
    )

    assert toolset.recipes == []
    assert "structured_filter_scope_unresolved" in bundle.limitations
    assert bundle.query_results == []


def test_rejected_structured_scope_never_falls_back_to_unfiltered_checklists() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="completed",
        final_text="done",
        transcript=(),
        tool_results=(
            {
                "result": {
                    "status": "failed",
                    "error_code": "analysis_v2.invalid_literal_filter",
                }
            },
        ),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,
        result=result,
        question="에바 결빙 관련 체크리스트?",
        interpretation=AnalysisInterpretation(
            needs_checklists=True,
            needs_semantic_evidence=False,
        ),
    )
    bundle = _agent_result_to_bundle(
        supplemented,
        interpretation=AnalysisInterpretation(
            needs_checklists=True,
            needs_semantic_evidence=False,
        ),
    )

    assert toolset.recipes == []
    assert "structured_filter_scope_unresolved" in bundle.limitations
    assert bundle.query_results == []


def test_existing_business_evidence_is_not_retrieved_twice() -> None:
    toolset = _EvidenceToolset()
    result = AnalysisAgentResult(
        status="completed",
        final_text="done",
        transcript=(),
        tool_results=(
            {
                "backend_id": "llamaindex-pgvector",
                "hits": [
                    {
                        "resource_type": "legacy_issue_record",
                        "resource_id": "issue-1",
                    }
                ],
            },
        ),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,
        result=result,
        question="결빙 관련 사례",
        interpretation=AnalysisInterpretation(needs_semantic_evidence=True),
    )

    assert supplemented is result
    assert toolset.queries == []


def test_checklist_intent_gets_the_generic_structured_baseline() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="model_error",
        final_text="",
        transcript=(),
        tool_results=(),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,  # type: ignore[arg-type]
        result=result,
        question="체크리스트 현황과 반영률이 낮은 차종 보고서",
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=False,
            needs_checklists=True,
        ),
    )

    recipe_ids = [item[0] for item in toolset.recipes]
    assert recipe_ids[:6] == [
        "checklist_total",
        "checklist_item_total",
        "checklist_status_summary",
        "checklist_item_breakdown",
        "checklist_item_breakdown",
        "issue_checklist_coverage",
    ]
    assert (
        "checklist_item_breakdown",
        1,
        {"dimension": "checklist_status", "limit": 100},
    ) in toolset.recipes
    assert (
        "checklist_item_breakdown",
        1,
        {"dimension": "module_key", "limit": 100},
    ) in toolset.recipes
    assert "issue_total" in recipe_ids
    coverage_call = next(
        item for item in toolset.recipes if item[0] == "issue_checklist_coverage"
    )
    assert coverage_call[2]["sort_direction"] == "ASC"
    assert len(supplemented.tool_results) >= 6


def test_hotspot_examples_use_exact_supplier_and_part_filters() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="completed",
        final_text="done",
        transcript=(),
        tool_results=(
            {
                "result": {
                    "recipe": {
                        "recipe_id": "issue_supplier_part_hotspots",
                        "version": 1,
                    },
                    "recipe_arguments": {"limit": 2},
                    "parameters": {"limit": 2},
                    "status": "succeeded",
                    "rows": [
                        {
                            "supplier": None,
                            "part_number": None,
                            "supplier_missing": True,
                            "part_number_missing": True,
                        },
                        {
                            "supplier": "Open ALM",
                            "part_number": "P-1",
                            "supplier_missing": False,
                            "part_number_missing": False,
                        },
                    ],
                }
            },
        ),
        steps=1,
    )

    _supplement_required_sources(
        toolset=toolset,  # type: ignore[arg-type]
        result=result,
        question="협력사·부품 상위 2개 조합의 대표 사례와 대책을 알려줘",
        interpretation=AnalysisInterpretation(
            needs_statistics=False,
            needs_semantic_evidence=False,
        ),
    )

    detail_calls = [
        parameters
        for recipe_id, _version, parameters in toolset.recipes
        if recipe_id == "issue_details"
    ]
    assert detail_calls == [
        {
            "limit": 2,
            "supplier_missing": True,
            "part_number_missing": True,
        },
        {
            "limit": 2,
            "suppliers": ["Open ALM"],
            "part_numbers": ["P-1"],
        },
    ]


def test_final_countermeasure_duration_is_declared_as_unsupported_capability() -> None:
    limitations = _requested_capability_limitations(
        "문제 발생일부터 최종 대책일까지 평균과 중앙값 소요기간을 알려줘"
    )

    assert len(limitations) == 1
    assert "최종 대책일" in limitations[0]
    assert "접수일" in limitations[0]


def test_checklist_intent_discards_coverage_order_opposite_to_the_question() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="completed",
        final_text="done",
        transcript=(),
        tool_results=(
            {
                "result": {
                    "recipe": {
                        "recipe_id": "issue_checklist_coverage",
                        "version": 1,
                    },
                    "parameterized_sql": (
                        "SELECT coverage_rate FROM records "
                        "ORDER BY coverage_rate DESC LIMIT %(limit)s"
                    ),
                    "parameters": {"limit": 50},
                    "status": "succeeded",
                    "rows": [{"coverage_rate": 100}],
                }
            },
        ),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,  # type: ignore[arg-type]
        result=result,
        question="체크리스트 반영률이 낮은 차종을 정리해줘",
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_checklists=True,
        ),
    )

    queries = [
        item["result"]
        for item in supplemented.tool_results
        if isinstance(item.get("result"), dict)
    ]
    assert all(
        "coverage_rate DESC" not in str(item.get("parameterized_sql") or "")
        for item in queries
    )
    coverage_calls = [
        item for item in toolset.recipes if item[0] == "issue_checklist_coverage"
    ]
    assert coverage_calls[-1][2]["sort_direction"] == "ASC"


def test_statistics_intent_gets_total_when_agent_returns_no_query() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="model_error",
        final_text="",
        transcript=(),
        tool_results=(),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,  # type: ignore[arg-type]
        result=result,
        question="전체 건수",
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=False,
            needs_checklists=False,
        ),
    )

    assert [item[0] for item in toolset.recipes] == ["issue_total"]
    assert len(supplemented.tool_results) == 1


def test_statistics_plan_covers_explicit_regions_and_requested_dimensions() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="max_steps",
        final_text="",
        transcript=(),
        tool_results=(),
        steps=8,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,  # type: ignore[arg-type]
        result=result,
        question=(
            "테스트-국내, 테스트-유럽, 테스트-북미, 테스트-중국에 한정해 "
            "권역별 건수와 비중, 권역별 상위 차종과 문제유형을 보고해줘"
        ),
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=False,
        ),
    )

    requested_regions = [
        "테스트-국내",
        "테스트-유럽",
        "테스트-북미",
        "테스트-중국",
    ]
    persisted_calls = [
        (item["result"]["recipe"]["recipe_id"], item["result"]["parameters"])
        for item in supplemented.tool_results
    ]
    assert ("issue_total", {"regions": requested_regions}) in persisted_calls
    assert (
        "issue_breakdown",
        {
            "dimension": "region_zone",
            "limit": 200,
            "regions": requested_regions,
        },
    ) in persisted_calls
    assert (
        "issue_matrix",
        {
            "row_dimension": "region_zone",
            "column_dimension": "vehicle_model",
            "limit": 500,
            "regions": requested_regions,
        },
    ) in persisted_calls
    assert (
        "issue_matrix",
        {
            "row_dimension": "region_zone",
            "column_dimension": "issue_type",
            "limit": 500,
            "regions": requested_regions,
        },
    ) in persisted_calls


def test_whole_scope_discards_invented_date_filters_and_adds_unfiltered_plan() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="max_steps",
        final_text="",
        transcript=(),
        tool_results=(
            {
                "result": {
                    "recipe": {"recipe_id": "issue_total", "version": 1},
                    "parameterized_sql": (
                        "SELECT COUNT(*) FROM records "
                        "WHERE date >= %(date_from)s"
                    ),
                    "parameters": {"date_from": "2010-01-01"},
                    "status": "succeeded",
                    "rows": [{"issue_count": 35}],
                }
            },
        ),
        steps=8,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,  # type: ignore[arg-type]
        result=result,
        question="전체 과거차 문제점을 차종별·문제유형별로 집계해줘",
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=False,
        ),
    )

    calls = [
        (item["result"]["recipe"]["recipe_id"], item["result"]["parameters"])
        for item in supplemented.tool_results
    ]
    assert ("issue_total", {}) in calls
    assert (
        "issue_matrix",
        {
            "row_dimension": "vehicle_model",
            "column_dimension": "issue_type",
            "limit": 500,
        },
    ) in calls
    assert all(call[1].get("date_from") is None for call in calls)


def test_unspecified_period_discards_invented_date_filters_without_whole_keyword() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="completed",
        final_text="done",
        transcript=(),
        tool_results=(
            {
                "result": {
                    "recipe": {
                        "recipe_id": "issue_response_duration",
                        "version": 1,
                    },
                    "parameterized_sql": (
                        "SELECT average_days FROM records "
                        "WHERE occurrence_date >= %(date_from)s"
                    ),
                    "parameters": {"date_from": "2020-01-01"},
                    "status": "succeeded",
                    "rows": [{"average_days": 10}],
                }
            },
        ),
        steps=1,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,  # type: ignore[arg-type]
        result=result,
        question="문제 대응 소요기간을 분석해줘",
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=False,
        ),
    )

    retained = [
        item["result"]
        for item in supplemented.tool_results
        if isinstance(item.get("result"), dict)
    ]
    assert all(
        item.get("parameters", {}).get("date_from") is None
        for item in retained
    )
    assert all(
        item.get("recipe", {}).get("recipe_id") != "issue_response_duration"
        for item in retained
    )


def test_statistical_plan_covers_every_requested_dimension_pair() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="max_steps",
        final_text="",
        transcript=(),
        tool_results=(),
        steps=8,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,  # type: ignore[arg-type]
        result=result,
        question="차종과 발생 단계와 공정의 교차 분포를 보고해줘",
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=False,
        ),
    )

    matrix_pairs = {
        (
            item["result"]["parameters"]["row_dimension"],
            item["result"]["parameters"]["column_dimension"],
        )
        for item in supplemented.tool_results
        if item.get("result", {}).get("recipe", {}).get("recipe_id")
        == "issue_matrix"
    }
    assert matrix_pairs == {
        ("vehicle_model", "occurrence_stage"),
        ("vehicle_model", "process_name"),
        ("occurrence_stage", "process_name"),
    }
    cube_calls = [
        item["result"]["parameters"]
        for item in supplemented.tool_results
        if item.get("result", {}).get("recipe", {}).get("recipe_id")
        == "issue_cube"
    ]
    assert cube_calls == [
        {
            "row_dimension": "vehicle_model",
            "column_dimension": "occurrence_stage",
            "detail_dimension": "process_name",
            "limit": 500,
        }
    ]


def test_two_year_comparison_does_not_expand_generic_period_word_to_range() -> None:
    toolset = _ChecklistToolset()
    result = AnalysisAgentResult(
        status="max_steps",
        final_text="",
        transcript=(),
        tool_results=(),
        steps=8,
    )

    supplemented = _supplement_required_sources(
        toolset=toolset,  # type: ignore[arg-type]
        result=result,
        question="2022년과 2024년을 비교하고 각 기간의 원인 유형을 알려줘",
        interpretation=AnalysisInterpretation(
            needs_statistics=True,
            needs_semantic_evidence=False,
        ),
    )

    totals = [
        item["result"]["parameters"]
        for item in supplemented.tool_results
        if item.get("result", {}).get("recipe", {}).get("recipe_id")
        == "issue_total"
    ]
    assert totals == [
        {"date_from": "2022-01-01", "date_to": "2022-12-31"},
        {"date_from": "2024-01-01", "date_to": "2024-12-31"},
    ]
    assert {
        "date_from": "2022-01-01",
        "date_to": "2024-12-31",
    } not in totals
