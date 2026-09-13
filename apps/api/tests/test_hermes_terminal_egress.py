from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from uuid import uuid4


def _load_terminal_egress(monkeypatch):
    agent = ModuleType("agent")
    agent.__path__ = []  # type: ignore[attr-defined]
    proxy_sources = ModuleType("agent.proxy_sources")
    proxy_sources.__path__ = []  # type: ignore[attr-defined]
    iron_proxy = ModuleType("agent.proxy_sources.iron_proxy")
    for name in (
        "build_proxy_config",
        "discover_provider_mappings",
        "ensure_audit_log",
        "ensure_ca_cert",
        "find_iron_proxy",
        "get_status",
        "load_mappings",
        "merge_mappings",
        "start_proxy",
        "stop_proxy",
        "write_mappings",
        "write_proxy_config",
    ):
        setattr(iron_proxy, name, lambda *args, **kwargs: None)

    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.proxy_sources", proxy_sources)
    monkeypatch.setitem(sys.modules, "agent.proxy_sources.iron_proxy", iron_proxy)

    source = Path(__file__).resolve().parents[3] / "ops/hermes/terminal_egress.py"
    module_name = f"open_work_hub_hermes_terminal_egress_test_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_terminal_egress_extends_the_upstream_header_timeout(monkeypatch) -> None:
    terminal_egress = _load_terminal_egress(monkeypatch)
    config = {"proxy": {"upstream_response_header_timeout": "120s"}}

    terminal_egress._apply_managed_proxy_policy(config)

    assert config["proxy"]["upstream_response_header_timeout"] == "300s"


def test_egress_starts_without_legacy_provider_secret(monkeypatch, tmp_path):
    module = _load_terminal_egress(monkeypatch)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cert = tmp_path / "source.crt"
    cert.write_text("test certificate")
    module._CLIENT_DIR = tmp_path / "client"
    module._stop_requested = True
    module.find_iron_proxy = lambda **kwargs: "iron-proxy-test"
    module.ensure_ca_cert = lambda: (cert, tmp_path / "source.key")
    module.discover_provider_mappings = lambda **kwargs: []
    module.build_proxy_config = lambda **kwargs: {
        "proxy": {},
        "transforms": [{}, {"config": {"secrets": []}}],
    }
    module.get_status = lambda: type("Status", (), {"listening": True})()
    calls = []
    module.start_proxy = lambda **kwargs: calls.append(kwargs)
    monkeypatch.setattr(module.signal, "signal", lambda *args: None)
    module.main()
    assert calls[0]["extra_env"] == {}
    assert (module._CLIENT_DIR / "ca.crt").read_text() == "test certificate"
    assert not (module._CLIENT_DIR / "openrouter.token").exists()
