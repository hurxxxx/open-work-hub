from __future__ import annotations

import asyncio
from types import SimpleNamespace

from langgraph.checkpoint.memory import MemorySaver
import pytest

from open_alm_api.core.llm_errors import LlmRuntimeError
from open_alm_api.domains.ai_graph.contracts import AiGraphNodeResult
from open_alm_api.domains.ai_graph.runtime import AiGraphRuntimeContext, compile_graph
from open_alm_api.domains.legacy_issues.analysis_graph.application import (
    LegacyIssueAnalysisIncompleteError,
    LegacyIssueGraphDependencies,
    _source_payload,
    build_legacy_issue_node_adapters,
)
from open_alm_api.domains.legacy_issues.analysis_graph.contracts import (
    AnalysisDataBundle,
    AnalysisEvidence,
    AnalysisInterpretation,
    AnalysisQueryResult,
)
from open_alm_api.domains.legacy_issues.analysis_graph.llm import (
    GraphStructuredOutputError,
    parse_json_object,
)
from open_alm_api.domains.legacy_issues.analysis_graph.topology import (
    legacy_issue_analysis_graph_spec,
)


def test_legacy_issue_graph_topology_compiles_with_all_node_adapters() -> None:
    spec = legacy_issue_analysis_graph_spec()

    async def adapter(_state, _context) -> AiGraphNodeResult:
        return AiGraphNodeResult(output={})

    compiled = compile_graph(
        spec,
        {node.node_id: adapter for node in spec.nodes},
        MemorySaver(),
    )

    assert compiled.spec.graph_id == "legacy_issues.analysis"
    assert compiled.spec.graph_version == "2.0.0"
    assert len(compiled.spec.nodes) == 18
    assert {
        node.node_id
        for node in compiled.spec.nodes
        if node.node_id.endswith("analyst")
    } == {
        "quantitative_analyst",
        "evidence_analyst",
        "checklist_analyst",
    }


def test_parse_json_object_accepts_fenced_or_surrounded_json() -> None:
    assert parse_json_object('```json\n{"grounded":true}\n```') == {
        "grounded": True
    }
    assert parse_json_object('result: {"report_requested":false}') == {
        "report_requested": False
    }


def test_parse_json_object_rejects_non_object() -> None:
    try:
        parse_json_object("[1,2,3]")
    except ValueError as error:
        assert "object" in str(error)
    else:
        raise AssertionError("non-object JSON must be rejected")


def test_interpretation_failure_does_not_silently_change_requested_output() -> None:
    class InvalidJsonGateway:
        def invoke(self, _request):
            return SimpleNamespace(text="not-json")

    dependencies = LegacyIssueGraphDependencies(
        gateway=InvalidJsonGateway(),
        data_provider=SimpleNamespace(),
        artifact_writer=SimpleNamespace(),
    )
    adapter = build_legacy_issue_node_adapters(dependencies)["interpret"]

    with pytest.raises(GraphStructuredOutputError):
        asyncio.run(
            adapter(
                {
                    "inputs": {
                        "question": "결빙 문제 보고서를 작성해줘",
                        "recent_messages": [],
                    }
                },
                _runtime_context(),
            )
        )


def test_grounding_review_degrades_conservatively_when_structured_output_is_invalid(
) -> None:
    class InvalidJsonGateway:
        def invoke(self, _request):
            return SimpleNamespace(text="not-json")

    dependencies = LegacyIssueGraphDependencies(
        gateway=InvalidJsonGateway(),
        data_provider=SimpleNamespace(),
        artifact_writer=SimpleNamespace(),
    )
    adapter = build_legacy_issue_node_adapters(dependencies)["grounding_review"]

    result = asyncio.run(
        adapter(
            _grounding_state(),
            _runtime_context(),
        )
    )

    assert result.output["grounded"] is False
    assert result.output["correction_instructions"]


