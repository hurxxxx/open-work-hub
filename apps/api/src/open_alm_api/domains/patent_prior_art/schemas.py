from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


PatentPriorArtScopeSource = Literal["user", "input_derived"]
PatentPriorArtJobStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
]
PatentPriorArtFailureCode = Literal[
    "access_revoked",
    "pipeline_failed",
    "provider_timeout",
    "worker_lost",
]
PatentPriorArtQueryFailureCode = Literal[
    "provider_timeout",
    "provider_unavailable",
]
PatentPriorArtRelevanceBand = Literal["high", "medium", "low", "unrated"]
PatentPriorArtArtifactKind = Literal["result_json", "report_markdown"]
PatentPriorArtReportFormat = Literal[
    "html",
    "pdf",
    "docx",
    "summary_pdf",
    "summary_docx",
]
PatentPriorArtShortValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]
PatentPriorArtIdentifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]
PatentPriorArtJurisdiction = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=8),
]
PatentPriorArtIdempotencyKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=8, max_length=80),
]


class PatentPriorArtCategoryOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label_key: str
    fallback_label: str
    description_key: str | None = None
    fallback_description: str | None = None
    selected_by_default: bool = False


class PatentPriorArtJurisdictionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label_key: str
    fallback_label: str
    selected_by_default: bool = False


class PatentPriorArtConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_invention_chars: int
    max_invention_chars: int
    max_plan_values_per_field: int
    max_plan_value_chars: int
    max_upload_bytes: int
    allowed_upload_extensions: list[str]
    categories: list[PatentPriorArtCategoryOption]
    jurisdictions: list[PatentPriorArtJurisdictionOption]
    report_formats: list[PatentPriorArtReportFormat]
    visual_extraction_available: bool = False


class PatentPriorArtSearchValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[PatentPriorArtShortValue] = Field(default_factory=list, max_length=30)
    source: PatentPriorArtScopeSource


class PatentPriorArtSearchPlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_ids: PatentPriorArtSearchValues
    keywords_ko: PatentPriorArtSearchValues
    keywords_en: PatentPriorArtSearchValues
    ipc_codes: PatentPriorArtSearchValues
    cpc_codes: PatentPriorArtSearchValues
    applicants: PatentPriorArtSearchValues
    excluded_terms: PatentPriorArtSearchValues
    display_query: str = Field(default="", max_length=8_000)


class PatentPriorArtSourceQueryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_label: str
    jurisdiction: str
    query_text: str
    result_count: int | None = None


class PatentPriorArtQueryPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invention_text: str = Field(min_length=30, max_length=200_000)
    category_ids: list[PatentPriorArtIdentifier] = Field(default_factory=list, max_length=10)
    jurisdictions: list[PatentPriorArtJurisdiction] = Field(
        default_factory=lambda: ["KR"], max_length=10
    )


class PatentPriorArtQueryPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technology_summary: str
    plan: PatentPriorArtSearchPlanDraft
    source_queries: list[PatentPriorArtSourceQueryOut] = Field(default_factory=list)


class PatentPriorArtFileParseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    mime_type: str
    extracted_text: str
    character_count: int
    embedded_object_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class PatentPriorArtJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=200)
    idempotency_key: PatentPriorArtIdempotencyKey
    invention_text: str = Field(min_length=30, max_length=200_000)
    technology_summary: str = Field(default="", max_length=1_200)
    jurisdictions: list[PatentPriorArtJurisdiction] = Field(
        default_factory=lambda: ["KR"], max_length=10
    )
    search_plan: PatentPriorArtSearchPlanDraft


class PatentPriorArtJobOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    status: PatentPriorArtJobStatus
    title: str
    progress_percent: int = Field(default=0, ge=0, le=100)
    stage: str = ""
    status_message: str | None = None
    failure_code: PatentPriorArtFailureCode | None = None
    execution_attempts: int = Field(default=0, ge=0)
    automatic_restart_count: int = Field(default=0, ge=0, le=1)
    next_attempt_at: datetime | None = None
    can_cancel: bool = False
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class PatentPriorArtJobListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PatentPriorArtJobOut] = Field(default_factory=list)
    total: int = 0


class PatentPriorArtCandidateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    publication_number: str
    title: str
    assignees: list[str] = Field(default_factory=list)
    jurisdiction: str
    filing_date: str | None = None
    publication_date: str | None = None
    classification_codes: list[str] = Field(default_factory=list)
    abstract: str | None = None
    summary: str | None = None
    relevance_band: PatentPriorArtRelevanceBand = "unrated"
    match_reasons: list[str] = Field(default_factory=list)
    external_url: str | None = None


class PatentPriorArtExecutedQueryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_label: str
    jurisdiction: str
    query_text: str
    result_count: int | None = None
    status: Literal["succeeded", "failed"]
    failure_code: PatentPriorArtQueryFailureCode | None = None


class PatentPriorArtArtifactOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: PatentPriorArtArtifactKind
    filename: str
    mime_type: str
    size_bytes: int = Field(ge=0)


class PatentPriorArtResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: PatentPriorArtJobOut
    candidate_count: int
    candidates: list[PatentPriorArtCandidateOut] = Field(default_factory=list)
    partial: bool = False
    executed_queries: list[PatentPriorArtExecutedQueryOut] = Field(default_factory=list)
    report_markdown: str = ""
    artifacts: list[PatentPriorArtArtifactOut] = Field(default_factory=list)


class PatentPriorArtDeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    deleted: bool
