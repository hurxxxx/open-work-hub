from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field

from open_work_hub_api.domains.ai.tool_argument_validation import (
    ToolArgumentValidationFailure,
    validate_tool_arguments,
)
from open_work_hub_api.domains.pms.tools import PmsUpdateTaskAiInput


class AliasArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_at: str | None = Field(default=None, alias="from")
    q: str = ""
    limit: int | None = None


class CountArgs(BaseModel):
    count: int = Field(..., ge=1)


def test_validate_tool_arguments_without_model_returns_raw_arguments() -> None:
    result = validate_tool_arguments(
        args_model=None,
        arguments={"q": "hello", "limit": 5},
    )

    assert result.validated_arguments == {"q": "hello", "limit": 5}
    assert result.parsed_args == {"q": "hello", "limit": 5}


def test_validate_tool_arguments_dumps_aliases_and_excludes_none() -> None:
    result = validate_tool_arguments(
        args_model=AliasArgs,
        arguments={"from": "2026-05-01", "q": "meeting"},
    )

    assert result.validated_arguments == {
        "from": "2026-05-01",
        "q": "meeting",
    }
    assert isinstance(result.parsed_args, AliasArgs)


def test_validate_tool_arguments_normalizes_generic_validation_failure() -> None:
    with pytest.raises(ToolArgumentValidationFailure) as failure_info:
        validate_tool_arguments(
            args_model=CountArgs,
            arguments={"count": 0},
        )

    failure = failure_info.value
    assert failure.message.startswith("Invalid tool arguments: count:")
    assert failure.generic_reason == failure.message.removeprefix(
        "Invalid tool arguments: "
    )
    assert failure.localized_error is None


def test_validate_tool_arguments_maps_localized_domain_validation_failure() -> None:
    with pytest.raises(ToolArgumentValidationFailure) as failure_info:
        validate_tool_arguments(
            args_model=PmsUpdateTaskAiInput,
            arguments={"task_id": "task-1"},
        )

    failure = failure_info.value
    assert failure.localized_error == ("pms.update_mutable_field_required", {})
    assert "PMS task updates must provide at least one mutable field." in failure.message
