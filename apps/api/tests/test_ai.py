from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient
from openai import OpenAIError
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core import llm as llm_core
from open_work_hub_api.core.db import get_engine
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.model_credentials import encrypt_api_key
from open_work_hub_api.domains.ai.model_settings_models import (
    AiModelCatalogEntry,
    AiModelProviderConfig,
)
from open_work_hub_api.domains.ai.registry import get_ai_capability_registry
from open_work_hub_api.domains.auth.models import AuditLog
from open_work_hub_api.domains.meeting import conversation_scope as meeting_conversation_scope
from test_meeting import _auth_headers, _bootstrap_admin_session, _create_meeting, _dev_login


pytestmark = pytest.mark.usefixtures("configured_local_llm_control_plane")


class FakeModels:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def list(self) -> SimpleNamespace:
        return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in self._ids])


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
        self.chat = SimpleNamespace(completions=FakeChatCompletions(content, error=error))
        self.option_calls: list[dict[str, object]] = []

    def with_options(self, **kwargs) -> FakePoolClient:
        self.option_calls.append(kwargs)
        return self


def _workspace_ai_path(workspace_slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/chatbot{suffix}"


def _seeded_dev_login(client: TestClient, account_key: str) -> dict:
    _bootstrap_admin_session(client)
    return _dev_login(client, account_key)


def _set_policy(task_kind: str, policy_mode: str) -> None:
    registry = get_ai_capability_registry()
    workload = registry.resolve_llm_workload("chatbot")
    assert workload.task_kind == task_kind
    registry.llm_workloads[workload.workload_id] = replace(
        workload,
        default_route="external" if policy_mode == "external" else "local",
    )


def _configure_external_llm(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_external_allowed_providers", "openai,anthropic")
    with Session(get_engine()) as db:
        provider = db.get(AiModelProviderConfig, "openai")
        assert provider is not None
        model = db.get(AiModelCatalogEntry, "openai-gpt-5-4-mini")
        if model is None:
            model = AiModelCatalogEntry(
                id="openai-gpt-5-4-mini",
                provider_id="openai",
                model_key="gpt-5.4-mini",
                display_name="GPT-5.4 mini",
                capabilities_json=["chat", "tool_calling", "vision"],
                source="manual",
                discovery_status="active",
                enabled=True,
                version=1,
            )
            db.add(model)
        provider.enabled = True
        provider.endpoint_url = "https://api.openai.com/v1"
        provider.api_key_ciphertext = encrypt_api_key("test-openai-key")
        provider.default_model_id = model.id
        db.commit()


def _llm_audit_rows() -> list[AuditLog]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "llm_call")
                .order_by(AuditLog.created_at.asc())
            ).all()
        )


def _install_pool_clients(
    monkeypatch,
    *,
    local: FakePoolClient,
    external: FakePoolClient | None = None,
) -> None:
    def factory(config):  # type: ignore[no-untyped-def]
        if config.pool == "local":
            return local
        assert external is not None
        return external

    monkeypatch.setattr(llm_core, "_new_pool_client", factory)


