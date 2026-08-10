"""Patent compose orchestration: KIPRIS search + LLM generation.

Each function performs the work of one legacy ``/api/patent/*`` route: build a
KIPRIS query and/or an LLM prompt, then shape the response.
"""

from __future__ import annotations

import hashlib
import time

from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.conversations import app_persistence
from ai_do_api.domains.conversations.app_scope_adapters import (
    PATENT_AGENT_SCOPE_REF,
    PATENT_BRAINY_SCOPE_REF,
)
from ai_do_api.domains.document_processing import UnsupportedDocumentType, extract_document
from ai_do_api.domains.patent import llm, prompts
from ai_do_api.domains.patent.kipris import (
    KiprisClient,
    KiprisError,
    KiprisNotConfiguredError,
    detect_foreign_country,
    get_kipris_client,
)
from ai_do_api.domains.patent.schemas import (
    AgentChatResponse,
    AiSearchResponse,
    AskBrainyResponse,
    ClaimsExplainResponse,
    DescriptionMappingResponse,
    ExtractResponse,
    FetchResponse,
    FilingAssistResponse,
    InfringeCheckResponse,
    KeywordGroup,
    PatentItem,
    PatentTranslateResponse,
    PdfUrlResponse,
    ReportResponse,
    RightsScopeResponse,
    SearchQueryResponse,
    TopApplicant,
)

# Extracted attachment text is fed into the report input, so cap it to the
# same order of magnitude the report prompt accepts.
_EXTRACT_MAX_CHARS = 50000

# Aggregate top applicants over a bounded number of pages (KIPRIS caps a page
# at 30 rows). The legacy tool parallelised up to 10 pages; v1 scans fewer
# sequentially to keep latency predictable.
_AGG_PAGE_SIZE = 30
_AGG_MAX_PAGES = 5
# Interactive Patent Compose requests run in FastAPI's synchronous worker pool.
# Keep their entire KIPRIS search/aggregation section within the legacy
# single-request bound instead of allowing every page and retry to reset it.
_KIPRIS_INTERACTIVE_SEARCH_TIMEOUT_SECONDS = 15.0


def _client() -> KiprisClient:
    try:
        return get_kipris_client()
    except KiprisNotConfiguredError:
        raise localized_http_exception(status_code=503, code="patent.kipris_not_configured")


def _claims_text(claims: list[str], *, limit: int = 15, max_chars: int = 10000) -> str:
    text = "\n".join(claims[:limit])
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[이하 생략]"
    return text


