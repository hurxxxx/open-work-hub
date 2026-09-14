"""Pinned native tools + real sandbox smoke; no inference or application data.

Run in the dev gateway as documented in docs/domains/ai/hermes.md. Only the
authenticated context/file RPC and profile configuration use synthetic data.
Native dispatch, middleware chain, approvals, code kernel and file tools run.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, "/opt/hermes/plugins")
import owh_runtime
from owh_runtime.native_execution import install_code_guard
from owh_runtime.sandbox import OpenWorkHubSandbox
from agent.terminal_env_registry import register_provider
from hermes_cli import config, middleware
import hermes_constants
import model_tools
from tools import approval, terminal_tool
from tools.interrupt import set_interrupt

logging.disable(logging.CRITICAL)
image = sys.argv[1]
profile = "owh-" + uuid4().hex
server_name = "owh-mcp-" + hashlib.sha256(profile.encode()).hexdigest()[:20] + "-internal"
server = {"url": "http://synthetic.invalid", "headers": {"Authorization": "Bearer synthetic"}}
current = ContextVar("native_check_conversation", default="first")
snapshots = {"first": {}, "second": {}}
tasks = {key: "native-check-" + uuid4().hex for key in snapshots}
settings = {
    "mcp_servers": {server_name: server},
    "terminal": {"backend": "owh_sandbox", "cwd": "/workspace", "container_persistent": False},
    "approvals": {"unattended_mode": "deny", "mode": "manual"},
    "code_execution": {"timeout": 10},
}


def transport():
    return server, "run_" + tasks[current.get()]


def rpc(configured, run_id, method, params):
    assert configured == server and run_id == transport()[1]
    files = snapshots[current.get()]
    if method == "owh/context":
        return {"allow_native_tools": True, "sandbox": {"image": image, "no_proxy": "localhost"}}
    if method == "owh/files/list":
        return {"files": list(files.values())}
    if method == "owh/files/read":
        return files[params["id"]]
    if method == "owh/files/write":
        path = params["path"]
        files[path] = {
            "id": path, "relative_path": path,
            "sha256": hashlib.sha256(base64.b64decode(params["data"])).hexdigest(),
            "data": params["data"],
        }
        return {}
    if method == "owh/files/checkpoint":
        return {"previews": 0}
    raise AssertionError("Unexpected synthetic RPC")


def call(tool, args, conversation="first"):
    current.set(conversation)
    approval.set_current_session_key(transport()[1])
    result = model_tools.handle_function_call(
        tool, args, task_id=tasks[conversation],
        enabled_tools=["execute_code", "terminal", "read_file", "write_file", "patch"],
    )
    return json.loads(result)


def content(path, conversation="first"):
    return base64.b64decode(snapshots[conversation][path]["data"]).decode()


def absent(container):
    return subprocess.run(
        ["docker", "inspect", container], capture_output=True, check=False,
    ).returncode != 0


with (
    tempfile.TemporaryDirectory() as home,
    patch.dict(os.environ, {
        "HERMES_HOME": str(Path(home) / profile),
        "HERMES_WRITE_SAFE_ROOT": "/workspace",
        "HERMES_SESSION_PLATFORM": "api_server",
        "TERMINAL_ENV": "owh_sandbox",
        "TERMINAL_CWD": "/workspace",
        "TERMINAL_CONTAINER_PERSISTENT": "false",
    }),
    patch.object(config, "load_config", lambda *a, **kw: settings),
    patch.object(config, "read_raw_config", lambda *a, **kw: {"code_execution": settings["code_execution"]}),
    patch.object(hermes_constants, "get_hermes_home", lambda: Path(home) / profile),
    patch.object(owh_runtime, "_rpc", rpc),
    patch.object(owh_runtime, "runtime_transport", transport),
    patch.object(middleware, "_get_middleware_callbacks", lambda kind: [owh_runtime.execute_tool] if kind == "tool_execution" else []),
):
    register_provider(OpenWorkHubSandbox())
    install_code_guard()  # Checks real pinned source hashes, not mocks.
    try:
        # Unattended guard remains denied outside an admitted OWH tool call.
        assert not approval.check_execute_code_guard("pass", "owh_sandbox")["approved"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda name: call("execute_code", {"code": "print('OWH_NATIVE_CODE_OK')"}, name),
                ["first", "second"],
            ))
        assert all(row.get("status") == "success" for row in results), results
        assert all("OWH_NATIVE_CODE_OK" in row.get("output", "") for row in results), results
        first = terminal_tool.get_active_env(tasks["first"])
        second = terminal_tool.get_active_env(tasks["second"])
        assert first._container != second._container
        print("PASS: unattended execute_code and concurrent conversation isolation", flush=True)

        write = call("write_file", {"path": "/workspace/proof.txt", "content": "before\n"})
        assert content("proof.txt") == "before\n", write
        changed = call("patch", {"path": "/workspace/proof.txt", "old_string": "before", "new_string": "after"})
        assert content("proof.txt") == "after\n", changed
        added = call("patch", {"mode": "patch", "patch": "*** Begin Patch\n*** Add File: /workspace/v4a.txt\n+v4a-before\n*** End Patch"})
        assert content("v4a.txt").rstrip("\n") == "v4a-before", added
        moved = call("patch", {"mode": "patch", "patch": "*** Begin Patch\n*** Move File: /workspace/v4a.txt -> /workspace/v4a-moved.txt\n*** End Patch"})
        assert "v4a-moved.txt" in snapshots["first"] and content("v4a-moved.txt").rstrip("\n") == "v4a-before", moved
        # Native code RPC must retain this call's middleware and run context.
        nested = call("execute_code", {"code": "from hermes_tools import write_file\nprint(write_file(path='/workspace/rpc.txt', content='rpc-ok'))"})
        assert nested.get("status") == "success" and content("rpc.txt") == "rpc-ok", nested
        assert not snapshots["second"]
        print("PASS: native write/patch, code tool RPC and durable file binding", flush=True)

        current.set("first")
        approval.set_current_session_key(transport()[1])
        first.execute("mkdir -p /tmp/outside; printf unchanged > /tmp/outside/target; ln -s /tmp/outside /workspace/escape; ln -s /tmp/outside/target /workspace/leaf")
        for path in ("/tmp/outside/target", "/workspace/escape/target", "/workspace/leaf", "/workspace/escape/new"):
            result = call("write_file", {"path": path, "content": "forbidden"})
            assert "error" in result or result.get("success") is False, (path, result)
        for patch_body in (
            "*** Delete File: /workspace/escape/target",
            "*** Move File: /workspace/v4a-moved.txt -> /workspace/escape/moved",
        ):
            result = call("patch", {"mode": "patch", "patch": "*** Begin Patch\n" + patch_body + "\n*** End Patch"})
            assert "error" in result or result.get("success") is False, result
        probe = first.execute("test ! -e /tmp/outside/new && test \"$(cat /tmp/outside/target)\" = unchanged")
        assert probe["returncode"] == 0, probe
        print("PASS: outside-root and parent/leaf symlink writes denied", flush=True)

        # Deadline must kill detached descendants, then a fresh native call
        # must restore previously persisted files in the same conversation.
        previous = first._container
        settings["code_execution"]["timeout"] = 2
        timed_out = call("execute_code", {"code": "import subprocess, time\nsubprocess.Popen(['sh', '-c', 'sleep 8; echo late > /workspace/late.txt'], start_new_session=True)\ntime.sleep(30)"})
        assert timed_out.get("status") == "timeout", timed_out
        assert absent(previous), "Timed-out sandbox still exists"
        settings["code_execution"]["timeout"] = 10
        fresh = call("execute_code", {"code": "print(open('/workspace/proof.txt').read())"})
        assert fresh.get("status") == "success" and "after" in fresh.get("output", ""), fresh
        assert "late.txt" not in snapshots["first"]
        print("PASS: timeout removes descendants; next call restores saved files", flush=True)

        environment = terminal_tool.get_active_env(tasks["first"])
        previous = environment._container
        worker = []

        def cancellable():
            worker.append(threading.get_ident())
            return call("execute_code", {"code": "import subprocess, time\nsubprocess.Popen(['sh', '-c', 'sleep 8; echo late > /workspace/cancel-late.txt'], start_new_session=True)\nopen('/tmp/owh-cancel-ready', 'w').close()\ntime.sleep(60)"})

        settings["code_execution"]["timeout"] = 30
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(cancellable)
            deadline = time.monotonic() + 15
            ready = False
            while time.monotonic() < deadline and not pending.done():
                ready = subprocess.run(
                    ["docker", "exec", previous, "test", "-f", "/tmp/owh-cancel-ready"],
                    capture_output=True, timeout=3, check=False,
                ).returncode == 0
                if ready:
                    break
                time.sleep(0.1)
            assert ready, "Synthetic cancellation script did not start"
            set_interrupt(True, thread_id=worker[0], reason="synthetic cancellation check")
            try:
                stopped = pending.result(timeout=20)
            finally:
                set_interrupt(False, thread_id=worker[0])
        assert stopped.get("status") in {"interrupted", "error"}, stopped
        assert absent(previous), "Cancelled sandbox still exists"
        assert "cancel-late.txt" not in snapshots["first"]
        other = call("execute_code", {"code": "print('other-still-works')"}, "second")
        assert other.get("status") == "success", other
        print("PASS: cancellation removes detached children and preserves the other conversation", flush=True)
    finally:
        for name, task in tasks.items():
            current.set(name)
            approval.set_current_session_key(transport()[1])
            environment = terminal_tool.get_active_env(task)
            if environment is not None:
                terminal_tool.cleanup_vm(environment._task_id)
