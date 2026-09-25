"""Official Hermes middleware for the pinned MCP transport gap.

Native MCP connections have profile-static HTTP headers. Never mutate those
shared connections: forward internal tools with the approval context's run ID
on a separate request. Hermes still owns discovery, schemas and approvals.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from uuid import uuid4

import httpx


_INTERACTIVE_TOOLS = frozenset({
    "web_search", "web_extract", "tool_search", "tool_describe", "terminal",
    "process", "read_file", "write_file", "patch", "search_files", "skills_list",
    "skill_view", "skill_manage", "todo", "memory", "execute_code", "delegate_task",
    "owh_preview",
})


def _error(message: str, *, code: str | None = None) -> str:
    return json.dumps({"error": message, **({"code": code} if code else {})})


def _interactive_definitions(config: dict) -> list[dict]:
    # Use the same resolver as the pinned api_server agent construction. There
    # is no public platform resolver; do not duplicate its composite/default/
    # disabled-toolset rules. This reads the native registry without changing it.
    from hermes_cli.tools_config import _get_platform_tools
    from model_tools import get_tool_definitions

    return get_tool_definitions(
        enabled_toolsets=sorted(_get_platform_tools(config, "api_server")),
        quiet_mode=True,
        skip_tool_search_assembly=True,
    )


def _scoped_discovery(tool_name, args, *, config, server_name, server, run_id, execution):
    from tools.mcp_tool import mcp_prefixed_tool_name
    from tools.registry import registry
    from tools.tool_search import dispatch_tool_describe, dispatch_tool_search

    if not execution.get("allow_native_tools"):
        definitions = registry.get_definitions(
            {"owh_submit_result", *execution.get("native_tools", [])}, quiet=True
        )
    else:
        listed = _rpc(server, run_id, "tools/list", {})
        expected = {
            mcp_prefixed_tool_name(server_name, tool["name"])
            for tool in listed["tools"]
        }
        if len(expected) != len(listed["tools"]):
            return _error("App tool names are ambiguous; execution was blocked",
                          code="owh.tools.catalog_invalid")
        native = _interactive_definitions(config)
        actual = {item["function"]["name"] for item in native}
        missing = sorted(expected - actual)
        if missing:
            # Counts alone miss an equal-size tool replacement. Report only
            # names the server currently admits; never silently return no tools.
            return json.dumps({
                "error": "App tools require a runtime catalog refresh. Contact the administrator; do not use an alternative execution path.",
                "code": "owh.tools.catalog_refresh_required",
                "missing_tools": missing,
                "missing_count": len(missing),
            })
        internal_prefix = mcp_prefixed_tool_name(server_name, "")
        external_prefixes = tuple(
            mcp_prefixed_tool_name(name, "")
            for name in config.get("mcp_servers", {})
            if name != server_name and name.startswith(server_name.removesuffix("internal"))
        )
        definitions = []
        for item in native:
            name = item["function"]["name"]
            if name.startswith(internal_prefix):
                allowed = name in expected
            else:
                allowed = name in _INTERACTIVE_TOOLS or name.startswith(external_prefixes)
            if allowed:
                definitions.append(item)
    dispatch = dispatch_tool_search if tool_name == "tool_search" else dispatch_tool_describe
    return dispatch(args, current_tool_defs=definitions)


def _request_write_consent(
    message: str, description: str, *, run_id: str, surface: str, arguments: dict,
) -> str:
    """Bridge the pinned API elicitation gap without changing unattended guards.

    v2026.8.31 registers an API run notifier but its public elicitation helper
    excludes api_server. Reuse its queue/wait/interrupt lifecycle for that exact
    run only. Remove this adapter when the public helper routes API notifiers.
    """
    from gateway.session_context import get_session_env
    from tools import approval

    if get_session_env("HERMES_SESSION_PLATFORM", "") != "api_server":
        return approval.request_elicitation_consent(message, description, surface=surface)
    if not run_id.startswith("run_") or approval.get_current_session_key(default="") != run_id:
        return "decline"
    with approval._lock:
        notify = approval._gateway_notify_cbs.get(run_id)
    if not callable(notify):
        return "decline"
    decision = approval._await_gateway_decision(
        run_id,
        notify,
        {
            "command": message,
            "description": description,
            "arguments": arguments,
            "pattern_key": "mcp_elicitation",
            # Native coalescing compares command and pattern_keys, not description.
            "pattern_keys": [
                "mcp_elicitation", hashlib.sha256(description.encode()).hexdigest(),
            ],
            "allow_session": False,
            "allow_permanent": False,
        },
        surface=surface,
    )
    accepted = (
        decision.get("resolved")
        and decision.get("choice") == "once"
        and not decision.get("notify_failed")
    )
    return "accept" if accepted else "decline"


def runtime_transport():
    from hermes_cli.config import load_config
    from hermes_constants import get_hermes_home
    from tools.approval import get_current_session_key

    profile = get_hermes_home().name
    if not re.fullmatch(r"owh-[0-9a-f]{32}(?:-local)?", profile):
        raise ValueError("Managed interactive/workload profile required")
    namespace = hashlib.sha256(profile.encode()).hexdigest()[:20]
    server_name = f"owh-mcp-{namespace}-internal"
    run_id = get_current_session_key(default="")
    server = load_config().get("mcp_servers", {}).get(server_name)
    if not run_id.startswith("run_") or not isinstance(server, dict):
        raise ValueError("Trusted runtime context required")
    if not server.get("headers", {}).get("Authorization"):
        raise ValueError("Authenticated transport required")
    return server, run_id


def _rpc(server: dict, run_id: str, method: str, params: dict) -> dict:
    from tools.mcp_tool import _interpolate_env_vars

    # Management stores bearer tokens as profile-local ${VAR} references.
    # The pinned native resolver reads the current multiplexed secret scope.
    configured_headers = _interpolate_env_vars(server.get("headers", {}))
    authorization = configured_headers.get("Authorization", "")
    if not authorization.startswith("Bearer ") or "${" in authorization:
        raise ValueError("Resolved profile authentication required")
    headers = {
        **configured_headers,
        "X-Hermes-Run-Id": run_id,
        "Accept": "application/json",
    }
    # A run may reach its first tool before the dispatcher has committed the
    # native run ID. Only discovery can retry; never replay a mutating call.
    deadline = time.monotonic() + 10
    # This middleware owns its HTTP request; native MCP SDK timeouts do not
    # cover it. Allow the bounded one-hour workload plus dispatch/cleanup
    # overhead to finish, while keeping connection and control waits short.
    timeout = httpx.Timeout(30, read=3900 if method == "tools/call" else 30)
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        while True:
            response = client.post(
                server["url"],
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": uuid4().hex,
                    "method": method,
                    "params": params,
                },
            )
            if (
                method in {"tools/list", "owh/context"}
                and response.status_code == 409
                and time.monotonic() < deadline
            ):
                time.sleep(0.1)
                continue
            response.raise_for_status()
            body = response.json()
            if "error" in body:
                raise ValueError("Open Work Hub rejected the tool request")
            return body["result"]


def execute_tool(*, tool_name: str, args: dict, next_call, **context):
    # Check every OWH internal prefix, including another profile's tool names.
    # Returning an error is deliberate: native middleware falls through when
    # a callback raises. A transport/policy failure must never invoke next_call.
    call_started = False
    try:
        from hermes_cli.config import load_config
        from hermes_constants import get_hermes_home
        from tools.approval import get_current_session_key
        from tools.mcp_tool import mcp_prefixed_tool_name

        profile = get_hermes_home().name
        if not re.fullmatch(r"owh-[0-9a-f]{32}(?:-local)?(?:-jobs)?", profile):
            return next_call()
        namespace = hashlib.sha256(profile.encode()).hexdigest()[:20]
        server_name = f"owh-mcp-{namespace}-internal"
        run_id = get_current_session_key(default="")
        if not run_id.startswith("run_"):
            return _error("Trusted Hermes run context is required")
        config = load_config()
        server = config.get("mcp_servers", {}).get(server_name)
        if not isinstance(server, dict) or not server.get("headers", {}).get("Authorization"):
            return _error("Authenticated Open Work Hub transport is unavailable")
        execution = _rpc(server, run_id, "owh/context", {})
        if tool_name == "owh_submit_result":
            return json.dumps(_rpc(server, run_id, "owh/submit", args), ensure_ascii=False)
        if tool_name == "tool_call":
            # The native executor keeps the bridge name when parsing, scope or
            # required-argument validation rejects unwrapping. Preserve useful
            # native validation feedback only for currently admitted tools.
            # Never dispatch here: valid calls arrive under the underlying name.
            from tools.tool_search import resolve_underlying_call, validate_deferred_call_args

            target, arguments, parse_error = resolve_underlying_call(args)
            if parse_error:
                return _error(parse_error, code="owh.tools.invalid_tool_call")
            described = json.loads(_scoped_discovery(
                "tool_describe", {"names": [target]}, config=config,
                server_name=server_name, server=server, run_id=run_id, execution=execution,
            ))
            if described.get("error"):
                return json.dumps(described)
            if target not in described.get("tools", {}):
                return _error("Tool is not available for this run", code="owh.tools.tool_unavailable")
            invalid = validate_deferred_call_args(target, arguments)
            if invalid:
                return invalid
            return _error("The native executor did not admit this call. Use tool_search to check available tools.",
                          code="owh.tools.tool_unavailable")
        if tool_name in {"tool_search", "tool_describe"}:
            return _scoped_discovery(
                tool_name, args, config=config, server_name=server_name,
                server=server, run_id=run_id, execution=execution,
            )
        # Profile history includes app workloads. Native search has no trusted
        # OWH app/resource ACL filter, including its direct session-read mode.
        if tool_name == "session_search":
            return _error("Native history search has no Open Work Hub source-access policy")
        if tool_name in execution.get("native_tools", []):
            if not _rpc(server, run_id, "owh/native_admit", {"tool": tool_name}).get("accepted"):
                return _error("The workload tool limit was reached")
            return next_call()
        if not tool_name.startswith(mcp_prefixed_tool_name(server_name, "")):
            if not execution.get("allow_native_tools"):
                return _error("This workload may only submit its result")
            if tool_name == "owh_preview":
                from .preview import render_preview

                return render_preview(args, execution=execution, server=server, run_id=run_id)
            if tool_name.startswith("mcp__owh_mcp_") and not tool_name.startswith(
                f"mcp__owh_mcp_{namespace}_"
            ):
                return _error("Tool is not available in this execution profile")
            if not tool_name.startswith(f"mcp__owh_mcp_{namespace}_") and tool_name not in _INTERACTIVE_TOOLS:
                return _error("Tool has no configured Open Work Hub execution policy")
            if tool_name.startswith(f"mcp__owh_mcp_{namespace}_") and tool_name not in {
                item["function"]["name"] for item in _interactive_definitions(config)
            }:
                return _error("Tool is not enabled in this execution profile")
            if tool_name in {
                "execute_code", "terminal", "process", "read_file",
                "write_file", "patch", "search_files",
            }:
                from .native_execution import execute_native

                return execute_native(
                    tool_name,
                    next_call,
                    task_id=context.get("task_id"),
                    server=server,
                    run_id=run_id,
                )
            return next_call()
        listed = _rpc(server, run_id, "tools/list", {})
        matches = [
            tool
            for tool in listed.get("tools", [])
            if mcp_prefixed_tool_name(server_name, tool["name"]) == tool_name
        ]
        if len(matches) != 1:
            return _error("Tool is not available for this run")
        tool = matches[0]
        if not tool.get("annotations", {}).get("readOnlyHint", False):
            digest = hashlib.sha256(
                json.dumps(
                    args,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            consent = _request_write_consent(
                f"MCP tool '{tool['name']}' on UNTRUSTED server '{server_name}' wants to run.",
                f"Approve this call once. Arguments SHA-256: {digest}",
                run_id=run_id,
                arguments=args,
                surface=f"mcp-trust/{server_name}",
            )
            if consent != "accept":
                return _error("Tool approval was denied")
        call_started = True
        result = _rpc(server, run_id, "tools/call", {"name": tool["name"], "arguments": args})
        return json.dumps(result.get("structuredContent", result), ensure_ascii=False)
    except Exception as error:
        if call_started:
            return _error(
                "Open Work Hub did not confirm this tool's outcome. The server may still "
                "complete the call; do not repeat it. Verify the result before continuing."
            )
        return _error(
            f"Open Work Hub tool transport failed ({type(error).__name__}); execution was blocked",
            code="owh.tools.discovery_unavailable" if tool_name in {"tool_search", "tool_describe", "tool_call"} else None,
        )


def register(ctx):
    from .native_execution import install_code_guard
    from .sandbox import OpenWorkHubSandbox

    install_code_guard()
    ctx.register_terminal_environment_provider(OpenWorkHubSandbox())
    ctx.register_middleware("tool_execution", execute_tool)
    ctx.register_tool(
        name="owh_preview",
        toolset="owh_runtime",
        schema={
            "name": "owh_preview",
            "description": "Render a saved workspace HTML file and its local JS/CSS/images in an offline sandboxed Chromium. Returns bounded console/resource errors and a screenshot for vision-capable models. Use after creating or modifying interactive results, before claiming they work. No Playwright installation, public URL or running server is needed. External dependencies/fetch are blocked as in the chat preview; save dependencies locally. A rendering is evidence, not proof of task correctness.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                           "required": ["path"], "additionalProperties": False},
        },
        handler=lambda args, **kwargs: _error("Trusted interactive context is required"),
    )
    ctx.register_tool(
        name="owh_submit_result",
        toolset="owh_runtime",
        schema={
            "name": "owh_submit_result",
            "description": "Submit the structured result required by this workload. Correct validation errors and resubmit before finishing.",
            "parameters": {
                "type": "object",
                "properties": {"result": {"type": "object"}},
                "required": ["result"],
                "additionalProperties": False,
            },
        },
        handler=lambda args, **kwargs: _error("Trusted workload context is required"),
    )
