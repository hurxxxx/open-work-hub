from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DocumentProviderHealthResponse(BaseModel):
    provider_name: str
    ready: bool


class DocumentOcrStatusResponse(BaseModel):
    provider: str
    endpoint_configured: bool
    credential_configured: bool
    force_ocr: bool
    engine: str
    languages: list[str]
    minimum_text_chars: int


class DocumentModelStatusResponse(BaseModel):
    provider: str
    endpoint_configured: bool
    credential_configured: bool
    model: str
    revision: str | None = None
    batch_size: int


class DocumentRerankStatusResponse(DocumentModelStatusResponse):
    candidate_limit: int


class DocumentVectorIndexStatusResponse(BaseModel):
    provider: str
    endpoint_configured: bool
    credential_configured: bool
    collection_prefix: str
    active_collection: str | None = None


class DocumentKeywordIndexStatusResponse(BaseModel):
    provider: str
    endpoint_configured: bool
    index_prefix: str


class DocumentChunkingStatusResponse(BaseModel):
    strategy: str
    target_chars: int
    hard_max_chars: int
    overlap_chars: int
    minimum_chars: int
    index_text_max_chars: int


class DocumentVisionWorkloadResponse(BaseModel):
    workload_id: str
    owner_domain: str
    app_ids: list[str]
    effective_route: Literal["local", "external"]
    provider_id: str | None = None
    model_key: str | None = None
    max_output_tokens: int
    ready: bool
    readiness_code: str | None = None


class DocumentVisionStatusResponse(BaseModel):
    enabled: bool
    timeout_seconds: float
    max_pages: int
    dpi: int
    max_new_tokens: int
    workloads: list[DocumentVisionWorkloadResponse] = Field(default_factory=list)


class AdminDocumentProcessingResponse(BaseModel):
    configuration_scope: Literal["api_environment"] = "api_environment"
    health_scope: Literal["api_process"] = "api_process"
    worker_health_available: bool = False
    enabled: bool
    ready: bool
    query_timeout_ms: int
    providers: list[DocumentProviderHealthResponse] = Field(default_factory=list)
    ocr: DocumentOcrStatusResponse
    vision: DocumentVisionStatusResponse
    embedding: DocumentModelStatusResponse
    rerank: DocumentRerankStatusResponse
    vector_index: DocumentVectorIndexStatusResponse
    keyword_index: DocumentKeywordIndexStatusResponse
    chunking: DocumentChunkingStatusResponse


__all__ = ["AdminDocumentProcessingResponse"]
