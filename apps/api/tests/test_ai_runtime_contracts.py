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
    EvidenceQuality,
    ExecutionGraph,
    GraphNodeOutput,
    QueryPlan,
    RuntimeRegistry,
    RuntimeRegistryValidationError,
    RuntimeTraceSequencer,
    build_deterministic_manager_candidate,
    build_execution_graph_response_schema,
    build_graph_execution_schedule,
    build_graph_node_messages,
    build_graph_writer_system_prompt,
    graph_verifier_failure_policy,
    materialize_graph_evidence_packet,
    render_evidence_packet,
    summarize_graph_evidence_packet,
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
        quality=EvidenceQuality(
            verifier_status="completed",
            ready_for_grounded_write=True,
            failed_node_count=0,
            evidence_item_count=1,
            tool_result_count=0,
        ),
    )

    assert packet.packet_version == "evidence_packet.v1"
    assert packet.items[0].authority_class == "internal_system_of_record"
    assert packet.coverage.intents_covered == ["summarize_decisions"]
    assert packet.quality.ready_for_grounded_write is True


def test_graph_evidence_packet_materializes_node_outputs_and_verifier_policy() -> None:
    node_outputs = [
        GraphNodeOutput(
            agent_id="domain.meeting",
            status="completed",
            text="회의에서 일정 리스크와 대응 방안을 확인했다.",
        ),
        GraphNodeOutput(
            agent_id="search.executor",
            status="completed",
            tool_results=("PMS 이슈 ABC-1 상태는 진행 중이다.",),
        ),
        GraphNodeOutput(
            agent_id="verifier.grounding",
            status="failed",
            error="unsupported claim detected",
        ),
    ]

    packet = materialize_graph_evidence_packet(
        messages=[{"role": "user", "content": "회의록과 PMS를 비교한 보고서를 작성해줘"}],
        node_outputs=node_outputs,
        candidate_summary={
            "intent": "report",
            "output_kind": "artifact",
            "requires_verifier": True,
        },
    )

    assert packet.intent == "report"
    assert packet.output_kind == "artifact"
    assert packet.source_agent_ids == [
        "domain.meeting",
        "search.executor",
        "verifier.grounding",
    ]
    assert [item.source_kind for item in packet.items] == ["meeting", "rag"]
    assert packet.coverage.intents_missed == ["verifier.grounding"]
    assert packet.quality.verifier_status == "failed"
    assert packet.quality.ready_for_grounded_write is False
    assert packet.quality.failed_node_count == 1
    assert packet.gaps == [
        "verifier.grounding: unsupported claim detected",
        "verifier.grounding: grounding verification failed",
    ]
    assert graph_verifier_failure_policy(
        node_outputs,
        requires_verifier=True,
    ) == "failed_continue_with_gap_disclaimer"
    rendered = render_evidence_packet(packet)
    assert '"packet_version": "evidence_packet.v1"' in rendered
    assert "unsupported claim detected" in rendered
    summary = summarize_graph_evidence_packet(packet)
    assert summary["evidence_item_count"] == 2
    assert summary["ready_for_grounded_write"] is False


