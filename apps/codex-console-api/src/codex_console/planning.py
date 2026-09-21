"""Compatibility parser for structured planning turns created before native plan projection."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["requirements", "plan"]
    base_version: int = Field(ge=0)
    body: str = Field(min_length=1, max_length=100000)
    summary: str = Field(min_length=1, max_length=4000)


class PlanningOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=100000)
    documents: list[DocumentUpdate] = Field(max_length=2)


def parse(text):
    try:
        return PlanningOutput.model_validate_json(text)
    except (ValidationError, ValueError, TypeError):
        return None


def unwrap_proposed_plan(text: str) -> str:
    """Remove the presentation wrapper used by older Codex plan answers."""
    opening = "<proposed_plan>"
    closing = "</proposed_plan>"
    candidate = text.strip()
    if not candidate.startswith(opening) or not candidate.endswith(closing):
        return text
    body = candidate[len(opening) : -len(closing)].strip()
    return body or text
