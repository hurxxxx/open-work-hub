from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from open_work_hub_api.domains.ai.runtime.inspection_projection import (
    RuntimeRunInspectionResponse,
    runtime_run_inspection_response,
)


def test_runtime_run_inspection_response_scrubs_invocations_and_trace_payloads() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    runtime_run = SimpleNamespace(
        id="run-1",
        workspace_id="workspace-1",
        conversation_id="conversation-1",
        requested_by_user_id="user-1",
        legacy_snapshot_id="snapshot-1",
        status="completed",
        runtime_profile="grounded_report",
        graph_enabled=True,
        model_profile_id="model-1",
        fallback_reason=None,
        created_at=now,
        updated_at=now,
    )
    invocation = SimpleNamespace(
        id="invocation-1",
        invocation_seq=1,
        agent_id="writer.template",
        status="completed",
        purpose="draft",
        input_ref="Bearer secret-token",
        output_ref="artifact://safe",
        error="api_key=secret",
        created_at=now,
        updated_at=now,
    )
    trace_event = SimpleNamespace(
        id="event-1",
        agent_invocation_id="invocation-1",
        run_seq=1,
        invocation_seq=1,
        event_seq=2,
        event_type="llm_request",
        payload_json={
            "messages": [{"role": "user", "content": "secret"}],
            "safe": "ok",
            "nested": {"authorization": "Bearer secret-token"},
        },
        created_at=now,
    )

    response = runtime_run_inspection_response(
        runtime_run,
        invocations=[invocation],
        trace_events=[trace_event],
    )

    assert isinstance(response, RuntimeRunInspectionResponse)
    assert response.id == "run-1"
    assert response.invocations[0].input_ref == "[redacted]"
    assert response.invocations[0].output_ref == "artifact://safe"
    assert response.invocations[0].error == "[redacted]"
    assert response.trace_events[0].payload == {
        "messages": "[redacted]",
        "safe": "ok",
        "nested": {"authorization": "[redacted]"},
    }
