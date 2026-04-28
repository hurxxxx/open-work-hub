from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aidoo_api.app import runtime_registry_validation_exception_handler
from aidoo_api.domains.ai.runtime import (
    DEFAULT_AGENT_DEFINITIONS,
    AgentDefinitionResolver,
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
    build_deterministic_manager_candidate,
    build_execution_graph_response_schema,
    build_graph_execution_schedule,
    resolve_agent_definitions,
    summarize_graph_execution_schedule,
    summarize_graph_schedule_failure,
    summarize_execution_graph,
    validate_execution_graph,
    validate_manager_graph_candidate,
    GraphSchedulerError,
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


def test_manager_graph_response_schema_keeps_registry_values_open() -> None:
    response_schema = build_execution_graph_response_schema()

    assert response_schema["name"] == "ExecutionGraph"
    assert response_schema["strict"] is True
    graph_schema = response_schema["schema"]
    graph_properties = graph_schema["properties"]
    invocation_properties = graph_schema["$defs"]["AgentInvocationSpec"]["properties"]

    assert graph_schema["additionalProperties"] is False
    assert graph_properties["intent"]["type"] == "string"
    assert "enum" not in graph_properties["intent"]
    assert graph_properties["output_kind"]["type"] == "string"
    assert "enum" not in graph_properties["output_kind"]
    assert graph_properties["domains"]["items"]["type"] == "string"
    assert invocation_properties["agent_id"]["type"] == "string"
    assert "enum" not in invocation_properties["agent_id"]
    assert graph_properties["risk"]["enum"] == ["low", "medium", "high"]


def test_manager_graph_validator_accepts_schema_and_registry_valid_candidate() -> None:
    result = validate_manager_graph_candidate(
        {
            "intent": "report",
            "domains": ["meeting", "docs"],
            "risk": "medium",
            "output_kind": "artifact",
            "invocations": [
                {
                    "agent_id": "domain.meeting",
                    "purpose": "collect meeting evidence",
                },
                {
                    "agent_id": "writer.template",
                    "must_run_after": ["domain.meeting"],
                    "purpose": "write draft",
                },
            ],
            "requires_verifier": True,
        },
        registry=_registry(),
        source="external_planning",
    )

    assert result.accepted is True
    assert result.graph is not None
    assert result.source == "external_planning"
    assert result.graph.intent == "report"
    assert result.fallback_reason is None
    assert result.error is None


def test_manager_graph_validator_returns_schema_failure_without_execution() -> None:
    result = validate_manager_graph_candidate(
        {
            "intent": "report",
            "domains": ["meeting"],
            "risk": "critical",
            "output_kind": "artifact",
        },
        registry=_registry(),
    )

    assert result.accepted is False
    assert result.graph is None
    assert result.fallback_reason == "schema_validation_failed"
    assert "risk" in (result.error or "")


def test_manager_graph_validator_returns_registry_failure_without_execution() -> None:
    result = validate_manager_graph_candidate(
        {
            "intent": "report",
            "domains": ["finance"],
            "risk": "medium",
            "output_kind": "artifact",
        },
        registry=_registry(),
    )

    assert result.accepted is False
    assert result.graph is None
    assert result.fallback_reason == "runtime_registry_validation_failed"
    assert result.error == "unknown domain(s): ['finance']"


def test_manager_graph_validator_enforces_write_agent_risk_floor() -> None:
    result = validate_manager_graph_candidate(
        {
            "intent": "report",
            "domains": ["docs"],
            "risk": "medium",
            "output_kind": "artifact",
            "invocations": [
                {
                    "agent_id": "writer.template",
                    "purpose": "write draft",
                }
            ],
        },
        registry=_registry(),
        write_agent_ids=frozenset({"writer.template"}),
    )

    assert result.accepted is False
    assert result.graph is None
    assert result.fallback_reason == "risk_floor_violation"
    assert "writer.template" in (result.error or "")


def test_agent_definition_resolver_exposes_v1_agent_set() -> None:
    agent_ids = {definition.agent_id for definition in DEFAULT_AGENT_DEFINITIONS}

    assert {
        "manager.orchestrator",
        "domain.pms",
        "domain.meeting",
        "domain.docs",
        "domain.planner",
        "domain.rag",
        "search.planner",
        "search.executor",
        "verifier.grounding",
        "writer.template",
        "approval.proposal_preview",
    } <= agent_ids


def test_agent_definition_resolver_builds_runtime_registry_from_scope() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["ai", "meeting", "docs", "pms"],
        allowed_app_ids=["meeting", "docs"],
    )
    registry = resolved.runtime_registry

    assert "manager.orchestrator" in registry.agent_ids
    assert "writer.template" in registry.agent_ids
    assert "domain.meeting" in registry.agent_ids
    assert "domain.docs" in registry.agent_ids
    assert "domain.pms" not in registry.agent_ids
    assert registry.domains >= {"meeting", "docs", "rag"}
    assert "pms" not in registry.domains
    assert registry.output_kinds >= {"answer", "artifact", "approval_preview"}
    assert resolved.write_agent_ids == frozenset({"approval.proposal_preview"})


