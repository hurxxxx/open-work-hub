from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

from ai_do_api.domains.ai.gateway import AiGatewayDecision
from ai_do_api.domains.legacy_issues import (
    ai_assistant,
    analysis_application,
    analysis_sql_fallback,
    conversation_scope,
)
from ai_do_api.domains.legacy_issues.ai_assistant import (
    LegacyIssueAssistantResult,
    run_legacy_issue_assistant,
)
from ai_do_api.domains.legacy_issues.ai_search import (
    LegacyIssueAssistantSearchPlan,
    LegacyIssueEvidence,
    LegacyIssueSearchProfile,
    sanitize_legacy_issue_search_plan,
)
from ai_do_api.domains.legacy_issues.analysis_application import (
    LegacyIssueAnalysisOutcome,
    compact_analysis_prompt_payload,
    run_legacy_issue_analysis,
)
from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisColumnV1,
    AnalysisCountingUnit,
    AnalysisDataSource,
    AnalysisMode,
    AnalysisPlanV1,
    AnalysisResultV1,
    AnalysisScopeV1,
    LegacyIssueAnalysisArtifactV1,
    LegacyIssuePlannerDiagnosticsV1,
    QueryFamilyId,
    QueryRequestV1,
)
from ai_do_api.domains.legacy_issues.analysis_planner import LegacyIssuePlannerResult
from ai_do_api.domains.legacy_issues.dataset_records import DatasetFieldDefinition
from ai_do_api.domains.legacy_issues.conversation_scope import (
    LegacyIssueConversationScopeAdapter,
    LegacyIssuePromptAnalysis,
)
from ai_do_api.domains.legacy_issues import router as legacy_issue_router


def test_analytics_executes_exact_catalog_without_semantic_retrieval(
    monkeypatch,
) -> None:
    analysis_decision = _decision("analysis")
    plan = _analysis_plan(AnalysisMode.ANALYTICS)
    payload = _artifact_payload("analytics")
    execute_analysis = Mock(return_value=SimpleNamespace(to_payload=Mock(return_value=payload)))
    semantic_plan = Mock(side_effect=AssertionError("semantic planner must not run"))
    semantic_search = Mock(side_effect=AssertionError("semantic retrieval must not run"))
    planner = _patch_orchestration(
        monkeypatch,
        plan=plan,
        decisions=[analysis_decision],
        execute_analysis=execute_analysis,
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )

    outcome = _run()

    assert outcome.analysis_plan is plan
    assert outcome.analysis_result == payload
    assert outcome.evidence == []
    assert outcome.search_profile.semantic_enabled is False
    assert outcome.gateway_decisions == [analysis_decision]
    assert outcome.degraded_reason is None
    execute_analysis.assert_called_once()
    semantic_plan.assert_not_called()
    semantic_search.assert_not_called()
    active_fields = planner.call_args.kwargs["fields"]
    assert [field.key for field in active_fields] == ["region_zone"]


def test_semantic_mode_uses_existing_retrieval_path(monkeypatch) -> None:
    analysis_decision = _decision("analysis")
    semantic_decision = _decision("semantic")
    evidence = [_evidence()]
    profile = _semantic_profile()
    semantic_plan, semantic_search = _semantic_mocks(
        evidence=evidence,
        profile=profile,
        decision=semantic_decision,
    )
    execute_analysis = Mock(side_effect=AssertionError("catalog executor must not run"))
    _patch_orchestration(
        monkeypatch,
        plan=_analysis_plan(AnalysisMode.SEMANTIC),
        decisions=[analysis_decision],
        execute_analysis=execute_analysis,
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )

    outcome = _run()

    assert outcome.analysis_plan.mode == AnalysisMode.SEMANTIC
    assert outcome.analysis_result is None
    assert outcome.evidence == evidence
    assert outcome.search_profile is profile
    assert outcome.gateway_decisions == [analysis_decision, semantic_decision]
    execute_analysis.assert_not_called()
    semantic_plan.assert_called_once()
    semantic_search.assert_called_once()


def test_hybrid_keeps_exact_analysis_and_semantic_evidence_separate(
    monkeypatch,
) -> None:
    analysis_decision = _decision("analysis")
    semantic_decision = _decision("semantic")
    payload = _artifact_payload("hybrid")
    evidence = [_evidence()]
    profile = _semantic_profile()
    execute_analysis = Mock(return_value=SimpleNamespace(to_payload=Mock(return_value=payload)))
    semantic_plan, semantic_search = _semantic_mocks(
        evidence=evidence,
        profile=profile,
        decision=semantic_decision,
    )
    _patch_orchestration(
        monkeypatch,
        plan=_analysis_plan(AnalysisMode.HYBRID),
        decisions=[analysis_decision],
        execute_analysis=execute_analysis,
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )

    outcome = _run()

    assert outcome.analysis_plan.mode == AnalysisMode.HYBRID
    assert outcome.analysis_result == payload
    assert outcome.evidence == evidence
    assert outcome.search_profile is profile
    assert outcome.gateway_decisions == [analysis_decision, semantic_decision]
    assert outcome.analysis_result["queries"][0]["rows"][0]["issue_count"] == 7
    assert outcome.search_profile.evidence_count == 1
    execute_analysis.assert_called_once()
    semantic_search.assert_called_once()


def test_catalog_failure_degrades_to_semantic_without_partial_exact_result(
    monkeypatch,
) -> None:
    analysis_decision = _decision("analysis")
    semantic_decision = _decision("semantic")
    evidence = [_evidence()]
    profile = _semantic_profile()
    semantic_plan, semantic_search = _semantic_mocks(
        evidence=evidence,
        profile=profile,
        decision=semantic_decision,
    )
    execute_analysis = Mock(side_effect=RuntimeError("catalog execution failed"))
    _patch_orchestration(
        monkeypatch,
        plan=_analysis_plan(AnalysisMode.ANALYTICS),
        decisions=[analysis_decision],
        execute_analysis=execute_analysis,
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )

    outcome = _run()

    assert outcome.analysis_plan.mode == AnalysisMode.SEMANTIC
    assert outcome.analysis_result is None
    assert outcome.evidence == evidence
    assert outcome.gateway_decisions == [analysis_decision, semantic_decision]
    assert outcome.degraded_reason == "catalog execution failed"
    semantic_search.assert_called_once()


def test_salvaged_catalog_plan_is_executed_and_marked_degraded(monkeypatch) -> None:
    plan = _analysis_plan(AnalysisMode.ANALYTICS)
    payload = _artifact_payload("analytics")
    planner = _patch_orchestration(
        monkeypatch,
        plan=plan,
        decisions=[],
        execute_analysis=Mock(
            return_value=SimpleNamespace(to_payload=Mock(return_value=payload))
        ),
        semantic_plan=Mock(side_effect=AssertionError("semantic planner must not run")),
        semantic_search=Mock(side_effect=AssertionError("semantic search must not run")),
    )
    planner.return_value = LegacyIssuePlannerResult(
        plan=plan,
        decisions=[],
        diagnostics=LegacyIssuePlannerDiagnosticsV1(
            status="fallback",
            attempt_count=2,
            candidate_family_count=8,
            catalog_family_count=62,
            prompt_chars=30_000,
            fallback_reason="partial_plan_salvaged",
            validation_error_code="plan_schema_invalid",
        ),
    )

    outcome = _run(routing_mode=AnalysisMode.ANALYTICS)

    assert outcome.analysis_result == payload
    assert outcome.degraded_reason == "analysis_planner_fallback"


