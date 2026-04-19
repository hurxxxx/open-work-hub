from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from openai import OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core import llm as llm_core
from aidoo_api.core.db import get_engine
from aidoo_api.domains.ai.models import LlmPolicy
from aidoo_api.domains.auth.models import AuditLog
from test_meeting import _auth_headers, _bootstrap_admin_session, _dev_login


class FakeModels:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def list(self) -> SimpleNamespace:
        return SimpleNamespace(
            data=[SimpleNamespace(id=model_id) for model_id in self._ids]
        )


class FakeChatCompletions:
    def __init__(self, content: str, *, error: Exception | None = None) -> None:
        self._content = content
        self._error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            model=str(kwargs["model"]),
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        )


class FakePoolClient:
    def __init__(
        self,
        ids: list[str],
        *,
        content: str = "ok",
        error: Exception | None = None,
    ) -> None:
        self.models = FakeModels(ids)
        self.chat = SimpleNamespace(
            completions=FakeChatCompletions(content, error=error)
        )
        self.option_calls: list[dict[str, object]] = []

    def with_options(self, **kwargs) -> FakePoolClient:
        self.option_calls.append(kwargs)
        return self


def _workspace_ai_path(workspace_slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/ai{suffix}"


def _seeded_dev_login(client: TestClient, account_key: str) -> dict:
    _bootstrap_admin_session(client)
    return _dev_login(client, account_key)


def _set_policy(task_kind: str, policy_mode: str) -> None:
    with Session(get_engine()) as session:
        policy = session.scalar(
            select(LlmPolicy).where(LlmPolicy.task_kind == task_kind)
        )
        assert policy is not None
        policy.policy_mode = policy_mode
        session.add(policy)
        session.commit()


def _llm_audit_rows() -> list[AuditLog]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "llm_call")
                .order_by(AuditLog.created_at.asc())
            ).all()
        )


def test_ai_chat_rejects_deprecated_openrouter_override(client: TestClient) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "openrouter",
            "messages": [{"role": "user", "content": "테스트"}],
        },
    )

    assert response.status_code == 400
    assert "no longer supported" in response.json()["detail"]


def test_ai_chat_local_mode_uses_policy_path_and_persists_audit(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")

    local_client = FakePoolClient(
        ["mlx-community/Qwen3.6-35B-A3B-4bit"],
        content="local response",
    )
    external_client = FakePoolClient(
        ["qwen/qwen3.5-35b-a3b"],
        content="external response",
    )
    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool: local_client if pool == "local" else external_client,
    )

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "로컬로 보내줘"}],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["content"] == "local response"
    assert payload["policy"] == "external"
    assert payload["chosen_pool"] == "local"
    assert payload["decision_reason"] == "local_hint"
    assert payload["forced_local"] is True
    assert external_client.chat.completions.calls == []
    assert local_client.chat.completions.calls

    audit_rows = _llm_audit_rows()
    assert len(audit_rows) == 1
    assert audit_rows[0].payload["policy"] == "external"
    assert audit_rows[0].payload["chosen_pool"] == "local"
    assert audit_rows[0].payload["decision_reason"] == "local_hint"
    assert audit_rows[0].payload["forced_local"] is True
    assert audit_rows[0].payload["status"] == "ok"


def test_ai_chat_external_policy_uses_external_reasoning_shape(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")

    local_client = FakePoolClient(
        ["mlx-community/Qwen3.6-35B-A3B-4bit"],
        content="local response",
    )
    external_client = FakePoolClient(
        ["qwen/qwen3.5-35b-a3b"],
        content="external response",
    )
    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool: local_client if pool == "local" else external_client,
    )

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "auto",
            "messages": [{"role": "user", "content": "간단한 요약을 해줘"}],
            "reasoning_effort": "high",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["chosen_pool"] == "external"
    assert payload["policy"] == "external"
    assert payload["decision_reason"] == "policy_external"
    assert payload["forced_local"] is False
    assert local_client.chat.completions.calls == []
    assert external_client.chat.completions.calls[0]["extra_body"] == {
        "reasoning": {"effort": "high"}
    }


