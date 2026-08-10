from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from open_alm_api.domains.ai.tool_approval_gate import (
    validate_replayed_approval,
)


def test_validate_replayed_approval_allows_matching_tool_and_call_id() -> None:
    approval = SimpleNamespace(
        tool_name="pms.update_issue",
        tool_call_id="call-1",
    )

    validate_replayed_approval(
        approval=approval,
        tool_name="pms.update_issue",
        call_id="call-1",
    )
    validate_replayed_approval(
        approval=approval,
        tool_name="pms.update_issue",
        call_id=None,
    )


def test_validate_replayed_approval_rejects_mismatches() -> None:
    approval = SimpleNamespace(
        tool_name="pms.update_issue",
        tool_call_id="call-1",
    )

    with pytest.raises(HTTPException) as tool_mismatch:
        validate_replayed_approval(
            approval=approval,
            tool_name="planner.update_event",
            call_id="call-1",
        )
    assert tool_mismatch.value.status_code == 409
    assert tool_mismatch.value.detail.code == "ai.approval_tool_mismatch"

    with pytest.raises(HTTPException) as call_mismatch:
        validate_replayed_approval(
            approval=approval,
            tool_name="pms.update_issue",
            call_id="call-2",
        )
    assert call_mismatch.value.status_code == 409
    assert call_mismatch.value.detail.code == "ai.approval_tool_call_mismatch"
