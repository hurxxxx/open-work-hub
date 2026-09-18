"""Pinned result-discovery/dispatch smoke with synthetic RPC; no inference."""

import hashlib
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, "/opt/hermes/plugins")
import hermes_constants
import model_tools
import owh_runtime
from agent.terminal_env_registry import register_provider
from hermes_cli import config, middleware
from tools import approval
from tools.registry import registry

logging.disable(logging.CRITICAL)
profile = "owh-" + uuid4().hex
server_name = "owh-mcp-" + hashlib.sha256(profile.encode()).hexdigest()[:20] + "-internal"
server = {"url": "http://synthetic.invalid", "headers": {"Authorization": "Bearer synthetic"}}
submissions = []


def rpc(configured, run_id, method, params):
    assert configured == server and run_id == "run_synthetic"
    if method == "owh/context":
        return {"allow_native_tools": False, "native_tools": []}
    assert method == "owh/submit"
    submissions.append(params)
    return {"accepted": type(params["result"].get("answer")) is int}


def call(name, args):
    # The agent wraps bridge lookups in execution middleware. Native model_tools
    # unwraps tool_call and re-enters middleware for the actual target.
    if name in {"tool_search", "tool_describe"}:
        return json.loads(middleware.run_tool_execution_middleware(
            name, args, lambda args: (_ for _ in ()).throw(AssertionError("Unscoped lookup"))
        ))
    return json.loads(model_tools.handle_function_call(
        name, args, enabled_toolsets=["owh_runtime"], enabled_tools=["owh_submit_result"]
    ))


with (
    tempfile.TemporaryDirectory() as home,
    patch.dict(os.environ, {"HERMES_HOME": str(Path(home) / profile)}),
    patch.object(config, "load_config", lambda *a, **kw: {"mcp_servers": {server_name: server}}),
    patch.object(hermes_constants, "get_hermes_home", lambda: Path(home) / profile),
    patch.object(owh_runtime, "_rpc", rpc),
    patch.object(middleware, "_get_middleware_callbacks", lambda kind: [owh_runtime.execute_tool] if kind == "tool_execution" else []),
):
    owh_runtime.register(SimpleNamespace(
        register_terminal_environment_provider=register_provider,
        register_middleware=lambda *args: None,
        register_tool=registry.register,
    ))
    approval.set_current_session_key("run_synthetic")
    found = call("tool_search", {"queries": ["submit result"]})
    assert set(found["tools"]) == {"owh_submit_result"}, found
    described = call("tool_describe", {"names": ["owh_submit_result", "owh_preview", "terminal"]})
    assert set(described["tools"]) == {"owh_submit_result"}, described
    assert described["tools"]["owh_submit_result"]["parameters"]["required"] == ["result"]
    for value, accepted in [("invalid", False), (5, True)]:
        result = call("tool_call", {"name": "owh_submit_result", "arguments": {"result": {"answer": value}}})
        assert result == {"accepted": accepted}, result
    assert len(submissions) == 2
    denied = call("tool_call", {"name": "owh_preview", "arguments": {"path": "index.html"}})
    assert "error" in denied, denied
    approval.set_current_session_key("")
    assert "error" in call("tool_describe", {"names": ["owh_submit_result"]})
    assert "error" in call("tool_call", {"name": "owh_submit_result", "arguments": {"result": {"answer": 5}}})
    assert len(submissions) == 2
    print("PASS: scoped workload discovery, native bridge submission/correction and denied unauthorized tools/context")
