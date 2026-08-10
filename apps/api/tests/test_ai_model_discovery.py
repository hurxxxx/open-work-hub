from __future__ import annotations

from types import SimpleNamespace

import pytest

from open_work_hub_api.core.llm_provider_registry import (
    ExternalLlmProviderDescriptor,
    ensure_default_external_llm_providers_registered,
    register_external_llm_provider,
    reset_external_llm_providers,
)
from open_work_hub_api.domains.ai import model_discovery
from open_work_hub_api.domains.ai.model_discovery import (
    ProviderModelDiscoveryError,
    discover_provider_models,
)


class _FakeModels:
    def __init__(self, items: list[object], *, error: Exception | None = None) -> None:
        self.items = items
        self.error = error
        self.calls: list[dict[str, object]] = []

    def list(self, **kwargs: object) -> list[object]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.items


class _FakeClient:
    def __init__(self, items: list[object], *, error: Exception | None = None) -> None:
        self.models = _FakeModels(items, error=error)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_openai_compatible_plugin_reuses_registered_discovery_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_external_llm_providers()
    ensure_default_external_llm_providers_registered()
    register_external_llm_provider(
        ExternalLlmProviderDescriptor(
            "compatible-plugin",
            official=False,
            openai_compatible=True,
        )
    )
    client = _FakeClient([SimpleNamespace(id="plugin-model")])
    monkeypatch.setattr(model_discovery, "_new_openai_client", lambda **_kwargs: client)
    try:
        result = discover_provider_models(
            "compatible-plugin",
            "https://plugin.example.test/v1",
            "secret",
            5,
        )
    finally:
        reset_external_llm_providers()
        ensure_default_external_llm_providers_registered()

    assert [item.model_key for item in result] == ["plugin-model"]
    assert client.closed is True


def test_local_openai_compatible_discovery_allows_an_empty_key_and_normalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient(
        [
            SimpleNamespace(id=" model-a "),
            SimpleNamespace(id="model-a"),
            SimpleNamespace(id=""),
            SimpleNamespace(id="x" * 161),
            SimpleNamespace(id="model-b"),
        ]
    )
    captured: dict[str, object] = {}

    def factory(**kwargs: object) -> _FakeClient:
        captured.update(kwargs)
        return client

    monkeypatch.setattr(model_discovery, "_new_openai_client", factory)

    result = discover_provider_models(
        " LOCAL ",
        "http://local.test/v1/",
        None,
        2.5,
    )

    assert [model.model_key for model in result] == ["model-a", "model-b"]
    assert all(model.capabilities == () for model in result)
    assert captured == {
        "endpoint_url": "http://local.test/v1",
        "api_key": "",
        "timeout_seconds": 2.5,
    }
    assert client.closed is True


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
def test_external_discovery_requires_an_api_key(provider: str) -> None:
    with pytest.raises(ProviderModelDiscoveryError) as caught:
        discover_provider_models(provider, "https://provider.test", " ", 5)

    assert caught.value.code == "api_key_required"
    assert str(caught.value) == "api_key_required"


def test_anthropic_discovery_uses_display_name_and_chat_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient([SimpleNamespace(id="claude-model", display_name="Claude Model")])
    monkeypatch.setattr(
        model_discovery,
        "_new_anthropic_client",
        lambda **_kwargs: client,
    )

    result = discover_provider_models(
        "anthropic",
        "https://api.anthropic.test",
        "secret",
        10,
    )

    assert result[0].model_key == "claude-model"
    assert result[0].display_name == "Claude Model"
    assert result[0].capabilities == ("chat",)
    assert client.models.calls == [{"limit": 100}]
    assert client.closed is True


def test_gemini_discovery_normalizes_resource_names_and_advertised_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient(
        [
            SimpleNamespace(
                name="models/gemini-chat",
                display_name="Gemini Chat",
                supported_actions=["generateContent"],
            ),
            SimpleNamespace(
                name="models/gemini-embed",
                display_name="Gemini Embed",
                supported_actions=["embedContent"],
            ),
        ]
    )
    monkeypatch.setattr(
        model_discovery,
        "_new_gemini_client",
        lambda **_kwargs: client,
    )

    result = discover_provider_models(
        "gemini",
        "https://generativelanguage.test",
        "secret",
        10,
    )

    assert [(item.model_key, item.capabilities) for item in result] == [
        ("gemini-chat", ("chat",)),
        ("gemini-embed", ()),
    ]
    assert client.models.calls[0]["config"].page_size == 100
    assert client.closed is True


def test_discovery_limits_unique_results_and_display_name_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient([SimpleNamespace(id=f"model-{index}") for index in range(501)])
    monkeypatch.setattr(
        model_discovery,
        "_new_openai_client",
        lambda **_kwargs: client,
    )

    result = discover_provider_models(
        "openai",
        "https://api.openai.test/v1",
        "secret",
        10,
    )

    assert len(result) == 500
    assert result[-1].model_key == "model-499"


def test_provider_errors_are_replaced_with_a_safe_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_message = "request failed with Authorization: Bearer top-secret"
    client = _FakeClient([], error=RuntimeError(raw_message))
    monkeypatch.setattr(
        model_discovery,
        "_new_openai_client",
        lambda **_kwargs: client,
    )

    with pytest.raises(ProviderModelDiscoveryError) as caught:
        discover_provider_models(
            "openai",
            "https://api.openai.test/v1",
            "top-secret",
            10,
        )

    assert caught.value.code == "provider_unavailable"
    assert raw_message not in str(caught.value)
    assert "top-secret" not in repr(caught.value)
    assert client.closed is True


def test_unknown_provider_fails_before_sdk_dispatch() -> None:
    with pytest.raises(ProviderModelDiscoveryError) as caught:
        discover_provider_models("unknown", "https://provider.test", "secret", 5)

    assert caught.value.code == "provider_not_supported"
