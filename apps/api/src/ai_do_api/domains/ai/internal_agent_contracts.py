from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_do_api.domains.ai.boundary_safety import assert_external_manager_payload_safe


LocalAgentResultStatus = Literal["completed", "blocked", "failed"]


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
        normalized = [tool_name.strip() for tool_name in value if tool_name.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed_tool_names must not contain duplicates")
        return normalized

    @field_validator("tool_arguments")
    @classmethod
    def _tool_arguments_must_be_safe(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        for item in value.values():
            if isinstance(item, str):
                assert_external_manager_payload_safe(item)
            elif isinstance(item, list):
                for nested_item in item:
                    if isinstance(nested_item, str):
                        assert_external_manager_payload_safe(nested_item)
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
        assert_external_manager_payload_safe(self.redacted_summary)
        if self.blocked_reason:
            assert_external_manager_payload_safe(self.blocked_reason)
        for coverage_values in self.coverage.values():
            for coverage_value in coverage_values:
                assert_external_manager_payload_safe(coverage_value)
        return self
