from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RetrievalStrategy(StrEnum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    GRAPH_HYBRID = "graph_hybrid"


class RetrievalAnswerMode(StrEnum):
    SEARCH_ONLY = "search-only"
    GROUNDED_ANSWER = "grounded-answer"


class RetrievalQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
    sources: list[str] = Field(default_factory=list, max_length=50)
    source_kinds: list[str] = Field(default_factory=list, max_length=50)
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=8, ge=1, le=100)
    answer_mode: RetrievalAnswerMode = RetrievalAnswerMode.SEARCH_ONLY
    include_binary_hits: bool = False


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    source_kind: str | None = None
    resource_type: str
    resource_id: str
    title: str | None = None
    summary: str | None = None
    excerpt: str | None = None
    score: float = 0.0
    citation: str | None = None
    methods: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    source: str
    quote: str
    locator: str | None = None


class RetrievalGroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    citations: list[RetrievalCitation] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)


class RetrievalProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: RetrievalStrategy
    requested_sources: list[str] = Field(default_factory=list)
    resolved_sources: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    backend_profiles: dict[str, Any] = Field(default_factory=dict)
    degraded_reasons: list[str] = Field(default_factory=list)


class RetrievalQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    strategy: RetrievalStrategy
    hits: list[RetrievalHit] = Field(default_factory=list)
    citations: list[RetrievalCitation] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    profile: RetrievalProfile
    grounded_answer: RetrievalGroundedAnswer | None = None
    trace_id: str | None = None
    latency_ms: int = 0


class RetrievalSourceDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    label: str
    scope: str
    backend: str
    required_app_ids: list[str] = Field(default_factory=list)
    active: bool = True
    available: bool = True
    description: str = ""


class RetrievalSourceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[RetrievalSourceDescriptor] = Field(default_factory=list)
