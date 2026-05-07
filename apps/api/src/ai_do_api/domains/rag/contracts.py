from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RagSyncOperation(StrEnum):
    UPSERT = "upsert"
    DELETE = "delete"
    VISIBILITY_UPDATE = "visibility_update"


class RagSyncLane(StrEnum):
    REALTIME = "realtime"
    BACKFILL = "backfill"


class RagJobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RagAnswerMode(StrEnum):
    SEARCH_ONLY = "search-only"
    GROUNDED_ANSWER = "grounded-answer"


class RagTraceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    traceparent: str | None = None
    tracestate: str | None = None
    baggage: dict[str, str] = Field(default_factory=dict)


class RagProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    resource_type: str
    resource_id: str
    source_kind: str
    title: str | None = None
    summary: str | None = None
    text_content: str = ""
    owner_label: str | None = None
    visibility_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    text: str
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagVectorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    text: str
    summary: str | None = None
    embedding: list[float] = Field(default_factory=list)
    sparse_terms: dict[str, float] = Field(default_factory=dict)
    projection: RagProjection
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str
    projection: RagProjection
    chunks: list[RagChunk]
    trace_context: RagTraceContext | None = None


class RagDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str
    workspace_id: str
    resource_type: str
    resource_id: str
    trace_context: RagTraceContext | None = None


class RagVectorSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str
    query: str
    workspace_id: str
    query_embedding: list[float] = Field(default_factory=list)
    source_kinds: list[str] = Field(default_factory=list)
    metadata_filter: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=10, ge=1, le=100)
    trace_context: RagTraceContext | None = None


class RagVectorSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    text: str
    summary: str | None = None
    score: float
    citation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    projection: RagProjection


class RagGroundedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    source_kind: str
    quote: str
    locator: str | None = None


class RagGroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    citations: list[RagGroundedCitation] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)


class RagQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str
    workspace_id: str
    query: str
    answer_mode: RagAnswerMode = RagAnswerMode.SEARCH_ONLY
    source_kinds: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=10, ge=1, le=100)
    include_binary_hits: bool = False
    trace_context: RagTraceContext | None = None


class RagQueryHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: str
    resource_type: str
    resource_id: str
    workspace_id: str
    title: str | None = None
    summary: str | None = None
    score: float
    citation: str | None = None
    owner_label: str | None = None
    acl_summary: list[str] = Field(default_factory=list)
    origin_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    answer_mode: RagAnswerMode
    hits: list[RagQueryHit] = Field(default_factory=list)
    grounded_answer: RagGroundedAnswer | None = None
    sources_used: list[str] = Field(default_factory=list)
    query_profile: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    latency_ms: int = 0


class RagSyncResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str
    operation: RagSyncOperation
    chunk_count: int = 0
    deleted_count: int = 0
    trace_id: str | None = None


class RagProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_name: str
    ready: bool
    detail: str | None = None