def test_ai_chat_caller_provider_does_not_override_local_workload_route(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    pool_client = FakePoolClient(
        ["local/current-moe-test-model"],
        content="local response",
    )
    _install_pool_clients(monkeypatch, local=pool_client)

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "external_provider": "anthropic",
            "messages": [{"role": "user", "content": "테스트"}],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["content"] == "local response"
    assert response.json()["chosen_pool"] == "local"
    assert pool_client.chat.completions.calls


def test_ai_chat_caller_model_does_not_override_local_workload_model(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    pool_client = FakePoolClient(
        ["local/current-moe-test-model"],
        content="configured model response",
    )
    _install_pool_clients(monkeypatch, local=pool_client)
    before = len(_llm_audit_rows())

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "model": "gpt-5.4-mini",
            "messages": [{"role": "user", "content": "테스트"}],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["content"] == "configured model response"
    assert pool_client.chat.completions.calls[0]["model"] == "local/current-moe-test-model"
    assert len(_llm_audit_rows()) == before + 1


def test_ai_chat_auto_backend_still_uses_registered_local_workload_route(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    pool_client = FakePoolClient(
        ["local/current-moe-test-model"],
        content="registered route response",
    )
    _install_pool_clients(monkeypatch, local=pool_client)
    before = len(_llm_audit_rows())

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "auto",
            "model": "gpt-5.4-mini",
            "messages": [{"role": "user", "content": "테스트"}],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["chosen_pool"] == "local"
    assert pool_client.chat.completions.calls[0]["model"] == "local/current-moe-test-model"
    assert len(_llm_audit_rows()) == before + 1


def test_ai_chat_caller_local_mode_cannot_override_external_workload_route(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")
    _configure_external_llm(monkeypatch)

    local_client = FakePoolClient(
        ["local/current-moe-test-model"],
        content="local response",
    )
    external_client = FakePoolClient(
        ["gpt-5.4-mini"],
        content="external response",
    )
    _install_pool_clients(monkeypatch, local=local_client, external=external_client)

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
    assert payload["content"] == "external response"
    assert payload["policy"] == "external"
    assert payload["chosen_pool"] == "external"
    assert payload["decision_reason"] == "ai_security_enforcement_disabled"
    assert payload["forced_local"] is False
    assert external_client.chat.completions.calls
    assert local_client.chat.completions.calls == []

    audit_rows = _llm_audit_rows()
    assert len(audit_rows) == 1
    assert audit_rows[0].payload["policy"] == "external"
    assert audit_rows[0].payload["chosen_pool"] == "external"
    assert audit_rows[0].payload["decision_reason"] == "workload_route"
    assert audit_rows[0].payload["forced_local"] is False
    assert audit_rows[0].payload["status"] == "ok"


def test_ai_chat_tool_command_uses_registered_business_tool(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    workspace_slug = "delivery-hub"

    def _unexpected_pool_call(config):  # type: ignore[no-untyped-def]
        raise AssertionError(f"LLM pool should not be called for /tool commands: {config.pool}")

    monkeypatch.setattr(llm_core, "_new_pool_client", _unexpected_pool_call)

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "messages": [
                {
                    "role": "user",
                    "content": '/tool pms.search_tasks {"q":"AI chat tool issue","limit":5}',
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] == "tool"
    assert payload["decision_reason"] == "direct_tool_command"
    assert payload["model"] == "tool://pms.search_tasks"


def test_ai_chat_business_context_question_reaches_llm(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    workspace_slug = "delivery-hub"
    _set_policy("chatbot", "local_only")

    pool_client = FakePoolClient(
        ["local/current-moe-test-model"],
        content="업무 질문도 LLM 경로에서 답변",
    )
    _install_pool_clients(monkeypatch, local=pool_client)

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "PMS에서 내 업무 이슈를 검색해줘",
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["content"] == "업무 질문도 LLM 경로에서 답변"
    assert payload["chosen_pool"] == "local"
    assert payload["decision_reason"] == "workload_route"
    assert pool_client.chat.completions.calls


def test_ai_chat_tool_command_scoped_conversation_skips_scope_prompt_lookup(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    meeting = _create_meeting(
        client,
        auth["token"],
        workspace_slug=workspace_slug,
        title="Scoped AI chat meeting",
    )

    conversation_response = client.post(
        _workspace_ai_path(workspace_slug, "/conversations"),
        headers=_auth_headers(auth["token"]),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )
    assert conversation_response.status_code == 201, conversation_response.text
    conversation_id = conversation_response.json()["id"]

    def _unexpected_scope_prompt(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("scope prompt lookup should not run for /tool commands")

    def _unexpected_pool_call(config):  # type: ignore[no-untyped-def]
        raise AssertionError(f"LLM pool should not be called for /tool commands: {config.pool}")

    monkeypatch.setattr(
        meeting_conversation_scope.meeting_service,
        "build_meeting_scope_prompt",
        _unexpected_scope_prompt,
    )
    monkeypatch.setattr(llm_core, "_new_pool_client", _unexpected_pool_call)

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "conversationId": conversation_id,
            "messages": [
                {
                    "role": "user",
                    "content": '/tool pms.search_tasks {"q":"Scoped AI chat tool issue","limit":5}',
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] == "tool"
    assert payload["decision_reason"] == "direct_tool_command"


def test_ai_chat_external_workload_is_not_silently_rerouted_by_payload(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")
    _configure_external_llm(monkeypatch)

    local_client = FakePoolClient(
        ["local/current-moe-test-model"],
        content="safe local response",
    )
    external_client = FakePoolClient(
        ["gpt-5.4-mini"],
        content="external response",
    )
    _install_pool_clients(monkeypatch, local=local_client, external=external_client)

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
    assert payload["chosen_pool"] == "external"
    assert payload["decision_reason"] == "ai_security_enforcement_disabled"
    assert payload["forced_local"] is False
    assert payload["pii_hits"] == []
    assert external_client.chat.completions.calls
    assert local_client.chat.completions.calls == []

    audit_rows = _llm_audit_rows()
    assert audit_rows[-1].payload["chosen_pool"] == "external"
    assert audit_rows[-1].payload["decision_reason"] == "workload_route"
    assert audit_rows[-1].payload["pii_hits"] == []


def test_ai_chat_external_provider_error_does_not_fallback_to_local(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")
    _configure_external_llm(monkeypatch)

    local_client = FakePoolClient(
        ["local/current-moe-test-model"],
        content="local response",
    )
    external_client = FakePoolClient(
        ["gpt-5.4-mini"],
        error=OpenAIError("provider boom"),
    )
    _install_pool_clients(monkeypatch, local=local_client, external=external_client)

    response = client.post(
        _workspace_ai_path(workspace_slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "auto",
            "messages": [{"role": "user", "content": "에러를 재현해줘"}],
        },
    )

    assert response.status_code == 503, response.text
    assert external_client.chat.completions.calls
    assert local_client.chat.completions.calls == []
    audit_rows = _llm_audit_rows()
    assert audit_rows[-1].payload["status"] == "error"
    assert audit_rows[-1].payload["chosen_pool"] == "external"
    assert audit_rows[-1].payload["decision_reason"] == "workload_route"


@pytest.mark.fresh_api_app
def test_readyz_uses_configured_readiness_while_ai_health_stays_live(
    client: TestClient,
    monkeypatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    workspace_slug = auth["user"]["workspaces"][0]["slug"]
    _configure_external_llm(monkeypatch)

    def fake_pool_client(config: llm_core.LlmPoolConfig) -> FakePoolClient:
        if config.pool == "external":
            assert config.provider == "openai"
            return FakePoolClient(["gpt-5.4-mini"])
        return FakePoolClient(["other-local-model"])

    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("readyz must not call live LLM providers")
        ),
    )

    readyz_response = client.get("/readyz")
    assert readyz_response.status_code == 503
    readyz_payload = readyz_response.json()
    assert readyz_payload["status"] == "degraded"
    assert readyz_payload["llm"]["ready"] is True
    assert readyz_payload["llm"]["local"]["status"] == "ready"
    assert "base_url" not in readyz_payload["llm"]["local"]
    assert readyz_payload["llm_effective"]["ready"] is False
    effective_tasks = {task["task_kind"]: task for task in readyz_payload["llm_effective"]["tasks"]}
    assert any(task["ready"] is False for task in effective_tasks.values())
    assert effective_tasks["chatbot"]["chosen_pool"] == "local"

    _set_policy("chatbot", "external")
    monkeypatch.setattr(llm_core, "_new_pool_client", fake_pool_client)
    health_response = client.get(
        _workspace_ai_path(workspace_slug, "/health"),
        headers={**_auth_headers(auth["token"]), "x-open-work-hub-locale": "en-US"},
    )
    assert health_response.status_code == 200, health_response.text
    health_payload = health_response.json()
    assert health_payload["ready"] is True
    assert health_payload["local"]["status"] == "model_missing"
    assert health_payload["local"]["detail"].startswith("Configured LLM model was not found.")
    assert health_payload["external"]["ready"] is True