def test_grounding_review_does_not_hide_gateway_failures() -> None:
    class FailingGateway:
        def invoke(self, _request):
            raise RuntimeError("gateway unavailable")

    dependencies = LegacyIssueGraphDependencies(
        gateway=FailingGateway(),
        data_provider=SimpleNamespace(),
        artifact_writer=SimpleNamespace(),
    )
    adapter = build_legacy_issue_node_adapters(dependencies)["grounding_review"]

    with pytest.raises(RuntimeError, match="gateway unavailable"):
        asyncio.run(adapter(_grounding_state(), _runtime_context()))


def test_grounding_review_degrades_conservatively_after_provider_timeout() -> None:
    class TimeoutGateway:
        def invoke(self, _request):
            raise LlmRuntimeError("Request timed out.")

    dependencies = LegacyIssueGraphDependencies(
        gateway=TimeoutGateway(),
        data_provider=SimpleNamespace(),
        artifact_writer=SimpleNamespace(),
    )
    adapter = build_legacy_issue_node_adapters(dependencies)["grounding_review"]

    result = asyncio.run(adapter(_grounding_state(), _runtime_context()))

    assert result.output["grounded"] is False
    assert result.output["correction_instructions"]


def test_graph_llm_defers_timeout_to_the_configured_provider_pool() -> None:
    requests = []

    class CapturingGateway:
        def invoke(self, request):
            requests.append(request)
            return SimpleNamespace(text='{"grounded":true}')

    dependencies = LegacyIssueGraphDependencies(
        gateway=CapturingGateway(),
        data_provider=SimpleNamespace(),
        artifact_writer=SimpleNamespace(),
    )
    adapter = build_legacy_issue_node_adapters(dependencies)["grounding_review"]

    asyncio.run(adapter(_grounding_state(), _runtime_context()))

    assert requests[0].timeout_seconds is None


def test_llm_source_projection_reserves_evidence_and_hides_internal_query_details() -> None:
    data = AnalysisDataBundle(
        query_results=[
            AnalysisQueryResult(
                query_id=f"query-{index}",
                recipe_id="issue_matrix",
                sql="SELECT internal_sql FROM restricted_view",
                columns=["value"],
                rows=[{"value": "x" * 500} for _ in range(50)],
                row_count=50,
            )
            for index in range(3)
        ],
        evidence=[
            AnalysisEvidence(
                evidence_id="E1",
                source_kind="legacy_issue",
                title="결빙 사례",
                excerpt="저온 조건에서 결빙이 확인됨",
            )
        ],
    )

    payload = _source_payload(data, max_chars=30_000)

    assert any(item.get("evidence_id") == "E1" for item in payload)
    serialized = str(payload)
    assert "internal_sql" not in serialized
    assert "query-0" not in serialized


def test_llm_source_projection_preserves_query_semantics_and_sample_role() -> None:
    data = AnalysisDataBundle(
        query_results=[
            AnalysisQueryResult(
                query_id="query-matrix-1",
                recipe_id="issue_matrix",
                recipe_arguments={
                    "row_dimension": "occurrence_stage",
                    "column_dimension": "process_name",
                    "limit": 50,
                },
                sql="SELECT hidden_sql",
                columns=[
                    "row_value",
                    "column_value",
                    "issue_count",
                    "row_total_count",
                    "row_share",
                ],
                rows=[
                    {
                        "row_value": "MP",
                        "column_value": "조립",
                        "issue_count": 11,
                        "row_total_count": 147,
                        "row_share": 7.48,
                    }
                ],
                row_count=50,
            )
        ],
        evidence=[
            AnalysisEvidence(
                evidence_id="E1",
                source_kind="legacy_issue",
                title="대표 사례",
                excerpt="확인된 단일 사례",
            )
        ],
    )

    payload = _source_payload(data)
    query = next(item for item in payload if item["source_type"] == "query")
    example = next(item for item in payload if item["source_type"] == "evidence")

    assert query["source_label"] == "과거차 문제점 복합 기준 교차 집계"
    assert query["recipe_arguments"]["row_dimension"] == "occurrence_stage"
    assert query["counting_unit"] == "issues"
    assert query["selection"]["population_complete"] is False
    assert query["result_row_count_is_business_metric"] is False
    assert "recipe_id" not in query
    assert query["row_atomicity"] == "one row is one indivisible result record"
    assert example["qualitative_example"] is True
    assert example["population_metric"] is False


