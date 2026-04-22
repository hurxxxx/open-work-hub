from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException, status
import pytest

from aidoo_api.domains.ai import tool_runtime


def test_execute_tool_call_treats_non_approval_conflict_as_error(
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


def test_execute_tool_call_maps_approval_conflict_to_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_tool(*args, **kwargs):
        del args, kwargs
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI tool requires approval before execution: docs.create_page",
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
    assert result.approval_id is not None
