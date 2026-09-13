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


def test_bootstrap_preserves_db_model_policy_and_configures_native_runtime(monkeypatch) -> None:
    config = {
        "model": {"provider": "custom:db-policy", "default": "admin-model"},
        "providers": {"db-policy": {"key_env": "SCOPED_TEST_KEY"}},
        "fallback_providers": [],
        "auxiliary": {"compression": {"provider": "main"}},
        "plugins": {"enabled": ["other-plugin"], "disabled": ["owh_runtime"]},
        "agent": {"environment_probe": False},
    }
    bootstrap, saved = _load_bootstrap(monkeypatch, config)
    assert bootstrap._reconcile_runtime_config("default") is True
    reconciled = saved[0]
    for key in ("model", "providers", "fallback_providers", "auxiliary"):
        assert reconciled[key] == config[key]
    assert reconciled["plugins"] == {"enabled": ["other-plugin", "owh_runtime"], "disabled": []}
    assert reconciled["gateway"]["api_server"]["max_concurrent_runs"] == 0
    assert reconciled["terminal"] == {
        "backend": "owh_sandbox",
        "container_persistent": False,
        "cwd": "/workspace",
    }
    assert reconciled["agent"]["environment_probe"] is False
    assert bootstrap._apply_runtime_policy(reconciled) is False


def test_bootstrap_does_not_pin_unmanaged_named_profiles(monkeypatch) -> None:
    bootstrap, saved = _load_bootstrap(
        monkeypatch,
        {"model": {"provider": "ollama", "default": "local-model"}},
    )

    assert bootstrap._reconcile_runtime_config("personal") is False
    assert saved == []