def ai_search(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    query: str,
    page: int,
    applicant_filter: str,
) -> AiSearchResponse:
    query = query.strip()
    if not query:
        raise localized_http_exception(status_code=400, code="patent.query_required")
    client = _client()

    # 1) Expand the idea/keywords into an optimised KIPRIS query.
    gemini_input = query[:8000]
    expanded = llm.generate_json(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.ai_search_expand_prompt(gemini_input),
        max_tokens=1024,
    )
    search_query = str(expanded.get("search_query") or "").strip()
    main_keywords = expanded.get("main_keywords") or []
    tech_summary = str(expanded.get("tech_summary") or "")

    if not search_query or len(search_query) > 200:
        if main_keywords:
            search_query = " ".join(str(k).strip() for k in main_keywords[:4] if k)
        else:
            search_query = query[:200]
    search_query = search_query.strip()[:200]
    if not search_query:
        raise localized_http_exception(status_code=400, code="patent.keyword_extract_failed")

    # 2) KIPRIS search (+ optional applicant filtering).
    kipris_deadline = time.monotonic() + _KIPRIS_INTERACTIVE_SEARCH_TIMEOUT_SECONDS
    try:
        if applicant_filter:
            scanned: list[dict[str, str]] = []
            for p in range(1, _AGG_MAX_PAGES + 1):
                items, _ = client.word_search(
                    search_query,
                    page=p,
                    num_rows=_AGG_PAGE_SIZE,
                    deadline_monotonic=kipris_deadline,
                )
                if not items:
                    break
                scanned.extend(items)
            af = applicant_filter.strip()
            prefix = af.split("|")[0]
            filtered = [
                r
                for r in scanned
                if af
                and (af in r.get("applicant", "") or r.get("applicant", "").startswith(prefix))
            ]
            total = len(filtered)
            start = (page - 1) * 15
            raw_results = filtered[start : start + 15]
        else:
            raw_results, total = client.word_search(
                search_query,
                page=page,
                num_rows=15,
                deadline_monotonic=kipris_deadline,
            )
    except KiprisError as error:
        raise localized_http_exception(
            status_code=502, code="patent.search_failed", error=str(error)
        ) from error

    # 3) Aggregate top applicants over a few pages.
    top_applicants: list[TopApplicant] = []
    applicant_sample_size = 0
    if not applicant_filter and total > 0:
        counts: dict[str, int] = {}
        max_pages = min(_AGG_MAX_PAGES, (total + _AGG_PAGE_SIZE - 1) // _AGG_PAGE_SIZE)
        try:
            for p in range(1, max_pages + 1):
                for name in client.applicant_names(
                    search_query,
                    page=p,
                    num_rows=_AGG_PAGE_SIZE,
                    deadline_monotonic=kipris_deadline,
                ):
                    counts[name] = counts.get(name, 0) + 1
                    applicant_sample_size += 1
        except KiprisError:
            counts = {}
            for r in raw_results:
                name = r.get("applicant", "").strip()
                if name:
                    counts[name] = counts.get(name, 0) + 1
                    applicant_sample_size += 1
        top_applicants = [
            TopApplicant(name=n, count=c)
            for n, c in sorted(counts.items(), key=lambda x: -x[1])[:10]
        ]

    # 4) AI summary + per-patent tags/relevance.
    results = [PatentItem(**r) for r in raw_results]
    ai_summary = ""
    core_techs: list[str] = []
    suggested_queries: list[str] = []
    if results:
        items_text = "\n".join(
            f"[{i + 1}] {r.title} | 출원인: {r.applicant} | 요약: {r.abstract[:100]}"
            for i, r in enumerate(results[:10])
        )
        summary = llm.generate_json(
            db,
            workspace_id=workspace.id,
            actor_user_id=user.id,
            prompt=prompts.ai_search_summary_prompt(query, items_text),
            max_tokens=2048,
        )
        ai_summary = str(summary.get("summary") or "")
        core_techs = summary.get("core_techs") or []
        suggested_queries = summary.get("suggested_queries") or []
        patent_tags = summary.get("patent_tags") or {}
        for i, r in enumerate(results[:10]):
            tag = patent_tags.get(str(i + 1), {}) if isinstance(patent_tags, dict) else {}
            r.ai_tags = tag.get("tags", []) if isinstance(tag, dict) else []
            r.relevance = tag.get("relevance", 0) if isinstance(tag, dict) else 0

    return AiSearchResponse(
        results=results,
        total=total,
        page=page,
        search_query=search_query,
        main_keywords=[str(k) for k in main_keywords],
        tech_summary=tech_summary,
        top_applicants=top_applicants,
        applicant_sample_size=applicant_sample_size,
        applicant_filter=applicant_filter,
        ai_summary=ai_summary,
        core_techs=core_techs,
        suggested_queries=suggested_queries,
    )


def fetch_patent(patent_number: str) -> FetchResponse:
    patent_number = patent_number.strip()
    if not patent_number:
        raise localized_http_exception(status_code=400, code="patent.number_required")
    client = _client()

    # Foreign numbers (EP/US/CN/JP/WO) go to the KIPRIS foreign service, not the
    # Korea-only DB (which would mis-match on stray digits).
    foreign = detect_foreign_country(patent_number)
    if foreign:
        try:
            result = client.fetch_foreign_full(patent_number, foreign)
        except KiprisError as error:
            raise localized_http_exception(
                status_code=502, code="patent.fetch_failed", error=str(error)
            ) from error
        if result.get("error"):
            raise localized_http_exception(
                status_code=422,
                code="patent.foreign_not_found",
                country=foreign,
                url=result.get("google_patents_url", ""),
            )
        return FetchResponse(**result)

    try:
        result = client.fetch_full(patent_number)
    except KiprisError as error:
        raise localized_http_exception(
            status_code=502, code="patent.fetch_failed", error=str(error)
        ) from error
    if not result:
        raise localized_http_exception(
            status_code=404, code="patent.not_found", number=patent_number
        )
    return FetchResponse(**result)


# Translate in small batches so long claim sets don't blow the output token
# budget; a truncated batch leaves its items untranslated rather than failing.
_TRANSLATE_CHUNK = 6

# Per-request guardrails on this LLM-backed endpoint: cap how much external-LLM
# work a single authenticated request can trigger (item count / per-item length /
# total characters). A real patent's abstract + claims stays well under these.
_TRANSLATE_MAX_ITEMS = 100
_TRANSLATE_MAX_ITEM_CHARS = 10_000
_TRANSLATE_MAX_TOTAL_CHARS = 200_000


def translate_texts(
    db: Session, *, workspace: Workspace, user: User, texts: list[str]
) -> PatentTranslateResponse:
    """Translate foreign abstract/claims (English) to Korean for the HTML report.
    Input order is preserved; empty entries pass through untouched."""
    total_chars = sum(len(str(t or "")) for t in texts)
    if (
        len(texts) > _TRANSLATE_MAX_ITEMS
        or total_chars > _TRANSLATE_MAX_TOTAL_CHARS
        or any(len(str(t or "")) > _TRANSLATE_MAX_ITEM_CHARS for t in texts)
    ):
        raise localized_http_exception(status_code=413, code="patent.translate_input_too_large")

    translations = [str(t or "") for t in texts]
    targets = [(i, str(t).strip()) for i, t in enumerate(texts) if str(t or "").strip()]
    if not targets:
        return PatentTranslateResponse(translations=translations)

    for start in range(0, len(targets), _TRANSLATE_CHUNK):
        batch = targets[start : start + _TRANSLATE_CHUNK]
        numbered = "\n\n".join(f"[{i}]\n{text}" for i, text in batch)
        result = llm.generate_json(
            db,
            workspace_id=workspace.id,
            actor_user_id=user.id,
            prompt=prompts.translate_to_korean_prompt(numbered),
            max_tokens=8192,
        )
        if isinstance(result, dict):
            for i, _text in batch:
                value = result.get(str(i))
                if isinstance(value, str) and value.strip():
                    translations[i] = value.strip()
    return PatentTranslateResponse(translations=translations)


def generate_search_query(
    db: Session, *, workspace: Workspace, user: User, tech_description: str
) -> SearchQueryResponse:
    tech_description = tech_description.strip()
    if not tech_description:
        raise localized_http_exception(status_code=400, code="patent.tech_required")
    result = llm.generate_json(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.search_query_prompt(tech_description[:5000]),
        max_tokens=16384,
    )
    groups = [
        KeywordGroup(**g) for g in (result.get("keyword_groups") or []) if isinstance(g, dict)
    ]
    return SearchQueryResponse(
        tech_summary=str(result.get("tech_summary") or ""),
        ipc_codes=result.get("ipc_codes") or [],
        keyword_groups=groups,
        search_formula=str(result.get("search_formula") or ""),
    )


def generate_report(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    content: str,
    report_type: str,
    patent_context: str,
) -> ReportResponse:
    content = content.strip()
    if not content:
        raise localized_http_exception(status_code=400, code="patent.content_required")
    if report_type not in prompts.REPORT_PROMPTS:
        raise localized_http_exception(status_code=400, code="patent.invalid_report_type")
    if len(content) > 50000:
        content = content[:50000] + "\n[이하 생략]"
    result = llm.generate_text(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.report_prompt(report_type, content, patent_context.strip()),
        max_tokens=24576,
    )
    return ReportResponse(
        result=result,
        report_type=report_type,
        label=prompts.REPORT_LABELS.get(report_type, ""),
    )


def filing_assist(
    db: Session, *, workspace: Workspace, user: User, invention: str, mode: str
) -> FilingAssistResponse:
    invention = invention.strip()
    if not invention:
        raise localized_http_exception(status_code=400, code="patent.invention_required")
    if len(invention) > 50000:
        invention = invention[:50000] + "\n[이하 생략]"
    result = llm.generate_text(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.filing_assist_prompt(mode, invention),
        max_tokens=16384,
    )
    return FilingAssistResponse(result=result)


def agent_chat(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    message: str,
    context: str,
    history: list,
    conversation_id: str | None = None,
) -> AgentChatResponse:
    message = message.strip()
    if not message:
        raise localized_http_exception(status_code=400, code="patent.message_required")
    conversation = app_persistence.get_or_create_app_conversation(
        db,
        workspace=workspace,
        user=user,
        conversation_id=conversation_id,
        scope_ref=PATENT_AGENT_SCOPE_REF,
        scope_resource_id=_resource_id_from_text("search", context),
    )
    prior_turns = app_persistence.recent_turns_for_prompt(conversation, limit=6)
    history_text = _history_text_from_turns(prior_turns)
    if not history_text:
        history_text = "".join(
            f"{'사용자' if h.role == 'user' else 'AI'}: {h.content}\n" for h in history[-6:]
        )
    app_persistence.append_user_app_turn(
        db,
        conversation=conversation,
        content=message,
        meta={"kind": "patent_agent"},
    )
    result = llm.generate_text(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.agent_chat_prompt(message, context, history_text),
        max_tokens=2048,
        conversation_id=conversation.id,
    )
    app_persistence.append_assistant_app_turn(
        db,
        conversation=conversation,
        content=result,
        meta={"kind": "patent_agent", "response_status": "done"},
    )
    return AgentChatResponse(reply=result, conversation_id=conversation.id)


def ask_brainy(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    patent_context: str,
    messages: list,
    question: str,
    conversation_id: str | None = None,
) -> AskBrainyResponse:
    question = question.strip()
    if not question:
        raise localized_http_exception(status_code=400, code="patent.question_required")
    conversation = app_persistence.get_or_create_app_conversation(
        db,
        workspace=workspace,
        user=user,
        conversation_id=conversation_id,
        scope_ref=PATENT_BRAINY_SCOPE_REF,
        scope_resource_id=_resource_id_from_text("detail", patent_context),
    )
    prior_turns = app_persistence.recent_turns_for_prompt(conversation, limit=10)
    history = _bracketed_history_text_from_turns(prior_turns)
    if not history:
        history = "".join(
            f"[{'사용자' if m.role == 'user' else 'AI'}] {m.content}\n" for m in messages[-10:]
        )
    app_persistence.append_user_app_turn(
        db,
        conversation=conversation,
        content=question,
        meta={"kind": "patent_brainy"},
    )
    if len(patent_context) > 12000:
        patent_context = patent_context[:12000] + "\n[이하 생략]"
    result = llm.generate_text(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.ask_brainy_prompt(patent_context, history, question),
        max_tokens=8192,
        conversation_id=conversation.id,
    )
    app_persistence.append_assistant_app_turn(
        db,
        conversation=conversation,
        content=result,
        meta={"kind": "patent_brainy", "response_status": "done"},
    )
    return AskBrainyResponse(answer=result, conversation_id=conversation.id)


def _resource_id_from_text(prefix: str, text: str) -> str:
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest or 'default'}"


