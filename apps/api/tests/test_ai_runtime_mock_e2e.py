from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

from ai_runtime_mock_harness import run_mock_external_graph_stream
from aidoo_api.domains.ai import router as ai_router


@pytest.fixture(autouse=True)
def _reset_sse_starlette_app_status() -> None:
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit = False
    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


def test_mock_external_graph_e2e_guard(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = run_mock_external_graph_stream(client, monkeypatch)

    assert result.status_code == 200
    assert [event["type"] for event in result.chat_events] == ["content_delta", "done"]
    assert result.chat_events[0]["data"]["text"] == "mock graph final"

    done_meta = result.done_meta
    assert done_meta["graph_used"] is True
    assert done_meta["graph_execution_adapter"] == "graph_node_runner_v0"
    assert done_meta["graph_execution_status"] == "adapter_selected"
    assert done_meta["graph_validation_status"] == "accepted"
    assert done_meta["graph_schedule_summary"]["execution_enabled"] is True

    egress_reasons = {
        decision["capability"]: decision["reason"]
        for decision in done_meta["external_egress_summary"]["decisions"]
    }
    assert egress_reasons == {"planning": "allowed", "search": "allowed"}

    planner_execution = done_meta["external_planner_execution_summary"]
    assert planner_execution["execution_provider"] == "mock"
    assert planner_execution["status"] == "completed"
    assert planner_execution["planned_agent_count"] == done_meta[
        "graph_schedule_summary"
    ]["step_count"]
    assert planner_execution["latency_ms"] == 0
    assert planner_execution["retry_count"] == 0
    assert planner_execution["error_class"] is None
    assert planner_execution["estimated_cost_microunits"] == 0

    search_execution = done_meta["external_search_execution_summary"]
    assert search_execution["execution_provider"] == "mock"
    assert search_execution["status"] == "completed"
    assert search_execution["query_digest"]
    assert search_execution["cache_key"] == (
        f"external_search_v0:mock:openai:{search_execution['query_digest']}"
    )
    assert search_execution["cache_hit"] is False
    assert search_execution["result_refs"] == [
        f"mock://external-search/{search_execution['query_digest']}/result-1",
        f"mock://external-search/{search_execution['query_digest']}/result-2",
    ]
    assert search_execution["latency_ms"] == 0
    assert search_execution["retry_count"] == 0
    assert search_execution["error_class"] is None
    assert search_execution["estimated_cost_microunits"] == 0

    node_summary = done_meta["graph_node_execution_summary"]
    packet_summary = node_summary["evidence_packet_summary"]
    assert "public_web_mock" in packet_summary["source_kinds"]
    assert packet_summary["evidence_item_count"] >= search_execution["result_count"]
    assert packet_summary["ready_for_grounded_write"] is True

    final_system_prompt = result.pool_client.chat.completions.calls[-1]["messages"][0][
        "content"
    ]
    assert '"external_search_used": true' in final_system_prompt
    assert (
        f'"sanitized_query_ref": "sha256:{search_execution["query_digest"]}"'
        in final_system_prompt
    )
    assert search_execution["result_refs"][0] in final_system_prompt
    assert "public_web_mock" in final_system_prompt

    assert result.inspection_status_code == 200
    inspected_trace = {
        event["event_type"]: event["payload"]
        for event in result.inspection_json["trace_events"]
    }
    generated = inspected_trace["graph_candidate_generated"]
    assert generated["external_planner_execution_summary"] == planner_execution
    assert generated["external_search_execution_summary"] == search_execution

    serialized_execution = json.dumps(search_execution, ensure_ascii=False)
    assert "EU CE 인증 리스크" not in serialized_execution
    assert "회의록과 PMS 이슈" not in serialized_execution


def test_unimplemented_external_adapter_selection_is_trace_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metric_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        ai_router,
        "record_external_execution",
        lambda **payload: metric_calls.append(payload),
    )

    result = run_mock_external_graph_stream(
        client,
        monkeypatch,
        planner_execution_adapter="openai",
        search_execution_adapter="anthropic",
    )

    assert result.status_code == 200
    assert [event["type"] for event in result.chat_events] == ["content_delta", "done"]
    assert result.chat_events[0]["data"]["text"] == "mock graph final"

    done_meta = result.done_meta
    assert done_meta["graph_used"] is True
    assert done_meta["graph_execution_status"] == "adapter_selected"

    planner_execution = done_meta["external_planner_execution_summary"]
    assert planner_execution["execution_provider"] == "openai"
    assert planner_execution["status"] == "failed"
    assert planner_execution["error_class"] == "adapter_not_implemented"
    assert planner_execution["raw_output_persisted"] is False

    search_execution = done_meta["external_search_execution_summary"]
    assert search_execution["execution_provider"] == "anthropic"
    assert search_execution["status"] == "failed"
    assert search_execution["error_class"] == "adapter_not_implemented"
    assert search_execution["query_digest"]
    assert search_execution["cache_key"].startswith("external_search_v0:anthropic:openai:")
    assert search_execution["result_count"] == 0
    assert search_execution["result_refs"] == []
    assert search_execution["source_kinds"] == []
    assert search_execution["raw_output_persisted"] is False

    packet_summary = done_meta["graph_node_execution_summary"]["evidence_packet_summary"]
    assert "public_web_mock" not in packet_summary["source_kinds"]
    assert packet_summary["ready_for_grounded_write"] is True

    final_system_prompt = result.pool_client.chat.completions.calls[-1]["messages"][0][
        "content"
    ]
    assert '"external_search_used": false' in final_system_prompt
    assert "public_web_mock" not in final_system_prompt
    assert "mock://external-search/" not in final_system_prompt

    inspected_trace = {
        event["event_type"]: event["payload"]
        for event in result.inspection_json["trace_events"]
    }
    generated = inspected_trace["graph_candidate_generated"]
    assert generated["external_planner_execution_summary"] == planner_execution
    assert generated["external_search_execution_summary"] == search_execution
    assert metric_calls == [
        {
            "capability": "planning",
            "adapter_id": "external_planner_v0",
            "execution_provider": "openai",
            "status": "failed",
            "error_class": "adapter_not_implemented",
        },
        {
            "capability": "search",
            "adapter_id": "external_search_v0",
            "execution_provider": "anthropic",
            "status": "failed",
            "error_class": "adapter_not_implemented",
        },
    ]