def test_checklist_catalog_failure_never_substitutes_legacy_semantic_evidence(
    monkeypatch,
) -> None:
    analysis_decision = _decision("analysis")
    semantic_plan = Mock(side_effect=AssertionError("legacy semantic planner must not run"))
    semantic_search = Mock(side_effect=AssertionError("legacy semantic search must not run"))
    checklist_plan = AnalysisPlanV1(
        mode=AnalysisMode.ANALYTICS,
        queries=(
            QueryRequestV1(
                query_id="q1",
                family_id=QueryFamilyId.TOTAL_COUNT,
                data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
            ),
        ),
    )
    _patch_orchestration(
        monkeypatch,
        plan=checklist_plan,
        decisions=[analysis_decision],
        execute_analysis=Mock(side_effect=RuntimeError("catalog execution failed")),
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )

    outcome = _run(data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,))

    assert outcome.analysis_plan is checklist_plan
    assert outcome.analysis_result is None
    assert outcome.evidence == []
    assert outcome.gateway_decisions == [analysis_decision]
    assert outcome.degraded_reason == "catalog execution failed"
    semantic_plan.assert_not_called()
    semantic_search.assert_not_called()


def test_generated_failure_degrades_to_semantic_and_preserves_all_decisions(
    monkeypatch,
) -> None:
    analysis_decision = _decision("analysis")
    generated_decision = _decision("generated")
    semantic_decision = _decision("semantic")
    semantic_plan, semantic_search = _semantic_mocks(
        evidence=[_evidence()],
        profile=_semantic_profile(),
        decision=semantic_decision,
    )
    generated_planner = Mock(return_value=(object(), [generated_decision]))
    generated_executor = Mock(side_effect=RuntimeError("generated execution failed"))
    generated_module = ModuleType("ai_do_api.domains.legacy_issues.analysis_generated_executor")
    setattr(generated_module, "execute_generated_analysis", generated_executor)
    monkeypatch.setitem(sys.modules, generated_module.__name__, generated_module)
    monkeypatch.setattr(
        analysis_sql_fallback,
        "plan_legacy_issue_generated_sql",
        generated_planner,
    )
    _patch_orchestration(
        monkeypatch,
        plan=_analysis_plan(AnalysisMode.GENERATED),
        decisions=[analysis_decision],
        execute_analysis=Mock(side_effect=AssertionError("catalog executor must not run")),
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )

    outcome = _run()

    assert outcome.analysis_plan.mode == AnalysisMode.SEMANTIC
    assert outcome.analysis_result is None
    assert outcome.gateway_decisions == [
        analysis_decision,
        generated_decision,
        semantic_decision,
    ]
    assert outcome.degraded_reason == "generated execution failed"
    generated_planner.assert_called_once()
    generated_executor.assert_called_once()
    semantic_search.assert_called_once()


def test_unrepresented_question_constraint_never_reaches_generated_sql(
    monkeypatch,
) -> None:
    analysis_decision = _decision("analysis")
    generated_plan = _analysis_plan(AnalysisMode.GENERATED)
    semantic_plan = Mock(side_effect=AssertionError("semantic planner must not run"))
    semantic_search = Mock(side_effect=AssertionError("semantic search must not run"))
    planner = _patch_orchestration(
        monkeypatch,
        plan=generated_plan,
        decisions=[analysis_decision],
        execute_analysis=Mock(side_effect=AssertionError("catalog executor must not run")),
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )
    planner.return_value = LegacyIssuePlannerResult(
        plan=generated_plan,
        decisions=[analysis_decision],
        diagnostics=LegacyIssuePlannerDiagnosticsV1(
            status="fallback",
            attempt_count=2,
            candidate_family_count=8,
            catalog_family_count=62,
            prompt_chars=30_000,
            fallback_reason="attempts_exhausted",
            validation_error_code="question_constraint_unrepresented",
        ),
    )

    outcome = _run(routing_mode=AnalysisMode.HYBRID)

    assert outcome.analysis_result is None
    assert outcome.evidence == []
    assert outcome.gateway_decisions == [analysis_decision]
    assert outcome.degraded_reason == "question_constraint_unrepresented"
    semantic_plan.assert_not_called()
    semantic_search.assert_not_called()


def test_checklist_generated_failure_never_substitutes_legacy_semantic_evidence(
    monkeypatch,
) -> None:
    analysis_decision = _decision("analysis")
    generated_decision = _decision("generated")
    semantic_plan = Mock(side_effect=AssertionError("legacy semantic planner must not run"))
    semantic_search = Mock(side_effect=AssertionError("legacy semantic search must not run"))
    generated_planner = Mock(return_value=(object(), [generated_decision]))
    generated_executor = Mock(side_effect=RuntimeError("generated execution failed"))
    generated_module = ModuleType("ai_do_api.domains.legacy_issues.analysis_generated_executor")
    setattr(generated_module, "execute_generated_analysis", generated_executor)
    monkeypatch.setitem(sys.modules, generated_module.__name__, generated_module)
    monkeypatch.setattr(
        analysis_sql_fallback,
        "plan_legacy_issue_generated_sql",
        generated_planner,
    )
    checklist_plan = AnalysisPlanV1(
        mode=AnalysisMode.GENERATED,
        delegated_family_id=QueryFamilyId.GENERATED_SQL_FALLBACK,
        delegated_data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
    )
    _patch_orchestration(
        monkeypatch,
        plan=checklist_plan,
        decisions=[analysis_decision],
        execute_analysis=Mock(side_effect=AssertionError("catalog executor must not run")),
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )

    outcome = _run(data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,))

    assert outcome.analysis_plan is checklist_plan
    assert outcome.analysis_result is None
    assert outcome.evidence == []
    assert outcome.gateway_decisions == [analysis_decision, generated_decision]
    assert outcome.degraded_reason == "generated execution failed"
    semantic_plan.assert_not_called()
    semantic_search.assert_not_called()


def test_generated_fallback_preserves_hybrid_semantic_evidence(monkeypatch) -> None:
    analysis_decision = _decision("analysis")
    generated_decision = _decision("generated")
    semantic_decision = _decision("semantic")
    evidence = [_evidence()]
    profile = _semantic_profile()
    semantic_plan, semantic_search = _semantic_mocks(
        evidence=evidence,
        profile=profile,
        decision=semantic_decision,
    )
    generated_planner = Mock(return_value=(object(), [generated_decision]))
    generated_payload = {
        "version": 1,
        "mode": "generated",
        "queries": [],
    }
    generated_executor = Mock(return_value=generated_payload)
    generated_module = ModuleType("ai_do_api.domains.legacy_issues.analysis_generated_executor")
    setattr(generated_module, "execute_generated_analysis", generated_executor)
    monkeypatch.setitem(sys.modules, generated_module.__name__, generated_module)
    monkeypatch.setattr(
        analysis_sql_fallback,
        "plan_legacy_issue_generated_sql",
        generated_planner,
    )
    _patch_orchestration(
        monkeypatch,
        plan=AnalysisPlanV1(
            mode=AnalysisMode.GENERATED,
            delegated_family_id=QueryFamilyId.GENERATED_SQL_FALLBACK,
        ),
        decisions=[analysis_decision],
        execute_analysis=Mock(side_effect=AssertionError("catalog executor must not run")),
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )

    outcome = _run(routing_mode=AnalysisMode.HYBRID)

    assert outcome.analysis_result == generated_payload
    assert outcome.evidence == evidence
    assert outcome.search_profile is profile
    assert outcome.gateway_decisions == [
        analysis_decision,
        generated_decision,
        semantic_decision,
    ]
    generated_executor.assert_called_once()
    semantic_search.assert_called_once()