def test_graph_evidence_packet_includes_external_mock_search_metadata() -> None:
    packet = materialize_graph_evidence_packet(
        messages=[{"role": "user", "content": "EU CE 인증 기준을 보고서로 정리해줘"}],
        node_outputs=[
            GraphNodeOutput(
                agent_id="domain.meeting",
                status="completed",
                text="회의에서 인증 리스크 검토 필요성을 확인했다.",
            )
        ],
        candidate_summary={
            "intent": "report",
            "output_kind": "artifact",
            "requires_verifier": False,
        },
        external_planner_execution_summary={
            "adapter_id": "external_planner_v0",
            "execution_provider": "mock",
            "status": "completed",
            "provider": "openai",
            "planned_agent_count": 3,
            "intent_hint": "report",
            "output_kind_hint": "artifact",
            "raw_output_persisted": False,
        },
        external_search_execution_summary={
            "adapter_id": "external_search_v0",
            "execution_provider": "mock",
            "status": "completed",
            "provider": "openai",
            "query_digest": "abc123digest",
            "cache_key": "external_search_v0:mock:openai:abc123digest",
            "cache_hit": False,
            "result_count": 2,
            "result_refs": [
                "mock://external-search/abc123digest/result-1",
                "mock://external-search/abc123digest/result-2",
            ],
            "source_kinds": ["public_web_mock"],
            "raw_output_persisted": False,
        },
    )

    assert packet.source_agent_ids == [
        "domain.meeting",
        "external_planner_v0",
        "external_search_v0",
    ]
    assert packet.query_plan.external_search_used is True
    assert packet.query_plan.external_search_provider == "openai"
    assert packet.query_plan.sanitized_query_ref == "sha256:abc123digest"
    assert packet.query_plan.source_kinds == ["meeting", "public_web_mock"]
    external_items = [
        item for item in packet.items if item.source_kind == "public_web_mock"
    ]
    assert [item.ref for item in external_items] == [
        "mock://external-search/abc123digest/result-1",
        "mock://external-search/abc123digest/result-2",
    ]
    assert {item.trust_level for item in external_items} == {"untrusted"}
    assert {item.authority_class for item in external_items} == {"public_web"}
    assert all("sha256:abc123digest" in item.excerpt for item in external_items)
    assert "EU CE" not in render_evidence_packet(packet)


def test_external_mock_search_metadata_does_not_make_packet_ready_alone() -> None:
    packet = materialize_graph_evidence_packet(
        messages=[{"role": "user", "content": "EU CE 인증 기준을 보고서로 정리해줘"}],
        node_outputs=[],
        candidate_summary={
            "intent": "report",
            "output_kind": "artifact",
            "requires_verifier": False,
        },
        external_search_execution_summary={
            "adapter_id": "external_search_v0",
            "execution_provider": "mock",
            "status": "completed",
            "provider": "openai",
            "query_digest": "abc123digest",
            "cache_key": "external_search_v0:mock:openai:abc123digest",
            "cache_hit": False,
            "result_count": 2,
            "result_refs": [
                "mock://external-search/abc123digest/result-1",
                "mock://external-search/abc123digest/result-2",
            ],
            "source_kinds": ["public_web_mock"],
            "raw_output_persisted": False,
        },
    )

    assert packet.items
    assert packet.query_plan.external_search_used is True
    assert packet.quality.ready_for_grounded_write is False


def test_graph_node_input_builder_is_deterministic_and_scoped() -> None:
    messages = [{"role": "user", "content": "회의록과 PMS를 비교한 보고서를 작성해줘"}]
    prior_outputs = [
        GraphNodeOutput(
            agent_id="domain.meeting",
            status="completed",
            text="회의에서 출시 일정 리스크를 확인했다.",
        )
    ]

    built = build_graph_node_messages(
        messages,
        agent_id="search.executor",
        step={
            "agent_id": "search.executor",
            "depends_on_agent_ids": ["search.planner"],
        },
        prior_outputs=prior_outputs,
        candidate_summary={
            "intent": "report",
            "output_kind": "artifact",
            "requires_verifier": True,
        },
    )

    assert built[0] == messages[0]
    node_input = built[-1]["content"]
    assert "Deterministic graph node input" in node_input
    assert "agent_id: search.executor" in node_input
    assert "depends_on_agent_ids: ['search.planner']" in node_input
    assert "EvidencePacket JSON" in node_input
    assert "writer.template" not in node_input

    writer_prompt = build_graph_writer_system_prompt(
        messages=messages,
        node_outputs=prior_outputs,
        candidate_summary={
            "intent": "report",
            "output_kind": "artifact",
            "requires_verifier": True,
        },
    )
    assert "verifier_failure_policy: not_run_continue_with_gap_disclaimer" in writer_prompt
    assert '"ready_for_grounded_write": false' in writer_prompt


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