def test_interpretation_normalizes_business_data_for_evidence_request() -> None:
    interpretation = AnalysisInterpretation.model_validate(
        {
            "needs_business_data": False,
            "needs_semantic_evidence": True,
        }
    )

    assert interpretation.needs_business_data is True


def test_llm_source_projection_exposes_draft_status_without_revision_id() -> None:
    data = AnalysisDataBundle(
        evidence=[
            AnalysisEvidence(
                evidence_id="E1",
                source_kind="legacy_issue",
                title="결빙 사례",
                excerpt="증발기 결빙이 확인됨",
                revision_id="revision-private",
                metadata={"revision_status": "draft"},
            )
        ]
    )

    payload = _source_payload(data)
    evidence = next(item for item in payload if item["source_type"] == "evidence")

    assert evidence["source_status"] == "draft"
    assert "revision-private" not in str(payload)


def test_llm_query_projection_discloses_draft_scope_without_revision_id() -> None:
    data = AnalysisDataBundle.model_validate(
        {
            "query_results": [
                {
                    "query_id": "query-1",
                    "recipe_id": "issue_total",
                    "sql": "SELECT hidden",
                    "columns": ["issue_count"],
                    "rows": [{"issue_count": 1}],
                    "row_count": 1,
                }
            ],
            "source_revisions": [
                {
                    "revision_id": "revision-private",
                    "status": "draft",
                    "module_key": "aircon",
                }
            ],
        }
    )

    payload = _source_payload(data)
    query = next(item for item in payload if item["source_type"] == "query")

    assert query["source_status"] == "draft"
    assert "revision-private" not in str(payload)


def test_answer_fails_closed_when_agent_did_not_complete() -> None:
    class FailingGateway:
        def invoke(self, _request):
            raise AssertionError("incomplete analysis must not call the answer LLM")

    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=FailingGateway(),
            data_provider=SimpleNamespace(),
            artifact_writer=SimpleNamespace(),
        )
    )
    state = {
        "inputs": {"question": "에바(증발기)가 얼어서 문제된 이력이 있어?"},
        "outputs": {
            "analyze_data": {
                "query_results": [
                    {
                        "query_id": "q1",
                        "recipe_id": "issue_total",
                        "sql": "SELECT hidden",
                        "rows": [{"issue_count": 0}],
                        "row_count": 1,
                    }
                ],
                "evidence": [
                    {
                        "evidence_id": "E1",
                        "source_kind": "legacy_issue",
                        "title": "SW PSV2 / EVA FREEZE",
                        "excerpt": "EVA FREEZE 현상이 확인됨",
                        "metadata": {"revision_status": "draft"},
                    }
                ],
                "limitations": ["analysis_agent:model_error"],
            }
        },
    }

    with pytest.raises(
        LegacyIssueAnalysisIncompleteError,
        match="legacy_issue_analysis_data_incomplete",
    ):
        asyncio.run(adapters["answer_draft"](state, _runtime_context()))


def test_output_routing_fails_closed_before_persistence_on_incomplete_analysis() -> None:
    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=SimpleNamespace(),
            data_provider=SimpleNamespace(),
            artifact_writer=SimpleNamespace(),
        )
    )
    state = {
        "outputs": {
            "interpret": {"report_requested": False},
            "analyze_data": {
                "limitations": ["one_or_more_queries_failed"],
            },
        },
    }

    with pytest.raises(LegacyIssueAnalysisIncompleteError):
        asyncio.run(adapters["choose_output"](state, _runtime_context()))


def test_output_routing_allows_recovered_agent_with_grounded_sources() -> None:
    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=SimpleNamespace(),
            data_provider=SimpleNamespace(),
            artifact_writer=SimpleNamespace(),
        )
    )
    state = {
        "outputs": {
            "interpret": {"report_requested": False},
            "analyze_data": {
                "query_results": [
                    {
                        "query_id": "query-recovered",
                        "recipe_id": "issue_total",
                        "sql": "SELECT COUNT(*) AS issue_count",
                        "columns": ["issue_count"],
                        "rows": [{"issue_count": 5}],
                        "row_count": 1,
                    }
                ],
                "source_snapshot_captured": True,
                "execution_warnings": ["analysis_agent:max_steps"],
            },
        },
    }

    result = asyncio.run(adapters["choose_output"](state, _runtime_context()))

    assert result.route == "answer"