def test_agent_definition_resolver_never_widens_beyond_workspace_entitlements() -> None:
    resolved = AgentDefinitionResolver().resolve(
        enabled_app_ids=["ai", "meeting"],
        allowed_app_ids=["meeting", "pms"],
    )

    assert "domain.meeting" in resolved.agent_ids
    assert "domain.pms" not in resolved.agent_ids
    assert "pms" not in resolved.runtime_registry.domains


def test_agent_definition_resolver_empty_scope_hides_domain_agents() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["ai", "meeting", "docs"],
        allowed_app_ids=[],
    )

    assert "manager.orchestrator" in resolved.agent_ids
    assert "domain.meeting" not in resolved.agent_ids
    assert "domain.docs" not in resolved.agent_ids
    assert "search.executor" not in resolved.agent_ids
    assert resolved.runtime_registry.domains == frozenset()


def test_agent_definition_resolver_requires_ai_app_entitlement() -> None:
    resolved = AgentDefinitionResolver().resolve(
        enabled_app_ids=["meeting", "docs"],
    )

    assert resolved.definitions == ()
    assert resolved.agent_ids == frozenset()
    assert resolved.runtime_registry.domains == frozenset()


def test_manager_validator_uses_resolved_registry_to_block_hidden_agent() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["ai", "meeting"],
    )

    result = validate_manager_graph_candidate(
        {
            "intent": "report",
            "domains": ["meeting"],
            "risk": "medium",
            "output_kind": "artifact",
            "invocations": [
                {
                    "agent_id": "domain.pms",
                    "purpose": "collect hidden PMS evidence",
                }
            ],
        },
        registry=resolved.runtime_registry,
        write_agent_ids=resolved.write_agent_ids,
    )

    assert result.accepted is False
    assert result.fallback_reason == "runtime_registry_validation_failed"
    assert result.error == "unknown agent id(s): ['domain.pms']"


def test_manager_validator_uses_resolved_write_agent_risk_floor() -> None:
    resolved = resolve_agent_definitions(enabled_app_ids=["ai", "pms"])

    result = validate_manager_graph_candidate(
        {
            "intent": "write",
            "domains": [],
            "risk": "medium",
            "output_kind": "approval_preview",
            "invocations": [
                {
                    "agent_id": "approval.proposal_preview",
                    "purpose": "preview PMS write before approval",
                }
            ],
        },
        registry=resolved.runtime_registry,
        write_agent_ids=resolved.write_agent_ids,
    )

    assert result.accepted is False
    assert result.fallback_reason == "risk_floor_violation"
    assert "approval.proposal_preview" in (result.error or "")