def test_ai_chat_local_defaults_disable_reasoning_and_use_30k_budget(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    local_client = FakePoolClient(
        ["mlx-community/Qwen3.6-35B-A3B-4bit"],
        content="local response",
    )
    monkeypatch.setattr(llm_core, "get_pool_client", lambda pool: local_client)

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "길게 설명해줘"}],
        },
    )

    assert response.status_code == 200, response.text
    call = local_client.chat.completions.calls[0]
    assert call["max_tokens"] == llm_core.LOCAL_DEFAULT_MAX_TOKENS
    assert call["extra_body"] == {"think": False}


def test_ai_chat_external_defaults_use_medium_reasoning_and_256k_budget(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")

    local_client = FakePoolClient(
        ["mlx-community/Qwen3.6-35B-A3B-4bit"],
        content="local response",
    )
    external_client = FakePoolClient(
        ["qwen/qwen3.5-35b-a3b"],
        content="external response",
    )
    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool: local_client if pool == "local" else external_client,
    )

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "auto",
            "messages": [{"role": "user", "content": "LLM과 머신러닝 차이를 길게 설명해줘"}],
        },
    )

    assert response.status_code == 200, response.text
    call = external_client.chat.completions.calls[0]
    assert call["max_tokens"] == llm_core.EXTERNAL_DEFAULT_MAX_TOKENS
    assert call["extra_body"] == {"reasoning": {"effort": "medium"}}


def test_ai_chat_external_policy_forces_local_on_pii(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")

    local_client = FakePoolClient(
        ["mlx-community/Qwen3.6-35B-A3B-4bit"],
        content="safe local response",
    )
    external_client = FakePoolClient(
        ["qwen/qwen3.5-35b-a3b"],
        content="external response",
    )
    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool: local_client if pool == "local" else external_client,
    )

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "auto",
            "messages": [
                {
                    "role": "user",
                    "content": "주민번호는 900101 1234567 이고 연락처는 010 1234 5678 입니다.",
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["chosen_pool"] == "local"
    assert payload["decision_reason"] == "pii_detected"
    assert payload["forced_local"] is True
    assert "rrn_kr" in payload["pii_hits"]
    assert "phone_kr" in payload["pii_hits"]
    assert external_client.chat.completions.calls == []
    assert local_client.chat.completions.calls

    audit_rows = _llm_audit_rows()
    assert audit_rows[-1].payload["chosen_pool"] == "local"
    assert audit_rows[-1].payload["decision_reason"] == "pii_detected"
    assert audit_rows[-1].payload["pii_hits"] == ["rrn_kr", "phone_kr"]


def test_ai_chat_provider_error_still_persists_audit(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")

    local_client = FakePoolClient(
        ["mlx-community/Qwen3.6-35B-A3B-4bit"],
        content="local response",
    )
    external_client = FakePoolClient(
        ["qwen/qwen3.5-35b-a3b"],
        error=OpenAIError("provider boom"),
    )
    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool: local_client if pool == "local" else external_client,
    )

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "auto",
            "messages": [{"role": "user", "content": "에러를 재현해줘"}],
        },
    )

    assert response.status_code == 503
    audit_rows = _llm_audit_rows()
    assert audit_rows[-1].payload["status"] == "error"
    assert audit_rows[-1].payload["chosen_pool"] == "external"
    assert audit_rows[-1].payload["decision_reason"] == "policy_external"
    assert "provider boom" in str(audit_rows[-1].payload["error"])


def test_readyz_uses_effective_readiness_while_ai_health_stays_raw(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]

    def fake_pool_client(pool: llm_core.LlmPoolName) -> FakePoolClient:
        if pool == "external":
            return FakePoolClient(["qwen/qwen3.5-35b-a3b"])
        return FakePoolClient(["gemma4:31b"])

    monkeypatch.setattr(llm_core, "get_pool_client", fake_pool_client)

    readyz_response = client.get("/readyz")
    assert readyz_response.status_code == 503
    readyz_payload = readyz_response.json()
    assert readyz_payload["status"] == "degraded"
    assert readyz_payload["llm"]["ready"] is True
    assert readyz_payload["llm_effective"]["ready"] is False
    assert all(
        task["chosen_pool"] == "local" and task["ready"] is False
        for task in readyz_payload["llm_effective"]["tasks"]
    )

    health_response = client.get(
        _workspace_ai_path(workspace_slug, "/health"),
        headers=_auth_headers(auth["token"]),
    )
    assert health_response.status_code == 200, health_response.text
    health_payload = health_response.json()
    assert health_payload["ready"] is True
    assert health_payload["local"]["status"] == "model_missing"
    assert health_payload["external"]["ready"] is True
