from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchEntityType(StrEnum):
    DOC = "doc"
    MEETING = "meeting"
    PMS_ISSUE = "pms_issue"
    PLANNER_EVENT = "planner_event"


class SearchPeopleFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["any", "owner", "assignee", "participant"] = "any"
    user_ids: list[str] = Field(default_factory=list)


class SearchDateFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["updated_at", "created_at", "due_date", "start_date", "event_start_at"]
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None


class SearchContainerRefFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1, max_length=64)
    id: str = Field(..., min_length=1, max_length=128)


class SearchSort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["relevance", "updated_at", "created_at"] = "relevance"
    direction: Literal["desc", "asc"] = "desc"


class KeywordSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    workspace_id: str | None = None
    query: str = Field(default="", max_length=2000)
    entity_types: list[SearchEntityType] = Field(default_factory=list)
    people: SearchPeopleFilter = Field(default_factory=SearchPeopleFilter)
    status_by_type: dict[SearchEntityType, list[str]] = Field(default_factory=dict)
    date_filters: list[SearchDateFilter] = Field(default_factory=list)
    container_refs: list[SearchContainerRefFilter] = Field(default_factory=list)
    sort: SearchSort = Field(default_factory=SearchSort)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchHighlight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int
    end: int


class SearchSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    highlights: list[SearchHighlight] = Field(default_factory=list)


class SearchPerson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    user_id: str
    label: str


class SearchContainerRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    id: str
    label: str


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: SearchEntityType
    entity_id: str
    workspace_id: str
    title: str
    summary: str
    snippet: SearchSnippet
    score: float
    status: str | None = None
    status_label: str | None = None
    visibility: str | None = None
    updated_at: datetime
    created_at: datetime
    date_markers: dict[str, Any] = Field(default_factory=dict)
    people: list[SearchPerson] = Field(default_factory=list)
    containers: list[SearchContainerRef] = Field(default_factory=list)
    deep_link: str
    preview_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityTypeFacet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: SearchEntityType
    label: str
    count: int


class StatusFacet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: SearchEntityType
    value: str
    label: str
    count: int


class ContainerFacet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    id: str
    label: str
    count: int


class SearchFacets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_types: list[EntityTypeFacet] = Field(default_factory=list)
    status: list[StatusFacet] = Field(default_factory=list)
    containers: list[ContainerFacet] = Field(default_factory=list)


class KeywordSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    hits: list[SearchHit]
    facets: SearchFacets
    total: int
    has_more: bool
    next_offset: int | None = None
    trace_id: str | None = None