def _history_text_from_turns(turns) -> str:
    return "".join(
        f"{'사용자' if turn.role == 'user' else 'AI'}: {turn.content}\n" for turn in turns
    )


def _bracketed_history_text_from_turns(turns) -> str:
    return "".join(
        f"[{'사용자' if turn.role == 'user' else 'AI'}] {turn.content}\n" for turn in turns
    )


def claims_explain(
    db: Session, *, workspace: Workspace, user: User, claims: list[str], abstract: str, title: str
) -> ClaimsExplainResponse:
    if not claims:
        raise localized_http_exception(status_code=400, code="patent.claims_required")
    result = llm.generate_json(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.claims_explain_prompt(title, abstract, _claims_text(claims)),
        max_tokens=16384,
    )
    return ClaimsExplainResponse(
        summary=str(result.get("summary") or ""),
        key_features=result.get("key_features") or [],
        technical_significance=str(result.get("technical_significance") or ""),
        per_claim=result.get("per_claim") or [],
    )


def rights_scope(
    db: Session, *, workspace: Workspace, user: User, claims: list[str], title: str
) -> RightsScopeResponse:
    if not claims:
        raise localized_http_exception(status_code=400, code="patent.claims_required")
    result = llm.generate_json(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.rights_scope_prompt(title, _claims_text(claims)),
        max_tokens=16384,
    )
    return RightsScopeResponse(
        overall_analysis=str(result.get("overall_analysis") or ""),
        scope_breadth=str(result.get("scope_breadth") or ""),
        key_elements=result.get("key_elements") or [],
        per_claim=result.get("per_claim") or [],
        caution=str(result.get("caution") or ""),
    )


