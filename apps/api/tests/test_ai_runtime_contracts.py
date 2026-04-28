from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aidoo_api.app import runtime_registry_validation_exception_handler
from aidoo_api.domains.ai.runtime import (
    AgentInvocationContract,
    AgentInvocationSpec,
    AgentRunContract,
    AgentTraceEventContract,
    EvidenceCoverage,
    EvidenceItem,
    EvidencePacket,
    ExecutionGraph,
    QueryPlan,
    RuntimeRegistry,
    RuntimeRegistryValidationError,
    RuntimeTraceSequencer,
    validate_execution_graph,
)
from aidoo_api.domains.ai.runtime.metrics import (
    record_inspection_request,
    record_shadow_write_failure,
    record_trace_event,
    record_trace_payload_truncated,
)


def _registry(*, include_external_search: bool = False) -> RuntimeRegistry:
    agent_ids = {
        "manager.orchestrator",
        "domain.meeting",
        "domain.docs",
        "search.executor",
        "verifier.grounding",
        "writer.template",
    }
    if include_external_search:
        agent_ids.add("external.search")
    return RuntimeRegistry(
        agent_ids=frozenset(agent_ids),
        intents=frozenset({"read", "report"}),
        domains=frozenset({"meeting", "docs", "rag"}),
        output_kinds=frozenset({"answer", "artifact"}),
    )


def test_execution_graph_validates_registry_strings() -> None:
    graph = ExecutionGraph(
        intent="report",
        domains=["meeting", "docs"],
        risk="medium",
        output_kind="artifact",
        invocations=[
            AgentInvocationSpec(
                agent_id="domain.meeting",
                purpose="collect meeting evidence",
            ),
            AgentInvocationSpec(
                agent_id="writer.template",
                must_run_after=["domain.meeting"],
                purpose="write draft",
            ),
        ],
        requires_verifier=True,
    )

    assert validate_execution_graph(graph, registry=_registry()) == graph


def test_execution_graph_rejects_unknown_registry_value() -> None:
    graph = ExecutionGraph(
        intent="report",
        domains=["finance"],
        risk="medium",
        output_kind="artifact",
        invocations=[],
    )

    with pytest.raises(RuntimeRegistryValidationError, match="unknown domain"):
        validate_execution_graph(graph, registry=_registry())


def test_execution_graph_blocks_direct_external_search_invocation() -> None:
    graph = ExecutionGraph(
        intent="read",
        domains=["rag"],
        risk="low",
        output_kind="answer",
        invocations=[
            AgentInvocationSpec(
                agent_id="external.search",
                purpose="search public web",
            )
        ],
    )

    with pytest.raises(RuntimeRegistryValidationError, match="external.search"):
        validate_execution_graph(graph, registry=_registry(include_external_search=True))


def test_execution_graph_rejects_unknown_dependency() -> None:
    graph = ExecutionGraph(
        intent="report",
        domains=["meeting"],
        risk="medium",
        output_kind="artifact",
        invocations=[
            AgentInvocationSpec(
                agent_id="writer.template",
                must_run_after=["domain.missing"],
                purpose="write draft",
            )
        ],
    )

    with pytest.raises(RuntimeRegistryValidationError, match="depends on unknown"):
        validate_execution_graph(graph, registry=_registry())


def test_execution_graph_rejects_duplicate_domains() -> None:
    with pytest.raises(ValidationError, match="domains must not contain duplicates"):
        ExecutionGraph(
            intent="read",
            domains=["meeting", "meeting"],
            risk="low",
            output_kind="answer",
            invocations=[],
        )


def test_evidence_packet_minimal_contract() -> None:
    packet = EvidencePacket(
        query_plan=QueryPlan(
            keywords=["결정사항"],
            source_kinds=["meeting"],
            sources_used=["fixture-meeting-001"],
            candidate_top_k=20,
            rerank_top_k=4,
            final_evidence_token_budget=2048,
        ),
        items=[
            EvidenceItem(
                ref="meeting:fixture-meeting-001#decision-1",
                source_kind="meeting",
                excerpt="테스트 회의에서 일정 리스크를 논의했다.",
                trust_level="trusted",
                authority_class="internal_system_of_record",
            )
        ],
        coverage=EvidenceCoverage(
            intents_covered=["summarize_decisions"],
            intents_missed=[],
        ),
    )

    assert packet.items[0].authority_class == "internal_system_of_record"
    assert packet.coverage.intents_covered == ["summarize_decisions"]


def test_agent_run_invocation_and_trace_contracts() -> None:
    run = AgentRunContract(
        run_id="run-1",
        workspace_id="workspace-1",
        conversation_id="conversation-1",
        requested_by_user_id="user-1",
        status="running",
        runtime_profile="interactive_read",
    )
    invocation = AgentInvocationContract(
        invocation_id="invocation-1",
        run_id=run.run_id,
        invocation_seq=0,
        agent_id="domain.meeting",
        status="running",
        purpose="answer meeting question",
    )
    trace = AgentTraceEventContract(
        event_id="event-1",
        run_id=run.run_id,
        invocation_id=invocation.invocation_id,
        run_seq=0,
        invocation_seq=0,
        event_seq=0,
        event_type="invocation_started",
        payload={"agent_id": invocation.agent_id},
    )

    assert run.graph_enabled is False
    assert invocation.run_id == run.run_id
    assert trace.payload["agent_id"] == "domain.meeting"


def test_trace_sequence_is_monotonic_within_run() -> None:
    sequencer = RuntimeTraceSequencer(run_seq=7)

    assert sequencer.next_event(invocation_seq=0) == (7, 0, 0)
    assert sequencer.next_event(invocation_seq=0) == (7, 0, 1)
    assert sequencer.next_event(invocation_seq=2) == (7, 2, 2)


def test_trace_sequence_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="invocation_seq"):
        RuntimeTraceSequencer().next_event(invocation_seq=-1)


def test_runtime_registry_validation_error_maps_to_http_422() -> None:
    app = FastAPI()
    app.add_exception_handler(
        RuntimeRegistryValidationError,
        runtime_registry_validation_exception_handler,
    )

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeRegistryValidationError("unknown agent id(s): ['x']")

    response = TestClient(app).get("/boom")

    assert response.status_code == 422
    assert response.json() == {"detail": "unknown agent id(s): ['x']"}


def test_runtime_metric_wrappers_are_safe_without_exporter() -> None:
    record_trace_event(event_type="run_created", result="ok")
    record_trace_payload_truncated(event_type="large_payload")
    record_shadow_write_failure(operation="shadow_fixture")
    record_inspection_request(result="ok")
