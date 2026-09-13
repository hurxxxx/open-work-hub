from __future__ import annotations

import importlib.util
import hashlib
import json
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
    runs_module._http_routes = lambda self: []  # type: ignore[attr-defined]
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


@pytest.fixture
def cancellation_gateway(monkeypatch):
    entry, runs = _load_gateway_entry(monkeypatch)
    records = {}
    state = SimpleNamespace(profile="owh-" + "a" * 32)

    class Store:
        durable = True

        def reserve(self, scope, key, fingerprint, run_id, status, **kwargs):
            previous = records.get((scope, key))
            if previous:
                return ("reused" if previous[0] == fingerprint else "conflict"), previous[1]
            record = {"run_id": run_id, "status": status}
            records[scope, key] = fingerprint, record
            return "created", record

    api = SimpleNamespace(
        _api_request_profile=SimpleNamespace(get=lambda: state.profile),
        _openai_error=lambda message, **kwargs: {"error": {"message": message, **kwargs}},
        web=SimpleNamespace(
            json_response=lambda body, status=200: SimpleNamespace(body=body, status=status)
        ),
    )
    monkeypatch.setattr(sys.modules["gateway.platforms"], "api_server", api, raising=False)
    adapter = SimpleNamespace(
        _check_auth=lambda request: None,
        _run_idempotency_store=Store(),
        _run_idempotency_scope=lambda request: state.profile,
        _parse_session_key_header=lambda request: (
            request.headers.get("X-Hermes-Session-Key"),
            None,
        ),
        _run_owner_pid=123,
        _run_owner_started=456,
    )
    body = {
        "input": "test",
        "session_id": "session",
        "provider": "custom:synthetic",
        "model": "test",
    }

    async def request_json():
        return body

    request = SimpleNamespace(
        headers={"Idempotency-Key": "owh-run", "X-Hermes-Session-Key": "conversation"},
        json=request_json,
    )
    route = next(
        row for row in runs._http_routes(adapter) if row[1] == "/v1/owh/runs/cancel-admission"
    )
    assert route[0] == "POST"
    return SimpleNamespace(
        handler=route[2],
        request=request,
        body=body,
        adapter=adapter,
        records=records,
        state=state,
    )


async def test_cancel_admission_fences_a_late_creation_and_replays_exact_requests(
    cancellation_gateway,
):
    state = cancellation_gateway
    first = await state.handler(state.request)
    assert first.status == 202 and first.body["status"] == "cancelled"
    fingerprint = hashlib.sha256(
        json.dumps(
            {"body": state.body, "gateway_session_key": "conversation"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    # Native admission uses this same store/fingerprint. Its late reserve must
    # replay cancellation, so native _handle_runs never starts its background task.
    outcome, record = state.adapter._run_idempotency_store.reserve(
        state.state.profile, "owh-run", fingerprint, "late-native-id", {"status": "queued"}
    )
    assert outcome == "reused" and record["run_id"] == first.body["run_id"]
    assert record["status"]["status"] == "cancelled"
    replay = await state.handler(state.request)
    assert replay.body == {**first.body, "replayed": True}
    state.body["input"] = "different"
    conflict = await state.handler(state.request)
    assert conflict.status == 409 and len(state.records) == 1


async def test_cancel_admission_recovers_existing_native_identity_in_its_profile(
    cancellation_gateway,
):
    state = cancellation_gateway
    fingerprint = hashlib.sha256(
        json.dumps(
            {"body": state.body, "gateway_session_key": "conversation"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    state.adapter._run_idempotency_store.reserve(
        state.state.profile, "owh-run", fingerprint, "run_existing", {"status": "running"}
    )
    response = await state.handler(state.request)
    assert response.body == {"run_id": "run_existing", "status": "running", "replayed": True}
    state.state.profile = "owh-" + "b" * 32
    other = await state.handler(state.request)
    assert other.body["status"] == "cancelled" and other.body["run_id"] != "run_existing"


@pytest.mark.parametrize("invalid", ["auth", "profile", "key", "body", "storage", "outage"])
async def test_cancel_admission_fails_closed(cancellation_gateway, invalid):
    state = cancellation_gateway
    if invalid == "auth":
        state.adapter._check_auth = lambda request: SimpleNamespace(status=401)
    elif invalid == "profile":
        state.state.profile = "default"
    elif invalid == "key":
        state.request.headers.pop("Idempotency-Key")
    elif invalid == "body":
        state.body["hosted_room_dispatch"] = {}
    elif invalid == "storage":
        state.adapter._run_idempotency_store.durable = False
    else:
        state.adapter._run_idempotency_store.reserve = lambda *args, **kwargs: (
            _ for _ in ()
        ).throw(OSError("test"))
    response = await state.handler(state.request)
    assert response.status in {400, 401, 403, 503}
    assert not state.records
