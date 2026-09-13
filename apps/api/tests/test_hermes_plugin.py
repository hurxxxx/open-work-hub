from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def plugin(monkeypatch):
    run = ContextVar("native_test_run", default="run_test")
    profile = "owh-" + "a" * 32
    namespace = hashlib.sha256(profile.encode()).hexdigest()[:20]
    server = f"owh-mcp-{namespace}-internal"
    transport = {"url": "http://api.test/internal", "headers": {"Authorization": "Bearer fixture"}}
    consent = []
    modules = {
        "hermes_cli.config": {"load_config": lambda: {"mcp_servers": {server: transport}}},
        "hermes_constants": {"get_hermes_home": lambda: Path(profile)},
        "tools.approval": {
            "get_current_session_key": lambda **kwargs: run.get(),
            "request_elicitation_consent": lambda *args, **kwargs: consent.append(args) or "accept",
        },
        "tools.mcp_tool": {
            "_interpolate_env_vars": lambda value: dict(value),
            "mcp_prefixed_tool_name": lambda server, tool: (
                f"mcp__{server.replace('-', '_')}__{tool}"
            ),
        },
    }
    for name, members in modules.items():
        module = ModuleType(name)
        module.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, module)
    source = Path(__file__).resolve().parents[3] / "ops/hermes/plugins/owh_runtime/__init__.py"
    spec = importlib.util.spec_from_file_location("owh_plugin_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return SimpleNamespace(
        module=module, run=run, server=server, transport=transport, consent=consent
    )


def test_parallel_internal_calls_bind_native_run_and_exact_arguments(plugin, monkeypatch):
    calls = []

    def rpc(server, run_id, method, params):
        if method == "owh/context":
            return {"allow_native_tools": True}
        if method == "tools/list":
            return {"tools": [{"name": "tasks.create", "annotations": {"readOnlyHint": False}}]}
        calls.append((run_id, params["arguments"]))
        return {"structuredContent": {"created": True}}

    monkeypatch.setattr(plugin.module, "_rpc", rpc)

    def invoke(number):
        plugin.run.set(f"run_{number}")
        return plugin.module.execute_tool(
            tool_name=f"mcp__{plugin.server.replace('-', '_')}__tasks.create",
            args={"title": f"task-{number}", "run_id": "model-forged-id"},
            next_call=lambda: pytest.fail("Internal MCP must use the run-bound transport"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, [1, 2]))
    assert all(json.loads(result) == {"created": True} for result in results)
    assert {run_id for run_id, _ in calls} == {"run_1", "run_2"}
    for _, arguments in calls:
        digest = hashlib.sha256(
            json.dumps(
                arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        assert any(digest in message[1] for message in plugin.consent)
    assert "X-Hermes-Run-Id" not in plugin.transport["headers"]


def test_policy_import_transport_and_missing_run_fail_closed(plugin, monkeypatch):
    def invoke():
        return json.loads(
            plugin.module.execute_tool(
                tool_name="terminal", args={}, next_call=lambda: pytest.fail("Must fail closed")
            )
        )

    plugin.run.set("")
    assert "error" in invoke()
    plugin.run.set("run_test")
    monkeypatch.setattr(
        plugin.module, "_rpc", lambda *args: (_ for _ in ()).throw(OSError("offline"))
    )
    assert "error" in invoke()
    monkeypatch.setattr(
        sys.modules["hermes_constants"],
        "get_hermes_home",
        lambda: (_ for _ in ()).throw(ValueError("profile unavailable")),
    )
    assert "error" in invoke()


def test_workload_blocks_native_tools_but_can_correct_and_submit(plugin, monkeypatch):
    attempts = []

    def rpc(server, run, method, params):
        if method == "owh/context":
            return {"allow_native_tools": False}
        assert method == "owh/submit"
        attempts.append(params)
        return {"accepted": isinstance(params["result"].get("answer"), int)}

    monkeypatch.setattr(plugin.module, "_rpc", rpc)

    def invoke(tool, args):
        return json.loads(
            plugin.module.execute_tool(
                tool_name=tool, args=args, next_call=lambda: pytest.fail("Native execution denied")
            )
        )

    assert "error" in invoke("terminal", {})
    assert invoke("owh_submit_result", {"result": {"answer": "invalid"}}) == {"accepted": False}
    assert invoke("owh_submit_result", {"result": {"answer": 42}}) == {"accepted": True}
    assert len(attempts) == 2


def test_registered_native_tool_requires_admission_for_every_call(plugin, monkeypatch):
    admissions = []
    executions = []

    def rpc(server, run, method, params):
        if method == "owh/context":
            return {"allow_native_tools": False, "native_tools": ["web_search"]}
        assert method == "owh/native_admit" and params == {"tool": "web_search"}
        admissions.append(run)
        return {"accepted": len(admissions) == 1}

    monkeypatch.setattr(plugin.module, "_rpc", rpc)

    def invoke(tool):
        return plugin.module.execute_tool(
            tool_name=tool, args={}, next_call=lambda: executions.append(tool) or "search result"
        )

    assert invoke("web_search") == "search result"
    assert "error" in json.loads(invoke("web_search"))
    assert "error" in json.loads(invoke("terminal"))
    assert executions == ["web_search"] and admissions == ["run_test", "run_test"]


def test_rpc_resolves_native_profile_secret_references_and_rejects_unresolved(plugin, monkeypatch):
    import httpx

    server = {
        "url": "http://api.test/internal",
        "headers": {"Authorization": "Bearer ${PROFILE_KEY}"},
    }
    real_client = httpx.Client
    seen = []

    def handler(request):
        seen.append(request.headers["Authorization"])
        assert request.headers["X-Hermes-Run-Id"] == "run_test"
        return httpx.Response(200, json={"result": {"accepted": True}})

    monkeypatch.setattr(
        plugin.module.httpx,
        "Client",
        lambda **kwargs: real_client(
            **kwargs,
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(ValueError, match="Resolved profile authentication"):
        plugin.module._rpc(server, "run_test", "owh/context", {})
    assert seen == []
    monkeypatch.setattr(
        sys.modules["tools.mcp_tool"],
        "_interpolate_env_vars",
        lambda headers: {
            **headers,
            "Authorization": "Bearer active-profile-secret",
        },
    )
    assert plugin.module._rpc(server, "run_test", "owh/context", {}) == {"accepted": True}
    assert seen == ["Bearer active-profile-secret"]
    assert server["headers"]["Authorization"] == "Bearer ${PROFILE_KEY}"
