from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from aidoo_api.domains.ai.mcp import AiMcpClient, _descriptor_matches_app
from aidoo_api.domains.ai.registry import AiCapabilityDescriptor


@dataclass
class _RecordingTransport:
    result: dict
    call: dict | None = None

    def call_tool(
        self,
        db,
        *,
        workspace,
        principal,
        user,
        tool_name,
        arguments,
        source,
        call_id=None,
        agent_run_id=None,
        conversation_id=None,
    ) -> dict:
        self.call = {
            "db": db,
            "workspace": workspace,
            "principal": principal,
            "user": user,
            "tool_name": tool_name,
            "arguments": arguments,
            "source": source,
            "call_id": call_id,
            "agent_run_id": agent_run_id,
            "conversation_id": conversation_id,
        }
        return dict(self.result)


def test_descriptor_matches_ai_app_for_rag_tools() -> None:
    # Tool naming and workspace_app_id are now decoupled: a "rag.*" tool can
    # legitimately live under the "ai" workspace app, and the matcher uses
    # the explicit workspace_app_id rather than parsing the name prefix.
    descriptor = AiCapabilityDescriptor(
        name="rag.query",
        kind="tool",
        mode="read",
        description="RAG query",
        ai_input_model=None,
        approval_policy="none",
        discoverability_predicate_id="ai.enabled",
        preview_builder_id=None,
        output_projection="full",
        service_handler_id="rag.query",
        workspace_app_id="ai",
    )

    assert _descriptor_matches_app(descriptor, app_id="ai")
    assert not _descriptor_matches_app(descriptor, app_id="rag")
    assert not _descriptor_matches_app(descriptor, app_id="docs")


def test_ai_mcp_client_call_tool_forwards_to_transport() -> None:
    transport = _RecordingTransport(result={"ok": True})
    client = AiMcpClient(transport=transport)
    db = object()
    workspace = SimpleNamespace(id="ws-1")
    principal = SimpleNamespace(kind="user")
    user = SimpleNamespace(id="user-1")

    response = client.call_tool(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        tool_name="rag.query",
        arguments={"query": "phase 5"},
        source="test",
        call_id="call-1",
        agent_run_id="run-1",
    )

    assert response == {"ok": True}
    assert transport.call == {
        "db": db,
        "workspace": workspace,
        "principal": principal,
        "user": user,
        "tool_name": "rag.query",
        "arguments": {"query": "phase 5"},
        "source": "test",
        "call_id": "call-1",
        "agent_run_id": "run-1",
        "conversation_id": None,
    }
