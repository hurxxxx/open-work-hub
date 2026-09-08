from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


def _camel_config() -> ConfigDict:
    return ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class PersonalTodoCreateRequest(BaseModel):
    model_config = _camel_config()

    title: str = Field(..., min_length=1, max_length=240)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be empty")
        return normalized


class PersonalTodoUpdateRequest(BaseModel):
    model_config = _camel_config()

    title: str | None = Field(default=None, min_length=1, max_length=240)
    completed: bool | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be empty")
        return normalized


class PersonalTodoItemOut(BaseModel):
    model_config = _camel_config()

    id: str
    title: str
    completed: bool
    sort_order: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PersonalTodoListResponse(BaseModel):
    model_config = _camel_config()

    items: list[PersonalTodoItemOut]


class PersonalMemoUpdateRequest(BaseModel):
    model_config = _camel_config()

    body: str = Field(default="", max_length=20000)


class PersonalMemoOut(BaseModel):
    model_config = _camel_config()

    id: str | None
    body: str
    created_at: datetime | None
    updated_at: datetime | None


class PersonalPmsTaskOut(BaseModel):
    id: str
    list_id: str
    reference: str
    title: str
    description: str
    description_blocks: list[dict] | None = None
    parent_id: str | None = None
    subtask_count: int = 0
    status: str
    status_label: str
    priority: str
    priority_label: str
    assignee_id: str | None
    assignee_name: str | None
    assignee_ids: list[str] = Field(default_factory=list)
    assignee_names: list[str] = Field(default_factory=list)
    follower_ids: list[str] = Field(default_factory=list)
    follower_names: list[str] = Field(default_factory=list)
    reporter_id: str
    reporter_name: str
    milestone_id: str | None
    milestone_title: str | None
    start_date: date | None
    due_date: date | None
    completed_date: date | None
    board_position: int
    archived: bool
    progress: float | None
    comments_count: int
    checklist_total: int = 0
    checklist_done: int = 0
    recurrence_rule: str | None = None
    labels: list[dict[str, str]] = Field(default_factory=list)
    updated_at: datetime


class PersonalPmsAssignedTasksResponse(BaseModel):
    items: list[PersonalPmsTaskOut]
    total: int
    page: int
    page_size: int
