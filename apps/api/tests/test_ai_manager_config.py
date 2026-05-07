from __future__ import annotations

from ai_do_api.core.settings import Settings
from ai_do_api.domains.ai.manager_runtime import (
    AI_MANAGER_ADAPTER_ID,
    build_ai_manager_config,
)


def _settings(**overrides):
    aliases = {
        "ai_manager_enabled": "AI_DO_AI_MANAGER_ENABLED",
        "ai_manager_provider": "AI_DO_AI_MANAGER_PROVIDER",
        "ai_manager_model": "AI_DO_AI_MANAGER_MODEL",
        "ai_manager_max_loops": "AI_DO_AI_MANAGER_MAX_LOOPS",
        "ai_manager_trace_sensitive_data": (
            "AI_DO_AI_MANAGER_TRACE_SENSITIVE_DATA"
        ),
        "ai_manager_store_response": "AI_DO_AI_MANAGER_STORE_RESPONSE",
        "ai_manager_hosted_tools_enabled": (
            "AI_DO_AI_MANAGER_HOSTED_TOOLS_ENABLED"
        ),
    }
    return Settings(
        _env_file=None,
        DOOWON_POSTGRES_DSN="postgresql+psycopg://ai_do_test:ai_do_test@127.0.0.1:5432/ai_do_test",
        **{aliases.get(key, key): value for key, value in overrides.items()},
    )


def test_ai_manager_settings_are_disabled_and_safe_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = _settings()

    assert settings.ai_manager_enabled is False
    assert settings.ai_manager_provider == "openai"
    assert settings.ai_manager_model == ""
    assert settings.ai_manager_max_loops == 3
    assert settings.ai_manager_trace_sensitive_data is False
    assert settings.ai_manager_store_response is False
    assert settings.ai_manager_hosted_tools_enabled is False

    config = build_ai_manager_config(settings)

    assert config.public_summary() == {
        "adapter_id": AI_MANAGER_ADAPTER_ID,
        "enabled": False,
        "ready": False,
        "disabled_reason": "feature_disabled",
        "provider": "openai",
        "model_configured": False,
        "max_loops": 3,
        "trace_sensitive_data": False,
        "store_response": False,
        "hosted_tools_enabled": False,
    }
    assert config.safety_defaults_enabled is True


def test_ai_manager_enabled_requires_model() -> None:
    config = build_ai_manager_config(
        _settings(
            ai_manager_enabled=True,
            ai_manager_model="",
        )
    )

    assert config.enabled is True
    assert config.ready is False
    assert config.disabled_reason == "model_not_configured"


def test_ai_manager_accepts_openai_model_when_enabled() -> None:
    config = build_ai_manager_config(
        _settings(
            ai_manager_enabled=True,
            ai_manager_model="gpt-5.4",
        )
    )

    assert config.enabled is True
    assert config.ready is True
    assert config.disabled_reason is None
    assert config.provider == "openai"
    assert config.model == "gpt-5.4"
    assert config.max_loops == 3
    assert config.safety_defaults_enabled is True


def test_ai_manager_rejects_non_openai_provider() -> None:
    config = build_ai_manager_config(
        _settings(
            ai_manager_enabled=True,
            ai_manager_provider="claude",
            ai_manager_model="claude-sonnet",
        )
    )

    assert config.ready is False
    assert config.disabled_reason == "unsupported_provider"


def test_ai_manager_env_aliases_parse() -> None:
    settings = Settings(
        _env_file=None,
        DOOWON_POSTGRES_DSN="postgresql+psycopg://ai_do_test:ai_do_test@127.0.0.1:5432/ai_do_test",
        AI_DO_AI_MANAGER_ENABLED="1",
        AI_DO_AI_MANAGER_PROVIDER="openai",
        AI_DO_AI_MANAGER_MODEL="gpt-test",
        AI_DO_AI_MANAGER_MAX_LOOPS="2",
        AI_DO_AI_MANAGER_TRACE_SENSITIVE_DATA="0",
        AI_DO_AI_MANAGER_STORE_RESPONSE="0",
        AI_DO_AI_MANAGER_HOSTED_TOOLS_ENABLED="0",
    )

    config = build_ai_manager_config(settings)

    assert config.ready is True
    assert config.model == "gpt-test"
    assert config.max_loops == 2
    assert config.trace_sensitive_data is False
    assert config.store_response is False
    assert config.hosted_tools_enabled is False
