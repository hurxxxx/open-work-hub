from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from threading import RLock
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
        "gateway.session_context": {"get_session_env": lambda *args: "cli"},
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
    tools_package = ModuleType("tools")
    tools_package.approval = sys.modules["tools.approval"]
    monkeypatch.setitem(sys.modules, "tools", tools_package)
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


@pytest.mark.parametrize(
    "choice,accepted",
    [("once", True), ("deny", False), ("session", False), ("always", False), (None, False)],
)
def test_api_write_consent_uses_exact_run_notifier_once(plugin, monkeypatch, choice, accepted):
    approval = sys.modules["tools.approval"]
    monkeypatch.setattr(
        sys.modules["gateway.session_context"], "get_session_env", lambda *args: "api_server"
    )
    approval._lock = RLock()

    def notify(payload):
        pass

    approval._gateway_notify_cbs = {"run_test": notify}
    captured = []

    def wait(run_id, callback, data, *, surface):
        assert run_id == "run_test" and callback is notify
        assert surface == "mcp-trust/internal"
        captured.append(data)
        return {"resolved": choice is not None, "choice": choice}

    approval._await_gateway_decision = wait
    for digest in ("a" * 64, "b" * 64):
        result = plugin.module._request_write_consent(
            "write",
            f"Arguments SHA-256: {digest}",
            run_id="run_test",
            surface="mcp-trust/internal",
            arguments={"title": digest},
        )
        assert (result == "accept") is accepted
    assert captured[0]["pattern_keys"] != captured[1]["pattern_keys"]
    assert captured[0]["arguments"] == {"title": "a" * 64}
    assert all(
        data["allow_session"] is False and data["allow_permanent"] is False for data in captured
    )
    assert plugin.consent == []  # The pinned CLI fallback must not receive API consent.


@pytest.mark.parametrize("notifier", [None, "another_run", "broken"])
def test_api_write_consent_failure_never_dispatches_write(plugin, monkeypatch, notifier):
    approval = sys.modules["tools.approval"]
    monkeypatch.setattr(
        sys.modules["gateway.session_context"], "get_session_env", lambda *args: "api_server"
    )
    approval._lock = RLock()
    approval._gateway_notify_cbs = {
        "run_other" if notifier == "another_run" else "run_test": (
            None if notifier is None else lambda data: None
        ),
    }

    def failed_wait(*args, **kwargs):
        raise RuntimeError("notification failed")

    approval._await_gateway_decision = failed_wait

    def rpc(server, run_id, method, params):
        if method == "owh/context":
            return {"allow_native_tools": True}
        assert method == "tools/list", "Unapproved mutation dispatched"
        return {"tools": [{"name": "tasks.create", "annotations": {"readOnlyHint": False}}]}

    monkeypatch.setattr(plugin.module, "_rpc", rpc)
    result = plugin.module.execute_tool(
        tool_name=f"mcp__{plugin.server.replace('-', '_')}__tasks.create",
        args={"title": "test"},
        next_call=lambda: pytest.fail("Must not fall through"),
    )
    assert "error" in json.loads(result)


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
    assert "error" in invoke("owh_preview", {"path": "index.html"})
    assert invoke("owh_submit_result", {"result": {"answer": "invalid"}}) == {"accepted": False}
    assert invoke("owh_submit_result", {"result": {"answer": 42}}) == {"accepted": True}
    assert len(attempts) == 2


