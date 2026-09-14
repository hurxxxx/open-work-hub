from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def native(monkeypatch):
    root = Path(__file__).resolve().parents[3] / "ops/hermes/plugins/owh_runtime"
    package = ModuleType("owh_native_test")
    package.__path__ = [str(root)]
    current = ContextVar("test_native_run", default="run_first")
    server = {"profile": "first"}
    package.runtime_transport = lambda: (server, current.get())
    monkeypatch.setitem(sys.modules, package.__name__, package)
    spec = importlib.util.spec_from_file_location(
        "owh_native_test.native_execution", root / "native_execution.py"
    )
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

    class WorkspaceEnvironment:
        _hermes_backend_name = "owh_sandbox"
        _container = "isolated"
        _closed = False
        _server = server

        def __init__(self):
            self._recovery_lock = threading.Lock()
            self._task_id = "conversation"

        def cleanup(self):
            self._container = None
            self._closed = True

    class OpenWorkHubSandbox:
        pass

    environment = WorkspaceEnvironment()
    state = SimpleNamespace(environment=environment, backend="owh_sandbox")
    denied = {"approved": False, "outcome": "blocked"}

    def guard(code, env_type, has_host_access=False):
        return dict(denied)

    def get_environment(task_id):
        return state.environment, state.backend

    modules = {
        "tools.approval": {"check_execute_code_guard": guard},
        "tools.code_execution_tool": {"_get_or_create_env": get_environment},
        "tools.terminal_tool": {
            "_get_env_config": lambda: {"env_type": state.backend},
            "_get_plugin_env_provider": lambda _: OpenWorkHubSandbox(),
            "get_active_env": lambda _: state.environment,
            "cleanup_vm": lambda _: pytest.fail("Unexpected cache cleanup"),
        },
        "tools.file_tools": {"_get_file_ops": lambda _: SimpleNamespace(env=state.environment)},
        "owh_native_test.sandbox": {
            "WorkspaceEnvironment": WorkspaceEnvironment,
            "OpenWorkHubSandbox": OpenWorkHubSandbox,
        },
    }
    tools = ModuleType("tools")
    monkeypatch.setitem(sys.modules, "tools", tools)
    for name, members in modules.items():
        module = ModuleType(name)
        module.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, module)
        if name.startswith("tools."):
            setattr(tools, name.split(".")[-1], module)
    # Unit doubles have their own source; the pinned-image smoke separately
    # verifies the production fingerprints against the real native functions.
    monkeypatch.setattr(bridge, "_GUARD_SHA256", bridge._fingerprint(guard))
    monkeypatch.setattr(bridge, "_ENV_SHA256", bridge._fingerprint(get_environment))
    bridge.install_code_guard()
    return SimpleNamespace(
        bridge=bridge, state=state, server=server, current=current,
        approval=tools.approval, environment=environment,
    )


def invoke(native, tool, callback, run="run_first"):
    return native.bridge.execute_native(
        tool, callback, task_id="conversation", server=native.server, run_id=run
    )


def test_only_verified_code_call_can_skip_whole_script_guard(native):
    guard = native.approval.check_execute_code_guard
    assert not guard("pass", "owh_sandbox")["approved"]

    def dispatch():
        assert guard("pass", "owh_sandbox")["approved"]
        assert not guard("pass", "local")["approved"]
        assert not guard("pass", "owh_sandbox", has_host_access=True)["approved"]
        return '{"status":"success"}'

    assert json.loads(invoke(native, "execute_code", dispatch))["status"] == "success"
    assert not guard("pass", "owh_sandbox")["approved"]


@pytest.mark.parametrize("failure", ["backend", "object", "stamp", "profile", "run"])
def test_stale_or_forged_environment_cannot_dispatch(native, failure):
    if failure == "backend":
        native.state.backend = "local"
    elif failure == "object":
        native.state.environment = SimpleNamespace(_container="host")
    elif failure == "stamp":
        native.environment._hermes_backend_name = "local"
    elif failure == "profile":
        native.environment._server = {"profile": "second"}
    else:
        native.current.set("run_second")
    with pytest.raises(ValueError):
        invoke(native, "execute_code", lambda: pytest.fail("Dispatch must be blocked"))


def test_context_is_reset_after_failure_and_not_shared_between_threads(native):
    guard = native.approval.check_execute_code_guard

    def dispatch():
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert not pool.submit(guard, "pass", "owh_sandbox").result()["approved"]
        raise RuntimeError("synthetic failure")

    with pytest.raises(RuntimeError):
        invoke(native, "execute_code", dispatch)
    assert not guard("pass", "owh_sandbox")["approved"]


def test_file_boundary_is_scoped_to_actual_environment(native):
    def dispatch():
        assert native.bridge.file_write_environment.get() is native.environment
        assert not native.approval.check_execute_code_guard("pass", "owh_sandbox")["approved"]
        return "saved"

    assert invoke(native, "patch", dispatch) == "saved"
    assert native.bridge.file_write_environment.get() is None


def test_timeout_removes_the_entire_sandbox(native):
    result = invoke(native, "execute_code", lambda: '{"status":"timeout"}')
    assert json.loads(result)["status"] == "timeout"
    assert native.environment._container is None


def test_unknown_native_contract_fails_plugin_startup(native, monkeypatch):
    original = native.approval.check_execute_code_guard.__wrapped__
    monkeypatch.setattr(native.approval, "check_execute_code_guard", original)
    monkeypatch.setattr(native.bridge, "_GUARD_SHA256", "unsupported")
    with pytest.raises(RuntimeError, match="Unsupported Hermes"):
        native.bridge.install_code_guard()
    assert native.approval.check_execute_code_guard is original


def test_separate_plugin_module_loads_use_the_installed_guard_context(native):
    spec = importlib.util.spec_from_file_location(
        "owh_native_test.second", native.bridge.__file__
    )
    second = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(second)
    second.install_code_guard()
    result = second.execute_native(
        "execute_code",
        lambda: {"approved": native.approval.check_execute_code_guard("pass", "owh_sandbox")["approved"]},
        task_id="conversation", server=native.server, run_id="run_first",
    )
    assert result == {"approved": True}
    assert not native.approval.check_execute_code_guard("pass", "owh_sandbox")["approved"]


def test_parallel_recovery_never_retires_the_replacement(native, monkeypatch):
    previous = native.environment
    previous.cleanup()
    barrier = threading.Barrier(2)
    first_lookup = threading.local()
    retired = []

    def get_active(task_id):
        if not getattr(first_lookup, "done", False):
            first_lookup.done = True
            barrier.wait(timeout=5)
            return previous
        return native.state.environment

    def cleanup(task_id):
        retired.append(native.state.environment)
        native.state.environment = None

    def create(task_id):
        if native.state.environment is None:
            native.state.environment = type(previous)()
        return native.state.environment, "owh_sandbox"

    terminal = sys.modules["tools.terminal_tool"]
    monkeypatch.setattr(terminal, "get_active_env", get_active)
    monkeypatch.setattr(terminal, "cleanup_vm", cleanup)
    monkeypatch.setattr(sys.modules["tools.code_execution_tool"], "_get_or_create_env", create)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: invoke(native, "terminal", lambda: "ok"), [1, 2]))
    assert results == ["ok", "ok"]
    assert retired == [previous]
    assert native.state.environment is not previous and not native.state.environment._closed
