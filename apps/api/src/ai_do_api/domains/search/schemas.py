from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchEntityType(StrEnum):
    DOC = "doc"
    FILE = "file"
    MEETING = "meeting"
    PMS_TASK = "pms_task"
    PLANNER_EVENT = "planner_event"


SEARCH_TOKEN_PATTERN = r"^[A-Za-z0-9_.:-]+$"
SearchToken = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=SEARCH_TOKEN_PATTERN),
]
SearchResourceId = Annotated[str, Field(min_length=1, max_length=128)]
SearchTokenList = Annotated[list[SearchToken], Field(max_length=50)]


class SearchPeopleFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: SearchToken = "any"
    user_ids: list[SearchResourceId] = Field(default_factory=list, max_length=100)


class SearchDateFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: SearchToken
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None


class SearchTargetRefFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: SearchToken | None = None
    type: SearchToken
    id: SearchResourceId


class SearchSort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: SearchToken = "relevance"
    direction: Literal["desc", "asc"] = "desc"


class KeywordSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    workspace_id: str | None = None
    query: str = Field(default="", max_length=2000)
    entity_types: list[SearchToken] = Field(default_factory=list, max_length=50)
    people: SearchPeopleFilter = Field(default_factory=SearchPeopleFilter)
    status_by_type: dict[SearchToken, SearchTokenList] = Field(
        default_factory=dict,
        max_length=50,
    )
    date_filters: list[SearchDateFilter] = Field(default_factory=list, max_length=20)
    target_refs: list[SearchTargetRefFilter] = Field(
        default_factory=list,
        max_length=50,
    )
    target_ref_match: Literal["any", "all"] = "any"
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


class SearchTargetRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: str | None = None
    type: str
    id: str
    label: str


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
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
    targets: list[SearchTargetRef] = Field(default_factory=list)
    deep_link: str
    preview_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityTypeFacet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    count: int


class StatusFacet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    value: str
    label: str
    count: int


class TargetFacet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: str | None = None
    type: str
    id: str
    label: str
    count: int


class SearchFacets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_types: list[EntityTypeFacet] = Field(default_factory=list)
    status: list[StatusFacet] = Field(default_factory=list)
    targets: list[TargetFacet] = Field(default_factory=list)


class KeywordSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    hits: list[SearchHit]
    facets: SearchFacets
    total: int
    has_more: bool
    next_offset: int | None = None
    trace_id: str | None = None
