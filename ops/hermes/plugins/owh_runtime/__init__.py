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


def _error(message: str) -> str:
    return json.dumps({"error": message})


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
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
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
    try:
        from hermes_cli.config import load_config
        from hermes_constants import get_hermes_home
        from tools.approval import get_current_session_key, request_elicitation_consent
        from tools.mcp_tool import mcp_prefixed_tool_name

        profile = get_hermes_home().name
        if not re.fullmatch(r"owh-[0-9a-f]{32}(?:-local)?(?:-jobs)?", profile):
            return next_call()
        namespace = hashlib.sha256(profile.encode()).hexdigest()[:20]
        server_name = f"owh-mcp-{namespace}-internal"
        run_id = get_current_session_key(default="")
        if not run_id.startswith("run_"):
            return _error("Trusted Hermes run context is required")
        server = load_config().get("mcp_servers", {}).get(server_name)
        if not isinstance(server, dict) or not server.get("headers", {}).get("Authorization"):
            return _error("Authenticated Open Work Hub transport is unavailable")
        execution = _rpc(server, run_id, "owh/context", {})
        if tool_name == "owh_submit_result":
            return json.dumps(_rpc(server, run_id, "owh/submit", args), ensure_ascii=False)
        if tool_name in execution.get("native_tools", []):
            if not _rpc(server, run_id, "owh/native_admit", {"tool": tool_name}).get("accepted"):
                return _error("The workload tool limit was reached")
            return next_call()
        if not tool_name.startswith(mcp_prefixed_tool_name(server_name, "")):
            if not execution.get("allow_native_tools"):
                return _error("This workload may only submit its result")
            if tool_name.startswith("mcp__owh_mcp_") and not tool_name.startswith(
                f"mcp__owh_mcp_{namespace}_"
            ):
                return _error("Tool is not available in this execution profile")
            if not tool_name.startswith(f"mcp__owh_mcp_{namespace}_") and tool_name not in {
                "web_search",
                "web_extract",
                "terminal",
                "process",
                "read_file",
                "write_file",
                "patch",
                "search_files",
                "skills_list",
                "skill_view",
                "skill_manage",
                "todo",
                "memory",
                "session_search",
                "execute_code",
                "delegate_task",
            }:
                return _error("Tool has no configured Open Work Hub execution policy")
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
            consent = request_elicitation_consent(
                f"MCP tool '{tool['name']}' on UNTRUSTED server '{server_name}' wants to run.",
                f"Approve this call once. Arguments SHA-256: {digest}",
                surface=f"mcp-trust/{server_name}",
            )
            if consent != "accept":
                return _error("Tool approval was denied")
        result = _rpc(server, run_id, "tools/call", {"name": tool["name"], "arguments": args})
        return json.dumps(result.get("structuredContent", result), ensure_ascii=False)
    except Exception as error:
        return _error(
            f"Open Work Hub tool transport failed ({type(error).__name__}); execution was blocked"
        )


def register(ctx):
    from .sandbox import OpenWorkHubSandbox

    ctx.register_terminal_environment_provider(OpenWorkHubSandbox())
    ctx.register_middleware("tool_execution", execute_tool)
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
