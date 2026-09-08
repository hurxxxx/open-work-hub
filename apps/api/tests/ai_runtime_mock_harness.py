from __future__ import annotations

from dataclasses import dataclass
import json
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
import pytest
from open_work_hub_api.core import llm as llm_core
from open_work_hub_api.core.settings import get_settings
from test_meeting import _auth_headers, _bootstrap_admin_session, _dev_login


DEFAULT_GRAPH_MOCK_PROMPT = (
    "EU CE 인증 리스크를 회의록과 PMS 이슈 기준으로 근거 있는 보고서로 정리해줘"
)


@dataclass(frozen=True)
class MockExternalGraphRun:
    status_code: int
    events: list[dict[str, Any]]
    chat_events: list[dict[str, Any]]
    done_meta: dict[str, Any]
    inspection_status_code: int
    inspection_json: dict[str, Any]
    pool_client: MockGraphAsyncPoolClient


def run_mock_external_graph_stream(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    prompt: str = DEFAULT_GRAPH_MOCK_PROMPT,
    planner_execution_adapter: str = "mock",
    search_execution_adapter: str = "mock",
    planner_execution_enabled: bool = True,
    search_execution_enabled: bool = True,
) -> MockExternalGraphRun:
    auth = _seeded_dev_login(client, "administrator")
    _set_policy("chatbot", "local_only")
    _enable_mock_external_graph_runtime(
        monkeypatch,
        planner_execution_adapter=planner_execution_adapter,
        search_execution_adapter=search_execution_adapter,
        planner_execution_enabled=planner_execution_enabled,
        search_execution_enabled=search_execution_enabled,
    )

    pool_client = MockGraphAsyncPoolClient()
    monkeypatch.setattr(
        llm_core,
        "get_async_pool_client",
        lambda *args, **kwargs: pool_client,
    )

    status_code, events = _stream_post(
        client,
        _ai_path("/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": prompt}],
            "allowed_app_ids": ["meeting", "pms"],
        },
    )
    chat_events = _chat_events(events)
    done_meta = (
        chat_events[-1]["data"]["meta"]
        if chat_events and chat_events[-1].get("type") == "done"
        else {}
    )
    agent_run_id = done_meta.get("agent_run_id")
    if isinstance(agent_run_id, str) and agent_run_id:
        inspection = client.get(
            _ai_path(f"/runtime/runs/{agent_run_id}"),
            headers=_auth_headers(auth["token"]),
        )
        inspection_status_code = inspection.status_code
        inspection_json = inspection.json() if inspection.status_code == 200 else {}
    else:
        inspection_status_code = 0
        inspection_json = {}

    return MockExternalGraphRun(
        status_code=status_code,
        events=events,
        chat_events=chat_events,
        done_meta=done_meta,
        inspection_status_code=inspection_status_code,
        inspection_json=inspection_json,
        pool_client=pool_client,
    )


def _enable_mock_external_graph_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    planner_execution_adapter: str,
    search_execution_adapter: str,
    planner_execution_enabled: bool,
    search_execution_enabled: bool,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_runtime_graph_enabled", True)
    monkeypatch.setattr(settings, "ai_runtime_graph_execution_enabled", True)
    monkeypatch.setattr(settings, "ai_tool_calling_enabled", False)
    monkeypatch.setattr(settings, "ai_external_llm_enabled", True)
    monkeypatch.setattr(settings, "ai_external_planning_enabled", True)
    monkeypatch.setattr(settings, "ai_external_search_enabled", True)
    monkeypatch.setattr(
        settings,
        "ai_external_planner_execution_enabled",
        planner_execution_enabled,
    )
    monkeypatch.setattr(
        settings,
        "ai_external_search_execution_enabled",
        search_execution_enabled,
    )
    monkeypatch.setattr(
        settings,
        "ai_external_planner_execution_adapter",
        planner_execution_adapter,
    )
    monkeypatch.setattr(
        settings,
        "ai_external_search_execution_adapter",
        search_execution_adapter,
    )


class MockGraphAsyncPoolClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=MockGraphAsyncChatCompletions())
        self.models = _MockModels()

    def with_options(self, **_: Any) -> MockGraphAsyncPoolClient:
        return self


class MockGraphAsyncChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.node_call_count = 0

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        system_prompt = _first_message_content(kwargs.get("messages"))
        if "writer.template graph node" in system_prompt:
            content = "mock graph final"
        elif "Execute graph node" in system_prompt:
            self.node_call_count += 1
            content = f"mock node evidence {self.node_call_count}"
        else:
            content = "mock graph fallback"
        return _MockAsyncStream([_delta(content=content, finish_reason="stop")])


class _MockAsyncStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = list(chunks)
        self._index = 0

    def __aiter__(self) -> _MockAsyncStream:
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    async def aclose(self) -> None:
        return None


class _MockModels:
    def list(self) -> SimpleNamespace:
        return SimpleNamespace(data=[])


def _delta(*, content: str, finish_reason: str) -> SimpleNamespace:
    delta = SimpleNamespace(
        content=content,
        reasoning_content=None,
        reasoning=None,
        tool_calls=None,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)],
        usage=None,
    )


def _first_message_content(messages: Any) -> str:
    if not isinstance(messages, list) or not messages:
        return ""
    first = messages[0]
    if not isinstance(first, dict):
        return ""
    content = first.get("content")
    return content if isinstance(content, str) else ""


def _ai_path(suffix: str) -> str:
    return f"/api/v1/chatbot{suffix}"


def _seeded_dev_login(client: TestClient, account_key: str) -> dict[str, Any]:
    _bootstrap_admin_session(client)
    return _dev_login(client, account_key)


def _set_policy(task_kind: str, mode: str) -> None:
    # Legacy test shim: registered workload routing is no longer DB task-policy driven.
    _ = (task_kind, mode)


def _stream_post(
    client: TestClient,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any],
) -> tuple[int, list[dict[str, Any]]]:
    response = client.post(url, headers=headers, json=json_body)
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        return response.status_code, _parse_sse(response.text)
    return response.status_code, []


def _parse_sse(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        data_str: str | None = None
        for line in block.split("\n"):
            if line.startswith("data:"):
                data_str = line[len("data:") :].strip()
        if data_str:
            events.append(json.loads(data_str))
    return events


def _chat_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") != "conversation_attached"]
