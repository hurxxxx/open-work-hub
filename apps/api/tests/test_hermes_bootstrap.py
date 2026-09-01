from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Any
from uuid import uuid4


def _load_bootstrap(monkeypatch, config: dict[str, Any]):
    saved: list[dict[str, Any]] = []

    hermes_cli = ModuleType("hermes_cli")
    hermes_cli.__path__ = []  # type: ignore[attr-defined]
    config_module = ModuleType("hermes_cli.config")
    config_module.load_config = lambda: deepcopy(config)  # type: ignore[attr-defined]
    config_module.save_config = lambda value: saved.append(deepcopy(value))  # type: ignore[attr-defined]
    config_module.save_env_value = lambda _name, _value: None  # type: ignore[attr-defined]
    profiles_module = ModuleType("hermes_cli.profiles")
    profiles_module.list_profiles = lambda: []  # type: ignore[attr-defined]
    constants_module = ModuleType("hermes_constants")
    constants_module.get_hermes_home = lambda: Path("/tmp/hermes-test")  # type: ignore[attr-defined]
    constants_module.set_hermes_home_override = lambda _path: object()  # type: ignore[attr-defined]
    constants_module.reset_hermes_home_override = lambda _token: None  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config_module)
    monkeypatch.setitem(sys.modules, "hermes_cli.profiles", profiles_module)
    monkeypatch.setitem(sys.modules, "hermes_constants", constants_module)

    source = Path(__file__).resolve().parents[3] / "ops/hermes/bootstrap.py"
    module_name = f"open_work_hub_hermes_bootstrap_test_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, saved


def test_bootstrap_uses_official_settings_to_replace_gemini_fallback(monkeypatch) -> None:
    config = {
        "model": {"provider": "anthropic", "default": "claude"},
        "fallback_providers": [
            {"provider": "openai-codex", "model": "gpt-codex"}
        ],
        "fallback_model": {"provider": "google", "model": "gemini"},
        "auxiliary": {
            "openrouter_model": "google/gemini-3.6-flash",
            "approval": {
                "provider": "google",
                "model": "gemini",
                "base_url": "https://unexpected.example.test",
                "api_key": "unexpected-secret",
                "fallback_chain": [{"provider": "nous", "model": "hermes"}],
            },
        },
        "delegation": {
            "provider": "openai-codex",
            "model": "gpt-codex",
            "api_mode": "codex_responses",
        },
        "moa": {
            "presets": {
                "custom": {
                    "reference_models": [
                        {"provider": "openai-codex", "model": "gpt-codex"},
                        {"provider": "google", "model": "gemini"},
                    ],
                    "aggregator": {"provider": "anthropic", "model": "claude"},
                }
            }
        },
    }
    bootstrap, saved = _load_bootstrap(monkeypatch, config)

    assert bootstrap._reconcile_fixed_model_config("default") is True
    assert len(saved) == 1
    reconciled = saved[0]
    assert reconciled["model"] == {
        "provider": "openrouter",
        "default": "qwen/qwen3.8-flash",
    }
    assert reconciled["fallback_providers"] == []
    assert "fallback_model" not in reconciled
    assert reconciled["auxiliary"]["openrouter_model"] == "qwen/qwen3.8-flash"
    assert reconciled["auxiliary"]["free_only"] is False
    assert reconciled["auxiliary"]["approval"] == {
        "provider": "google",
        "model": "gemini",
        "base_url": "https://unexpected.example.test",
        "api_key": "unexpected-secret",
        "fallback_chain": [{"provider": "nous", "model": "hermes"}],
    }
    assert reconciled["delegation"] == {
        "provider": "openai-codex",
        "model": "gpt-codex",
        "api_mode": "codex_responses",
    }
    preset = reconciled["moa"]["presets"]["custom"]
    assert preset["reference_models"][0]["provider"] == "openai-codex"
    assert preset["aggregator"] == {"provider": "anthropic", "model": "claude"}
    assert bootstrap._apply_fixed_model_policy(reconciled) is False


def test_bootstrap_does_not_pin_unmanaged_named_profiles(monkeypatch) -> None:
    bootstrap, saved = _load_bootstrap(
        monkeypatch,
        {"model": {"provider": "ollama", "default": "local-model"}},
    )

    assert bootstrap._reconcile_fixed_model_config("personal") is False
    assert saved == []