def test_deterministic_manager_candidate_builds_valid_grounded_report_graph() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["ai", "meeting", "docs", "pms"],
        allowed_app_ids=["meeting", "pms"],
    )

    candidate = build_deterministic_manager_candidate(
        runtime_profile="grounded_report",
        resolved_agents=resolved,
    )
    assert candidate is not None
    assert candidate.intent == "report"
    assert candidate.risk == "medium"
    assert candidate.output_kind == "artifact"
    assert candidate.requires_verifier is True
    assert set(candidate.domains) >= {"meeting", "pms", "rag"}
    assert "domain.docs" not in {invocation.agent_id for invocation in candidate.invocations}

    result = validate_manager_graph_candidate(
        candidate,
        registry=resolved.runtime_registry,
        write_agent_ids=resolved.write_agent_ids,
    )
    assert result.accepted is True
    summary = summarize_execution_graph(candidate)
    assert summary == {
        "intent": "report",
        "domains": candidate.domains,
        "risk": "medium",
        "output_kind": "artifact",
        "invocation_agent_ids": [
            invocation.agent_id for invocation in candidate.invocations
        ],
        "requires_verifier": True,
        "requires_approval_preview": False,
    }
    assert "purpose" not in summary
    assert "must_run_after" not in summary
    assert "inputs_ref" not in summary


def test_graph_scheduler_builds_planned_topological_order() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["ai", "meeting", "docs", "pms"],
        allowed_app_ids=["meeting", "pms"],
    )
    candidate = build_deterministic_manager_candidate(
        runtime_profile="grounded_report",
        resolved_agents=resolved,
    )
    assert candidate is not None

    schedule = build_graph_execution_schedule(candidate)
    summary = summarize_graph_execution_schedule(schedule)

    assert summary["state"] == "planned"
    assert summary["execution_enabled"] is False
    assert summary["step_count"] == len(candidate.invocations)
    planned_agent_ids = summary["planned_agent_ids"]
    assert planned_agent_ids.index("search.planner") > planned_agent_ids.index("domain.pms")
    assert planned_agent_ids.index("search.executor") > planned_agent_ids.index("search.planner")
    assert planned_agent_ids.index("writer.template") == len(planned_agent_ids) - 1
    assert set(summary["steps"][0]) == {
        "invocation_seq",
        "agent_id",
        "state",
        "depends_on_agent_ids",
    }
    assert {step["state"] for step in summary["steps"]} == {"planned"}
    assert "purpose" not in summary["steps"][0]


def test_graph_scheduler_rejects_cyclic_dependencies() -> None:
    graph = ExecutionGraph(
        intent="report",
        domains=["meeting"],
        risk="medium",
        output_kind="artifact",
        invocations=[
            AgentInvocationSpec(
                agent_id="domain.meeting",
                must_run_after=["writer.template"],
                purpose="collect evidence",
            ),
            AgentInvocationSpec(
                agent_id="writer.template",
                must_run_after=["domain.meeting"],
                purpose="write draft",
            ),
        ],
    )

    with pytest.raises(GraphSchedulerError, match="cyclic invocation dependency"):
        build_graph_execution_schedule(graph)


def test_graph_schedule_failure_summary_is_trace_safe() -> None:
    summary = summarize_graph_schedule_failure(
        GraphSchedulerError("cyclic invocation dependency: ['writer.template']")
    )

    assert summary == {
        "state": "failed",
        "execution_enabled": False,
        "fallback_reason": "graph_schedule_failed",
        "error_type": "GraphSchedulerError",
        "error": "cyclic invocation dependency: ['writer.template']",
        "step_count": 0,
        "planned_agent_ids": [],
        "steps": [],
    }


def test_deterministic_manager_candidate_builds_valid_high_risk_preview_graph() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["ai", "pms"],
        allowed_app_ids=["pms"],
    )

    candidate = build_deterministic_manager_candidate(
        runtime_profile="high_risk_action",
        resolved_agents=resolved,
    )
    assert candidate is not None
    assert candidate.intent == "write"
    assert candidate.risk == "high"
    assert candidate.output_kind == "approval_preview"
    assert candidate.requires_approval_preview is True
    assert candidate.domains == ["pms"]

    result = validate_manager_graph_candidate(
        candidate,
        registry=resolved.runtime_registry,
        write_agent_ids=resolved.write_agent_ids,
    )
    assert result.accepted is True


def test_deterministic_manager_candidate_is_unavailable_without_scoped_domain() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["ai"],
        allowed_app_ids=["ai"],
    )

    assert (
        build_deterministic_manager_candidate(
            runtime_profile="high_risk_action",
            resolved_agents=resolved,
        )
        is None
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
