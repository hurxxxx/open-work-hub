"""Bounded, provider-neutral planning for patent prior-art searches."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Annotated, Literal, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)
from sqlalchemy.orm import Session

from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.domains.ai.gateway import (
    LlmWorkloadContext,
    execute_llm,
)
from open_alm_api.domains.patent.kipris import (
    SUPPORTED_PATENT_SEARCH_COUNTRIES,
    PatentSearchCriteria,
)
from open_alm_api.domains.patent_prior_art import (
    PATENT_PRIOR_ART_APP_ID,
    PATENT_PRIOR_ART_SEARCH_PLAN_TASK_KIND,
    PATENT_PRIOR_ART_SEARCH_PLAN_WORKLOAD_ID,
)
from open_alm_api.domains.patent_prior_art.catalog import get_category_definitions
from open_alm_api.domains.patent_prior_art.schemas import (
    PatentPriorArtQueryPreviewResponse,
    PatentPriorArtSearchPlanDraft,
    PatentPriorArtSearchValues,
    PatentPriorArtSourceQueryOut,
)


MAX_PLANNING_INPUT_CHARS = 16_000
MAX_TECHNOLOGY_SUMMARY_CHARS = 1_200
MAX_PLAN_VALUES = 30
# Classification codes must stay focused. Models otherwise enumerate a whole
# subclass (e.g. every H05B3/xx group), which adds noise without improving recall.
MAX_CLASSIFICATION_CODES = 8
# Up to three query kinds (category / broad technical / applicant-focused) across
# up to six jurisdictions, so applicant coverage is not starved when several
# countries and a category are selected together.
MAX_COMPILED_QUERIES = 18
_V1_MAX_COMPILED_QUERIES = 12
MAX_PROVIDER_QUERY_CHARS = 2_000
_PLANNING_TIMEOUT_SECONDS = 90.0
_PLANNING_MAX_TOKENS = 1_800
_MAX_EXPLICIT_APPLICANTS = MAX_PLAN_VALUES

_ShortPlanValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]
_CODE_RE = re.compile(r"\b([A-HY]\d{2}[A-Z](?:\s*\d{1,4}(?:/\d{1,6})?)?)\b", re.I)
# Applicant/competitor names appear behind an explicit label. Real request docs
# use several labels ("출원인", but also "차량 메이커 :", "공조 부품사 메이커 :",
# "경쟁사 :") and list the values on the same line, so we match the label anywhere
# (not only at line start) and read the run of values that follows each colon.
_APPLICANT_LABEL_RE = re.compile(
    r"(?:출원인|신청인|출원\s*기업|경쟁사|벤치마킹(?:\s*대상)?|메이커|maker|applicants?|assignees?)"
    r"\s*[:：]",
    re.I,
)
_APPLICANT_ITEM_BOUNDARY_RE = re.compile(r"\d+\s*[).]")
_APPLICANT_SPLIT_RE = re.compile(r"[,;|/、]")
_BRACKET_TOKEN_RE = re.compile(r"\[[^\]]*\]")
_LEADING_ENUM_RE = re.compile(r"^\s*\d+\s*[).]?\s*")
_TRAILING_APPLICANT_NOISE_RE = re.compile(r"\s*(?:등등|등|외|기타)\s*$")
_APPLICANT_LETTER_RE = re.compile(r"[A-Za-z가-힣]")
_APPLICANT_VALUE_WINDOW = 300
# Hangul, CJK ideographs, and Japanese kana — used to avoid quoting CJK phrases in
# provider queries (KIPRIS returns zero hits for quoted CJK phrases).
_CJK_RE = re.compile(r"[가-힣぀-ヿ㐀-䶿一-鿿]")
# Structural locators injected by our own extractor ("[Slide 3]", "[Slide 3 notes]",
# "[삽입 파일: Foo.pptx]"). They help a human read the attachment but are pure noise
# for planning — dropping them keeps them out of both the LLM and the fallback plan.
_STRUCTURAL_MARKER_RE = re.compile(
    r"\[(?:slide\s+\d+(?:\s+notes)?|삽입\s*파일\s*:[^\]]*)\]",
    re.I,
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
_WHITESPACE_RE = re.compile(r"\s+")
_LEGAL_CONCLUSION_RE = re.compile(
    r"(?:특허.{0,12}(?:유효|무효)|침해|비침해|자유\s*실시|권리\s*회피|"
    r"freedom[- ]to[- ]operate|non[- ]?infring|infring(?:e|ement)|"
    r"patent\s+(?:is\s+)?(?:valid|invalid)|safe\s+to\s+launch|clearance)",
    re.I,
)
_KOREAN_TOKEN_RE = re.compile(r"[가-힣]{2,20}")
_ENGLISH_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,30}")
_FALLBACK_STOPWORDS = frozenset(
    {
        "그리고",
        "또는",
        "위한",
        "대한",
        "관련",
        "기술",
        "발명",
        "장치",
        "방법",
        "system",
        "method",
        "device",
        "invention",
        "using",
        "with",
        "from",
        "that",
        "this",
    }
)


class _SearchPlanLlmResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technology_summary: str = Field(min_length=1, max_length=MAX_TECHNOLOGY_SUMMARY_CHARS)
    keywords_ko: list[_ShortPlanValue] = Field(default_factory=list, max_length=MAX_PLAN_VALUES)
    keywords_en: list[_ShortPlanValue] = Field(default_factory=list, max_length=MAX_PLAN_VALUES)
    ipc_codes: list[_ShortPlanValue] = Field(default_factory=list, max_length=MAX_PLAN_VALUES)
    cpc_codes: list[_ShortPlanValue] = Field(default_factory=list, max_length=MAX_PLAN_VALUES)
    excluded_terms: list[_ShortPlanValue] = Field(default_factory=list, max_length=MAX_PLAN_VALUES)

    @field_validator("technology_summary")
    @classmethod
    def _normalise_summary(cls, value: str) -> str:
        return _normalise_text(value)[:MAX_TECHNOLOGY_SUMMARY_CHARS]


class _InvalidSearchPlanResponse(ValueError):
    """The registered workload ran, but its response violated the app schema."""


@dataclass(frozen=True, slots=True)
class CompiledPatentQuery:
    """A validated provider call; ``display_query`` is deliberately absent."""

    source_id: str
    source_label: str
    jurisdiction: str
    query_text: str
    classification_codes: tuple[str, ...]
    applicants: tuple[str, ...]
    purpose: Literal["category_anchor", "technical", "applicant_focus"]

    def to_criteria(self) -> PatentSearchCriteria:
        return PatentSearchCriteria(
            query=self.query_text,
            countries=(self.jurisdiction,),
            classification_codes=self.classification_codes,
            applicants=self.applicants,
        )

    def to_preview(self, *, result_count: int | None = None) -> PatentPriorArtSourceQueryOut:
        return PatentPriorArtSourceQueryOut(
            source_id=self.source_id,
            source_label=self.source_label,
            jurisdiction=self.jurisdiction,
            query_text=self.query_text,
            result_count=result_count,
        )


def preview_patent_prior_art_search(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    invention_text: str,
    category_ids: Sequence[str],
    jurisdictions: Sequence[str],
    explicit_applicants: Sequence[str] = (),
) -> PatentPriorArtQueryPreviewResponse:
    """Create a typed preview through the registered planning workload.

    A deterministic technical plan is returned only when a completed workload
    response is invalid. Gateway, registry, route, and provider failures remain
    fail-closed. Applicant values are reconstructed only from explicit inputs
    after model parsing, so a model cannot invent or append company names.
    """

    technical_invention = _strip_structural_markers(strip_applicant_mentions(invention_text))
    bounded_invention = _normalise_text(technical_invention)
    if len(bounded_invention) < 30:
        raise ValueError("invention_text must contain at least 30 characters")
    bounded_invention = bounded_invention[:MAX_PLANNING_INPUT_CHARS]
    ordered_categories = tuple(
        definition.id for definition in get_category_definitions(list(category_ids))
    )
    ordered_jurisdictions = normalise_jurisdictions(jurisdictions)
    applicants, applicants_source = _collect_explicit_applicants(
        invention_text,
        explicit_applicants=explicit_applicants,
    )

    try:
        planned = _run_planning_workload(
            db,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            invention_text=bounded_invention,
            category_ids=ordered_categories,
            jurisdictions=ordered_jurisdictions,
        )
    except _InvalidSearchPlanResponse:
        planned = _fallback_plan_payload(bounded_invention)

    # We never auto-generate exclusions from the model. Small models kept dumping
    # competitor names (Korean and English, any case) and document-meta words into
    # excluded_terms, which turns into `NOT (...)` and filters the exact prior art
    # the user wants *out* while only shrinking recall. Prior-art search wants broad
    # recall, so exclusions are opt-in: the user adds them in the plan editor.
    excluded_values: list[str] = []

    plan = PatentPriorArtSearchPlanDraft(
        category_ids=PatentPriorArtSearchValues(values=list(ordered_categories), source="user"),
        keywords_ko=PatentPriorArtSearchValues(
            values=_normalise_plan_values(planned.keywords_ko),
            source="input_derived",
        ),
        keywords_en=PatentPriorArtSearchValues(
            values=_normalise_plan_values(planned.keywords_en),
            source="input_derived",
        ),
        ipc_codes=PatentPriorArtSearchValues(
            values=_normalise_classification_codes(planned.ipc_codes),
            source="input_derived",
        ),
        cpc_codes=PatentPriorArtSearchValues(
            values=_normalise_classification_codes(planned.cpc_codes),
            source="input_derived",
        ),
        applicants=PatentPriorArtSearchValues(
            values=list(applicants),
            source=applicants_source,
        ),
        excluded_terms=PatentPriorArtSearchValues(
            values=excluded_values,
            source="input_derived",
        ),
        display_query="",
    )
    compiled = compile_provider_queries(plan, ordered_jurisdictions)
    plan = plan.model_copy(update={"display_query": build_display_query(compiled)})
    return PatentPriorArtQueryPreviewResponse(
        technology_summary=planned.technology_summary,
        plan=plan,
        source_queries=[query.to_preview() for query in compiled],
    )


def compile_provider_queries(
    plan: PatentPriorArtSearchPlanDraft,
    jurisdictions: Sequence[str],
) -> tuple[CompiledPatentQuery, ...]:
    """Compile typed fields into bounded provider calls.

    Category-anchor calls always precede technical calls, and applicant-focused
    calls come last. Broad calls (category + technical) run *without* an applicant
    filter so the full prior-art field is retrieved; applicant-focused calls add
    dedicated coverage for the document/user applicants so competitor patents are
    surfaced too. Applicant identity is used only to *retrieve* extra candidates
    here — it never affects ranking. The free-form ``display_query`` field is
    never read here and therefore cannot affect a provider request.
    """

    ordered_jurisdictions = normalise_jurisdictions(jurisdictions)
    categories = get_category_definitions(plan.category_ids.values)
    applicants = tuple(
        _normalise_plan_values(plan.applicants.values, limit=_MAX_EXPLICIT_APPLICANTS)
    )
    ipc_codes = tuple(_normalise_classification_codes(plan.ipc_codes.values))
    cpc_codes = tuple(_normalise_classification_codes(plan.cpc_codes.values))
    excluded_terms = tuple(_normalise_plan_values(plan.excluded_terms.values))
    technical_terms = tuple(
        _normalise_plan_values((*plan.keywords_ko.values, *plan.keywords_en.values, *cpc_codes))
    )

    compiled: list[CompiledPatentQuery] = []
    for category in categories:
        category_query = _render_provider_query(category.query_terms, excluded_terms=())
        for jurisdiction in ordered_jurisdictions:
            compiled.append(
                CompiledPatentQuery(
                    source_id=f"category-{category.id}-{jurisdiction.lower()}",
                    source_label="KIPRIS",
                    jurisdiction=jurisdiction,
                    query_text=category_query,
                    classification_codes=category.classification_anchors,
                    applicants=(),
                    purpose="category_anchor",
                )
            )

    broad_terms = technical_terms or ipc_codes
    if broad_terms:
        technical_query = _render_provider_query(broad_terms, excluded_terms=excluded_terms)
        for jurisdiction in ordered_jurisdictions:
            compiled.append(
                CompiledPatentQuery(
                    source_id=f"technical-{jurisdiction.lower()}",
                    source_label="KIPRIS",
                    jurisdiction=jurisdiction,
                    query_text=technical_query,
                    classification_codes=ipc_codes,
                    applicants=(),
                    purpose="technical",
                )
            )

    if applicants:
        focus_terms = technical_terms or ipc_codes or applicants
        focus_query = _render_provider_query(focus_terms, excluded_terms=excluded_terms)
        # Additive only: never displace the guaranteed broad coverage above.
        remaining = max(0, MAX_COMPILED_QUERIES - len(compiled))
        for jurisdiction in ordered_jurisdictions[:remaining]:
            compiled.append(
                CompiledPatentQuery(
                    source_id=f"applicant-{jurisdiction.lower()}",
                    source_label="KIPRIS",
                    jurisdiction=jurisdiction,
                    query_text=focus_query,
                    classification_codes=ipc_codes,
                    applicants=applicants,
                    purpose="applicant_focus",
                )
            )

    if not compiled:
        raise ValueError(
            "search plan must include a category, keyword, classification, or applicant"
        )
    if len(compiled) > MAX_COMPILED_QUERIES:
        raise ValueError(f"compiled search plan exceeds {MAX_COMPILED_QUERIES} provider queries")
    return tuple(compiled)


def build_display_query(compiled: Sequence[CompiledPatentQuery]) -> str:
    """Human-readable search expression.

    Each jurisdiction reuses the same ``query_text`` (only the provider country
    param differs), so the raw join repeats every expression once per country.
    We de-duplicate, preserving order, to show each distinct expression once.
    """

    unique = list(dict.fromkeys(query.query_text for query in compiled))
    return "\n".join(unique)[:8_000]


def build_v1_idempotency_display_query(
    plan: PatentPriorArtSearchPlanDraft,
    jurisdictions: Sequence[str],
) -> str:
    """Reproduce the deployed v1 display projection used in request fingerprints.

    This projection is never sent to KIPRIS. It intentionally freezes the prior
    compiler's 12-query bound, 30-code normalization, quoted multi-word terms,
    applicant filtering, and per-jurisdiction duplicate lines so jobs remain
    idempotent across rollout and rollback while the live compiler evolves.
    """

    def v1_classification_codes(values: Sequence[str]) -> tuple[str, ...]:
        codes: list[str] = []
        for value in values:
            match = _CODE_RE.search(str(value).upper())
            if not match:
                continue
            code = re.sub(r"\s+", "", match.group(1).upper())
            if code not in codes:
                codes.append(code)
            if len(codes) >= MAX_PLAN_VALUES:
                break
        return tuple(codes)

    def v1_provider_term(value: str) -> str:
        cleaned = re.sub(r"[(){}\[\]\"'\\]", " ", value)
        cleaned = _normalise_text(cleaned)
        if not cleaned:
            return ""
        cleaned = cleaned[:160].rstrip()
        if " " in cleaned or cleaned.upper() in {"AND", "OR", "NOT"}:
            return f'"{cleaned}"'
        return cleaned

    def v1_render(
        values: Sequence[str],
        *,
        excluded_terms: Sequence[str],
    ) -> str:
        terms = [v1_provider_term(value) for value in _normalise_plan_values(values)]
        terms = [term for term in terms if term]
        if not terms:
            raise ValueError("provider query requires at least one lexical value")
        exclusions = [v1_provider_term(value) for value in _normalise_plan_values(excluded_terms)]
        exclusions = [term for term in exclusions if term]
        positive_limit = 1_500 if exclusions else MAX_PROVIDER_QUERY_CHARS
        query = _bounded_or_group(terms, max_chars=positive_limit)
        if exclusions:
            overhead = len(query) + len("() NOT ()")
            exclusion_group = _bounded_or_group(
                exclusions,
                max_chars=MAX_PROVIDER_QUERY_CHARS - overhead,
            )
            query = f"({query}) NOT ({exclusion_group})"
        return query

    ordered_jurisdictions = normalise_jurisdictions(jurisdictions)
    categories = get_category_definitions(plan.category_ids.values)
    applicants = tuple(
        _normalise_plan_values(plan.applicants.values, limit=_MAX_EXPLICIT_APPLICANTS)
    )
    ipc_codes = v1_classification_codes(plan.ipc_codes.values)
    cpc_codes = v1_classification_codes(plan.cpc_codes.values)
    excluded_terms = tuple(_normalise_plan_values(plan.excluded_terms.values))
    technical_terms = tuple(
        _normalise_plan_values((*plan.keywords_ko.values, *plan.keywords_en.values, *cpc_codes))
    )

    query_texts: list[str] = []
    for category in categories:
        category_query = v1_render(category.query_terms, excluded_terms=())
        query_texts.extend(category_query for _jurisdiction in ordered_jurisdictions)
    if technical_terms or ipc_codes or applicants:
        lexical_terms = technical_terms or ipc_codes or applicants
        technical_query = v1_render(lexical_terms, excluded_terms=excluded_terms)
        query_texts.extend(technical_query for _jurisdiction in ordered_jurisdictions)

    if not query_texts:
        raise ValueError(
            "search plan must include a category, keyword, classification, or applicant"
        )
    if len(query_texts) > _V1_MAX_COMPILED_QUERIES:
        raise ValueError(
            f"compiled search plan exceeds {_V1_MAX_COMPILED_QUERIES} provider queries"
        )
    return "\n".join(query_texts)[:8_000]


def build_candidate_ranking_query(
    plan: PatentPriorArtSearchPlanDraft,
    *,
    technology_summary: str,
    invention_text: str,
) -> str:
    """Build the plan-first technical query consumed by the platform ranker.

    Reviewed technical fields precede summary and source text so the platform's
    query bound cannot discard them merely because the invention is long.
    Applicant, exclusion, and display-only fields are deliberately absent.
    """

    reviewed_terms = tuple(
        dict.fromkeys(
            (
                *_normalise_plan_values(plan.keywords_ko.values),
                *_normalise_plan_values(plan.keywords_en.values),
                *_normalise_classification_codes(plan.ipc_codes.values),
                *_normalise_classification_codes(plan.cpc_codes.values),
            )
        )
    )
    query_parts = (
        *reviewed_terms,
        _normalise_text(technology_summary),
        _normalise_text(invention_text),
    )
    query = "\n".join(part for part in query_parts if part)
    if not query:
        raise ValueError("candidate ranking query must not be blank")
    return query


def normalise_jurisdictions(jurisdictions: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for raw_jurisdiction in jurisdictions:
        jurisdiction = raw_jurisdiction.strip().upper()
        if not jurisdiction or jurisdiction in ordered:
            continue
        if jurisdiction not in SUPPORTED_PATENT_SEARCH_COUNTRIES:
            raise ValueError(f"Unsupported patent jurisdiction: {jurisdiction}")
        ordered.append(jurisdiction)
    if not ordered:
        raise ValueError("at least one patent jurisdiction is required")
    return tuple(ordered)


def _clean_applicant_token(raw: str) -> str:
    token = _BRACKET_TOKEN_RE.sub(" ", raw)
    token = _LEADING_ENUM_RE.sub("", token)
    token = _TRAILING_APPLICANT_NOISE_RE.sub("", token)
    return _normalise_text(token)


def _is_valid_applicant(token: str) -> bool:
    if not (2 <= len(token) <= 40):
        return False
    if token.count(" ") > 3:  # drop inline prose, keep multi-word company names
        return False
    if not _APPLICANT_LETTER_RE.search(token):
        return False
    return _APPLICANT_LABEL_RE.search(f"{token}:") is None


def _iter_applicant_mentions(invention_text: str) -> tuple[list[tuple[int, int]], list[str]]:
    """Return label→value spans and the cleaned applicant values behind each label."""

    text = invention_text[:MAX_PLANNING_INPUT_CHARS]
    spans: list[tuple[int, int]] = []
    values: list[str] = []
    for match in _APPLICANT_LABEL_RE.finditer(text):
        newline = text.find("\n", match.end())
        window_end = newline if newline != -1 else min(len(text), match.end() + _APPLICANT_VALUE_WINDOW)
        window = text[match.end() : window_end][:_APPLICANT_VALUE_WINDOW]
        # Values run only until the next enumerated item (e.g. "2 )") or label.
        window = _APPLICANT_ITEM_BOUNDARY_RE.split(window)[0]
        window = _APPLICANT_LABEL_RE.split(window)[0]
        spans.append((match.start(), match.end() + len(window)))
        for raw in _APPLICANT_SPLIT_RE.split(window):
            token = _clean_applicant_token(raw)
            if _is_valid_applicant(token):
                values.append(token)
    return spans, values


def extract_explicit_applicants(invention_text: str) -> tuple[str, ...]:
    """Extract only values behind an explicit applicant/competitor/maker label."""

    _spans, values = _iter_applicant_mentions(invention_text)
    return tuple(_normalise_plan_values(values, limit=_MAX_EXPLICIT_APPLICANTS))


def _strip_structural_markers(invention_text: str) -> str:
    """Remove extractor locators ("[Slide 3]", "[삽입 파일: X.pptx]") for planning."""

    return _STRUCTURAL_MARKER_RE.sub(" ", invention_text)


def strip_applicant_mentions(invention_text: str) -> str:
    """Blank labelled applicant runs so the planner LLM never sees company names.

    This keeps the model from re-surfacing applicants as keywords or, worse,
    dumping them into ``excluded_terms`` (which would filter competitors *out*
    of the search). Applicant identity is captured separately and only ever
    influences retrieval, never ranking.
    """

    spans, _values = _iter_applicant_mentions(invention_text)
    if not spans:
        return invention_text
    chars = list(invention_text)
    for start, end in spans:
        for index in range(start, min(end, len(chars))):
            chars[index] = " "
    return "".join(chars)


def _run_planning_workload(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    invention_text: str,
    category_ids: tuple[str, ...],
    jurisdictions: tuple[str, ...],
) -> _SearchPlanLlmResponse:
    category_context = [
        {
            "id": definition.id,
            "terms": list(definition.query_terms),
            "classification_anchors": list(definition.classification_anchors),
        }
        for definition in get_category_definitions(list(category_ids))
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "Create a provider-neutral patent search plan from supplied technical text. "
                "Return one strict JSON object matching the supplied schema. Use only supplied "
                "technical facts. Do not identify, infer, recommend, or add applicants or "
                "companies. For ipc_codes and cpc_codes, list only the few (at most 6) most "
                "relevant classification codes — never enumerate an entire subclass or a "
                "sequential range of groups. Category anchors are caller-selected context, "
                "not scoring rules."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "Extract a concise technical summary and generic search vocabulary.",
                    "schema": {
                        "technology_summary": "string",
                        "keywords_ko": ["string"],
                        "keywords_en": ["string"],
                        "ipc_codes": ["string"],
                        "cpc_codes": ["string"],
                    },
                    "limits": {
                        "max_values_per_field": MAX_PLAN_VALUES,
                        "max_classification_codes": MAX_CLASSIFICATION_CODES,
                        "max_summary_chars": MAX_TECHNOLOGY_SUMMARY_CHARS,
                    },
                    "selected_categories": category_context,
                    "selected_jurisdictions": list(jurisdictions),
                    "invention_text": invention_text,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]
    task_context = LlmTaskContext(
        source="patent_prior_art",
        workspace_id=workspace_id,
        task_kind=PATENT_PRIOR_ART_SEARCH_PLAN_TASK_KIND,
        app_id=PATENT_PRIOR_ART_APP_ID,
        actor_user_id=actor_user_id,
        principal_kind="user",
        principal_id=actor_user_id,
    )
    completion = execute_llm(
        PATENT_PRIOR_ART_SEARCH_PLAN_WORKLOAD_ID,
        LlmWorkloadContext.from_task_context(task_context),
        db,
        messages=messages,
        temperature=0,
        max_tokens=_PLANNING_MAX_TOKENS,
        reasoning_effort="none",
        timeout_seconds=_PLANNING_TIMEOUT_SECONDS,
    ).completion
    try:
        payload = json.loads(completion.text.strip())
        response = _SearchPlanLlmResponse.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as error:
        raise _InvalidSearchPlanResponse(
            "search planning workload returned an invalid response"
        ) from error
    response_text = "\n".join(
        (
            response.technology_summary,
            *response.keywords_ko,
            *response.keywords_en,
            *response.excluded_terms,
        )
    )
    if _LEGAL_CONCLUSION_RE.search(response_text):
        raise _InvalidSearchPlanResponse("search planning response contained a legal conclusion")
    return response


def _fallback_plan_payload(invention_text: str) -> _SearchPlanLlmResponse:
    codes = _normalise_classification_codes(_CODE_RE.findall(invention_text))
    keywords_ko = _fallback_keywords(_KOREAN_TOKEN_RE.findall(invention_text))
    keywords_en = _fallback_keywords(_ENGLISH_TOKEN_RE.findall(invention_text))
    summary = invention_text[:MAX_TECHNOLOGY_SUMMARY_CHARS].strip()
    return _SearchPlanLlmResponse(
        technology_summary=summary,
        keywords_ko=keywords_ko,
        keywords_en=keywords_en,
        ipc_codes=codes,
        cpc_codes=[],
        excluded_terms=[],
    )


def _fallback_keywords(values: Sequence[str]) -> list[str]:
    filtered = [value for value in values if value.lower() not in _FALLBACK_STOPWORDS]
    return _normalise_plan_values(filtered, limit=12)


def _collect_explicit_applicants(
    invention_text: str,
    *,
    explicit_applicants: Sequence[str],
) -> tuple[tuple[str, ...], Literal["user", "input_derived"]]:
    supplied = tuple(_normalise_plan_values(explicit_applicants, limit=_MAX_EXPLICIT_APPLICANTS))
    extracted = extract_explicit_applicants(invention_text)
    combined = tuple(dict.fromkeys((*supplied, *extracted)))[:_MAX_EXPLICIT_APPLICANTS]
    return combined, "user" if supplied else "input_derived"


def _normalise_plan_values(values: Sequence[str], *, limit: int = MAX_PLAN_VALUES) -> list[str]:
    normalised: list[str] = []
    for value in values:
        cleaned = _normalise_text(str(value))[:256]
        if cleaned and cleaned not in normalised:
            normalised.append(cleaned)
        if len(normalised) >= limit:
            break
    return normalised


def _normalise_classification_codes(values: Sequence[str]) -> list[str]:
    codes: list[str] = []
    for value in values:
        match = _CODE_RE.search(str(value).upper())
        if not match:
            continue
        code = re.sub(r"\s+", "", match.group(1).upper())
        if code not in codes:
            codes.append(code)
        if len(codes) >= MAX_CLASSIFICATION_CODES:
            break
    return codes


def _normalise_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", _CONTROL_RE.sub(" ", value)).strip()


def _render_provider_query(
    values: Sequence[str],
    *,
    excluded_terms: Sequence[str],
) -> str:
    terms = [_provider_term(value) for value in _normalise_plan_values(values)]
    terms = [term for term in terms if term]
    if not terms:
        raise ValueError("provider query requires at least one lexical value")
    exclusions = [_provider_term(value) for value in _normalise_plan_values(excluded_terms)]
    exclusions = [term for term in exclusions if term]
    positive_limit = 1_500 if exclusions else MAX_PROVIDER_QUERY_CHARS
    query = _bounded_or_group(terms, max_chars=positive_limit)
    if exclusions:
        overhead = len(query) + len("() NOT ()")
        exclusion_group = _bounded_or_group(
            exclusions,
            max_chars=MAX_PROVIDER_QUERY_CHARS - overhead,
        )
        query = f"({query}) NOT ({exclusion_group})"
    return query


def _provider_term(value: str) -> str:
    # Keep user terms literal while removing provider-expression delimiters.
    cleaned = re.sub(r"[(){}\[\]\"'\\]", " ", value)
    cleaned = _normalise_text(cleaned)
    if not cleaned:
        return ""
    cleaned = cleaned[:160].rstrip()
    if " " in cleaned or cleaned.upper() in {"AND", "OR", "NOT"}:
        # KIPRIS (both its Korean domestic and foreign collections) returns zero
        # hits for a *quoted* CJK phrase, and one such term poisons the whole OR
        # query. Only quote ASCII phrases; leave CJK phrases unquoted so KIPRIS
        # tokenises them and returns matches.
        if _CJK_RE.search(cleaned):
            return cleaned
        return f'"{cleaned}"'
    return cleaned


def _bounded_or_group(terms: Sequence[str], *, max_chars: int) -> str:
    selected: list[str] = []
    for term in terms:
        candidate = " OR ".join((*selected, term))
        if len(candidate) > max_chars:
            continue
        selected.append(term)
    if not selected:
        raise ValueError("provider query values exceed the safe expression limit")
    return " OR ".join(selected)


__all__ = [
    "MAX_COMPILED_QUERIES",
    "CompiledPatentQuery",
    "build_candidate_ranking_query",
    "build_display_query",
    "build_v1_idempotency_display_query",
    "compile_provider_queries",
    "extract_explicit_applicants",
    "normalise_jurisdictions",
    "preview_patent_prior_art_search",
]
