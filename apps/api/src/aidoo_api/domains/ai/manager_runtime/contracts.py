from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aidoo_api.domains.ai.boundary_safety import (
    assert_external_manager_payload_safe,
    detect_forbidden_external_payload_entities,
    has_meaningful_text_after_redaction,
    redact_external_manager_payload,
)
from aidoo_api.domains.ai.internal_agent_contracts import (
    LocalAgentResult as LocalAgentResult,
    LocalAgentTask as LocalAgentTask,
)


PromptEgressStatus = Literal["raw_allowed", "redacted", "blocked"]
ManagerReviewDecision = Literal["final", "retry", "ask_user", "partial", "failed"]


class ManagerPromptPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: PromptEgressStatus
    prompt: str = ""
    removed_entity_types: list[str] = Field(default_factory=list)
    redaction_summary: str | None = None
    blocked_reason: str | None = None

    @model_validator(mode="after")
    def _validate_prompt_safety(self) -> "ManagerPromptPayload":
        if self.status == "raw_allowed":
            if self.removed_entity_types:
                raise ValueError("raw prompt cannot carry removed_entity_types")
            assert_external_manager_payload_safe(self.prompt)
            return self
        if self.status == "redacted":
            if not self.prompt:
                raise ValueError("redacted prompt must not be empty")
            if not self.removed_entity_types:
                raise ValueError("redacted prompt must record removed entity types")
            assert_external_manager_payload_safe(self.prompt)
            return self
        if self.prompt:
            raise ValueError("blocked prompt payload must not include prompt text")
        if not self.blocked_reason:
            raise ValueError("blocked prompt payload must include blocked_reason")
        return self


class AiManagerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: ManagerPromptPayload
    available_agent_ids: list[str] = Field(default_factory=list)
    available_tool_names: list[str] = Field(default_factory=list)
    workspace_metadata: dict[str, str] = Field(default_factory=dict)
    prior_redacted_summaries: list[str] = Field(default_factory=list)

    @field_validator("available_agent_ids", "available_tool_names")
    @classmethod
    def _dedupe_non_empty_strings(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("values must not contain duplicates")
        return normalized

    @field_validator("workspace_metadata")
    @classmethod
    def _metadata_must_be_safe(cls, value: dict[str, str]) -> dict[str, str]:
        for metadata_value in value.values():
            assert_external_manager_payload_safe(metadata_value)
        return value

    @field_validator("prior_redacted_summaries")
    @classmethod
    def _summaries_must_be_safe(cls, value: list[str]) -> list[str]:
        for summary in value:
            assert_external_manager_payload_safe(summary)
        return value


class ManagerPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: str = Field(min_length=1)
    tasks: list[LocalAgentTask] = Field(default_factory=list)
    needs_user_decision: bool = False
    clarification_question: str | None = None


class ManagerReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: ManagerReviewDecision
    result_summary: str = ""
    gap_summary: str = ""
    next_tasks: list[LocalAgentTask] = Field(default_factory=list)
    user_question: str | None = None


def build_manager_prompt_payload(raw_prompt: str) -> ManagerPromptPayload:
    prompt = raw_prompt.strip()
    if not prompt:
        return ManagerPromptPayload(
            status="blocked",
            blocked_reason="empty_prompt",
        )

    removed_entity_types = detect_forbidden_external_payload_entities(prompt)
    if not removed_entity_types:
        return ManagerPromptPayload(status="raw_allowed", prompt=prompt)

    redacted = redact_external_manager_payload(prompt)
    if not has_meaningful_text_after_redaction(redacted):
        return ManagerPromptPayload(
            status="blocked",
            removed_entity_types=removed_entity_types,
            blocked_reason="redacted_prompt_empty",
        )
    return ManagerPromptPayload(
        status="redacted",
        prompt=redacted,
        removed_entity_types=removed_entity_types,
        redaction_summary="Removed sensitive entities before external manager egress.",
    )