@pytest.mark.parametrize("tool", ["tool_search", "tool_describe"])
def test_workload_discovery_only_receives_server_admitted_definitions(plugin, monkeypatch, tool):
    definitions = [{"type": "function", "function": {"name": "owh_submit_result"}}]
    calls = []

    def get_definitions(names, quiet):
        assert names == {"owh_submit_result", "web_search"} and quiet
        return definitions

    def dispatch(args, *, current_tool_defs):
        assert current_tool_defs is definitions
        calls.append(args)
        return '{"tools": {}}'

    for name, members in {
        "tools.registry": {"registry": SimpleNamespace(get_definitions=get_definitions)},
        "tools.tool_search": {"dispatch_tool_search": dispatch, "dispatch_tool_describe": dispatch},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(
        plugin.module,
        "_rpc",
        lambda *args: {"allow_native_tools": False, "native_tools": ["web_search"]},
    )
    args = {"names": ["terminal", "owh_submit_result"], "queries": ["tools"]}
    assert json.loads(
        plugin.module.execute_tool(
            tool_name=tool, args=args, next_call=lambda: pytest.fail("Unscoped discovery denied")
        )
    ) == {"tools": {}}
    assert calls == [args]


def test_workload_discovery_failure_does_not_fall_through(plugin, monkeypatch):
    monkeypatch.setattr(plugin.module, "_rpc", lambda *args: {"allow_native_tools": False})
    monkeypatch.setitem(sys.modules, "tools.registry", None)
    assert "error" in json.loads(
        plugin.module.execute_tool(
            tool_name="tool_describe",
            args={"names": ["owh_submit_result"]},
            next_call=lambda: pytest.fail("Import failure must fail closed"),
        )
    )


@pytest.mark.parametrize("native_run_id", ["", "cron_job_fixture", "run_forged"])
@pytest.mark.parametrize(
    "tool",
    [
        "web_search",
        "read_file",
        "terminal",
        "owh_preview",
        "tool_search",
        "tool_describe",
        "owh_submit_result",
    ],
)
def test_jobs_profile_intentionally_denies_tools_without_an_owh_run(
    plugin, monkeypatch, native_run_id, tool
):
    monkeypatch.setattr(
        sys.modules["hermes_constants"],
        "get_hermes_home",
        lambda: Path("owh-" + "a" * 32 + "-jobs"),
    )
    monkeypatch.setattr(
        sys.modules["hermes_cli.config"], "load_config", lambda: {"mcp_servers": {}}
    )
    monkeypatch.setattr(
        plugin.module, "_rpc", lambda *args: pytest.fail("Jobs have no app transport")
    )
    plugin.run.set(native_run_id)
    result = plugin.module.execute_tool(
        tool_name=tool, args={}, next_call=lambda: pytest.fail("Unowned jobs cannot execute tools")
    )
    assert "error" in json.loads(result)


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


@pytest.fixture
def interactive_catalog(plugin, monkeypatch):
    prefix = sys.modules["tools.mcp_tool"].mcp_prefixed_tool_name

    def internal(name):
        return prefix(plugin.server, name)

    external_server = plugin.server.removesuffix("internal") + "research"
    external = prefix(external_server, "search")
    names = [
        internal("tasks.list"),
        internal("tasks.create"),
        "terminal",
        "owh_preview",
        "session_search",
        "owh_submit_result",
        "unregistered_policy_tool",
        external,
        prefix("owh-mcp-other-internal", "tasks.list"),
    ]
    definitions = [{"type": "function", "function": {"name": name}} for name in names]
    scopes = {"run_test": ["tasks.list", "tasks.create"]}
    transport_calls = []

    def rpc(server, run_id, method, params):
        assert server is plugin.transport
        transport_calls.append((run_id, method))
        if method == "owh/context":
            return {"allow_native_tools": True}
        assert method == "tools/list", "Discovery must never mutate"
        return {"tools": [{"name": name} for name in scopes[run_id]]}

    def dispatch(args, *, current_tool_defs):
        return json.dumps({"tools": [item["function"]["name"] for item in current_tool_defs]})

    config = {
        "mcp_servers": {plugin.server: plugin.transport, external_server: {"url": "synthetic"}}
    }
    monkeypatch.setattr(sys.modules["hermes_cli.config"], "load_config", lambda: config)
    monkeypatch.setattr(plugin.module, "_rpc", rpc)
    monkeypatch.setattr(plugin.module, "_interactive_definitions", lambda config: list(definitions))
    for name, members in {
        "tools.registry": {"registry": SimpleNamespace()},
        "tools.tool_search": {"dispatch_tool_search": dispatch, "dispatch_tool_describe": dispatch},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, module)

    def invoke(tool="tool_search"):
        return json.loads(
            plugin.module.execute_tool(
                tool_name=tool,
                args={"queries": ["tools"]},
                next_call=lambda: pytest.fail("Unscoped discovery must never run"),
            )
        )

    return SimpleNamespace(
        invoke=invoke,
        scopes=scopes,
        definitions=definitions,
        internal=internal,
        external=external,
        config=config,
        calls=transport_calls,
    )


@pytest.mark.parametrize("tool", ["tool_search", "tool_describe"])
@pytest.mark.parametrize("scope", [[], ["tasks.list"], ["tasks.list", "tasks.create"]])
def test_interactive_discovery_intersects_live_scope_and_execution_policy(
    interactive_catalog, scope, tool
):
    catalog = interactive_catalog
    original = list(catalog.definitions)
    catalog.scopes["run_test"] = scope
    result = catalog.invoke(tool)
    assert set(result["tools"]) == {
        *(catalog.internal(name) for name in scope),
        "terminal",
        "owh_preview",
        catalog.external,
    }
    assert catalog.calls == [("run_test", "owh/context"), ("run_test", "tools/list")]
    assert catalog.definitions == original


def test_parallel_discovery_and_revocation_do_not_change_shared_catalog(
    plugin, interactive_catalog
):
    catalog = interactive_catalog
    catalog.scopes.update(run_read=["tasks.list"], run_write=["tasks.create"])

    def invoke(run):
        plugin.run.set(run)
        return set(catalog.invoke()["tools"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        read, write = list(pool.map(invoke, ["run_read", "run_write"]))
    assert catalog.internal("tasks.create") not in read
    assert catalog.internal("tasks.list") not in write
    catalog.scopes["run_test"] = []
    assert not any(name.startswith(catalog.internal("")) for name in catalog.invoke()["tools"])


def test_same_count_catalog_replacement_requires_refresh_then_recovers(interactive_catalog):
    catalog = interactive_catalog
    catalog.scopes["run_test"] = ["tasks.list", "tasks.archive"]
    result = catalog.invoke()
    assert result["code"] == "owh.tools.catalog_refresh_required"
    assert result["missing_tools"] == [catalog.internal("tasks.archive")]
    assert result["missing_count"] == 1
    # Simulate the native registry after the standard restart, keeping its size.
    catalog.definitions[1] = {
        "type": "function",
        "function": {"name": catalog.internal("tasks.archive")},
    }
    assert catalog.internal("tasks.archive") in catalog.invoke()["tools"]


def test_discovery_transport_failure_returns_stable_error(plugin, interactive_catalog, monkeypatch):
    monkeypatch.setattr(plugin.module, "_rpc", lambda *args: (_ for _ in ()).throw(OSError()))
    assert interactive_catalog.invoke()["code"] == "owh.tools.discovery_unavailable"


def test_removed_external_server_is_hidden(interactive_catalog):
    catalog = interactive_catalog
    catalog.config["mcp_servers"] = {
        key: value
        for key, value in catalog.config["mcp_servers"].items()
        if key.endswith("-internal")
    }
    assert catalog.external not in catalog.invoke()["tools"]


@pytest.mark.parametrize("admitted", [True, False])
def test_rejected_bridge_preserves_validation_only_for_admitted_tools(
    plugin, interactive_catalog, monkeypatch, admitted
):
    catalog = interactive_catalog
    target = catalog.internal("tasks.create")
    if not admitted:
        catalog.scopes["run_test"] = []
    search = sys.modules["tools.tool_search"]
    search.resolve_underlying_call = lambda args: (target, {}, None)
    validated = []

    def validate(name, args):
        validated.append(name)
        return json.dumps(
            {"error": "Missing required field", "parameters": {"required": ["title"]}}
        )

    search.validate_deferred_call_args = validate
    result = json.loads(
        plugin.module.execute_tool(
            tool_name="tool_call",
            args={"name": target},
            next_call=lambda: pytest.fail("Rejected bridge must never execute"),
        )
    )
    if admitted:
        assert result["parameters"] == {"required": ["title"]}
        assert validated == [target]
    else:
        assert result["code"] == "owh.tools.tool_unavailable"
        assert "parameters" not in result and validated == []


def test_parse_rejected_bridge_cannot_dispatch(plugin, interactive_catalog):
    search = sys.modules["tools.tool_search"]
    search.resolve_underlying_call = lambda args: (None, {}, "tool_call requires a name")
    search.validate_deferred_call_args = lambda *args: pytest.fail("No target to validate")
    result = json.loads(
        plugin.module.execute_tool(
            tool_name="tool_call",
            args={},
            next_call=lambda: pytest.fail("Malformed bridge cannot run"),
        )
    )
    assert result["code"] == "owh.tools.invalid_tool_call"


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


@pytest.mark.slow
def test_tool_rpc_waits_for_server_completion_beyond_thirty_seconds(plugin):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    import time

    completed = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert request["method"] == "tools/call"
            assert self.headers["X-Hermes-Run-Id"] == "run_test"
            time.sleep(31)
            completed.append(request["id"])
            body = json.dumps({"result": {"structuredContent": {"saved": True}}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = plugin.module._rpc(
            {
                "url": f"http://127.0.0.1:{server.server_port}",
                "headers": {"Authorization": "Bearer synthetic"},
            },
            "run_test",
            "tools/call",
            {"name": "fixture.slow_save", "arguments": {}},
        )
        assert result == {"structuredContent": {"saved": True}}
        assert len(completed) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("method", ["tools/list", "owh/context", "tools/call"])
def test_rpc_bounds_control_waits_and_never_retries_uncertain_calls(plugin, monkeypatch, method):
    import httpx

    real_client = httpx.Client
    seen = []

    def handler(request):
        seen.append(request)
        limits = request.extensions["timeout"]
        assert limits["connect"] == limits["write"] == limits["pool"] == 30
        assert limits["read"] == (3900 if method == "tools/call" else 30)
        raise httpx.ReadTimeout("synthetic connection loss")

    monkeypatch.setattr(
        plugin.module.httpx,
        "Client",
        lambda **kwargs: real_client(
            **kwargs,
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(httpx.ReadTimeout):
        plugin.module._rpc(plugin.transport, "run_test", method, {})
    assert len(seen) == 1


@pytest.mark.parametrize("failure", ["timeout", "invalid_response"])
def test_sent_tool_with_no_confirmation_reports_unknown_outcome_without_retry(
    plugin, monkeypatch, failure
):
    import httpx

    calls = []

    def rpc(server, run, method, params):
        if method == "owh/context":
            return {"allow_native_tools": True}
        if method == "tools/list":
            return {"tools": [{"name": "fixture.save", "annotations": {"readOnlyHint": False}}]}
        assert method == "tools/call"
        calls.append(params)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic connection loss")
        raise ValueError("synthetic invalid response")

    monkeypatch.setattr(plugin.module, "_rpc", rpc)
    result = json.loads(
        plugin.module.execute_tool(
            tool_name=f"mcp__{plugin.server.replace('-', '_')}__fixture.save",
            args={},
            next_call=lambda: pytest.fail(
                "Never repeat an uncertain call through the native handler"
            ),
        )
    )
    assert len(calls) == 1 and len(plugin.consent) == 1
    assert "did not confirm" in result["error"] and "do not repeat" in result["error"]
    assert "blocked" not in result["error"]


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": "mail"},
        {"session_id": "saved"},
        {"session_id": "saved", "around_message_id": 1},
    ],
)
@pytest.mark.parametrize("native_tools", [[], ["session_search"]])
def test_native_history_cannot_bypass_source_access_including_stale_profiles(
    plugin, monkeypatch, arguments, native_tools
):
    monkeypatch.setattr(
        plugin.module,
        "_rpc",
        lambda *_args: {"allow_native_tools": True, "native_tools": native_tools},
    )
    result = plugin.module.execute_tool(
        tool_name="session_search",
        args=arguments,
        next_call=lambda: pytest.fail("Native profile history has no source ACL"),
    )
    assert "source-access policy" in json.loads(result)["error"]


def test_revoked_app_workload_history_cannot_be_read_from_admitted_chatbot(
    plugin, monkeypatch, application_postgres_dsn
):
    from uuid import uuid4
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from open_work_hub_api.domains.auth.app_access import can_use_app
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
    from open_work_hub_api.domains.auth.models import CompanyAppControl, User
    from open_work_hub_api.domains.hermes.models import HermesProfileBinding
    from open_work_hub_api.domains.hermes.repository import HermesRunRepository
    from open_work_hub_api.domains.hermes.mcp_router import _available_tools

    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            user = User(
                id=str(uuid4()),
                login_id=uuid4().hex,
                email="history@example.test",
                full_name="History test",
                password_hash="not-used",
            )
            db.add(user)
            db.flush()
            binding = HermesProfileBinding(
                id=str(uuid4()),
                user_id=user.id,
                profile_name="owh-" + "a" * 32,
                status="active",
                provider="openai",
                model="test",
            )
            db.add(binding)
            db.flush()
            for app_id in ("chatbot", "mail"):
                db.merge(CompanyAppControl(app_id=app_id, enabled=True))
                db.flush()
                db.merge(AppAccessPolicy(app_id=app_id, audience="all"))
            repo = HermesRunRepository(db)
            runs = [
                repo.stage(
                    binding=binding,
                    session=None,
                    input_text="synthetic",
                    instructions=None,
                    conversation_history=[],
                    owner_app_id=app_id,
                )
                for app_id in ("chatbot", "mail")
            ]
            chat, mail = runs
            chat.hermes_run_id = "run_test"
            chat.status = "running"
            mail.status = "completed"
            mail.output_payload = {"private": "synthetic mail history"}
            db.commit()
            assert can_use_app(db, user_id=user.id, app_id="mail")
            db.get(CompanyAppControl, "mail").enabled = False
            db.commit()
            assert not can_use_app(db, user_id=user.id, app_id="mail")

            def rpc(_server, native_run_id, method, _params):
                assert method == "owh/context"
                _, _, active = _available_tools(
                    db, binding=binding, user=user, hermes_run_id=native_run_id
                )
                assert active.id == chat.id
                return {"allow_native_tools": True}

            monkeypatch.setattr(plugin.module, "_rpc", rpc)
            result = plugin.module.execute_tool(
                tool_name="session_search",
                args={"session_id": "saved-mail-session"},
                next_call=lambda: pytest.fail("Revoked workload transcript reached native search"),
            )
            assert "source-access policy" in json.loads(result)["error"]
            assert "synthetic mail history" not in result
    finally:
        engine.dispose()