def test_multi_source_generated_fallback_is_marked_degraded(monkeypatch) -> None:
    semantic_plan, semantic_search = _semantic_mocks(
        evidence=[_evidence()],
        profile=_semantic_profile(),
        decision=_decision("semantic"),
    )
    generated_payload = {
        "version": 1,
        "mode": "generated",
        "queries": [],
    }
    generated_module = ModuleType("ai_do_api.domains.legacy_issues.analysis_generated_executor")
    setattr(
        generated_module,
        "execute_generated_analysis",
        Mock(return_value=generated_payload),
    )
    monkeypatch.setitem(sys.modules, generated_module.__name__, generated_module)
    monkeypatch.setattr(
        analysis_sql_fallback,
        "plan_legacy_issue_generated_sql",
        Mock(return_value=(object(), [])),
    )
    plan = AnalysisPlanV1(
        mode=AnalysisMode.GENERATED,
        delegated_family_id=QueryFamilyId.GENERATED_SQL_FALLBACK,
        delegated_data_source=AnalysisDataSource.LEGACY_ISSUES,
    )
    planner = _patch_orchestration(
        monkeypatch,
        plan=plan,
        decisions=[],
        execute_analysis=Mock(side_effect=AssertionError("catalog executor must not run")),
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )
    planner.return_value = LegacyIssuePlannerResult(
        plan=plan,
        decisions=[],
        diagnostics=LegacyIssuePlannerDiagnosticsV1(
            status="fallback",
            attempt_count=2,
            candidate_family_count=8,
            catalog_family_count=62,
            prompt_chars=30_000,
            fallback_reason="attempts_exhausted",
            validation_error_code="catalog_validation_failed",
        ),
    )

    outcome = _run(
        routing_mode=AnalysisMode.HYBRID,
        data_sources=(
            AnalysisDataSource.LEGACY_ISSUES,
            AnalysisDataSource.VEHICLE_CHECKLISTS,
        ),
    )

    assert outcome.analysis_result == generated_payload
    assert outcome.degraded_reason == "analysis_planner_fallback"
    semantic_search.assert_called_once()


def test_multi_source_generated_failure_preserves_execution_error(monkeypatch) -> None:
    semantic_plan, semantic_search = _semantic_mocks(
        evidence=[_evidence()],
        profile=_semantic_profile(),
        decision=_decision("semantic"),
    )
    generated_module = ModuleType("ai_do_api.domains.legacy_issues.analysis_generated_executor")
    setattr(
        generated_module,
        "execute_generated_analysis",
        Mock(side_effect=RuntimeError("generated execution failed")),
    )
    monkeypatch.setitem(sys.modules, generated_module.__name__, generated_module)
    monkeypatch.setattr(
        analysis_sql_fallback,
        "plan_legacy_issue_generated_sql",
        Mock(return_value=(object(), [])),
    )
    plan = AnalysisPlanV1(
        mode=AnalysisMode.GENERATED,
        delegated_family_id=QueryFamilyId.GENERATED_SQL_FALLBACK,
        delegated_data_source=AnalysisDataSource.LEGACY_ISSUES,
    )
    planner = _patch_orchestration(
        monkeypatch,
        plan=plan,
        decisions=[],
        execute_analysis=Mock(side_effect=AssertionError("catalog executor must not run")),
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )
    planner.return_value = LegacyIssuePlannerResult(
        plan=plan,
        decisions=[],
        diagnostics=LegacyIssuePlannerDiagnosticsV1(
            status="fallback",
            attempt_count=2,
            candidate_family_count=8,
            catalog_family_count=62,
            prompt_chars=30_000,
            fallback_reason="attempts_exhausted",
            validation_error_code="catalog_validation_failed",
        ),
    )

    outcome = _run(
        routing_mode=AnalysisMode.HYBRID,
        data_sources=(
            AnalysisDataSource.LEGACY_ISSUES,
            AnalysisDataSource.VEHICLE_CHECKLISTS,
        ),
    )

    assert outcome.analysis_result is None
    assert outcome.degraded_reason == "generated execution failed"
    semantic_search.assert_called_once()


def test_generated_fallback_preserves_semantic_cohort_evidence(monkeypatch) -> None:
    semantic_plan, semantic_search = _semantic_mocks(
        evidence=[_evidence()],
        profile=_semantic_profile(),
        decision=_decision("semantic"),
    )
    generated_module = ModuleType("ai_do_api.domains.legacy_issues.analysis_generated_executor")
    setattr(
        generated_module,
        "execute_generated_analysis",
        Mock(return_value={"version": 1, "mode": "generated", "queries": []}),
    )
    monkeypatch.setitem(sys.modules, generated_module.__name__, generated_module)
    monkeypatch.setattr(
        analysis_sql_fallback,
        "plan_legacy_issue_generated_sql",
        Mock(return_value=(object(), [])),
    )
    _patch_orchestration(
        monkeypatch,
        plan=AnalysisPlanV1(
            mode=AnalysisMode.GENERATED,
            delegated_family_id=QueryFamilyId.GENERATED_SQL_FALLBACK,
        ),
        decisions=[],
        execute_analysis=Mock(side_effect=AssertionError("catalog executor must not run")),
        semantic_plan=semantic_plan,
        semantic_search=semantic_search,
    )

    outcome = _run(
        routing_mode=AnalysisMode.SEMANTIC,
        record_set_required=True,
    )

    assert outcome.analysis_result is not None
    assert outcome.evidence
    semantic_search.assert_called_once()


def test_compact_prompt_payload_bounds_query_rows_columns_and_coverage() -> None:
    payload = _artifact_payload("analytics")
    payload["queries"] = [
        {
            "id": f"q{query_index}",
            "title": f"Q{query_index}",
            "family_id": "multidim_breakdown",
            "family_version": 1,
            "exactness": "exact",
            "columns": [{"key": f"c{index}", "label": f"C{index}"} for index in range(40)],
            "rows": [{f"c{index}": row_index for index in range(40)} for row_index in range(25)],
            "totals": {"issue_count": 25},
            "coverage": [{"field_key": f"c{index}", "label": f"C{index}"} for index in range(40)],
            "warnings": [],
            "truncated": True,
        }
        for query_index in range(8)
    ]

    compact = compact_analysis_prompt_payload(payload)

    assert compact is not None
    assert len(compact["queries"]) == 6
    first = compact["queries"][0]
    assert len(first["columns"]) == 32
    assert 20 < len(first["rows"]) <= 25
    assert first["available_row_count"] == 25
    assert first["context_row_count"] == len(first["rows"])
    assert first["context_truncated"] is (len(first["rows"]) < 25)
    assert len(first["coverage"]) == 32
    assert len(payload["queries"]) == 8
    assert len(payload["queries"][0]["rows"]) == 25


