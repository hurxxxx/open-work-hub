from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException, status
import pytest

from aidoo_api.domains.ai import tool_runtime
from aidoo_api.domains.ai.tool_service import ToolRequiresApproval


def test_execute_tool_call_treats_http_conflict_as_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_tool(*args, **kwargs):
        del args, kwargs
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meeting recording summary is not available yet.",
        )

    monkeypatch.setattr(tool_runtime, "execute_tool", fake_execute_tool)

    result = tool_runtime.execute_tool_call(
        SimpleNamespace(),
        workspace=SimpleNamespace(id="ws-1"),
        principal=SimpleNamespace(kind="user", user_id="user-1"),
        user=SimpleNamespace(id="user-1"),
        tool_name="meeting.extract_actions",
        arguments={},
        source="test.runtime",
    )

    assert result.status == "error"
    assert result.error_message == "Meeting recording summary is not available yet."


def test_execute_tool_call_maps_approval_required_exception_to_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_tool(*args, **kwargs):
        del args, kwargs
        raise ToolRequiresApproval(
            tool_call_id="call-1",
            tool_name="docs.create_page",
            arguments_json='{"title":"Draft"}',
            resource_preview="Draft",
        )

    monkeypatch.setattr(tool_runtime, "execute_tool", fake_execute_tool)

    result = tool_runtime.execute_tool_call(
        SimpleNamespace(),
        workspace=SimpleNamespace(id="ws-1"),
        principal=SimpleNamespace(kind="user", user_id="user-1"),
        user=SimpleNamespace(id="user-1"),
        tool_name="docs.create_page",
        arguments={"title": "Draft"},
        source="test.runtime",
    )

    assert result.status == "blocked"
    assert result.resource_preview == "Draft"
    assert result.arguments_json == '{"title":"Draft"}'
