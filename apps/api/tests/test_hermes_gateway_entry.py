from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest

from open_work_hub_api.domains.hermes.service import internal_mcp_server_name


pytestmark = pytest.mark.anyio


def _load_gateway_entry(monkeypatch):
    async def original_handler(_self, _request, *, _api_server):
        return {"handler": "original", "api_server": _api_server}

    gateway_module = ModuleType("gateway")
    gateway_module.__path__ = []  # type: ignore[attr-defined]
    platforms_module = ModuleType("gateway.platforms")
    platforms_module.__path__ = []  # type: ignore[attr-defined]
    runs_module = ModuleType("gateway.platforms.api_server_runs")
    runs_module._handle_runs = original_handler  # type: ignore[attr-defined]
    platforms_module.api_server_runs = runs_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "gateway", gateway_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms", platforms_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms.api_server_runs", runs_module)

    source = Path(__file__).resolve().parents[3] / "ops/hermes/gateway_entry.py"
    module_name = f"open_work_hub_hermes_gateway_test_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, runs_module


def _install_mcp_stubs(
    monkeypatch,
    *,
    profile_name: str,
    status_rows: list[dict],
) -> list[str]:
    calls: list[str] = []
    constants_module = ModuleType("hermes_constants")
    plugins_module = ModuleType("hermes_cli.plugins")
    plugins_module.get_plugin_manager = lambda: SimpleNamespace(  # type: ignore[attr-defined]
        list_plugins=lambda: [{"name": "owh_runtime", "enabled": True}]
    )
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins_module)
    constants_module.get_hermes_home = lambda: Path("/profiles") / profile_name  # type: ignore[attr-defined]
    tools_module = ModuleType("tools")
    tools_module.__path__ = []  # type: ignore[attr-defined]
    mcp_module = ModuleType("tools.mcp_tool")
    mcp_module.discover_mcp_tools = lambda: calls.append("discover")  # type: ignore[attr-defined]
    mcp_module.get_mcp_status = lambda: status_rows  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_constants", constants_module)
    monkeypatch.setitem(sys.modules, "tools", tools_module)
    monkeypatch.setitem(sys.modules, "tools.mcp_tool", mcp_module)
    return calls


def test_gateway_discovers_and_requires_the_current_profile_bridge(monkeypatch) -> None:
    gateway_entry, _runs_module = _load_gateway_entry(monkeypatch)
    profile_name = "owh-11111111111111111111111111111111"
    calls = _install_mcp_stubs(
        monkeypatch,
        profile_name=profile_name,
        status_rows=[
            {
                "name": internal_mcp_server_name(profile_name),
                "status": "connected",
                "disabled": False,
            }
        ],
    )

    gateway_entry._discover_request_profile_mcp()

    assert calls == ["discover"]


def test_gateway_fails_closed_when_the_profile_bridge_is_missing(monkeypatch) -> None:
    gateway_entry, _runs_module = _load_gateway_entry(monkeypatch)
    _install_mcp_stubs(
        monkeypatch,
        profile_name="owh-11111111111111111111111111111111",
        status_rows=[],
    )

    with pytest.raises(RuntimeError, match="MCP bridge is not connected"):
        gateway_entry._discover_request_profile_mcp()


async def test_gateway_discovers_before_delegating_run_admission(monkeypatch) -> None:
    gateway_entry, runs_module = _load_gateway_entry(monkeypatch)
    order: list[str] = []

    def discover() -> None:
        order.append("discover")

    async def original(_self, _request, *, _api_server):
        order.append("admit")
        return {"ok": True}

    monkeypatch.setattr(gateway_entry, "_discover_request_profile_mcp", discover)
    monkeypatch.setattr(gateway_entry, "_original_handle_runs", original)
    response = await runs_module._handle_runs(
        object(),
        object(),
        _api_server=SimpleNamespace(),
    )

    assert response == {"ok": True}
    assert order == ["discover", "admit"]