def test_compact_prompt_payload_enforces_total_character_budget() -> None:
    payload = _artifact_payload("analytics")
    payload["queries"] = [
        {
            "id": f"q{query_index}",
            "title": "Q" * 2_000,
            "family_id": "detail_list",
            "family_version": 1,
            "exactness": "exact",
            "columns": [
                {
                    "key": f"c{column_index}",
                    "label": "L" * 2_000,
                    "type": "text",
                    "role": "dimension",
                }
                for column_index in range(32)
            ],
            "rows": [
                {f"c{column_index}": "V" * 5_000 for column_index in range(32)}
                for _row_index in range(20)
            ],
            "totals": {"summary": "T" * 50_000},
            "coverage": [],
            "warnings": ["W" * 50_000],
            "truncated": True,
        }
        for query_index in range(6)
    ]
    payload["scope"]["filters"] = [{"value": "F" * 50_000}]
    payload["warnings"] = ["A" * 50_000]

    compact = compact_analysis_prompt_payload(payload)

    assert compact is not None
    assert len(json.dumps(compact, ensure_ascii=False, separators=(",", ":"))) <= 60_000


def test_compact_prompt_payload_preserves_time_series_endpoints() -> None:
    payload = _artifact_payload("analytics")
    payload["queries"][0].update(
        {
            "family_id": "time_series",
            "shape": "time_series",
            "columns": [
                {"key": "year", "label": "연도", "role": "dimension"},
                {"key": "issue_count", "label": "건수", "role": "metric"},
            ],
            "rows": [
                {"year": str(1900 + index), "issue_count": index}
                for index in range(100)
            ],
        }
    )

    compact = compact_analysis_prompt_payload(payload)

    assert compact is not None
    query = compact["queries"][0]
    assert query["available_row_count"] == 100
    assert query["context_row_count"] == 64
    assert query["context_truncated"] is True
    assert query["rows"][0]["year"] == "1900"
    assert query["rows"][-1]["year"] == "1999"


def test_compact_prompt_payload_balances_grouped_time_series() -> None:
    payload = _artifact_payload("analytics")
    payload["queries"][0].update(
        {
            "family_id": "time_series",
            "shape": "time_series",
            "columns": [
                {"key": "region", "label": "권역", "type": "text", "role": "dimension"},
                {"key": "year", "label": "연도", "type": "date", "role": "dimension"},
                {"key": "issue_count", "label": "건수", "type": "number", "role": "metric"},
            ],
            "rows": [
                {
                    "region": region,
                    "year": str(2000 + index),
                    "issue_count": index,
                }
                for region in ("동부", "서부", "남부", "북부")
                for index in range(100)
            ],
        }
    )
    plan = AnalysisPlanV1.model_validate(
        {
            "mode": "analytics",
            "queries": [
                {
                    "query_id": "q1",
                    "family_id": "time_series",
                    "dimensions": [
                        {"field_key": "region_zone", "alias": "region"},
                        {
                            "field_key": "occurrence_date",
                            "alias": "year",
                            "time_grain": "year",
                        },
                    ],
                }
            ],
        }
    )

    compact = compact_analysis_prompt_payload(payload, analysis_plan=plan)

    assert compact is not None
    query = compact["queries"][0]
    assert query["context_row_count"] == 64
    rows_by_region = {
        region: [row for row in query["rows"] if row["region"] == region]
        for region in ("동부", "서부", "남부", "북부")
    }
    assert all(len(rows) == 16 for rows in rows_by_region.values())
    assert all(rows[0]["year"] == "2000" for rows in rows_by_region.values())
    assert all(rows[-1]["year"] == "2099" for rows in rows_by_region.values())


def test_compact_prompt_payload_balances_parent_rank_groups() -> None:
    payload = _artifact_payload("analytics")
    payload["queries"][0].update(
        {
            "family_id": "top_n_within_parent",
            "columns": [
                {"key": "severity", "label": "중요도", "role": "dimension"},
                {"key": "vehicle", "label": "차종", "role": "dimension"},
                {"key": "issue_count", "label": "건수", "role": "metric"},
                {"key": "within_parent_rank", "label": "순위", "role": "metric"},
            ],
            "rows": [
                {
                    "severity": severity,
                    "vehicle": f"{severity}-{rank}",
                    "issue_count": 100 - rank,
                    "within_parent_rank": rank,
                }
                for severity in ("A", "B", "C", "D")
                for rank in range(1, 21)
            ],
        }
    )

    compact = compact_analysis_prompt_payload(payload)

    assert compact is not None
    query = compact["queries"][0]
    assert query["context_row_count"] == 64
    assert {row["severity"] for row in query["rows"]} == {"A", "B", "C", "D"}


def test_compact_prompt_payload_samples_across_more_than_sixty_four_parent_groups() -> None:
    payload = _artifact_payload("analytics")
    payload["queries"][0].update(
        {
            "family_id": "top_n_within_parent",
            "columns": [
                {"key": "severity", "label": "중요도", "role": "dimension"},
                {"key": "vehicle", "label": "차종", "role": "dimension"},
                {"key": "issue_count", "label": "건수", "role": "metric"},
                {"key": "within_parent_rank", "label": "순위", "role": "metric"},
            ],
            "rows": [
                {
                    "severity": f"S{parent:03d}",
                    "vehicle": f"V{rank}",
                    "issue_count": 3 - rank,
                    "within_parent_rank": rank,
                }
                for parent in range(100)
                for rank in (1, 2)
            ],
        }
    )

    compact = compact_analysis_prompt_payload(payload)

    assert compact is not None
    rows = compact["queries"][0]["rows"]
    assert len(rows) == 64
    assert len({row["severity"] for row in rows}) == 64
    assert {row["within_parent_rank"] for row in rows} == {1}
    assert rows[0]["severity"] == "S000"
    assert rows[-1]["severity"] == "S099"


def test_compact_prompt_payload_preserves_record_set_and_detail_fields() -> None:
    payload = _artifact_payload("analytics")
    payload["queries"][0].update(
        {
            "family_id": "detail_list",
            "shape": "detail",
        }
    )
    plan = AnalysisPlanV1.model_validate(
        {
            "mode": "analytics",
            "queries": [
                {
                    "query_id": "q1",
                    "family_id": "detail_list",
                    "record_set": {
                        "key_fields": ["vehicle_model"],
                        "seed_filters": {
                            "conditions": [
                                {
                                    "field_key": "issue_type",
                                    "operator": "eq",
                                    "value": "시동 불량",
                                }
                            ]
                        },
                        "exclude_seed_matches": True,
                    },
                    "detail_fields": ["vehicle_model", "issue_type", "cause"],
                }
            ],
        }
    )

    compact = compact_analysis_prompt_payload(payload, analysis_plan=plan)

    assert compact is not None
    request = compact["queries"][0]["request"]
    assert request["record_set"]["key_fields"] == ["vehicle_model"]
    assert request["record_set"]["seed_filters"]["conditions"][0] == {
        "field_key": "issue_type",
        "operator": "eq",
        "match_mode": "literal",
        "value": "시동 불량",
        "values": [],
    }
    assert request["record_set"]["exclude_seed_matches"] is True
    assert request["detail_fields"] == ["vehicle_model", "issue_type", "cause"]