def test_disabled_external_execution_flags_are_trace_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metric_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        ai_router,
        "record_external_execution",
        lambda **payload: metric_calls.append(payload),
    )

    result = run_mock_external_graph_stream(
        client,
        monkeypatch,
        planner_execution_adapter="openai",
        search_execution_adapter="anthropic",
        planner_execution_enabled=False,
        search_execution_enabled=False,
    )

    assert result.status_code == 200
    assert result.chat_events[0]["data"]["text"] == "mock graph final"

    done_meta = result.done_meta
    egress_reasons = {
        decision["capability"]: decision["reason"]
        for decision in done_meta["external_egress_summary"]["decisions"]
    }
    assert egress_reasons == {"planning": "allowed", "search": "allowed"}

    planner_execution = done_meta["external_planner_execution_summary"]
    assert planner_execution["execution_provider"] == "openai"
    assert planner_execution["status"] == "disabled"
    assert planner_execution["disabled_reason"] == "execution_flag_disabled"
    assert planner_execution["planned_agent_count"] == 0
    assert planner_execution["raw_output_persisted"] is False

    search_execution = done_meta["external_search_execution_summary"]
    assert search_execution["execution_provider"] == "anthropic"
    assert search_execution["status"] == "disabled"
    assert search_execution["disabled_reason"] == "execution_flag_disabled"
    assert search_execution["query_digest"] is None
    assert search_execution["cache_key"] is None
    assert search_execution["result_count"] == 0
    assert search_execution["result_refs"] == []
    assert search_execution["source_kinds"] == []
    assert search_execution["raw_output_persisted"] is False

    packet_summary = done_meta["graph_node_execution_summary"]["evidence_packet_summary"]
    assert "public_web_mock" not in packet_summary["source_kinds"]
    assert packet_summary["ready_for_grounded_write"] is True

    final_system_prompt = result.pool_client.chat.completions.calls[-1]["messages"][0][
        "content"
    ]
    assert '"external_search_used": false' in final_system_prompt
    assert "public_web_mock" not in final_system_prompt
    assert "mock://external-search/" not in final_system_prompt

    inspected_trace = {
        event["event_type"]: event["payload"]
        for event in result.inspection_json["trace_events"]
    }
    generated = inspected_trace["graph_candidate_generated"]
    assert generated["external_planner_execution_summary"] == planner_execution
    assert generated["external_search_execution_summary"] == search_execution
    assert metric_calls == [
        {
            "capability": "planning",
            "adapter_id": "external_planner_v0",
            "execution_provider": "openai",
            "status": "disabled",
            "error_class": None,
        },
        {
            "capability": "search",
            "adapter_id": "external_search_v0",
            "execution_provider": "anthropic",
            "status": "disabled",
            "error_class": None,
        },
    ]


def test_no_external_search_directive_blocks_external_search_evidence(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metric_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        ai_router,
        "record_external_execution",
        lambda **payload: metric_calls.append(payload),
    )

    result = run_mock_external_graph_stream(
        client,
        monkeypatch,
        prompt=(
            "외부 검색 없이 EU CE 인증 리스크를 회의록과 PMS 이슈 기준으로 "
            "근거 있는 보고서로 정리해줘"
        ),
    )

    assert result.status_code == 200
    assert result.chat_events[0]["data"]["text"] == "mock graph final"

    done_meta = result.done_meta
    decisions = {
        decision["capability"]: decision
        for decision in done_meta["external_egress_summary"]["decisions"]
    }
    assert decisions["planning"]["reason"] == "allowed"
    assert decisions["search"]["allow_external"] is False
    assert decisions["search"]["reason"] == "user_no_external_search"
    assert decisions["search"]["sanitized_query"] == ""

    search_request = done_meta["external_search_summary"]
    assert search_request["status"] == "disabled"
    assert search_request["disabled_reason"] == "egress_denied"
    assert search_request["query_present"] is False

    search_execution = done_meta["external_search_execution_summary"]
    assert search_execution["execution_provider"] == "mock"
    assert search_execution["status"] == "skipped"
    assert search_execution["disabled_reason"] == "request_not_ready"
    assert search_execution["query_digest"] is None
    assert search_execution["cache_key"] is None
    assert search_execution["result_refs"] == []
    assert search_execution["source_kinds"] == []
    assert search_execution["raw_output_persisted"] is False

    packet_summary = done_meta["graph_node_execution_summary"]["evidence_packet_summary"]
    assert "public_web_mock" not in packet_summary["source_kinds"]

    final_system_prompt = result.pool_client.chat.completions.calls[-1]["messages"][0][
        "content"
    ]
    assert '"external_search_used": false' in final_system_prompt
    assert "public_web_mock" not in final_system_prompt
    assert "mock://external-search/" not in final_system_prompt

    assert metric_calls[-1] == {
        "capability": "search",
        "adapter_id": "external_search_v0",
        "execution_provider": "mock",
        "status": "skipped",
        "error_class": None,
    }
