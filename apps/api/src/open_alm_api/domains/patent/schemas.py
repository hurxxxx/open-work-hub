"""Pydantic request/response models for the patent compose tool.

Shapes mirror the legacy Flask ``/api/patent/*`` JSON so the frontend port is
a 1:1 mapping. LLM-generated structures whose nesting varies (per-claim
breakdowns, claim↔spec mappings) are typed as ``dict`` to stay robust to model
output drift.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PatentChatMessage(BaseModel):
    role: str
    content: str


# ── AI 특허 검색 ────────────────────────────────────────────────────────────
class AiSearchRequest(BaseModel):
    query: str
    page: int = 1
    applicant_filter: str = ""


class PatentItem(BaseModel):
    app_no: str = ""
    reg_no: str = ""
    title: str = ""
    applicant: str = ""
    date: str = ""
    status: str = ""
    ipc: str = ""
    abstract: str = ""
    ai_tags: list[str] = Field(default_factory=list)
    relevance: int = 0


class TopApplicant(BaseModel):
    name: str
    count: int


class AiSearchResponse(BaseModel):
    results: list[PatentItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    search_query: str = ""
    main_keywords: list[str] = Field(default_factory=list)
    tech_summary: str = ""
    top_applicants: list[TopApplicant] = Field(default_factory=list)
    applicant_sample_size: int = 0
    applicant_filter: str = ""
    ai_summary: str = ""
    core_techs: list[str] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)


# ── 특허 조회 (번호 검색 / 상세) ────────────────────────────────────────────
class FetchRequest(BaseModel):
    patent_number: str


class FetchResponse(BaseModel):
    app_no: str = ""
    reg_no: str = ""
    open_no: str = ""
    pub_no: str = ""
    title: str = ""
    title_eng: str = ""
    applicant: str = ""
    date: str = ""
    status: str = ""
    ipc: str = ""
    abstract: str = ""
    claims: list[str] = Field(default_factory=list)
    description: str = ""
    reg_date: str = ""
    open_date: str = ""
    pub_date: str = ""
    final_disposal: str = ""
    warning: str = ""
    foreign: bool = False
    google_patents_url: str = ""
    claims_source: str = ""


# ── 해외 초록/청구항 한글 번역 (리포트 다운로드용) ──────────────────────────
# Name prefixed with "Patent" to avoid an OpenAPI component-name collision with
# writing_assistant's TranslateRequest (which would force path-derived names).
class PatentTranslateRequest(BaseModel):
    texts: list[str] = Field(default_factory=list)


class PatentTranslateResponse(BaseModel):
    translations: list[str] = Field(default_factory=list)


# ── 파일 첨부 → 텍스트 추출 ─────────────────────────────────────────────────
class ExtractResponse(BaseModel):
    filename: str = ""
    text: str = ""
    char_count: int = 0
    truncated: bool = False


# ── 검색식 생성 ─────────────────────────────────────────────────────────────
class SearchQueryRequest(BaseModel):
    technology_description: str


class KeywordGroup(BaseModel):
    element: str = ""
    description: str = ""
    keywords_kr: list[str] = Field(default_factory=list)
    keywords_en: list[str] = Field(default_factory=list)
    synonyms_kr: list[str] = Field(default_factory=list)
    synonyms_en: list[str] = Field(default_factory=list)


class SearchQueryResponse(BaseModel):
    tech_summary: str = ""
    ipc_codes: list[str] = Field(default_factory=list)
    keyword_groups: list[KeywordGroup] = Field(default_factory=list)
    search_formula: str = ""


# ── AI 보고서 / 출원 도우미 ─────────────────────────────────────────────────
class ReportRequest(BaseModel):
    content: str
    report_type: str = "invention-disclosure"
    patent_context: str = ""


class ReportResponse(BaseModel):
    result: str = ""
    report_type: str = ""
    label: str = ""


class FilingAssistRequest(BaseModel):
    invention: str
    mode: str = "review"


class FilingAssistResponse(BaseModel):
    result: str = ""


# ── 에이전트 / Brainy 채팅 ──────────────────────────────────────────────────
class AgentChatRequest(BaseModel):
    message: str
    context: str = ""
    history: list[PatentChatMessage] = Field(default_factory=list)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)


class AgentChatResponse(BaseModel):
    reply: str = ""
    conversation_id: str | None = None


class AskBrainyRequest(BaseModel):
    patent_context: str = ""
    messages: list[PatentChatMessage] = Field(default_factory=list)
    question: str
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)


class AskBrainyResponse(BaseModel):
    answer: str = ""
    conversation_id: str | None = None


# ── 청구항 분석 (상세 뷰) ───────────────────────────────────────────────────
class ClaimsExplainRequest(BaseModel):
    claims: list[str]
    abstract: str = ""
    title: str = ""


class ClaimsExplainResponse(BaseModel):
    summary: str = ""
    key_features: list[str] = Field(default_factory=list)
    technical_significance: str = ""
    per_claim: list[dict[str, Any]] = Field(default_factory=list)


class RightsScopeRequest(BaseModel):
    claims: list[str]
    title: str = ""


class RightsScopeResponse(BaseModel):
    overall_analysis: str = ""
    scope_breadth: str = ""
    key_elements: list[str] = Field(default_factory=list)
    per_claim: list[dict[str, Any]] = Field(default_factory=list)
    caution: str = ""


class DescriptionMappingRequest(BaseModel):
    claims: list[str]
    description: str = ""
    abstract: str = ""


class DescriptionMappingResponse(BaseModel):
    mappings: list[dict[str, Any]] = Field(default_factory=list)


class InfringeCheckRequest(BaseModel):
    claims: list[str]
    title: str = ""
    tech_description: str


class InfringeCheckResponse(BaseModel):
    overall_verdict: str = ""
    overall_summary: str = ""
    per_claim: list[dict[str, Any]] = Field(default_factory=list)
    caution: str = ""


# ── 원문 열람 URL ───────────────────────────────────────────────────────────
class PdfUrlRequest(BaseModel):
    app_no: str
    reg_no: str = ""


class PdfUrlResponse(BaseModel):
    pdf_url: str = ""
    kipris_url: str = ""
    type: str = ""