def test_conversation_analysis_artifact_retains_valid_empty_rows() -> None:
    payload = _contract_artifact(rows=()).to_payload()

    artifact = conversation_scope._build_analysis_artifact(payload)

    assert artifact is not None
    assert artifact.type == "legacy-issue-analysis"
    assert artifact.title == "과거차 정형 분석"
    content = json.loads(artifact.content)
    assert content["queries"][0]["rows"] == []
    assert content["queries"][0]["columns"][0]["label"] == "전체 건수"


def test_hybrid_turn_prompt_exposes_exact_and_semantic_payloads_separately() -> None:
    payload = _contract_artifact(
        rows=({"issue_count": 7},),
        mode=AnalysisMode.HYBRID,
    ).to_payload()
    evidence = _evidence()
    profile = _semantic_profile()
    plan = _search_plan()

    prompt = conversation_scope._build_turn_prompt(
        question="전체 건수와 대표 사례",
        plan=plan,
        analysis_result=payload,
        analysis_mode="hybrid",
        clarification=None,
        evidence=[evidence],
        profile=profile,
    )

    context = json.loads(prompt.rsplit("\n\n", maxsplit=1)[-1])
    assert context["analysis_mode"] == "hybrid"
    assert context["exact_analysis"]["mode"] == "hybrid"
    assert context["exact_analysis"]["queries"][0]["rows"] == [{"issue_count": 7}]
    assert context["evidence_refs"][0]["id"] == "E1"
    assert context["retrieval_profile"]["candidate_count"] == 3
    assert "candidate_count" not in json.dumps(context["exact_analysis"])
    assert context["exact_analysis"] != context["evidence_refs"]


def test_turn_context_requires_persisted_conversation(monkeypatch) -> None:
    dispatch = Mock(side_effect=AssertionError("durable dispatch must not run"))
    monkeypatch.setattr(
        conversation_scope,
        "dispatch_legacy_issue_analysis",
        dispatch,
    )

    context = _adapter_turn_context(
        messages=[{"role": "user", "content": "안녕하세요"}],
    )

    assert context.artifacts == ()
    assert context.prompt is None
    assert context.direct_response is not None
    assert "대화를 저장" in context.direct_response
    dispatch.assert_not_called()


def test_prompt_analysis_returns_structured_routing_hints(monkeypatch) -> None:
    execute = Mock(
        return_value=SimpleNamespace(
            completion=SimpleNamespace(
                text=json.dumps(
                    {
                        "action": "retrieve",
                        "reason": "정확 집계와 근거가 모두 필요함",
                        "analysis_mode": "hybrid",
                        "family_categories": [
                            "scalar",
                            "detail",
                            "unknown",
                            "scalar",
                        ],
                        "record_set_required": True,
                        "record_set_seed_evidence": "문제가 발생한",
                        "record_set_reentry_evidence": "차종들의 다른 문제",
                    }
                )
            )
        )
    )
    monkeypatch.setattr(
        conversation_scope,
        "execute_llm",
        execute,
    )

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="문제가 발생한 차종들의 다른 문제를 보여줘",
    )

    assert analysis.should_search is True
    assert analysis.analysis_mode == AnalysisMode.HYBRID
    assert analysis.family_categories == ("scalar", "detail")
    assert analysis.record_set_required is True
    assert execute.call_args.args[0] == "legacy_issues.intent_router"
    assert execute.call_args.kwargs["max_tokens"] == 512


def test_prompt_analysis_requires_grounded_report_request(monkeypatch) -> None:
    question = "경영진 검토용 현황 보고서를 작성해줘"
    execute = Mock(
        return_value=SimpleNamespace(
            completion=SimpleNamespace(
                text=json.dumps(
                    {
                        "action": "retrieve",
                        "reason": "보고서 요청",
                        "analysis_mode": "hybrid",
                        "family_categories": ["composite", "scalar", "distribution"],
                        "response_format": "report",
                        "report_request_evidence": "현황 보고서를 작성해줘",
                    }
                )
            )
        )
    )
    monkeypatch.setattr(conversation_scope, "execute_llm", execute)

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question=question,
    )

    assert analysis.report_requested is True
    assert analysis.report_request_evidence == "현황 보고서를 작성해줘"
    request = json.loads(execute.call_args.kwargs["messages"][1]["content"])
    assert request["response_schema"]["response_format"] == "answer | report"

    execute.return_value.completion.text = json.dumps(
        {
            "action": "retrieve",
            "reason": "잘못된 보고서 신호",
            "analysis_mode": "analytics",
            "family_categories": ["scalar"],
            "response_format": "report",
            "report_request_evidence": "질문에 없는 보고서 요청",
        }
    )
    ungrounded = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="전체 건수 알려줘",
    )
    assert ungrounded.report_requested is False
    assert ungrounded.report_request_evidence is None


def test_prompt_analysis_failure_is_fail_closed_without_assuming_legacy_source(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        conversation_scope,
        "execute_llm",
        Mock(side_effect=RuntimeError("router unavailable")),
    )

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="차량 체크리스트 유사 항목을 찾아줘",
    )

    assert analysis.should_search is False
    assert analysis.action == "answer_only"
    assert analysis.reason == "intent_classifier_failed"
    assert analysis.analysis_mode is None


def test_prompt_analysis_rejects_ungrounded_record_set_signal(monkeypatch) -> None:
    monkeypatch.setattr(
        conversation_scope,
        "execute_llm",
        Mock(
            return_value=SimpleNamespace(
                completion=SimpleNamespace(
                    text=json.dumps(
                        {
                            "action": "retrieve",
                            "reason": "일반 순위 분석",
                            "analysis_mode": "analytics",
                            "family_categories": ["distribution"],
                            "record_set_required": True,
                            "record_set_seed_evidence": "질문에 없는 조건",
                            "record_set_reentry_evidence": "질문에 없는 재진입",
                        }
                    )
                )
            )
        ),
    )

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="차종별 상위 10개 문제와 구성비",
    )

    assert analysis.analysis_mode == AnalysisMode.ANALYTICS
    assert analysis.record_set_required is False
    assert analysis.record_set_seed_evidence is None
    assert analysis.record_set_reentry_evidence is None


def test_prompt_analysis_routes_grounded_vehicle_checklist_source(monkeypatch) -> None:
    monkeypatch.setattr(
        conversation_scope,
        "execute_llm",
        Mock(
            return_value=SimpleNamespace(
                completion=SimpleNamespace(
                    text=json.dumps(
                        {
                            "action": "retrieve",
                            "reason": "차량 체크리스트 분석",
                            "analysis_mode": "analytics",
                            "family_categories": ["scalar"],
                            "record_set_required": False,
                            "data_sources": ["vehicle_checklists"],
                            "vehicle_checklist_evidence": "차량 체크리스트",
                            "counting_unit": "checklist_items",
                            "counting_unit_evidence": "체크리스트 전체 항목 수",
                        }
                    )
                )
            )
        ),
    )

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="차량 체크리스트 전체 항목 수",
    )

    assert analysis.should_search is True
    assert analysis.data_sources == (AnalysisDataSource.VEHICLE_CHECKLISTS,)
    assert analysis.counting_unit == AnalysisCountingUnit.CHECKLIST_ITEMS


