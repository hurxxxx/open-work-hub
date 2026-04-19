from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core import llm as llm_core
from aidoo_api.core.db import get_engine, get_session_factory
from aidoo_api.domains.ai.models import LlmPolicy
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data
from aidoo_api.domains.auth.models import AuditLog


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workspace_tool_path(workspace_slug: str, tool_name: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/ai/tools/{tool_name}/invoke"


def _workspace_ai_path(slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{slug}/ai{suffix}"


def _set_policy(task_kind: str, mode: str) -> None:
    with Session(get_engine()) as session:
        policy = session.scalar(
            select(LlmPolicy).where(LlmPolicy.task_kind == task_kind)
        )
        assert policy is not None
        policy.policy_mode = mode
        session.add(policy)
        session.commit()


def _tool_audit_rows() -> list[AuditLog]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "llm_tool_call")
                .order_by(AuditLog.created_at.asc())
            ).all()
        )


def _parse_sse(body: str) -> list[dict[str, Any]]:
    normalized = body.replace("\r\n", "\n")
    events: list[dict[str, Any]] = []
    for block in normalized.split("\n\n"):
        block = block.strip("\n")
        if not block:
            continue
        data_str: str | None = None
        for line in block.split("\n"):
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_str = line[len("data:") :].strip()
        if data_str is None:
            continue
        events.append(json.loads(data_str))
    return events


class _FakeAsyncStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = iter(chunks)

    def __aiter__(self) -> "_FakeAsyncStream":
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def aclose(self) -> None:
        return None


class _SequencedAsyncChatCompletions:
    def __init__(self, chunk_sequences: list[list[Any]]) -> None:
        self._chunk_sequences = [list(chunks) for chunks in chunk_sequences]
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return _FakeAsyncStream(self._chunk_sequences.pop(0))


class _SequencedAsyncPoolClient:
    def __init__(self, chunk_sequences: list[list[Any]]) -> None:
        self.chat = SimpleNamespace(
            completions=_SequencedAsyncChatCompletions(chunk_sequences)
        )

    def with_options(self, **_: Any) -> "_SequencedAsyncPoolClient":
        return self


def _delta(*, content: str | None = None, tool_calls: list[Any] | None = None, finish_reason: str | None = None) -> SimpleNamespace:
    delta = SimpleNamespace(
        content=content,
        reasoning_content=None,
        reasoning=None,
        tool_calls=tool_calls,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)],
        usage=None,
    )


def _tool_call_delta(
    *,
    index: int,
    tool_id: str,
    name: str | None = None,
    arguments: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        index=index,
        id=tool_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def test_docs_tool_invoke_blocks_cross_workspace_page_access_and_audits_error(
    client: TestClient,
) -> None:
    owner = _dev_login(client, "delivery-hub-admin")
    outsider = _dev_login(client, "knowledge-base-admin")

    doc_response = client.post(
        "/api/v1/workspaces/delivery-hub/docs/native-docs",
        headers=_auth_headers(owner["token"]),
        json={"title": "Restricted Doc"},
    )
    assert doc_response.status_code == 201, doc_response.text
    doc = doc_response.json()

    page_response = client.post(
        f"/api/v1/workspaces/delivery-hub/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner["token"]),
        json={
            "title": "Restricted Page",
            "content_blocks": [{"type": "paragraph", "content": "secret body"}],
        },
    )
    assert page_response.status_code == 201, page_response.text
    page = page_response.json()

    response = client.post(
        _workspace_tool_path("knowledge-base", "docs.read_page"),
        headers=_auth_headers(outsider["token"]),
        json={"arguments": {"page_id": page["id"]}},
    )

    assert response.status_code == 403
    audit_payload = _tool_audit_rows()[-1].payload
    assert audit_payload["tool_name"] == "docs.read_page"
    assert audit_payload["status"] == "error"


def test_agent_loop_tool_error_does_not_leak_cross_workspace_doc_content(
    client: TestClient,
    monkeypatch,
) -> None:
    owner = _dev_login(client, "delivery-hub-admin")
    outsider = _dev_login(client, "knowledge-base-admin")
    _set_policy("chatbot", "local_only")

    doc_response = client.post(
        "/api/v1/workspaces/delivery-hub/docs/native-docs",
        headers=_auth_headers(owner["token"]),
        json={"title": "Restricted Agent Doc"},
    )
    assert doc_response.status_code == 201, doc_response.text
    doc = doc_response.json()

    page_response = client.post(
        f"/api/v1/workspaces/delivery-hub/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner["token"]),
        json={
            "title": "Restricted Agent Page",
            "content_blocks": [{"type": "paragraph", "content": "secret agent body"}],
        },
    )
    assert page_response.status_code == 201, page_response.text
    page = page_response.json()

    pool_client = _SequencedAsyncPoolClient(
        [
            [
                _delta(
                    tool_calls=[
                        _tool_call_delta(
                            index=0,
                            tool_id="call-1",
                            name="docs.read_page",
                            arguments=json.dumps({"page_id": page["id"]}),
                        )
                    ]
                ),
                _delta(finish_reason="tool_calls"),
            ],
            [
                _delta(content="접근 권한이 없어 문서를 읽을 수 없습니다.", finish_reason="stop"),
            ],
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    response = client.post(
        _workspace_ai_path("knowledge-base", "/chat/stream"),
        headers=_auth_headers(outsider["token"]),
        json={"messages": [{"role": "user", "content": "문서를 읽어줘"}]},
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert any(
        event["type"] == "tool_result" and event["data"]["status"] == "error"
        for event in events
    )
    assert "secret agent body" not in response.text
