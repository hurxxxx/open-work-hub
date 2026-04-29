from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

from ai_runtime_mock_harness import run_mock_external_graph_stream


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