def test_prompt_analysis_uses_grounded_counting_unit_to_reconcile_checklist_source(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        conversation_scope,
        "execute_llm",
        Mock(
            return_value=SimpleNamespace(
                completion=SimpleNamespace(
                    text=json.dumps(
                        {
                            "action": "retrieve",
                            "reason": "차량 체크리스트 항목 분석",
                            "analysis_mode": "analytics",
                            "family_categories": ["scalar"],
                            "record_set_required": False,
                            "data_sources": ["legacy_issues"],
                            "vehicle_checklist_evidence": None,
                            "counting_unit": "checklist_items",
                            "counting_unit_evidence": "체크리스트 전체 항목 수",
                        }
                    )
                )
            )
        ),
    )

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="차량 체크리스트 전체 항목 수",
    )

    assert analysis.data_sources == (AnalysisDataSource.VEHICLE_CHECKLISTS,)
    assert analysis.counting_unit == AnalysisCountingUnit.CHECKLIST_ITEMS


def test_prompt_analysis_ignores_ungrounded_vehicle_checklist_source(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        conversation_scope,
        "execute_llm",
        Mock(
            return_value=SimpleNamespace(
                completion=SimpleNamespace(
                    text=json.dumps(
                        {
                            "action": "retrieve",
                            "reason": "과거차 문제 분석",
                            "analysis_mode": "analytics",
                            "family_categories": ["scalar"],
                            "record_set_required": False,
                            "data_sources": ["vehicle_checklists"],
                            "vehicle_checklist_evidence": "질문에 없는 구절",
                            "counting_unit": "checklists",
                            "counting_unit_evidence": "질문에 없는 단위",
                        }
                    )
                )
            )
        ),
    )

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="과거차 문제 전체 건수",
    )

    assert analysis.data_sources == (AnalysisDataSource.LEGACY_ISSUES,)
    assert analysis.counting_unit is None


def test_prompt_analysis_missing_comparison_mode_requires_clarification(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        conversation_scope,
        "execute_llm",
        Mock(
            return_value=SimpleNamespace(
                completion=SimpleNamespace(
                    text=json.dumps(
                        {
                            "action": "retrieve",
                            "reason": "비교 요청이나 분석 모드 누락",
                            "analysis_mode": None,
                            "family_categories": ["comparison", "scalar"],
                            "record_set_required": False,
                            "record_set_seed_evidence": None,
                            "record_set_reentry_evidence": None,
                        }
                    )
                )
            )
        ),
    )

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="비교해줘",
    )

    assert analysis.analysis_mode == AnalysisMode.CLARIFY


def test_prompt_analysis_inconsistent_answer_action_preserves_retrieval_signal(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        conversation_scope,
        "execute_llm",
        Mock(
            return_value=SimpleNamespace(
                completion=SimpleNamespace(
                    text=json.dumps(
                        {
                            "action": "answer_only",
                            "reason": "inconsistent classifier output",
                            "analysis_mode": None,
                            "family_categories": ["comparison", "scalar"],
                            "record_set_required": False,
                        }
                    )
                )
            )
        ),
    )

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="두 범위를 비교해줘",
    )

    assert analysis.should_search is True
    assert analysis.action == "retrieve"
    assert analysis.analysis_mode == AnalysisMode.CLARIFY


def test_prompt_analysis_failure_is_fail_closed_for_unknown_source(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        conversation_scope,
        "execute_llm",
        Mock(side_effect=RuntimeError("provider unavailable")),
    )

    analysis = conversation_scope.analyze_legacy_issue_prompt(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="간헐 소음 과거 사례",
    )

    assert analysis.should_search is False
    assert analysis.action == "answer_only"
    assert analysis.reason == "intent_classifier_failed"
    assert analysis.analysis_mode is None


def test_turn_context_dispatches_every_question_to_durable_graph(monkeypatch) -> None:
    dispatch = Mock(return_value=("run-1", "artifact-1", "assistant-turn-1"))
    monkeypatch.setattr(
        conversation_scope,
        "dispatch_legacy_issue_analysis",
        dispatch,
    )
    conversation = cast(Any, SimpleNamespace(id="conversation-1"))

    context = _adapter_turn_context(
        messages=[
            {"role": "assistant", "content": "이전 답변"},
            {"role": "user", "content": "전체 건수와 대표 사례를 보고서로 작성해줘"},
        ],
        conversation=conversation,
    )

    assert context.prompt is None
    assert context.direct_response == "요청을 접수했습니다. 분석을 계속 진행합니다."
    assert context.artifacts == ()
    assert context.background_run_id == "run-1"
    assert context.background_artifact_id == "artifact-1"
    assert context.assistant_turn_persisted is True
    call = dispatch.call_args
    assert call.kwargs["conversation"] is conversation
    assert call.kwargs["question"] == "전체 건수와 대표 사례를 보고서로 작성해줘"
    assert call.kwargs["recent_messages"] == [
        {"role": "assistant", "content": "이전 답변"}
    ]


def test_assistant_answer_only_skips_analysis_orchestrator(monkeypatch) -> None:
    orchestrator = Mock(side_effect=AssertionError("analysis orchestrator must not run"))
    monkeypatch.setattr(
        ai_assistant,
        "analyze_legacy_issue_prompt",
        Mock(
            return_value=LegacyIssuePromptAnalysis(
                should_search=False,
                reason="greeting",
                action="answer_only",
            )
        ),
    )
    monkeypatch.setattr(
        ai_assistant,
        "run_legacy_issue_analysis",
        orchestrator,
    )

    result = _run_assistant(question="안녕하세요")

    assert result.analysis_result is None
    assert result.evidence == []
    assert result.search_profile.evidence_count == 0
    orchestrator.assert_not_called()


def test_assistant_returns_analysis_result_and_report_receives_exact_payload(
    monkeypatch,
) -> None:
    payload = _artifact_payload("analytics")
    outcome = _outcome(
        mode=AnalysisMode.ANALYTICS,
        analysis_result=payload,
        evidence=[],
        profile=_empty_profile(),
    )
    orchestrator = Mock(return_value=outcome)
    report = Mock(return_value=("정확 집계 보고", None))
    monkeypatch.setattr(
        ai_assistant,
        "analyze_legacy_issue_prompt",
        Mock(
            return_value=LegacyIssuePromptAnalysis(
                should_search=True,
                reason="analysis",
                action="retrieve",
            )
        ),
    )
    monkeypatch.setattr(
        ai_assistant,
        "run_legacy_issue_analysis",
        orchestrator,
    )
    monkeypatch.setattr(
        ai_assistant,
        "_generate_legacy_issue_report",
        report,
    )

    result = _run_assistant(question="전체 건수")

    assert result.answer_markdown == "정확 집계 보고"
    assert result.analysis_result is payload
    assert result.evidence == []
    assert report.call_args.kwargs["analysis_result"] is payload
    assert report.call_args.kwargs["evidence"] == []
    assert orchestrator.call_args.kwargs["audit_entity_id"] == result.run_id


def test_standalone_report_renderer_does_not_call_llm_or_invent_claims(
    monkeypatch,
) -> None:
    llm = Mock(side_effect=AssertionError("report renderer must not call the LLM"))
    monkeypatch.setattr(ai_assistant, "execute_llm", llm, raising=False)

    report, decision = ai_assistant._generate_legacy_issue_report(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="경영진 보고서",
        plan=_search_plan(),
        structured_plan=_analysis_plan(AnalysisMode.HYBRID),
        analysis_result=_report_artifact_payload(),
        analysis_degraded=False,
        evidence=[_evidence()],
        profile=_semantic_profile(),
        run_id="run-1",
    )

    assert decision is None
    assert "전체 문제 건수: **979건**" in report
    assert "2025 · 56건" in report
    assert "작성일" not in report
    assert "차종 수: 979" not in report
    llm.assert_not_called()


