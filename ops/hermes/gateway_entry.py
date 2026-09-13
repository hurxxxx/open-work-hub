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
import json
import logging
import re
import time
from uuid import uuid4

from gateway.platforms import api_server_runs

_LOG = logging.getLogger("open-work-hub.hermes-gateway")
_MANAGED_INTERACTIVE_PROFILE = re.compile(r"^owh-[0-9a-f]{32}(?:-local)?$")
_original_handle_runs = api_server_runs._handle_runs
_original_http_routes = api_server_runs._http_routes


async def _cancel_run_admission(self, request, *, _api_server):
    """Resolve a lost acceptance without ever starting an agent.

    v2026.8.31 exposes idempotency lookup only through creation, which creates
    on a miss. Reuse its atomic, scoped reservation store to fence a request
    still in flight with a cancelled record. A concurrent native admission
    either wins first (and returns its existing ID), or replays this record.
    Remove this pinned adapter when native cancellation accepts an idempotency key.
    """

    def error(message, code, status):
        return _api_server.web.json_response(
            _api_server._openai_error(message, code=code), status=status
        )

    # Native API authentication belongs to each handler, not the route table.
    # This compensation endpoint accepts only the existing runtime control key.
    auth_error = self._check_auth(request)
    if auth_error is not None:
        return auth_error
    profile = _api_server._api_request_profile.get() or ""
    if not _MANAGED_INTERACTIVE_PROFILE.fullmatch(profile):
        return error("Managed profile required.", "invalid_profile", 403)
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 255 or any(ord(ch) < 33 or ord(ch) > 126 for ch in key):
        return error("Idempotency key required.", "invalid_idempotency_key", 400)
    gateway_session_key, key_error = self._parse_session_key_header(request)
    if key_error is not None:
        return key_error
    try:
        body = await request.json()
    except Exception:
        return error("Invalid JSON.", "invalid_request", 400)
    # Only the native request shape emitted by the OWH client is supported;
    # hosted-room normalization has a separate identity/fingerprint contract.
    if (
        not isinstance(body, dict)
        or not isinstance(body.get("input"), str)
        or not body["input"]
        or not isinstance(body.get("session_id"), str)
        or not body["session_id"]
        or body.keys()
        - {
            "input",
            "session_id",
            "instructions",
            "conversation_history",
            "provider",
            "model",
            "model_options",
        }
    ):
        return error("Invalid cancellation request.", "invalid_request", 400)
    try:
        store = self._run_idempotency_store
        if not store.durable:
            raise RuntimeError("Durable run admission storage required")
        # This is the pinned native fingerprint, including the parsed session
        # header. The cancellation URL does not enter its fingerprint or scope.
        fingerprint = hashlib.sha256(
            json.dumps(
                {"body": body, "gateway_session_key": gateway_session_key or ""},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        now = time.time()
        cancelled_id = f"run_{uuid4().hex}"
        outcome, record = await asyncio.to_thread(
            store.reserve,
            self._run_idempotency_scope(request),
            key,
            fingerprint,
            cancelled_id,
            {
                "run_id": cancelled_id,
                "status": "cancelled",
                "last_event": "run.cancelled",
                "session_id": body["session_id"],
                "created_at": now,
                "updated_at": now,
            },
            owner_pid=self._run_owner_pid,
            owner_started=self._run_owner_started,
        )
        if outcome == "conflict":
            return error("Idempotency request conflicts.", "idempotency_key_conflict", 409)
        if outcome not in {"created", "reused"} or not isinstance(record, dict):
            raise RuntimeError("Invalid native reservation result")
        return _api_server.web.json_response(
            {
                "run_id": record["run_id"],
                "status": record["status"]["status"],
                "replayed": outcome == "reused",
            },
            status=202,
        )
    except Exception as failure:
        _LOG.error("Hermes cancellation reconciliation failed: %s", type(failure).__name__)
        return error("Run cancellation is unavailable.", "cancellation_unavailable", 503)


def _http_routes_with_cancellation(self):
    from gateway.platforms import api_server

    async def cancel(request):
        return await _cancel_run_admission(self, request, _api_server=api_server)

    return [
        *_original_http_routes(self),
        ("POST", "/v1/owh/runs/cancel-admission", cancel),
    ]


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
api_server_runs._http_routes = _http_routes_with_cancellation


def main() -> None:
    from hermes_cli.main import main as hermes_main

    hermes_main()


if __name__ == "__main__":
    main()