def test_persistence_rechecks_incomplete_analysis_after_checkpoint_resume() -> None:
    class FailingWriter:
        def persist(self, **_kwargs):
            raise AssertionError("incomplete analysis must never be persisted")

    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=SimpleNamespace(),
            data_provider=SimpleNamespace(),
            artifact_writer=FailingWriter(),
        )
    )
    state = {
        "inputs": {"question": "결빙 문제 이력이 있어?"},
        "outputs": {
            "analyze_data": {
                "limitations": ["analysis_agent:model_error"],
            },
            "answer_draft": "이전 체크포인트 답변",
        },
    }

    with pytest.raises(LegacyIssueAnalysisIncompleteError):
        asyncio.run(adapters["persist_answer"](state, _runtime_context()))


def test_old_sql_checkpoint_without_revision_snapshot_fails_closed() -> None:
    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=SimpleNamespace(),
            data_provider=SimpleNamespace(),
            artifact_writer=SimpleNamespace(),
        )
    )
    state = {
        "outputs": {
            "interpret": {"report_requested": False},
            "analyze_data": {
                "query_results": [
                    {
                        "query_id": "query-old-checkpoint",
                        "sql": "SELECT hidden",
                        "columns": ["issue_id"],
                        "rows": [],
                        "row_count": 0,
                    }
                ],
            },
        },
    }

    with pytest.raises(
        LegacyIssueAnalysisIncompleteError,
        match="legacy_issue_analysis_revision_snapshot_missing",
    ):
        asyncio.run(adapters["choose_output"](state, _runtime_context()))


def test_empty_current_revision_snapshot_is_not_mistaken_for_old_checkpoint() -> None:
    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=SimpleNamespace(),
            data_provider=SimpleNamespace(),
            artifact_writer=SimpleNamespace(),
        )
    )
    state = {
        "outputs": {
            "interpret": {"report_requested": False},
            "analyze_data": {
                "query_results": [
                    {
                        "query_id": "query-empty-current-scope",
                        "sql": "SELECT hidden",
                        "columns": ["issue_count"],
                        "rows": [{"issue_count": 0}],
                        "row_count": 1,
                    }
                ],
                "source_snapshot_captured": True,
            },
        },
    }

    result = asyncio.run(adapters["choose_output"](state, _runtime_context()))

    assert result.route == "answer"


def test_old_evidence_checkpoint_without_revision_snapshot_fails_closed() -> None:
    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=SimpleNamespace(),
            data_provider=SimpleNamespace(),
            artifact_writer=SimpleNamespace(),
        )
    )
    state = {
        "outputs": {
            "interpret": {"report_requested": False},
            "analyze_data": {
                "evidence": [
                    {
                        "evidence_id": "E1",
                        "source_kind": "legacy_issue",
                        "title": "결빙 사례",
                        "excerpt": "증발기 결빙 이력",
                        "revision_id": "revision-old-checkpoint",
                    }
                ],
            },
        },
    }

    with pytest.raises(
        LegacyIssueAnalysisIncompleteError,
        match="legacy_issue_analysis_revision_snapshot_missing",
    ):
        asyncio.run(adapters["choose_output"](state, _runtime_context()))


def test_answer_with_unknown_citation_falls_back_to_captured_sources() -> None:
    class UngroundedGateway:
        def invoke(self, _request):
            return SimpleNamespace(text="문제 이력이 있습니다. [E999]")

    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=UngroundedGateway(),
            data_provider=SimpleNamespace(),
            artifact_writer=SimpleNamespace(),
        )
    )
    state = {
        "inputs": {"question": "결빙 문제 이력이 있어?"},
        "outputs": {
            "analyze_data": {
                "evidence": [
                    {
                        "evidence_id": "E1",
                        "source_kind": "legacy_issue",
                        "title": "결빙 사례",
                        "excerpt": "저온 조건에서 결빙이 확인됨",
                        "metadata": {"revision_status": "published"},
                    }
                ],
                "source_snapshot_captured": True,
            }
        },
    }

    result = asyncio.run(adapters["answer_draft"](state, _runtime_context()))

    assert "[E999]" not in result.output
    assert "결빙 사례 (게시됨) [E1]" in result.output


