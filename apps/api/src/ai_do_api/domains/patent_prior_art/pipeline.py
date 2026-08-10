"""Generic patent prior-art search, ranking, assessment, and report pipeline."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy.orm import Session

from ai_do_api.core.llm import LlmTaskContext
from ai_do_api.domains.ai.gateway import (
    LlmWorkloadContext,
    execute_llm,
)
from ai_do_api.domains.patent.kipris import (
    KiprisClient,
    KiprisError,
    KiprisRetryableError,
    KiprisTimeoutError,
    PatentSearchResult,
    get_kipris_client,
)
from ai_do_api.domains.patent_prior_art import (
    PATENT_PRIOR_ART_APP_ID,
    PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_TASK_KIND,
    PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_WORKLOAD_ID,
)
from ai_do_api.domains.patent_prior_art.planning import (
    CompiledPatentQuery,
    build_candidate_ranking_query,
    compile_provider_queries,
    normalise_jurisdictions,
    preview_patent_prior_art_search,
)
from ai_do_api.domains.patent_prior_art.reporting import (
    build_result_payload,
    render_markdown_report,
    serialise_result_payload,
)
from ai_do_api.domains.patent_prior_art.schemas import (
    PatentPriorArtCandidateOut,
    PatentPriorArtExecutedQueryOut,
    PatentPriorArtSearchPlanDraft,
)
from ai_do_api.domains.rag.sparse_terms import tokenize_sparse_terms
from ai_do_api.domains.retrieval.candidate_ranking import (
    MAX_CANDIDATES as PLATFORM_MAX_CANDIDATES,
)
from ai_do_api.domains.retrieval.candidate_ranking import (
    CandidateDocument,
    CandidateRankingRequest,
    CandidateRankingService,
    get_candidate_ranking_service,
)


logger = logging.getLogger(__name__)

MAX_PROVIDER_PAGES_PER_QUERY = 2
MAX_PIPELINE_CANDIDATES = min(100, PLATFORM_MAX_CANDIDATES)
MAX_ASSESSMENT_BATCH_SIZE = 10
MAX_ASSESSMENT_INPUT_CHARS = 8_000
MAX_ASSESSMENT_ABSTRACT_CHARS = 3_000
MAX_SEARCH_STAGE_SECONDS = 10 * 60
_ASSESSMENT_MAX_TOKENS = 2_500
_ASSESSMENT_TIMEOUT_SECONDS = 120.0
_SAFE_REASON_COUNT = 4
_LEGAL_CONCLUSION_RE = re.compile(
    r"(?:특허.{0,12}(?:유효|무효)|침해|비침해|자유\s*실시|권리\s*회피|"
    r"freedom[- ]to[- ]operate|non[- ]?infring|infring(?:e|ement)|"
    r"patent\s+(?:is\s+)?(?:valid|invalid)|safe\s+to\s+launch|clearance|invalidity)",
    re.I,
)

ProgressCallback = Callable[[int, str], None]
CancelCallback = Callable[[], bool]
_AssessmentText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_200),
]


class PatentPriorArtPipelineCancelled(RuntimeError):
    """Raised when the job-local cancellation callback requests a stop."""


class PatentPriorArtTransientError(RuntimeError):
    """A safely retryable provider timeout; other failures are not translated."""


class _CandidateAssessmentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=128)
    relevance_band: Literal["high", "medium", "low"]
    summary: _AssessmentText
    match_reasons: list[_AssessmentText] = Field(min_length=1, max_length=_SAFE_REASON_COUNT)


class _CandidateAssessmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[_CandidateAssessmentItem] = Field(max_length=MAX_ASSESSMENT_BATCH_SIZE)


class _InvalidCandidateAssessmentResponse(ValueError):
    """The registered workload ran, but its response violated the app schema."""


@dataclass(frozen=True, slots=True)
class PatentPriorArtRunResult:
    technology_summary: str
    search_plan: PatentPriorArtSearchPlanDraft
    executed_queries: tuple[PatentPriorArtExecutedQueryOut, ...]
    candidates: tuple[PatentPriorArtCandidateOut, ...]
    ranking_profile: Mapping[str, object]
    result_payload: Mapping[str, object]
    result_json: str
    report_markdown: str


@dataclass(frozen=True, slots=True)
class _RankedPatent:
    rank: int
    result: PatentSearchResult


def run_patent_prior_art(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    title: str,
    invention_text: str,
    jurisdictions: Sequence[str],
    search_plan: PatentPriorArtSearchPlanDraft,
    technology_summary: str = "",
    max_pages_per_query: int = 1,
    max_candidates: int = 50,
    progress_callback: ProgressCallback | None = None,
    cancel_callback: CancelCallback | None = None,
    kipris_client: KiprisClient | None = None,
    ranking_service: CandidateRankingService | None = None,
) -> PatentPriorArtRunResult:
    """Run the bounded app pipeline using only platform-owned provider seams."""

    if not 1 <= max_pages_per_query <= MAX_PROVIDER_PAGES_PER_QUERY:
        raise ValueError(
            f"max_pages_per_query must be between 1 and {MAX_PROVIDER_PAGES_PER_QUERY}"
        )
    if not 1 <= max_candidates <= MAX_PIPELINE_CANDIDATES:
        raise ValueError(f"max_candidates must be between 1 and {MAX_PIPELINE_CANDIDATES}")
    bounded_invention = invention_text.strip()
    if len(bounded_invention) < 30:
        raise ValueError("invention_text must contain at least 30 characters")

    ordered_jurisdictions = normalise_jurisdictions(jurisdictions)
    compiled_queries = compile_provider_queries(search_plan, ordered_jurisdictions)
    summary = (technology_summary.strip() or bounded_invention[:1_200]).strip()
    _progress(progress_callback, 5, "validated")
    _raise_if_cancelled(cancel_callback)

    provider = kipris_client or get_kipris_client()
    provider_results, executed_queries = _execute_provider_queries(
        provider,
        compiled_queries=compiled_queries,
        max_pages_per_query=max_pages_per_query,
        max_candidates=max_candidates,
        progress_callback=progress_callback,
        cancel_callback=cancel_callback,
        deadline_monotonic=time.monotonic() + MAX_SEARCH_STAGE_SECONDS,
    )

    _raise_if_cancelled(cancel_callback)
    _progress(progress_callback, 58, "ranking")
    ranker = ranking_service or get_candidate_ranking_service()
    ranked, ranking_profile = _rank_candidates(
        ranker,
        invention_text=bounded_invention,
        technology_summary=summary,
        search_plan=search_plan,
        candidates=provider_results,
        max_candidates=max_candidates,
    )

    _raise_if_cancelled(cancel_callback)
    _progress(progress_callback, 72, "assessment")
    public_candidates = _assess_ranked_candidates(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        invention_text=bounded_invention,
        ranked=ranked,
        cancel_callback=cancel_callback,
    )

    _raise_if_cancelled(cancel_callback)
    _progress(progress_callback, 92, "reporting")
    payload = build_result_payload(
        title=title,
        invention_text=bounded_invention,
        technology_summary=summary,
        jurisdictions=ordered_jurisdictions,
        search_plan=search_plan,
        executed_queries=executed_queries,
        candidates=public_candidates,
        ranking_profile=ranking_profile,
    )
    result_json = serialise_result_payload(payload)
    report_markdown = render_markdown_report(payload)
    _progress(progress_callback, 100, "completed")
    return PatentPriorArtRunResult(
        technology_summary=summary,
        search_plan=search_plan,
        executed_queries=executed_queries,
        candidates=public_candidates,
        ranking_profile=ranking_profile,
        result_payload=payload,
        result_json=result_json,
        report_markdown=report_markdown,
    )


def _execute_provider_queries(
    client: KiprisClient,
    *,
    compiled_queries: Sequence[CompiledPatentQuery],
    max_pages_per_query: int,
    max_candidates: int,
    progress_callback: ProgressCallback | None,
    cancel_callback: CancelCallback | None,
    deadline_monotonic: float,
) -> tuple[tuple[PatentSearchResult, ...], tuple[PatentPriorArtExecutedQueryOut, ...]]:
    unique_results: dict[str, PatentSearchResult] = {}
    executed: list[PatentPriorArtExecutedQueryOut] = []
    query_count = len(compiled_queries)
    succeeded_count = 0
    errored_count = 0
    last_error: KiprisError | None = None
    last_hard_error: KiprisError | None = None
    for query_index, compiled in enumerate(compiled_queries, start=1):
        _raise_if_cancelled(cancel_callback)
        if time.monotonic() >= deadline_monotonic:
            deadline_error = KiprisTimeoutError(
                "KIPRIS search stage exceeded its time limit"
            )
            last_error = deadline_error
            for remaining in compiled_queries[query_index - 1 :]:
                executed.append(
                    _executed_query(
                        remaining,
                        result_count=None,
                        status="failed",
                        failure_code="provider_timeout",
                    )
                )
                errored_count += 1
            break
        total_count: int | None = None
        remaining_slots = max_candidates - len(unique_results)
        remaining_queries = query_count - query_index + 1
        query_quota = max(1, remaining_slots // remaining_queries) if remaining_slots > 0 else 0
        page_size = max(1, min(30, query_quota))
        added_for_query = 0
        query_failed = False
        for page_number in range(1, max_pages_per_query + 1):
            try:
                if isinstance(client, KiprisClient):
                    page = client.search(
                        compiled.to_criteria(),
                        page=page_number,
                        page_size=page_size,
                        deadline_monotonic=deadline_monotonic,
                    )
                else:
                    page = client.search(
                        compiled.to_criteria(),
                        page=page_number,
                        page_size=page_size,
                    )
            except KiprisError as error:
                # One source/jurisdiction query failing must not sink the whole
                # multi-source search. Record it and keep going; only a total
                # provider failure (every query failed) aborts the job below.
                last_error = error
                if not _is_retryable_provider_error(error):
                    last_hard_error = error
                logger.warning(
                    "patent prior-art query %s (%s) failed with code %s",
                    compiled.source_id,
                    compiled.jurisdiction,
                    _safe_query_failure_code(error),
                )
                query_failed = True
                break
            _raise_if_cancelled(cancel_callback)
            total_count = page.total_count
            for result in page.results:
                if len(unique_results) >= max_candidates or added_for_query >= query_quota:
                    break
                key = _dedupe_key(result)
                if key not in unique_results:
                    unique_results[key] = result
                    added_for_query += 1
            if (
                not page.has_next
                or len(unique_results) >= max_candidates
                or added_for_query >= query_quota
            ):
                break
            _raise_if_cancelled(cancel_callback)
        if query_failed:
            errored_count += 1
            executed.append(
                _executed_query(
                    compiled,
                    result_count=None,
                    status="failed",
                    failure_code=_safe_query_failure_code(last_error),
                )
            )
        else:
            succeeded_count += 1
            executed.append(
                _executed_query(
                    compiled,
                    result_count=total_count,
                    status="succeeded",
                    failure_code=None,
                )
            )
        percent = 10 + int((query_index / query_count) * 43)
        _progress(progress_callback, percent, "searching")
    if succeeded_count == 0 and errored_count > 0:
        # Retry only when every provider failure was temporary. A mixed failure
        # must preserve its hard error so the worker neither retries it nor records
        # a misleading provider_timeout terminal code.
        if last_hard_error is None:
            raise PatentPriorArtTransientError("patent search provider timed out") from last_error
        raise last_hard_error
    return tuple(unique_results.values()), tuple(executed)


def _executed_query(
    compiled: CompiledPatentQuery,
    *,
    result_count: int | None,
    status: Literal["succeeded", "failed"],
    failure_code: Literal["provider_timeout", "provider_unavailable"] | None,
) -> PatentPriorArtExecutedQueryOut:
    preview = compiled.to_preview(result_count=result_count)
    return PatentPriorArtExecutedQueryOut(
        **preview.model_dump(mode="json"),
        status=status,
        failure_code=failure_code,
    )


def _rank_candidates(
    service: CandidateRankingService,
    *,
    invention_text: str,
    technology_summary: str,
    search_plan: PatentPriorArtSearchPlanDraft,
    candidates: Sequence[PatentSearchResult],
    max_candidates: int,
) -> tuple[tuple[_RankedPatent, ...], dict[str, object]]:
    if not candidates:
        return (), {
            "input_candidate_count": 0,
            "returned_candidate_count": 0,
            "methods": ("bm25",),
            "degraded": False,
            "degraded_stages": (),
        }
    by_id: dict[str, PatentSearchResult] = {}
    documents: list[CandidateDocument] = []
    for result in candidates[:MAX_PIPELINE_CANDIDATES]:
        candidate_id = _dedupe_key(result)
        by_id[candidate_id] = result
        technical_body = "\n".join(
            part
            for part in (
                result.abstract,
                " ".join(result.ipc_codes),
            )
            if part.strip()
        )
        documents.append(
            CandidateDocument(
                candidate_id=candidate_id,
                title=result.title,
                text=technical_body or result.title or candidate_id,
                metadata={"jurisdiction": result.jurisdiction},
            )
        )
    ranking_query = build_candidate_ranking_query(
        search_plan,
        technology_summary=technology_summary,
        invention_text=invention_text,
    )
    ranking = service.rank(
        CandidateRankingRequest(
            query=ranking_query,
            candidates=documents,
            top_k=min(max_candidates, len(documents)),
            enable_semantic=True,
            enable_rerank=True,
        )
    )
    ranked = tuple(
        _RankedPatent(rank=item.rank, result=by_id[item.candidate.candidate_id])
        for item in ranking.candidates
    )
    return ranked, _public_ranking_profile(asdict(ranking.profile))


def _assess_ranked_candidates(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    invention_text: str,
    ranked: Sequence[_RankedPatent],
    cancel_callback: CancelCallback | None,
) -> tuple[PatentPriorArtCandidateOut, ...]:
    public: list[PatentPriorArtCandidateOut] = []
    for offset in range(0, len(ranked), MAX_ASSESSMENT_BATCH_SIZE):
        _raise_if_cancelled(cancel_callback)
        batch = tuple(ranked[offset : offset + MAX_ASSESSMENT_BATCH_SIZE])
        try:
            assessments = _run_assessment_workload(
                db,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                invention_text=invention_text,
                batch=batch,
            )
        except _InvalidCandidateAssessmentResponse:
            assessments = {
                _dedupe_key(item.result): _fallback_assessment(invention_text, item.result)
                for item in batch
            }
        _raise_if_cancelled(cancel_callback)
        for item in batch:
            result = item.result
            assessment = assessments[_dedupe_key(result)]
            public.append(
                PatentPriorArtCandidateOut(
                    rank=item.rank,
                    publication_number=(
                        result.publication_number
                        or result.canonical_number
                        or result.application_number
                    ),
                    title=result.title,
                    assignees=list(result.applicants),
                    jurisdiction=result.jurisdiction,
                    filing_date=result.filing_date.isoformat() if result.filing_date else None,
                    publication_date=(
                        result.publication_date.isoformat() if result.publication_date else None
                    ),
                    classification_codes=list(result.ipc_codes),
                    abstract=result.abstract or None,
                    summary=assessment.summary,
                    relevance_band=assessment.relevance_band,
                    match_reasons=list(assessment.match_reasons),
                    external_url=result.external_url or None,
                )
            )
    return tuple(public)


def _run_assessment_workload(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    invention_text: str,
    batch: Sequence[_RankedPatent],
) -> dict[str, _CandidateAssessmentItem]:
    candidate_payload = [
        {
            "candidate_id": _dedupe_key(item.result),
            "title": item.result.title[:500],
            "abstract": item.result.abstract[:MAX_ASSESSMENT_ABSTRACT_CHARS],
            "classification_codes": list(item.result.ipc_codes[:20]),
        }
        for item in batch
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "Assess technical relevance between supplied invention text and patent "
                "candidates. Use only titles, abstracts, and classifications. Return one strict "
                "JSON object matching the schema. Do not make legal validity, infringement, "
                "freedom-to-operate, or clearance conclusions. Do not use applicant identity."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "Assign a technical relevance band and concise evidence reasons.",
                    "schema": {
                        "items": [
                            {
                                "candidate_id": "one supplied candidate_id",
                                "relevance_band": "high | medium | low",
                                "summary": "technical comparison only",
                                "match_reasons": ["specific shared feature or term"],
                            }
                        ]
                    },
                    "invention_text": invention_text[:MAX_ASSESSMENT_INPUT_CHARS],
                    "candidates": candidate_payload,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]
    task_context = LlmTaskContext(
        source="patent_prior_art",
        workspace_id=workspace_id,
        task_kind=PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_TASK_KIND,
        app_id=PATENT_PRIOR_ART_APP_ID,
        actor_user_id=actor_user_id,
        principal_kind="user",
        principal_id=actor_user_id,
    )
    completion = execute_llm(
        PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_WORKLOAD_ID,
        LlmWorkloadContext.from_task_context(task_context),
        db,
        messages=messages,
        temperature=0,
        max_tokens=_ASSESSMENT_MAX_TOKENS,
        reasoning_effort="none",
        timeout_seconds=_ASSESSMENT_TIMEOUT_SECONDS,
    ).completion
    try:
        response = _CandidateAssessmentResponse.model_validate(json.loads(completion.text.strip()))
    except (json.JSONDecodeError, ValidationError) as error:
        raise _InvalidCandidateAssessmentResponse(
            "candidate assessment workload returned an invalid response"
        ) from error
    expected_ids = {_dedupe_key(item.result) for item in batch}
    by_id: dict[str, _CandidateAssessmentItem] = {}
    for item in response.items:
        if item.candidate_id not in expected_ids or item.candidate_id in by_id:
            raise _InvalidCandidateAssessmentResponse(
                "candidate assessment returned an unknown or duplicate candidate_id"
            )
        if _LEGAL_CONCLUSION_RE.search(item.summary) or any(
            _LEGAL_CONCLUSION_RE.search(reason) for reason in item.match_reasons
        ):
            raise _InvalidCandidateAssessmentResponse(
                "candidate assessment returned a legal conclusion"
            )
        by_id[item.candidate_id] = item
    if set(by_id) != expected_ids:
        raise _InvalidCandidateAssessmentResponse(
            "candidate assessment did not return every supplied candidate_id"
        )
    return by_id


def _fallback_assessment(
    invention_text: str,
    result: PatentSearchResult,
) -> _CandidateAssessmentItem:
    invention_terms = set(tokenize_sparse_terms(invention_text[:MAX_ASSESSMENT_INPUT_CHARS]))
    candidate_terms = set(
        tokenize_sparse_terms(
            "\n".join((result.title, result.abstract, " ".join(result.ipc_codes)))
        )
    )
    overlap = sorted(invention_terms & candidate_terms, key=lambda value: (len(value), value))
    overlap_count = len(overlap)
    band: Literal["high", "medium", "low"]
    if overlap_count >= 5:
        band = "high"
    elif overlap_count >= 2:
        band = "medium"
    else:
        band = "low"
    if overlap:
        reasons = [f"공통 기술 용어: {', '.join(overlap[:8])}"]
    else:
        reasons = ["제목·초록에서 직접 일치하는 기술 용어가 제한적임"]
    return _CandidateAssessmentItem(
        candidate_id=_dedupe_key(result),
        relevance_band=band,
        summary=(
            f"제목·초록·분류 기준으로 입력 발명과 공통 기술 용어 {overlap_count}개를 "
            "확인한 자동 기술 검토 결과입니다."
        ),
        match_reasons=reasons,
    )


def _dedupe_key(result: PatentSearchResult) -> str:
    raw = (
        result.canonical_number
        or result.publication_number
        or result.application_number
        or result.provider_document_id
    )
    compact = re.sub(r"[^A-Z0-9]", "", raw.upper())
    if not compact:
        raise ValueError("patent provider result is missing a stable identifier")
    return compact[:128]


def _has_timeout_cause(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, httpx.TimeoutException):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _is_retryable_provider_error(error: BaseException) -> bool:
    return isinstance(error, KiprisRetryableError) or _has_timeout_cause(error)


def _safe_query_failure_code(
    error: BaseException | None,
) -> Literal["provider_timeout", "provider_unavailable"]:
    return (
        "provider_timeout"
        if error is not None and _is_retryable_provider_error(error)
        else "provider_unavailable"
    )


def _public_ranking_profile(profile: Mapping[str, object]) -> dict[str, object]:
    """Expose neutral method provenance without provider/model implementation IDs."""

    allowed_fields = (
        "input_candidate_count",
        "ranked_candidate_count",
        "returned_candidate_count",
        "requested_top_k",
        "applied_top_k",
        "candidate_limit",
        "candidate_limit_applied",
        "candidate_text_char_limit",
        "truncated_text_count",
        "query_char_limit",
        "query_truncated",
        "semantic_requested",
        "semantic_applied",
        "fusion_applied",
        "rerank_requested",
        "rerank_applied",
        "methods",
    )
    public = {field: profile[field] for field in allowed_fields if field in profile}
    raw_reasons = profile.get("degraded_reasons")
    if isinstance(raw_reasons, Sequence) and not isinstance(raw_reasons, (str, bytes)):
        stages = tuple(
            dict.fromkeys(
                str(reason).partition(":")[0]
                for reason in raw_reasons
                if str(reason).partition(":")[0] in {"semantic", "rerank"}
            )
        )
    else:
        stages = ()
    public["degraded"] = bool(stages)
    public["degraded_stages"] = stages
    return public


def _raise_if_cancelled(callback: CancelCallback | None) -> None:
    if callback is not None and callback():
        raise PatentPriorArtPipelineCancelled("patent prior-art job was cancelled")


def _progress(callback: ProgressCallback | None, percent: int, stage: str) -> None:
    if callback is not None:
        callback(percent, stage)


__all__ = [
    "MAX_PIPELINE_CANDIDATES",
    "MAX_PROVIDER_PAGES_PER_QUERY",
    "MAX_SEARCH_STAGE_SECONDS",
    "PatentPriorArtPipelineCancelled",
    "PatentPriorArtRunResult",
    "PatentPriorArtTransientError",
    "preview_patent_prior_art_search",
    "run_patent_prior_art",
]