def description_mapping(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    claims: list[str],
    description: str,
    abstract: str,
) -> DescriptionMappingResponse:
    if not claims:
        raise localized_http_exception(status_code=400, code="patent.claims_required")
    if not description or description == "(발명의 설명 없음 - 초록 기반 분석)":
        description = abstract or "(발명의 설명 미제공)"
    claims_text = _claims_text(claims, limit=10, max_chars=8000)
    if len(description) > 12000:
        description = description[:12000] + "\n[이하 생략]"
    result = llm.generate_json(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.description_mapping_prompt(claims_text, description),
        max_tokens=16384,
    )
    return DescriptionMappingResponse(mappings=result.get("mappings") or [])


def infringe_check(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    claims: list[str],
    title: str,
    tech_description: str,
) -> InfringeCheckResponse:
    if not claims:
        raise localized_http_exception(status_code=400, code="patent.claims_required_fetch")
    tech = tech_description.strip()
    if not tech:
        raise localized_http_exception(status_code=400, code="patent.tech_description_required")
    if len(tech) > 6000:
        tech = tech[:6000] + "\n[이하 생략]"
    result = llm.generate_json(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        prompt=prompts.infringe_check_prompt(title, _claims_text(claims), tech),
        max_tokens=16384,
    )
    return InfringeCheckResponse(
        overall_verdict=str(result.get("overall_verdict") or ""),
        overall_summary=str(result.get("overall_summary") or ""),
        per_claim=result.get("per_claim") or [],
        caution=str(result.get("caution") or ""),
    )


