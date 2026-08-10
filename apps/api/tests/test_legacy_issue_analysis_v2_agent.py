from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ai_do_api.domains.ai.gateway import LlmWorkloadContext
from ai_do_api.domains.legacy_issues.analysis_v2.agent import (
    LEGACY_ISSUES_SQL_AGENT_WORKLOAD_ID,
    AiDoChatModel,
    build_sql_agent,
    run_analysis_tools,
)
from ai_do_api.domains.legacy_issues.analysis_v2.contracts import RetrievalHit
from ai_do_api.domains.legacy_issues.analysis_v2.execution import (
    AuthorizedQueryRequest,
    RawQueryResult,
    SafeAnalysisQueryService,
)
from ai_do_api.domains.legacy_issues.analysis_v2.recipes import default_recipe_catalog
from ai_do_api.domains.legacy_issues.analysis_v2.retrieval import (
    LlamaIndexRetrieverAdapter,
    RetrievalRequest,
)
from ai_do_api.domains.legacy_issues.analysis_v2.tools import AnalysisToolset


class _QueryGateway:
    gateway_id = "test"

    def execute(self, request: AuthorizedQueryRequest) -> RawQueryResult:
        del request
        return RawQueryResult(
            column_names=("issue_count",),
            rows=((2,),),
            elapsed_ms=4,
        )


class _Retriever:
    def __init__(self, backend_id: str) -> None:
        self.backend_id = backend_id

    def retrieve(self, request: RetrievalRequest) -> tuple[RetrievalHit, ...]:
        return (
            RetrievalHit(
                hit_id=f"{self.backend_id}-1",
                text=f"context for {request.query}",
                score=1,
                resource_type="analysis_metadata",
                resource_id="recipe-1",
                partition_id="partition-1",
            ),
        )


class _CompletionSequence:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.outputs = [
            (
                '{"tool":"run_recipe","arguments":'
                '{"recipe_id":"issue_total","version":1,"parameters":{}}}'
            ),
            '{"final":"허가된 데이터 기준 전체 문제점은 2건입니다."}',
        ]

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return SimpleNamespace(
            completion=SimpleNamespace(text=self.outputs.pop(0)),
        )


class _CompletionFailsAfterTool:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                completion=SimpleNamespace(
                    text=(
                        '{"tool":"run_recipe","arguments":'
                        '{"recipe_id":"issue_total","version":1,"parameters":{}}}'
                    )
                )
            )
        raise TimeoutError("model timed out")


def _toolset() -> AnalysisToolset:
    return AnalysisToolset(
        catalog=default_recipe_catalog(),
        query_service=SafeAnalysisQueryService(gateway=_QueryGateway()),
        metadata_retriever=LlamaIndexRetrieverAdapter(
            backend=_Retriever("metadata"),
            kind="analysis_metadata",
        ),
        evidence_retriever=LlamaIndexRetrieverAdapter(
            backend=_Retriever("evidence"),
            kind="legacy_evidence",
        ),
    )


def test_ai_do_chat_model_synthesizes_tool_calls_and_returns_typed_transcript() -> None:
    completions = _CompletionSequence()
    model = AiDoChatModel(
        db=object(),  # type: ignore[arg-type]
        context=LlmWorkloadContext(
            source="legacy_issues.analysis_v2.test",
            workspace_id="workspace-1",
            actor_user_id="user-1",
            app_id="legacy-issues",
        ),
        completion_executor=completions,
        agent_run_id="run-1",
        conversation_id="conversation-1",
    )
    agent = build_sql_agent(model=model, toolset=_toolset())
    graph_nodes = agent.graph.get_graph().nodes
    assert "model" in graph_nodes
    assert "tools" in graph_nodes

    result = run_analysis_tools(
        agent,
        messages=[{"role": "user", "content": "전체 문제점 건수"}],
    )

    assert result.status == "completed"
    assert result.final_text == "허가된 데이터 기준 전체 문제점은 2건입니다."
    assert result.steps == 2
    assert len(result.transcript) == 1
    assert result.transcript[0].tool == "run_recipe"
    assert result.transcript[0].status == "succeeded"
    query_result = result.tool_results[0]["result"]
    assert query_result["status"] == "succeeded"
    assert query_result["recipe"] == {"recipe_id": "issue_total", "version": 1}
    assert query_result["parameterized_sql"]
    assert query_result["rows"] == [{"issue_count": 2}]

    first_args, first_kwargs = completions.calls[0]
    assert first_args[0] == LEGACY_ISSUES_SQL_AGENT_WORKLOAD_ID
    first_messages = first_kwargs["messages"]
    assert [message["role"] for message in first_messages] == ["system", "user"]
    assert "Available tools" in first_messages[0]["content"]
    assert "You analyze legacy vehicle issues" in first_messages[0]["content"]
    assert first_messages[1] == {"role": "user", "content": "전체 문제점 건수"}
    assert first_kwargs["context_pack"].messages == first_messages
    assert first_kwargs["agent_run_id"] == "run-1"
    assert first_kwargs["conversation_id"] == "conversation-1"
    assert "timeout_seconds" not in first_kwargs


def test_analysis_agent_preserves_completed_tool_results_on_later_model_error(
    caplog,
) -> None:
    model = AiDoChatModel(
        db=object(),  # type: ignore[arg-type]
        context=LlmWorkloadContext(
            source="legacy_issues.analysis_v2.test",
            workspace_id="workspace-1",
            actor_user_id="user-1",
            app_id="legacy-issues",
        ),
        completion_executor=_CompletionFailsAfterTool(),
    )

    with caplog.at_level(
        "WARNING",
        logger="ai_do_api.domains.legacy_issues.analysis_v2.agent",
    ):
        result = run_analysis_tools(
            build_sql_agent(model=model, toolset=_toolset()),
            graph_run_id="run-model-error",
            messages=[{"role": "user", "content": "전체 문제점 건수"}],
        )

    assert result.status == "model_error"
    assert len(result.transcript) == 1
    assert result.transcript[0].tool == "run_recipe"
    assert result.tool_results[0]["result"]["rows"] == [{"issue_count": 2}]
    record = next(
        item
        for item in caplog.records
        if item.getMessage()
        == "Legacy issue analysis agent stopped before final action"
    )
    assert record.graph_run_id == "run-model-error"
    assert record.analysis_agent_status == "model_error"
    assert record.error_type == "TimeoutError"
    assert record.completed_tool_calls == 1
