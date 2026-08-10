from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LegacyIssueAnalysisIncompleteError(RuntimeError):
    """Analysis data is incomplete and must never be persisted as completed."""


class AnalysisInterpretation(BaseModel):
    """Small, domain-generic request contract produced by the first graph node."""

    model_config = ConfigDict(extra="ignore")

    needs_business_data: bool = True
    report_requested: bool = False
    needs_statistics: bool = False
    needs_semantic_evidence: bool = True
    needs_checklists: bool = False
    analysis_goal: str = Field(default="", max_length=600)
    scope_summary: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def _normalize_business_data_requirement(self) -> AnalysisInterpretation:
        if (
            self.needs_statistics
            or self.needs_semantic_evidence
            or self.needs_checklists
        ):
            self.needs_business_data = True
        return self


class AnalysisQueryResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query_id: str
    recipe_id: str | None = None
    sql: str
    params: dict[str, Any] = Field(default_factory=dict)
    recipe_arguments: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    duration_ms: int | None = None
    status: Literal["succeeded", "failed", "not_captured"] = "succeeded"
    error_code: str | None = None


class AnalysisEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    evidence_id: str
    source_kind: Literal[
        "legacy_issue",
        "attachment_text",
        "vehicle_checklist",
        "analysis_context",
    ]
    title: str
    excerpt: str = ""
    record_id: str | None = None
    revision_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisSourceRevision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    revision_id: str
    status: str | None = None
    module_key: str | None = None


class AnalysisDataBundle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query_results: list[AnalysisQueryResult] = Field(default_factory=list)
    evidence: list[AnalysisEvidence] = Field(default_factory=list)
    retrieval_backend_ids: list[str] = Field(default_factory=list)
    source_revisions: list[AnalysisSourceRevision] = Field(default_factory=list)
    source_snapshot_captured: bool = False
    limitations: list[str] = Field(default_factory=list)
    capability_limitations: list[str] = Field(default_factory=list)
    execution_warnings: list[str] = Field(default_factory=list)


def require_complete_analysis_data(data: AnalysisDataBundle) -> None:
    if data.limitations:
        raise LegacyIssueAnalysisIncompleteError(
            "legacy_issue_analysis_data_incomplete"
        )
    if (
        (
            any(result.status == "succeeded" for result in data.query_results)
            or bool(data.evidence)
        )
        and not data.source_snapshot_captured
        and not data.source_revisions
    ):
        raise LegacyIssueAnalysisIncompleteError(
            "legacy_issue_analysis_revision_snapshot_missing"
        )


class GroundingReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    grounded: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)
    invalid_citations: list[str] = Field(default_factory=list)
    unmet_requirements: list[str] = Field(default_factory=list)
    internal_commentary: list[str] = Field(default_factory=list)
    correction_instructions: list[str] = Field(default_factory=list)


class AnalysisGraphState(TypedDict):
    graph_run_id: str
    workspace_id: str
    requested_by_user_id: str
    conversation_id: str
    question: str
    recent_messages: list[dict[str, str]]
    interpretation: NotRequired[dict[str, Any]]
    query_results: NotRequired[list[dict[str, Any]]]
    evidence: NotRequired[list[dict[str, Any]]]
    checklist_evidence: NotRequired[list[dict[str, Any]]]
    report_outline: NotRequired[str]
    quantitative_analysis: NotRequired[str]
    evidence_analysis: NotRequired[str]
    checklist_analysis: NotRequired[str]
    draft_markdown: NotRequired[str]
    review: NotRequired[dict[str, Any]]
    final_markdown: NotRequired[str]
    artifact_id: NotRequired[str]
    validation_errors: NotRequired[list[str]]
    correction_attempted: NotRequired[bool]
    error_code: NotRequired[str]
    status: NotRequired[str]
    current_stage: NotRequired[str]
    progress_percent: NotRequired[int]


__all__ = [
    "AnalysisEvidence",
    "AnalysisDataBundle",
    "AnalysisGraphState",
    "AnalysisInterpretation",
    "AnalysisQueryResult",
    "AnalysisSourceRevision",
    "GroundingReview",
    "LegacyIssueAnalysisIncompleteError",
    "require_complete_analysis_data",
]
