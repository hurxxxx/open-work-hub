from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
import pytest

from dev_accounts import dev_login
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core import llm as llm_core
from open_work_hub_api.core.db import get_engine
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.models import AuditLog


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _tool_path(tool_name: str) -> str:
    return f"/api/v1/chatbot/tools/{tool_name}/invoke"


def _ai_path(suffix: str) -> str:
    return f"/api/v1/chatbot{suffix}"


def _set_policy(task_kind: str, mode: str) -> None:
    # Legacy test shim: registered workload routing is no longer DB task-policy driven.
    _ = (task_kind, mode)


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
        self.chat = SimpleNamespace(completions=_SequencedAsyncChatCompletions(chunk_sequences))

    def with_options(self, **_: Any) -> "_SequencedAsyncPoolClient":
        return self


def _delta(
    *,
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str | None = None,
) -> SimpleNamespace:
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


def test_docs_tool_invoke_blocks_other_users_private_page_access_and_audits_error(
    client: TestClient,
) -> None:
    owner = _dev_login(client, "delivery-hub-admin")
    outsider = _dev_login(client, "knowledge-base-admin")

    doc_response = client.post(
        "/api/v1/docs/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "Restricted Doc"},
    )
    assert doc_response.status_code == 201, doc_response.text
    doc = doc_response.json()

    page_response = client.post(
        f"/api/v1/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner["token"]),
        json={
            "title": "Restricted Page",
            "content_blocks": [{"type": "paragraph", "content": "secret body"}],
        },
    )
    assert page_response.status_code == 201, page_response.text
    page = page_response.json()

    response = client.post(
        _tool_path("docs.read_page"),
        headers=_auth_headers(outsider["token"]),
        json={"arguments": {"page_id": page["id"]}},
    )

    assert response.status_code == 403
    audit_payload = _tool_audit_rows()[-1].payload
    assert audit_payload["tool_name"] == "docs.read_page"
    assert audit_payload["status"] == "error"


@pytest.mark.usefixtures("configured_local_llm_control_plane")
def test_agent_loop_tool_error_does_not_leak_other_users_private_doc_content(
    client: TestClient,
    monkeypatch,
) -> None:
    owner = _dev_login(client, "delivery-hub-admin")
    outsider = _dev_login(client, "knowledge-base-admin")
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(get_settings(), "ai_local_tool_calling_enabled", True)

    doc_response = client.post(
        "/api/v1/docs/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "Restricted Agent Doc"},
    )
    assert doc_response.status_code == 201, doc_response.text
    doc = doc_response.json()

    page_response = client.post(
        f"/api/v1/docs/items/{doc['id']}/pages",
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
    monkeypatch.setattr(
        llm_core,
        "_new_async_pool_client",
        lambda config: pool_client,
    )

    response = client.post(
        _ai_path("/chat/stream"),
        headers=_auth_headers(outsider["token"]),
        json={
            "messages": [{"role": "user", "content": "문서를 읽어줘"}],
            "allowed_app_ids": ["docs"],
        },
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert any(
        event["type"] == "tool_result" and event["data"]["status"] == "error" for event in events
    ), events
    assert "secret agent body" not in response.text
