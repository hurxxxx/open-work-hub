from types import SimpleNamespace

import pytest

from aidoo_api.core import llm
from aidoo_api.core.settings import get_settings


class FakeModels:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def list(self) -> SimpleNamespace:
        return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in self._ids])


class FakeClient:
    def __init__(self, ids: list[str]) -> None:
        self.models = FakeModels(ids)


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

    settings = get_settings()

    assert settings.llm_provider == "ollama"
    assert settings.llm_base_url == "http://127.0.0.1:11434/v1"
    assert settings.llm_api_key == "ollama"
    assert settings.llm_default_model == "qwen3.5:35b-a3b-q4_K_M"


def test_llm_health_ready_when_configured_model_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOOWON_LLM_DEFAULT_MODEL", "qwen3.5:35b-a3b-q4_K_M")
    monkeypatch.setattr(llm, "get_llm_client", lambda: FakeClient(["qwen3.5:35b-a3b-q4_K_M"]))

    health = llm.check_llm_health()

    assert health.ready is True
    assert health.status == "ready"


def test_llm_health_reports_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOOWON_LLM_DEFAULT_MODEL", "qwen3.5:35b-a3b-q4_K_M")
    monkeypatch.setattr(llm, "get_llm_client", lambda: FakeClient(["gemma4:31b"]))

    health = llm.check_llm_health()

    assert health.ready is False
    assert health.status == "model_missing"
    assert "gemma4:31b" in (health.detail or "")
