from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aidoo_api.core import llm
from aidoo_api.core.settings import get_settings


class FakeModels:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def list(self) -> SimpleNamespace:
        return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in self._ids])


class FakeChatCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            model=str(kwargs["model"]),
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        )


class FakeClient:
    def __init__(self, ids: list[str], content: str = "ok") -> None:
        self.models = FakeModels(ids)
        self.chat = SimpleNamespace(completions=FakeChatCompletions(content))


def _clear_llm_client_cache() -> None:
    cache_clear = getattr(llm.get_llm_client, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DOOWON_POSTGRES_DSN",
        "postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test",
    )
    get_settings.cache_clear()
    _clear_llm_client_cache()
    yield
    get_settings.cache_clear()
    _clear_llm_client_cache()


def test_llm_settings_default_to_local_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOOWON_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DOOWON_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("DOOWON_LLM_API_KEY", raising=False)
    monkeypatch.delenv("DOOWON_LLM_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("DOOWON_LLM_CANONICAL_MODEL", raising=False)
    monkeypatch.delenv("DOOWON_LLM_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("DOOWON_LLM_FALLBACK_MODEL", raising=False)

    settings = get_settings()

    assert settings.llm_provider == "ollama"
    assert settings.llm_base_url == "http://127.0.0.1:11434/v1"
    assert settings.llm_api_key == "ollama"
    assert settings.llm_default_model == "qwen3.5:35b-a3b-q4_K_M"
    assert settings.llm_canonical_model == "qwen/qwen3.5-35b-a3b"
    assert settings.llm_fallback_enabled is True
    assert settings.llm_fallback_model == "qwen/qwen3.5-35b-a3b"


def test_llm_health_ready_when_configured_model_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOOWON_LLM_DEFAULT_MODEL", "qwen3.5:35b-a3b-q4_K_M")
    monkeypatch.setattr(
        llm,
        "get_llm_client",
        lambda backend="primary": FakeClient(["qwen3.5:35b-a3b-q4_K_M"]),
    )

    health = llm.check_llm_health()

    assert health.ready is True
    assert health.status == "ready"


def test_llm_health_reports_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOOWON_LLM_DEFAULT_MODEL", "qwen3.5:35b-a3b-q4_K_M")
    monkeypatch.setattr(llm, "get_llm_client", lambda backend="primary": FakeClient(["gemma4:31b"]))

    health = llm.check_llm_health()

    assert health.ready is False
    assert health.status == "model_missing"
    assert "gemma4:31b" in (health.detail or "")


def test_llm_stack_is_ready_when_fallback_has_same_canonical_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOOWON_LLM_DEFAULT_MODEL", "qwen3.5:35b-a3b-q4_K_M")
    monkeypatch.setenv("DOOWON_LLM_FALLBACK_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("DOOWON_LLM_FALLBACK_MODEL", "qwen/qwen3.5-35b-a3b")

    def fake_client(backend: llm.LlmBackendName = "primary") -> FakeClient:
        if backend == "fallback":
            return FakeClient(["qwen/qwen3.5-35b-a3b"])
        return FakeClient(["gemma4:31b"])

    monkeypatch.setattr(llm, "get_llm_client", fake_client)

    health = llm.check_llm_stack_health()

    assert health.ready is True
    assert health.primary.status == "model_missing"
    assert health.fallback is not None
    assert health.fallback.ready is True
    assert health.active.name == "fallback"
    assert health.active.canonical_model == "qwen/qwen3.5-35b-a3b"


def test_chat_falls_back_to_openrouter_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from aidoo_api.domains.ai import router as ai_router

    monkeypatch.setenv("DOOWON_LLM_DEFAULT_MODEL", "qwen3.5:35b-a3b-q4_K_M")
    monkeypatch.setenv("DOOWON_LLM_FALLBACK_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("DOOWON_LLM_FALLBACK_MODEL", "qwen/qwen3.5-35b-a3b")
    get_settings.cache_clear()

    clients = {
        "primary": FakeClient(["gemma4:31b"]),
        "fallback": FakeClient(["qwen/qwen3.5-35b-a3b"], content="fallback response"),
    }

    def fake_client(backend: llm.LlmBackendName = "primary") -> FakeClient:
        return clients[backend]

    monkeypatch.setattr(llm, "get_llm_client", fake_client)
    monkeypatch.setattr(ai_router, "get_llm_client", fake_client)

    response = ai_router.chat(
        ai_router.ChatRequest(
            messages=[ai_router.ChatMessage(role="user", content="테스트")],
        ),
    )

    assert response.backend == "fallback"
    assert response.provider == "openrouter"
    assert response.fallback_used is True
    assert response.content == "fallback response"
    assert clients["fallback"].chat.completions.calls[0]["model"] == "qwen/qwen3.5-35b-a3b"


def test_chat_can_force_openrouter_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from aidoo_api.domains.ai import router as ai_router

    monkeypatch.setenv("DOOWON_LLM_DEFAULT_MODEL", "qwen3.5:35b-a3b-q4_K_M")
    monkeypatch.setenv("DOOWON_LLM_FALLBACK_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("DOOWON_LLM_FALLBACK_MODEL", "qwen/qwen3.5-35b-a3b")
    get_settings.cache_clear()

    clients = {
        "primary": FakeClient(["qwen3.5:35b-a3b-q4_K_M"], content="local response"),
        "fallback": FakeClient(["qwen/qwen3.5-35b-a3b"], content="openrouter response"),
    }

    def fake_client(backend: llm.LlmBackendName = "primary") -> FakeClient:
        return clients[backend]

    monkeypatch.setattr(llm, "get_llm_client", fake_client)
    monkeypatch.setattr(ai_router, "get_llm_client", fake_client)

    response = ai_router.chat(
        ai_router.ChatRequest(
            backend_mode="openrouter",
            messages=[ai_router.ChatMessage(role="user", content="테스트")],
        ),
    )

    assert response.backend == "fallback"
    assert response.requested_backend_mode == "openrouter"
    assert response.content == "openrouter response"
    assert clients["primary"].chat.completions.calls == []


def test_chat_can_force_local_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from aidoo_api.domains.ai import router as ai_router

    monkeypatch.setenv("DOOWON_LLM_DEFAULT_MODEL", "qwen3.5:35b-a3b-q4_K_M")
    monkeypatch.setenv("DOOWON_LLM_FALLBACK_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("DOOWON_LLM_FALLBACK_MODEL", "qwen/qwen3.5-35b-a3b")
    get_settings.cache_clear()

    clients = {
        "primary": FakeClient(["gemma4:31b"], content="local response"),
        "fallback": FakeClient(["qwen/qwen3.5-35b-a3b"], content="openrouter response"),
    }

    def fake_client(backend: llm.LlmBackendName = "primary") -> FakeClient:
        return clients[backend]

    monkeypatch.setattr(llm, "get_llm_client", fake_client)
    monkeypatch.setattr(ai_router, "get_llm_client", fake_client)

    with pytest.raises(HTTPException) as exc_info:
        ai_router.chat(
            ai_router.ChatRequest(
                backend_mode="local",
                messages=[ai_router.ChatMessage(role="user", content="테스트")],
            ),
        )

    assert exc_info.value.status_code == 503
    assert clients["fallback"].chat.completions.calls == []
