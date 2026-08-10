from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_do_api.domains.ai.boundary_safety import assert_external_manager_payload_safe


LocalAgentResultStatus = Literal["completed", "blocked", "failed"]


def normalize_unique_non_empty_strings(value: list[str], *, duplicate_message: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized_item = item.strip()
        if not normalized_item:
            continue
        if normalized_item in seen:
            raise ValueError(duplicate_message)
        normalized.append(normalized_item)
        seen.add(normalized_item)
    return normalized


def assert_external_manager_payload_tree_safe(value: Any) -> None:
    if isinstance(value, str):
        assert_external_manager_payload_safe(value)
        return
    if isinstance(value, Mapping):
        for nested_value in value.values():
            assert_external_manager_payload_tree_safe(nested_value)
        return
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        for nested_value in value:
            assert_external_manager_payload_tree_safe(nested_value)


class LocalAgentTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    allowed_tool_names: list[str] = Field(default_factory=list)
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    approved_call_id: str | None = None
    context_boundary: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)

    @field_validator("allowed_tool_names")
    @classmethod
    def _allowed_tools_must_not_repeat(cls, value: list[str]) -> list[str]:
        return normalize_unique_non_empty_strings(
            value,
            duplicate_message="allowed_tool_names must not contain duplicates",
        )

    @field_validator("tool_arguments")
    @classmethod
    def _tool_arguments_must_be_safe(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        assert_external_manager_payload_tree_safe(value)
        return dict(value)


class LocalAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1)
    status: LocalAgentResultStatus
    redacted_summary: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    coverage: dict[str, list[str]] = Field(default_factory=dict)
    sensitivity_labels: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None

    @model_validator(mode="after")
    def _validate_result_safety(self) -> "LocalAgentResult":
        if self.status == "completed" and not self.redacted_summary:
            raise ValueError("completed local result must include redacted_summary")
        if self.status == "blocked" and not self.blocked_reason:
            raise ValueError("blocked local result must include blocked_reason")
        assert_external_manager_payload_tree_safe(self.redacted_summary)
        assert_external_manager_payload_tree_safe(self.blocked_reason)
        assert_external_manager_payload_tree_safe(self.coverage)
        return self