def test_evidence_only_answer_without_citation_falls_back_to_source_card() -> None:
    class UncitedGateway:
        def invoke(self, _request):
            return SimpleNamespace(text="결빙 문제 이력이 있습니다.")

    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=UncitedGateway(),
            data_provider=SimpleNamespace(),
            artifact_writer=SimpleNamespace(),
        )
    )
    state = {
        "inputs": {"question": "결빙 문제 이력이 있어?"},
        "outputs": {
            "analyze_data": {
                "evidence": [
                    {
                        "evidence_id": "E1",
                        "source_kind": "legacy_issue",
                        "title": "결빙 사례",
                        "excerpt": "저온 조건에서 결빙이 확인됨",
                        "metadata": {"revision_status": "published"},
                    }
                ],
                "source_snapshot_captured": True,
            }
        },
    }

    result = asyncio.run(adapters["answer_draft"](state, _runtime_context()))

    assert "결빙 사례 (게시됨) [E1]" in result.output


def test_llm_source_projection_prioritizes_aggregate_over_large_detail_results() -> None:
    data = AnalysisDataBundle(
        query_results=[
            AnalysisQueryResult(
                query_id="query-details-1",
                recipe_id="issue_details",
                recipe_arguments={"limit": 50},
                sql="SELECT hidden_detail_sql",
                columns=["issue_id", "cause", "countermeasure"],
                rows=[
                    {
                        "issue_id": f"issue-{index}",
                        "cause": "원인" * 1_000,
                        "countermeasure": "대책" * 1_000,
                    }
                    for index in range(50)
                ],
                row_count=50,
            ),
            AnalysisQueryResult(
                query_id="query-supplier-summary",
                recipe_id="issue_breakdown",
                recipe_arguments={"dimension": "supplier", "limit": 200},
                sql="SELECT hidden_summary_sql",
                columns=[
                    "dimension_value",
                    "dimension_missing",
                    "issue_count",
                    "total_issue_count",
                    "issue_share",
                ],
                rows=[
                    {
                        "dimension_value": None,
                        "dimension_missing": True,
                        "issue_count": 714,
                        "total_issue_count": 979,
                        "issue_share": 72.93,
                    }
                ],
                row_count=1,
            ),
        ]
    )

    payload = _source_payload(data, max_chars=8_000)

    assert any(
        item.get("source_label") == "과거차 문제점 단일 기준 분포"
        and item["rows"][0]["issue_count"] == 714
        for item in payload
    )


def test_llm_projection_preserves_distinct_checklist_and_issue_rankings() -> None:
    shared_arguments = {"dimension": "vehicle_model", "limit": 100}
    data = AnalysisDataBundle(
        query_results=[
            AnalysisQueryResult(
                query_id="coverage",
                recipe_id="issue_checklist_coverage",
                recipe_arguments={**shared_arguments, "sort_direction": "ASC"},
                sql="SELECT coverage",
                columns=["dimension_value", "issue_count", "coverage_rate"],
                rows=[
                    {
                        "dimension_value": "CV",
                        "issue_count": 39,
                        "coverage_rate": 0,
                    }
                ],
                row_count=1,
            ),
            AnalysisQueryResult(
                query_id="ranking",
                recipe_id="issue_ranked_summary",
                recipe_arguments={"dimension": "vehicle_model", "top_n": 10},
                sql="SELECT ranking",
                columns=["dimension_value", "issue_count"],
                rows=[{"dimension_value": "OV1", "issue_count": 29}],
                row_count=1,
            ),
        ],
        capability_limitations=["지원되지 않는 요청 지표입니다."],
    )

    payload = _source_payload(data)

    assert any(item.get("source_type") == "capability_limitation" for item in payload)
    query_sources = [item for item in payload if item.get("source_type") == "query"]
    assert len(query_sources) == 2
    assert {
        item["rows"][0]["dimension_value"] for item in query_sources
    } == {"CV", "OV1"}


