"""Narrow v2026.8.31 bridge for custom-provider execute_code admission.

The documented provider guard flag is ignored by this release's whole-script
guard. Keep native dispatch/lifecycle and every other approval guard intact.
Remove this bridge when upstream consults the provider at that guard.
"""

from contextvars import ContextVar
from functools import wraps
import hashlib
import inspect
import json


file_write_environment = ContextVar("owh_file_write_environment", default=None)
_GUARD_SHA256 = "3c207eaf98508e171d585e7aad15751a2758c5ba7f96d41ea2a5f64a2409914c"
_ENV_SHA256 = "0b102f97c63bcf239e592703a9aa54a421522e966e25508393407f55337f1a6f"


def _fingerprint(function):
    return hashlib.sha256(inspect.getsource(function).encode()).hexdigest()


def verified_environment(task_id, server, run_id):
    from tools.code_execution_tool import _get_or_create_env
    from tools.terminal_tool import (
        _get_env_config, _get_plugin_env_provider, cleanup_vm, get_active_env,
    )

    from . import runtime_transport
    from .sandbox import OpenWorkHubSandbox, WorkspaceEnvironment

    if not task_id or runtime_transport() != (server, run_id):
        raise ValueError("Current native execution identity required")
    if _get_env_config()["env_type"] != "owh_sandbox":
        raise ValueError("OWH sandbox backend required")
    if type(_get_plugin_env_provider("owh_sandbox")) is not OpenWorkHubSandbox:
        raise ValueError("OWH sandbox provider required")
    previous = get_active_env(task_id)
    if type(previous) is WorkspaceEnvironment and previous._closed:
        # A fresh admitted call, never a late callback from the old execution,
        # retires the dead environment via native lifecycle/cache cleanup.
        with previous._recovery_lock:
            if get_active_env(task_id) is previous:
                # A previous unconfirmed removal must succeed first.
                previous.cleanup()
                cleanup_vm(previous._task_id)
            environment, backend = _get_or_create_env(task_id)
    else:
        environment, backend = _get_or_create_env(task_id)
    if (
        backend != "owh_sandbox"
        or type(environment) is not WorkspaceEnvironment
        or getattr(environment, "_hermes_backend_name", None) != "owh_sandbox"
        or environment._server != server
        or not environment._container
        or environment._closed
    ):
        raise ValueError("Verified live OWH sandbox required")
    return environment


def install_code_guard():
    from tools import approval, code_execution_tool

    original = approval.check_execute_code_guard
    if getattr(original, "_owh_code_guard", False):
        return
    if (
        _fingerprint(original) != _GUARD_SHA256
        or _fingerprint(code_execution_tool._get_or_create_env) != _ENV_SHA256
    ):
        raise RuntimeError("Unsupported Hermes code-execution contract")
    # Hermes can load the same plugin under multiple module names/profiles.
    # Keep the context on the installed guard, not a module-global singleton.
    admitted_code = ContextVar("owh_admitted_code", default=None)

    @wraps(original)
    def guard(code, env_type, has_host_access=False):
        admitted = admitted_code.get()
        if admitted is not None and env_type == "owh_sandbox" and not has_host_access:
            task_id, server, run_id, environment, verify = admitted
            # Recheck the actual cached object, not just its configured name.
            if verify(task_id, server, run_id) is environment:
                return {"approved": True, "message": None}
        return original(code, env_type, has_host_access=has_host_access)

    guard._owh_code_guard = True
    guard._owh_admitted_code = admitted_code
    approval.check_execute_code_guard = guard


def execute_native(tool_name, next_call, *, task_id, server, run_id):
    environment = verified_environment(task_id, server, run_id)
    if tool_name == "execute_code":
        from tools.approval import check_execute_code_guard

        variable = check_execute_code_guard._owh_admitted_code
        value = (task_id, server, run_id, environment, verified_environment)
    elif tool_name in {"write_file", "patch"}:
        from tools.file_tools import _get_file_ops

        if _get_file_ops(task_id).env is not environment:
            raise ValueError("Native file environment does not match this execution")
        variable, value = file_write_environment, environment
    else:
        return next_call()
    token = variable.set(value)
    try:
        result = next_call()
        if tool_name == "execute_code":
            payload = json.loads(result) if isinstance(result, str) else result
            if isinstance(payload, dict) and (
                payload.get("status") == "timeout"
                or payload.get("kernel", {}).get("state_lost")
                and payload.get("kernel", {}).get("ended")
            ):
                # Native kernel timeout kills its Python process but may leave
                # detached grandchildren. Dispose the entire owned sandbox.
                environment.cleanup()
        return result
    finally:
        variable.reset(token)
