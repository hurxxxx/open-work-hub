from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


ArtifactType = Literal["report", "analysis"]
ArtifactVisibility = Literal["private", "workspace"]
ArtifactStatus = Literal["pending", "building", "completed", "failed"]
ArtifactExactness = Literal["exact", "estimated", "semantic", "mixed", "unknown"]
QueryExecutionStatus = Literal["not_executed", "completed", "failed"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class AiArtifactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=36)
    owner_user_id: str | None = Field(default=None, min_length=1, max_length=36)
    app_id: str = Field(min_length=1, max_length=64)
    artifact_type: ArtifactType
    title: str = Field(min_length=1, max_length=240)
    content_type: str = Field(default="text/markdown", min_length=1, max_length=128)
    content_text: str | None = None
    payload: dict[str, Any] | list[Any] | None = None
    graph_run_id: str | None = Field(default=None, max_length=36)
    conversation_id: str | None = Field(default=None, max_length=36)
    conversation_turn_id: str | None = Field(default=None, max_length=36)
    supersedes_artifact_id: str | None = Field(default=None, max_length=36)
    schema_version: int = Field(default=1, ge=1)
    visibility: ArtifactVisibility = "private"

    @model_validator(mode="after")
    def validate_ownership(self) -> "AiArtifactCreate":
        if self.owner_user_id is None and self.visibility != "workspace":
            raise ValueError("ownerless system artifacts must use workspace visibility")
        return self


class AiArtifactSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_kind: str = Field(min_length=1, max_length=64)
    source_ref: str = Field(min_length=1, max_length=512)
    source_version: str | None = Field(default=None, max_length=128)
    title: str | None = Field(default=None, max_length=240)
    locator: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    grid_columns: list[dict[str, Any]] | None = None
    grid_rows: list[dict[str, Any]] | None = None
    row_count: int | None = Field(default=None, ge=0)
    truncated: bool = False


class AiArtifactQueryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_kind: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=240)
    family_id: str | None = Field(default=None, max_length=128)
    query_spec: dict[str, Any] | None = None
    statement_text: str | None = None
    typed_params: dict[str, Any] | None = None
    execution_status: QueryExecutionStatus = "not_executed"
    error_code: str | None = Field(default=None, max_length=128)
    result_schema: list[dict[str, Any]] | None = None
    result_rows: list[dict[str, Any]] | None = None
    result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    row_count: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    truncated: bool = False
    payload_bytes: int | None = Field(default=None, ge=0)
    exactness: ArtifactExactness = "unknown"

    @model_validator(mode="after")
    def validate_query_payload(self) -> "AiArtifactQueryCreate":
        if self.query_spec is None and self.statement_text is None:
            raise ValueError("query_spec or statement_text is required")
        if self.execution_status == "failed" and not self.error_code:
            raise ValueError("failed query execution requires error_code")
        return self


class AiArtifactIndexGenerationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index_generation_id: str = Field(min_length=1, max_length=36)
    metadata: dict[str, Any] | None = None


class AiIndexGenerationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=36)
    app_id: str = Field(min_length=1, max_length=64)
    generation_key: str = Field(min_length=1, max_length=256)
    backend: str = Field(min_length=1, max_length=64)
    source_namespace: str = Field(min_length=1, max_length=256)
    schema_version: int = Field(default=1, ge=1)
    embedding_provider: str | None = Field(default=None, max_length=64)
    embedding_model: str | None = Field(default=None, max_length=256)
    embedding_dimensions: int | None = Field(default=None, ge=1)
    source_count: int = Field(default=0, ge=0)
    document_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(default=0, ge=0)
    corpus_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    created_by_user_id: str | None = Field(default=None, max_length=36)


class AiArtifactResponse(_CamelModel):
    id: str
    artifact_number: str
    workspace_id: str
    owner_user_id: str | None
    graph_run_id: str | None
    conversation_id: str | None
    conversation_turn_id: str | None
    supersedes_artifact_id: str | None
    app_id: str
    artifact_type: ArtifactType
    title: str
    content_type: str
    content_text: str | None
    schema_version: int
    content_sha256: str | None
    content_size_bytes: int | None
    visibility: ArtifactVisibility
    status: ArtifactStatus
    error_code: str | None
    completed_at: datetime | None
    created_at: datetime


class AiArtifactDetailResponse(AiArtifactResponse):
    payload: dict[str, Any] | list[Any] | None
    source_count: int
    query_count: int
    index_generation_count: int


class AiArtifactListResponse(_CamelModel):
    items: list[AiArtifactResponse]
    total: int


class AiArtifactSourceResponse(_CamelModel):
    id: str
    query_id: str | None = None
    ordinal: int
    source_kind: str
    source_ref: str
    source_version: str | None
    title: str | None
    locator: dict[str, Any] | None
    metadata: dict[str, Any] | None
    content_sha256: str | None
    grid_columns: list[dict[str, Any]] | None
    grid_rows: list[dict[str, Any]] | None
    row_count: int | None
    truncated: bool
    created_at: datetime


class AiArtifactSourceListResponse(_CamelModel):
    items: list[AiArtifactSourceResponse]


class AiArtifactQueryResponse(_CamelModel):
    id: str
    ordinal: int
    query_kind: str
    title: str | None
    family_id: str | None
    query_spec: dict[str, Any] | None
    statement_text: str | None
    typed_params: dict[str, Any] | None
    execution_status: QueryExecutionStatus
    error_code: str | None
    result_schema: list[dict[str, Any]] | None
    result_rows: list[dict[str, Any]] | None
    query_sha256: str
    result_sha256: str | None
    row_count: int | None
    duration_ms: int | None
    truncated: bool
    payload_bytes: int | None
    exactness: ArtifactExactness
    created_at: datetime


class AiArtifactQueryListResponse(_CamelModel):
    items: list[AiArtifactQueryResponse]


class AiArtifactIndexGenerationResponse(_CamelModel):
    id: str
    ordinal: int
    index_generation_id: str
    metadata: dict[str, Any] | None
    created_at: datetime


class AiArtifactIndexGenerationListResponse(_CamelModel):
    items: list[AiArtifactIndexGenerationResponse]
