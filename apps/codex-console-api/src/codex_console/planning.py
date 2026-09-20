"""The native final-output schema separates conversation from optional documents."""

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


INSTRUCTIONS = """
Planning includes ordinary questions, investigation and optional document authoring.
Return an answer and documents using the supplied output schema. For an ordinary question,
documents is empty: do not create a document merely because planning mode is selected.
Create requirements or a plan when the user requests that document. Once a document exists,
update it for the user's confirmed changes and decisions without requiring repeated save requests.
Do not treat exploratory questions or suggestions as confirmed scope. Separate open questions
from decisions. Keep unrelated content and follow the user's requested document format.
Use the supplied document base_version (0 for a new document), return the full updated body,
and explain the changes in summary and answer. Omit unchanged documents. Output at most one
update of each kind. These are console documents, not permission to edit repository files.
"""