def test_invalid_grounding_json_does_not_abort_the_report_graph() -> None:
    class ScriptedGateway:
        def invoke(self, request):
            outputs = {
                "legacy_issues.request_interpret": (
                    '{"report_requested":true,"needs_semantic_evidence":true}'
                ),
                "legacy_issues.report_template": "# 보고서 목차",
                "legacy_issues.evidence_analyst": "사례 근거를 확인했습니다.",
                "legacy_issues.report_draft": "# 초안\n\n근거 [E1]",
                "legacy_issues.grounding_review": "not-json",
                "legacy_issues.report_finalize": "# 최종 보고서\n\n확인된 사례 [E1]",
            }
            return SimpleNamespace(text=outputs[request.workload_id])

    class DataProvider:
        def analyze(self, **_kwargs):
                return AnalysisDataBundle(
                evidence=[
                    AnalysisEvidence(
                        evidence_id="E1",
                        source_kind="legacy_issue",
                        title="결빙 관련 사례",
                        excerpt="저온 조건에서 결빙 현상이 확인됨",
                        record_id="issue-1",
                        )
                    ],
                    source_snapshot_captured=True,
                )

    class ArtifactWriter:
        def persist(self, **kwargs):
            return {
                "artifact_id": "artifact-1",
                "artifact_type": kwargs["artifact_type"],
            }

    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=ScriptedGateway(),
            data_provider=DataProvider(),
            artifact_writer=ArtifactWriter(),
        )
    )
    compiled = compile_graph(
        legacy_issue_analysis_graph_spec(),
        adapters,
        MemorySaver(),
    )

    async def invoke() -> dict:
        return await compiled.graph.ainvoke(
            {
                "inputs": {
                    "question": "결빙 관련 문제를 보고해줘",
                    "recent_messages": [],
                },
                "outputs": {},
                "errors": {},
                "routes": {},
            },
            config={"configurable": {"thread_id": "run-report-1"}},
            context=_runtime_context(),
        )

    state = asyncio.run(invoke())

    assert state["outputs"]["grounding_review"]["grounded"] is False
    assert state["outputs"]["persist_report"] == {
        "artifact_id": "artifact-1",
        "artifact_type": "report",
    }
    assert "persist_source_fallback" not in state["outputs"]


def test_report_finalizer_uses_deterministic_capability_limit() -> None:
    class FailingGateway:
        def invoke(self, _request):
            raise AssertionError("LLM must not finalize an unsupported metric")

    adapters = build_legacy_issue_node_adapters(
        LegacyIssueGraphDependencies(
            gateway=FailingGateway(),
            data_provider=SimpleNamespace(),
            artifact_writer=SimpleNamespace(),
        )
    )
    state = {
        "inputs": {
            "question": "최종 대책일까지의 평균 대응기간을 알려줘",
        },
        "outputs": {
            "analyze_data": {
                "query_results": [],
                "evidence": [],
                "capability_limitations": [
                    "최종 대책일 컬럼이 없어 계산할 수 없습니다."
                ],
            }
        },
    }

    result = asyncio.run(adapters["report_finalize"](state, _runtime_context()))

    assert "최종 대책일 컬럼이 없어 계산할 수 없습니다." in result.output


def _grounding_state() -> dict:
    return {
        "inputs": {"question": "결빙 관련 문제를 보고해줘"},
        "outputs": {
            "analyze_data": {
                "query_results": [],
                "evidence": [],
                "retrieval_backend_ids": [],
                "limitations": ["analysis_agent:model_error"],
            },
            "report_draft": "# 결빙 관련 문제 보고서\n\n확인된 근거가 없습니다.",
        },
    }


def _runtime_context() -> AiGraphRuntimeContext:
    async def progress(_node_id: str) -> None:
        return None

    return AiGraphRuntimeContext(
        run_id="run-1",
        workspace_id="workspace-1",
        requested_by_user_id="user-1",
        app_id="legacy-issues",
        conversation_id="conversation-1",
        progress_callback=progress,
    )
