from __future__ import annotations

from types import SimpleNamespace

import pytest

from open_alm_api.domains.ai import tool_runtime
from open_alm_api.domains.ai.tool_service import ToolRequiresApproval


def test_execute_tool_call_maps_approval_required_exception_to_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_tool(*args, **kwargs):
        del args, kwargs
        raise ToolRequiresApproval(
            tool_call_id="call-1",
            tool_name="pms.delete_task",
            arguments_json='{"task_id":"issue-1"}',
            resource_preview="issue-1",
        )

    monkeypatch.setattr(tool_runtime, "execute_tool", fake_execute_tool)

    result = tool_runtime.execute_tool_call(
        SimpleNamespace(),
        workspace=SimpleNamespace(id="ws-1"),
        principal=SimpleNamespace(kind="user", user_id="user-1"),
        user=SimpleNamespace(id="user-1"),
        tool_name="pms.delete_task",
        arguments={"task_id": "issue-1"},
        source="test.runtime",
    )

    assert result.status == "blocked"
    assert result.resource_preview == "issue-1"
    assert result.arguments_json == '{"task_id":"issue-1"}'
