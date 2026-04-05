from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field


class SearchDocumentsFilters(BaseModel):
    doc_type: list[str] = Field(default_factory=list)
    project: list[str] = Field(default_factory=list)
    department: list[str] = Field(default_factory=list)


class SearchDocumentsRequest(BaseModel):
    query: str = Field(..., min_length=1)
    filters: SearchDocumentsFilters = Field(default_factory=SearchDocumentsFilters)
    top_k: int = Field(default=10, ge=1, le=50)
    answer_mode: Literal["search-only", "grounded-answer"] = "search-only"


class SearchHit(BaseModel):
    document_id: str
    title: str
    summary: str
    source_type: str
    score: float
    updated: str
    project: str
    department: str
    acl: str
    owner: str
    page_reference: str
    citation: str
    next_actions: list[str] = Field(default_factory=list)


class GroundedAnswerCitation(BaseModel):
    document_id: str
    title: str
    page_reference: str
    quote: str


class GroundedAnswer(BaseModel):
    summary: str
    key_points: list[str]
    citations: list[GroundedAnswerCitation]
    next_actions: list[str]


class SearchDocumentsResponse(BaseModel):
    scenario_id: str = "documents-rag"
    query_profile: str = "bm25 + vector + rerank"
    filters_applied: SearchDocumentsFilters
    hits: list[SearchHit]
    next_actions: list[str]
    grounded_answer: GroundedAnswer | None = None


DOCUMENT_FIXTURES = [
    SearchHit(
        document_id="doc-spec-001",
        title="KX-21 Compressor Specification",
        summary="Pressure rating and seal material revisions indexed for the latest production line.",
        source_type="spec",
        score=0.0,
        updated="2026-04-02",
        project="Project A",
        department="Engineering",
        acl="engineering",
        owner="Engineering Standards Team",
        page_reference="pp. 4-7",
        citation=(
            "Revision R12 updates the approved seal material and tightens the pressure "
            "rating requirement for high-temperature operation."
        ),
        next_actions=["Open source document", "Attach citation blocks to draft"],
    ),
    SearchHit(
        document_id="doc-revision-002",
        title="Seal Material Change Notice",
        summary="Change notice with approval history and linked project references.",
        source_type="revision-note",
        score=0.0,
        updated="2026-03-28",
        project="Project A",
        department="Engineering",
        acl="engineering",
        owner="Component Review Board",
        page_reference="pp. 2-3",
        citation=(
            "Change notice confirms the seal material replacement and links the update "
            "to project-specific approval history."
        ),
        next_actions=["Review approval chain", "Compare against current BOM"],
    ),
    SearchHit(
        document_id="doc-memo-003",
        title="High Temperature Risk Review Memo",
        summary="Risk memo covering compressor temperature drift, mitigation, and approval notes.",
        source_type="memo",
        score=0.0,
        updated="2026-03-18",
        project="Project B",
        department="Quality",
        acl="quality",
        owner="Quality Assurance",
        page_reference="pp. 5-6",
        citation=(
            "Risk review flags seal wear acceleration above the approved operating band "
            "and recommends design verification before release."
        ),
        next_actions=["Check linked test reports", "Escalate unresolved risk items"],
    ),
    SearchHit(
        document_id="doc-guide-004",
        title="Supplier Quality Response Guide",
        summary="Guide for supplier-facing issue triage, containment, and response templates.",
        source_type="guide",
        score=0.0,
        updated="2026-02-26",
        project="Shared",
        department="Supplier Quality",
        acl="supplier-quality",
        owner="Supplier Quality Team",
        page_reference="pp. 8-10",
        citation=(
            "Containment responses must include the originating defect, impacted lots, "
            "and the validation plan before closure is approved."
        ),
        next_actions=["Reuse in supplier response draft", "Send to audit preparation queue"],
    ),
]


def _tokenize_query(query: str) -> list[str]:
    return [term for term in re.split(r"[^0-9a-z]+", query.lower()) if term]


def _matches_filters(hit: SearchHit, filters: SearchDocumentsFilters) -> bool:
    if filters.doc_type and hit.source_type not in filters.doc_type:
        return False
    if filters.project and hit.project not in filters.project:
        return False
    if filters.department and hit.department not in filters.department:
        return False
    return True


def _score_hit(hit: SearchHit, query: str, terms: list[str]) -> float:
    haystack = " ".join(
        [
            hit.title,
            hit.summary,
            hit.citation,
            hit.project,
            hit.department,
            hit.owner,
            hit.source_type,
        ]
    ).lower()
    matches = sum(1 for term in terms if term in haystack)
    phrase_bonus = 0.14 if query.lower() in haystack else 0.0
    term_score = matches / max(len(terms), 1)
    return round(min(0.99, 0.52 + (term_score * 0.32) + phrase_bonus), 2)


def _build_grounded_answer(query: str, hits: list[SearchHit]) -> GroundedAnswer | None:
    if not hits:
        return None

    selected_hits = hits[:2]
    return GroundedAnswer(
        summary=(
            f"'{query}'에 대해 가장 관련 높은 문서는 "
            f"{selected_hits[0].title}이며, 관련 변경 근거는 citation과 함께 확인할 수 있습니다."
        ),
        key_points=[
            f"{hit.title}: {hit.summary}"
            for hit in selected_hits
        ],
        citations=[
            GroundedAnswerCitation(
                document_id=hit.document_id,
                title=hit.title,
                page_reference=hit.page_reference,
                quote=hit.citation,
            )
            for hit in selected_hits
        ],
        next_actions=[
            "Open the highest-ranked document",
            "Move selected evidence into a draft workflow",
        ],
    )


router = APIRouter(prefix="/search", tags=["documents"])


@router.post("/documents", response_model=SearchDocumentsResponse)
def search_documents(payload: SearchDocumentsRequest) -> SearchDocumentsResponse:
    query = payload.query.strip()
    terms = _tokenize_query(query)

    hits = [
        hit.model_copy(update={"score": _score_hit(hit, query, terms)})
        for hit in DOCUMENT_FIXTURES
        if _matches_filters(hit, payload.filters)
        and (not terms or any(term in " ".join([hit.title, hit.summary, hit.citation]).lower() for term in terms))
    ]
    hits.sort(key=lambda hit: hit.score, reverse=True)
    hits = hits[: payload.top_k]

    next_actions = (
        ["Open top-ranked evidence", "Attach citation blocks", "Switch to grounded answer"]
        if hits
        else ["Broaden filters", "Try a narrower keyword phrase", "Review ACL scope"]
    )

    return SearchDocumentsResponse(
        filters_applied=payload.filters,
        hits=hits,
        next_actions=next_actions,
        grounded_answer=(
            _build_grounded_answer(query, hits)
            if payload.answer_mode == "grounded-answer"
            else None
        ),
    )