def test_assistant_endpoint_persists_and_returns_analysis_result(
    monkeypatch,
) -> None:
    payload = _artifact_payload("analytics")
    assistant_result = LegacyIssueAssistantResult(
        run_id="run-1",
        answer_markdown="정확 집계 보고",
        analysis_plan=_search_plan(),
        analysis_result=payload,
        evidence=[],
        search_profile=_empty_profile(),
        gateway_decisions=[],
    )
    assistant = Mock(return_value=assistant_result)
    db = _RecordingDb()
    monkeypatch.setattr(
        legacy_issue_router,
        "run_legacy_issue_assistant",
        assistant,
    )
    monkeypatch.setattr(
        legacy_issue_router,
        "_enabled_module_keys",
        Mock(return_value=frozenset({"compressor"})),
    )

    response = legacy_issue_router.run_legacy_issue_assistant_analysis(
        legacy_issue_router.LegacyIssueAssistantRunRequest(
            question="전체 건수",
            dataset_keys=["common-master"],
            evidence_limit=5,
        ),
        db=cast(Any, db),
        current_user=cast(
            Any,
            SimpleNamespace(
                id="user-1",
                display_name="User",
                full_name=None,
                email="user@example.com",
            ),
        ),
        current_workspace=cast(
            Any,
            SimpleNamespace(id="workspace-1"),
        ),
    )

    assert response.analysis_result == payload
    assert len(db.added) == 1
    assert db.added[0].analysis_result == payload
    assert db.commit_count == 1
    assert assistant.call_args.kwargs["module_keys"] == frozenset({"compressor"})


def _patch_orchestration(
    monkeypatch,
    *,
    plan: AnalysisPlanV1,
    decisions: list[AiGatewayDecision],
    execute_analysis: Mock,
    semantic_plan: Mock,
    semantic_search: Mock,
) -> Mock:
    active = DatasetFieldDefinition(
        key="region_zone",
        label_ko="권역",
        label_en="Region",
        field_type="select",
        options=("국내", "해외"),
    )
    inactive = DatasetFieldDefinition(
        key="ignored",
        label_ko="비활성",
        label_en="Inactive",
        active=False,
    )
    planner = Mock(return_value=(plan, decisions))
    monkeypatch.setattr(
        analysis_application,
        "get_dataset_definition_with_all_module_fields",
        Mock(return_value=SimpleNamespace(fields=(active, inactive))),
    )
    monkeypatch.setattr(
        analysis_application,
        "plan_legacy_issue_analysis",
        planner,
    )
    monkeypatch.setattr(
        analysis_application,
        "execute_analysis_plan",
        execute_analysis,
    )
    monkeypatch.setattr(
        analysis_application,
        "plan_legacy_issue_search",
        semantic_plan,
    )
    monkeypatch.setattr(
        analysis_application.retrieval_application,
        "search_legacy_issue_evidence_response",
        semantic_search,
    )
    return planner


def _semantic_mocks(
    *,
    evidence: list[LegacyIssueEvidence],
    profile: LegacyIssueSearchProfile,
    decision: AiGatewayDecision,
) -> tuple[Mock, Mock]:
    return (
        Mock(return_value=(_search_plan(), decision)),
        Mock(return_value=(evidence, profile)),
    )


def _run(
    *,
    routing_mode: AnalysisMode | None = None,
    record_set_required: bool = False,
    data_sources: tuple[AnalysisDataSource, ...] = (),
):
    return run_legacy_issue_analysis(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="권역별 문제 현황",
        requested_dataset_keys=None,
        module_keys=frozenset({"compressor"}),
        evidence_limit=5,
        audit_entity_id="run-1",
        routing_mode=routing_mode,
        record_set_required=record_set_required,
        data_sources=data_sources,
    )


def _adapter_turn_context(
    *,
    messages: list[dict[str, Any]],
    conversation: Any | None = None,
):
    return LegacyIssueConversationScopeAdapter().turn_context(
        db=cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        principal=cast(Any, object()),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        scope_resource_id="workspace",
        messages=messages,
        conversation=conversation,
    )


def _run_assistant(*, question: str):
    return run_legacy_issue_assistant(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question=question,
        dataset_keys=("common-master",),
        evidence_limit=5,
        module_keys=frozenset({"compressor"}),
    )


def _outcome(
    *,
    mode: AnalysisMode,
    analysis_result: dict[str, Any] | None,
    evidence: list[LegacyIssueEvidence],
    profile: LegacyIssueSearchProfile,
) -> LegacyIssueAnalysisOutcome:
    return LegacyIssueAnalysisOutcome(
        analysis_plan=_analysis_plan(mode),
        search_plan=_search_plan(),
        analysis_result=analysis_result,
        evidence=evidence,
        search_profile=profile,
        gateway_decisions=[],
    )


def _analysis_plan(mode: AnalysisMode) -> AnalysisPlanV1:
    queries: tuple[QueryRequestV1, ...] = ()
    if mode in {
        AnalysisMode.METADATA,
        AnalysisMode.ANALYTICS,
        AnalysisMode.HYBRID,
    }:
        queries = (
            QueryRequestV1(
                query_id="q1",
                family_id=QueryFamilyId.TOTAL_COUNT,
            ),
        )
    return AnalysisPlanV1(
        schema_version=1,
        mode=mode,
        queries=queries,
        clarification=None,
    )


def _artifact_payload(mode: str) -> dict[str, Any]:
    return {
        "version": 1,
        "mode": mode,
        "title": "과거차 정형 분석",
        "exactness": "exact",
        "scope": {
            "dataset_key": "common-master",
            "module_keys": ["compressor"],
            "revision_ids": ["revision-1"],
            "source_count": 7,
        },
        "queries": [
            {
                "id": "q1",
                "title": "전체 건수",
                "family_id": "total_count",
                "family_version": 1,
                "shape": "scalar",
                "exactness": "exact",
                "columns": [
                    {
                        "key": "issue_count",
                        "label": "전체 건수",
                        "type": "number",
                        "role": "metric",
                    }
                ],
                "rows": [{"issue_count": 7}],
                "totals": {"issue_count": 7},
                "coverage": [],
                "warnings": [],
                "truncated": False,
            }
        ],
        "warnings": [],
    }