def pdf_url(app_no: str, reg_no: str = "") -> PdfUrlResponse:
    app_no = app_no.strip()
    if not app_no:
        raise localized_http_exception(status_code=400, code="patent.app_no_required")
    client = _client()
    return PdfUrlResponse(**client.resolve_view_urls(app_no))


def extract_text(*, filename: str, mime_type: str, content: bytes) -> ExtractResponse:
    """Extract plain text from an uploaded PPTX/PDF/DOCX/XLSX attachment."""
    if not content:
        raise localized_http_exception(status_code=400, code="patent.empty_file")
    try:
        bundle = extract_document(
            document_id="upload",
            filename=filename or "upload",
            mime_type=mime_type or "application/octet-stream",
            content=content,
        )
    except UnsupportedDocumentType as error:
        raise localized_http_exception(status_code=415, code="patent.unsupported_file") from error
    text = "\n\n".join(block.text for block in bundle.evidence_blocks if block.text).strip()
    if not text:
        raise localized_http_exception(status_code=422, code="patent.extract_empty")
    truncated = len(text) > _EXTRACT_MAX_CHARS
    if truncated:
        text = text[:_EXTRACT_MAX_CHARS]
    return ExtractResponse(
        filename=filename or "",
        text=text,
        char_count=len(text),
        truncated=truncated,
    )
