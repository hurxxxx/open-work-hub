"""Launch Hermes with profile-aware MCP discovery for API runs.

Hermes v2026.8.31 keeps MCP connections and registration process-global. Its
registration is safely idempotent by server name, but multiplex mode normally
discovers only the launch profile. Open Work Hub gives every managed profile
globally unique MCP server names, so discovering the request profile before
admitting `/v1/runs` safely fills the shared registry without replacing another
profile's connection or changing Hermes' autonomous execution loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re

from gateway.platforms import api_server_runs

_LOG = logging.getLogger("open-work-hub.hermes-gateway")
_MANAGED_INTERACTIVE_PROFILE = re.compile(r"^owh-[0-9a-f]{32}(?:-local)?$")
_original_handle_runs = api_server_runs._handle_runs


def _discover_request_profile_mcp() -> None:
    from hermes_cli.plugins import get_plugin_manager
    from hermes_constants import get_hermes_home
    from tools.mcp_tool import discover_mcp_tools, get_mcp_status

    discover_mcp_tools()
    profile_name = get_hermes_home().name
    if not _MANAGED_INTERACTIVE_PROFILE.fullmatch(profile_name):
        return
    if not any(
        item.get("name") == "owh_runtime" and item.get("enabled") and not item.get("error")
        for item in get_plugin_manager().list_plugins()
    ):
        raise RuntimeError("The Open Work Hub runtime plugin is not loaded.")
    namespace = hashlib.sha256(profile_name.encode()).hexdigest()[:20]
    expected_internal_name = f"owh-mcp-{namespace}-internal"
    internal_server = next(
        (
            row
            for row in (get_mcp_status() or [])
            if isinstance(row, dict) and row.get("name") == expected_internal_name
        ),
        None,
    )
    if (
        internal_server is None
        or bool(internal_server.get("disabled"))
        or internal_server.get("status") != "connected"
    ):
        raise RuntimeError("The Open Work Hub MCP bridge is not connected.")


async def _handle_runs_with_profile_mcp(self, request, *, _api_server):
    try:
        # asyncio.to_thread copies the request's contextvars, including the
        # Hermes profile home and secret scope installed by prefix middleware.
        await asyncio.to_thread(_discover_request_profile_mcp)
    except Exception as error:
        _LOG.error(
            "Hermes profile MCP discovery failed before run admission: %s",
            type(error).__name__,
        )
        return _api_server.web.json_response(
            _api_server._openai_error(
                "The profile tool bridge is unavailable.",
                err_type="server_error",
                code="profile_mcp_unavailable",
            ),
            status=503,
        )
    return await _original_handle_runs(self, request, _api_server=_api_server)


api_server_runs._handle_runs = _handle_runs_with_profile_mcp


def main() -> None:
    from hermes_cli.main import main as hermes_main

    hermes_main()


if __name__ == "__main__":
    main()