def _report_artifact_payload() -> dict[str, Any]:
    def column(
        key: str,
        label: str,
        *,
        role: str,
        value_type: str = "text",
    ) -> dict[str, str]:
        return {
            "key": key,
            "label": label,
            "type": value_type,
            "role": role,
        }

    return {
        "version": 1,
        "mode": "hybrid",
        "title": "전체 현황 보고서",
        "exactness": "exact",
        "scope": {
            "dataset_key": "common-master",
            "data_sources": ["legacy_issues"],
            "module_keys": ["compressor"],
            "revision_ids": ["revision-1"],
            "source_count": 979,
            "source_counts": {"legacy_issues": 979},
        },
        "queries": [
            {
                "id": "report_total",
                "title": "전체 건수",
                "family_id": "total_count",
                "family_version": 1,
                "shape": "scalar",
                "exactness": "exact",
                "columns": [
                    column(
                        "issue_count",
                        "문제 건수",
                        role="metric",
                        value_type="number",
                    )
                ],
                "rows": [{"issue_count": 979}],
                "totals": {},
                "coverage": [],
                "warnings": [],
                "truncated": False,
            },
            {
                "id": "report_severity",
                "title": "중요도 분포",
                "family_id": "severity",
                "family_version": 1,
                "shape": "bar",
                "exactness": "exact",
                "columns": [
                    column("severity_grade", "중요도/등급", role="dimension"),
                    column(
                        "issue_count",
                        "문제 건수",
                        role="metric",
                        value_type="number",
                    ),
                ],
                "rows": [
                    {"severity_grade": "미입력", "issue_count": 842},
                    {"severity_grade": "A", "issue_count": 78},
                    {"severity_grade": "B", "issue_count": 51},
                    {"severity_grade": "C", "issue_count": 8},
                ],
                "totals": {
                    "filtered_population_count": 979,
                    "population_count": 137,
                },
                "coverage": [],
                "warnings": [],
                "truncated": False,
            },
            {
                "id": "report_top_vehicle_models",
                "title": "상위 차종",
                "family_id": "top_bottom_n",
                "family_version": 1,
                "shape": "bar",
                "exactness": "exact",
                "columns": [
                    column("vehicle_model", "차종", role="dimension"),
                    column(
                        "issue_count",
                        "문제 건수",
                        role="metric",
                        value_type="number",
                    ),
                ],
                "rows": [
                    {"vehicle_model": "CV", "issue_count": 39},
                    {"vehicle_model": "KA4 PE", "issue_count": 34},
                    {"vehicle_model": "OV1", "issue_count": 29},
                ],
                "totals": {
                    "filtered_population_count": 979,
                    "population_count": 979,
                },
                "coverage": [],
                "warnings": [],
                "truncated": False,
            },
            {
                "id": "report_occurrence_years",
                "title": "연도별 추이",
                "family_id": "time_series",
                "family_version": 1,
                "shape": "time_series",
                "exactness": "exact",
                "columns": [
                    column("occurrence_year", "발생 연도", role="dimension"),
                    column(
                        "issue_count",
                        "문제 건수",
                        role="metric",
                        value_type="number",
                    ),
                ],
                "rows": [
                    {"occurrence_year": "2020", "issue_count": 1},
                    {"occurrence_year": "2021", "issue_count": 2},
                    {"occurrence_year": "2022", "issue_count": 1},
                    {"occurrence_year": "2023", "issue_count": 3},
                    {"occurrence_year": "2024", "issue_count": 2},
                    {"occurrence_year": "2025", "issue_count": 56},
                    {"occurrence_year": "2026", "issue_count": 34},
                ],
                "totals": {
                    "filtered_population_count": 979,
                    "population_count": 125,
                },
                "coverage": [],
                "warnings": [],
                "truncated": False,
            },
            {
                "id": "report_date_coverage",
                "title": "발생일 입력 품질",
                "family_id": "missing_populated_rate",
                "family_version": 1,
                "shape": "scalar",
                "exactness": "exact",
                "columns": [
                    column(
                        "present_count",
                        "입력 건수",
                        role="metric",
                        value_type="number",
                    ),
                    column(
                        "missing_count",
                        "미입력 건수",
                        role="metric",
                        value_type="number",
                    ),
                ],
                "rows": [{"present_count": 125, "missing_count": 854}],
                "totals": {},
                "coverage": [
                    {
                        "field_key": "occurrence_date",
                        "label": "발생일",
                        "present_count": 125,
                        "missing_count": 854,
                        "invalid_count": 0,
                    }
                ],
                "warnings": [],
                "truncated": False,
            },
            {
                "id": "report_severity_coverage",
                "title": "중요도 입력 품질",
                "family_id": "missing_populated_rate",
                "family_version": 1,
                "shape": "scalar",
                "exactness": "exact",
                "columns": [
                    column(
                        "present_count",
                        "입력 건수",
                        role="metric",
                        value_type="number",
                    ),
                    column(
                        "missing_count",
                        "미입력 건수",
                        role="metric",
                        value_type="number",
                    ),
                ],
                "rows": [{"present_count": 137, "missing_count": 842}],
                "totals": {},
                "coverage": [
                    {
                        "field_key": "severity_grade",
                        "label": "중요도/등급",
                        "present_count": 137,
                        "missing_count": 842,
                        "invalid_count": 0,
                    }
                ],
                "warnings": [],
                "truncated": False,
            },
        ],
        "warnings": [],
    }


def _contract_artifact(
    *,
    rows: tuple[dict[str, Any], ...],
    mode: AnalysisMode = AnalysisMode.ANALYTICS,
) -> LegacyIssueAnalysisArtifactV1:
    scope = AnalysisScopeV1(
        workspace_id=str(uuid4()),
        dataset_key="common-master",
        module_keys=("compressor",),
        revision_ids=("revision-1",),
        revision_by_module={"compressor": "revision-1"},
        retrieval_partition_ids=("partition-1",),
        source_count=7,
    )
    result = AnalysisResultV1(
        schema_version=1,
        query_id="q1",
        title="전체 건수",
        family_id=QueryFamilyId.TOTAL_COUNT,
        family_version=1,
        output_shape="scalar",
        scope=scope,
        columns=(
            AnalysisColumnV1(
                key="issue_count",
                label="전체 건수",
                kind="metric",
                value_type="number",
            ),
        ),
        rows=rows,
    )
    return LegacyIssueAnalysisArtifactV1(
        version=1,
        mode=mode,
        title="과거차 정형 분석",
        scope=scope,
        results=(result,),
    )


def _search_plan() -> LegacyIssueAssistantSearchPlan:
    return sanitize_legacy_issue_search_plan(
        question="권역별 문제 현황",
        dataset_keys=("common-master",),
        primary_keywords=("문제",),
        intent="investigate",
    )


def _semantic_profile() -> LegacyIssueSearchProfile:
    return LegacyIssueSearchProfile(
        semantic_enabled=True,
        vector_extension_available=True,
        vector_index_available=True,
        trigram_extension_available=True,
        full_text_enabled=True,
        searched_dataset_keys=("common-master",),
        searched_revision_ids=("revision-1",),
        candidate_count=3,
        evidence_count=1,
        methods=("semantic",),
    )


def _empty_profile() -> LegacyIssueSearchProfile:
    return LegacyIssueSearchProfile(
        semantic_enabled=False,
        vector_extension_available=False,
        vector_index_available=False,
        trigram_extension_available=False,
        full_text_enabled=False,
        searched_dataset_keys=("common-master",),
        searched_revision_ids=("revision-1",),
        candidate_count=0,
        evidence_count=0,
        methods=(),
    )


def _evidence() -> LegacyIssueEvidence:
    return LegacyIssueEvidence(
        evidence_id="E1",
        dataset_key="common-master",
        dataset_title="과거차 문제점",
        revision_id="revision-1",
        revision_no=1,
        record_id="record-1",
        stable_record_id="stable-1",
        label="간헐 소음",
        values={"symptom": "간헐 소음"},
        matched_fields=("symptom",),
        matched_chunks=(),
        score=0.91,
        methods=("semantic",),
    )


def _decision(name: str) -> AiGatewayDecision:
    return cast(AiGatewayDecision, SimpleNamespace(name=name))


class _RecordingDb:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commit_count = 0

    def add(self, value: Any) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commit_count += 1
