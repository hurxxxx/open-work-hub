from types import SimpleNamespace
import pytest
from open_work_hub_api.domains.ai import registry as module


def test_app_registration_alone_loads_and_deduplicates_ai_hooks(monkeypatch):
    module.reset_ai_capability_registry()
    calls = []
    monkeypatch.setattr(
        module,
        "iter_app_catalog",
        lambda: [SimpleNamespace(app_id="one"), SimpleNamespace(app_id="two")],
    )
    monkeypatch.setattr(
        module,
        "get_app_registration",
        lambda _app: SimpleNamespace(ai_capability_modules=("example.shared_ai",)),
    )
    monkeypatch.setattr(module, "_register_domain", lambda registry, name: calls.append(name))
    try:
        module.get_ai_capability_registry()
        assert calls == ["example.shared_ai"]
    finally:
        module.reset_ai_capability_registry()


def test_declared_missing_ai_hook_fails_closed():
    with pytest.raises(ValueError, match="Missing AI registration hook"):
        module._register_domain(module.AiCapabilityRegistry(), "types")


@pytest.mark.anyio
async def test_agent_status_uses_current_policy_when_cached_profile_metadata_is_stale(monkeypatch):
    from open_work_hub_api.domains.hermes import router

    binding = SimpleNamespace(
        profile_name="same-user", status="ready", provider="openai", model="B"
    )
    current = SimpleNamespace(provider="openrouter", model="A")
    seen = []

    async def ensure(db, *, user, model_policy):
        seen.append(model_policy.model)
        return binding

    async def healthy(_profile):
        return {}

    monkeypatch.setattr(router, "resolve_model_policy", lambda _db: current)
    monkeypatch.setattr(router, "ensure_profile_binding", ensure)
    monkeypatch.setattr(
        router, "runtime_client", lambda: SimpleNamespace(health=healthy, capabilities=healthy)
    )
    for model in ("A", "B", "A"):
        current.model = model
        result = await router.get_agent_status(db=object(), current_user=SimpleNamespace(id="user"))
        assert result.model == model and result.provider == current.provider
    assert seen == ["A", "B", "A"]
    assert binding.model == "B"


@pytest.mark.parametrize(
    "provider,route,endpoint,wire",
    [
        ("openai", "external", "https://api.openai.com/v1", "chat_completions"),
        ("openrouter", "external", "https://openrouter.ai/api/v1", "chat_completions"),
        ("anthropic", "external", "https://api.anthropic.com", "anthropic_messages"),
        ("gemini", "external", "https://generativelanguage.googleapis.com", "chat_completions"),
        ("openai_compatible", "local", "http://127.0.0.1:11434/v1", "chat_completions"),
    ],
)
def test_connection_families_share_native_policy_contract(provider, route, endpoint, wire):
    from open_work_hub_api.core.llm import LlmPoolConfig
    from open_work_hub_api.domains.hermes.model_policy import HermesModelPolicy

    config = LlmPoolConfig(
        pool=route,
        provider=provider,
        connection_id="connection-one",
        base_url=endpoint,
        api_key="synthetic-private-key",
        default_model="test/model",
        canonical_model="test/model",
        healthcheck_timeout_seconds=5,
        long_generation_timeout_seconds=30,
    )
    policy = HermesModelPolicy.from_pool(config, model="test/model", max_tokens=8192)
    assert policy.api_mode == wire
    assert policy.connection_id == "connection-one"
    assert policy.run_options()["owh_policy"]["model"] == "test/model"
    assert "synthetic-private-key" not in repr(config)
    assert "synthetic-private-key" not in repr(policy.run_options())
    if provider == "gemini":
        assert policy.endpoint.endswith("/v1beta/openai")


def test_retired_web_search_routes_are_absent_and_chatbot_remains(client):
    from open_work_hub_api.domains.auth.app_catalog import get_app_catalog_item

    assert get_app_catalog_item("web-search") is None
    assert get_app_catalog_item("chatbot") is not None
    paths = client.app.openapi()["paths"]
    assert not any(path.startswith("/api/v1/web-search") for path in paths)
    assert client.post("/api/v1/web-search/ask", json={"question": "test"}).status_code == 404
