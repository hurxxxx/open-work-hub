from __future__ import annotations

from ai_do_api.domains.patent_prior_art.models import (
    PatentPriorArtArtifact,
    PatentPriorArtCandidate,
    PatentPriorArtExecutedQuery,
    PatentPriorArtJob,
)
from ai_do_api.domains.patent_prior_art.schemas import (
    PatentPriorArtArtifactOut,
    PatentPriorArtCandidateOut,
    PatentPriorArtExecutedQueryOut,
    PatentPriorArtJobOut,
    PatentPriorArtResultResponse,
)

_SAFE_FAILURE_CODES = {
    "access_revoked",
    "pipeline_failed",
    "provider_timeout",
    "worker_lost",
}


def project_job(row: PatentPriorArtJob) -> PatentPriorArtJobOut:
    failure_code = row.failure_code if row.failure_code in _SAFE_FAILURE_CODES else None
    if row.status == "failed" and failure_code is None:
        failure_code = "pipeline_failed"
    return PatentPriorArtJobOut(
        id=row.id,
        status=row.status,
        title=row.title,
        progress_percent=row.progress_percent,
        stage=row.stage,
        status_message=None,
        failure_code=failure_code,
        execution_attempts=row.execution_attempts,
        automatic_restart_count=row.automatic_restart_count,
        next_attempt_at=row.next_attempt_at,
        can_cancel=(row.status in {"queued", "running"} and row.deletion_requested_at is None),
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


def project_candidate(row: PatentPriorArtCandidate) -> PatentPriorArtCandidateOut:
    return PatentPriorArtCandidateOut(
        rank=row.rank,
        publication_number=row.publication_number,
        title=row.title,
        assignees=list(row.assignees or []),
        jurisdiction=row.jurisdiction,
        filing_date=row.filing_date,
        publication_date=row.publication_date,
        classification_codes=list(row.classification_codes or []),
        abstract=row.abstract,
        summary=row.summary,
        relevance_band=row.relevance_band,
        match_reasons=list(row.match_reasons or []),
        external_url=row.external_url,
    )


def project_executed_query(
    row: PatentPriorArtExecutedQuery,
) -> PatentPriorArtExecutedQueryOut:
    failure_code = (
        row.failure_code
        if row.failure_code in {"provider_timeout", "provider_unavailable"}
        else None
    )
    return PatentPriorArtExecutedQueryOut(
        source_id=row.source_id,
        source_label=row.source_label,
        jurisdiction=row.jurisdiction,
        query_text=row.query_text,
        result_count=row.result_count,
        status=row.status,
        failure_code=failure_code,
    )


def project_artifact(row: PatentPriorArtArtifact) -> PatentPriorArtArtifactOut:
    return PatentPriorArtArtifactOut(
        id=row.id,
        kind=row.kind,
        filename=row.filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
    )


def project_result(
    row: PatentPriorArtJob,
    *,
    candidates: list[PatentPriorArtCandidate],
    executed_queries: list[PatentPriorArtExecutedQuery],
    artifacts: list[PatentPriorArtArtifact],
    report_markdown: str,
) -> PatentPriorArtResultResponse:
    return PatentPriorArtResultResponse(
        job=project_job(row),
        candidate_count=len(candidates),
        partial=any(query.status == "failed" for query in executed_queries),
        candidates=[project_candidate(candidate) for candidate in candidates],
        executed_queries=[
            project_executed_query(executed_query) for executed_query in executed_queries
        ],
        report_markdown=report_markdown,
        artifacts=[project_artifact(artifact) for artifact in artifacts],
    )


__all__ = [
    "project_artifact",
    "project_candidate",
    "project_executed_query",
    "project_job",
    "project_result",
]
