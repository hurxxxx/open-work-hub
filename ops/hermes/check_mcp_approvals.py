"""Pinned API MCP approval lifecycle check; synthetic identity, no inference/writes."""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, "/opt/hermes/plugins")
from gateway.session_context import clear_session_vars, set_session_vars
from tools import approval
from owh_runtime import _request_write_consent

logging.disable(logging.CRITICAL)


def check(choice, barrier=None):
    run_id = "run_" + uuid4().hex
    tokens = set_session_vars(platform="api_server", session_key=run_id)
    token = approval.set_current_session_key(run_id)
    notifications = []

    def notify(data):
        notifications.append(data)
        assert data["allow_session"] is False
        assert data["allow_permanent"] is False
        assert data["arguments"] == {"title": "synthetic task"}
        if barrier is not None:
            barrier.wait(timeout=10)
        assert approval.resolve_gateway_approval(
            "run_other", "once", request_id=data["request_id"]
        ) == 0
        if choice is not None:
            assert approval.resolve_gateway_approval(
                run_id, choice, request_id=data["request_id"]
            ) == 1

    try:
        approval.register_gateway_notify(run_id, notify)
        result = _request_write_consent(
            "MCP tool 'synthetic.write' wants to run.",
            "Approve this call once. Arguments SHA-256: " + "0" * 64,
            run_id=run_id,
            surface="mcp-trust/synthetic",
            arguments={"title": "synthetic task"},
        )
        assert result == ("accept" if choice == "once" else "decline")
        assert len(notifications) == 1
        assert approval.list_gateway_approvals(run_id) == []
        assert approval.resolve_gateway_approval(
            run_id, "once", request_id=notifications[0]["request_id"]
        ) == 0
        approval.unregister_gateway_notify(run_id)
        assert _request_write_consent(
            "write", "missing notifier", run_id=run_id, surface="mcp-trust/synthetic",
            arguments={},
        ) == "decline"
    finally:
        approval.unregister_gateway_notify(run_id)
        approval.reset_current_session_key(token)
        clear_session_vars(tokens)


barrier = Barrier(2)
with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(check, choice, barrier) for choice in ("once", "deny")]
    for future in futures:
        future.result(timeout=20)
with patch.object(approval, "_get_approval_timeout", lambda: 0):
    check(None)
for choice in ("session", "always"):
    check(choice)
print("PASS: API MCP consent, denial, timeout, one-time choice, replay and concurrent run isolation")
