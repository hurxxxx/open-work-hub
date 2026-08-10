"""Neutral, deterministic report projection for patent prior-art research."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import re
from typing import Any

from ai_do_api.domains.patent_prior_art.schemas import (
    PatentPriorArtCandidateOut,
    PatentPriorArtExecutedQueryOut,
    PatentPriorArtSearchPlanDraft,
)


MAX_REPORT_INVENTION_CHARS = 20_000
MAX_REPORT_CANDIDATES = 100
MAX_REPORT_QUERIES = 100
_MARKDOWN_META_RE = re.compile(r"([`*_{}\[\]<>#+])")
_YEAR_RE = re.compile(r"\A(19|20)\d{2}")
_CLASSIFICATION_SUBCLASS_RE = re.compile(r"\A([A-HY]\d{2}[A-Z])")
_RELEVANCE_LABELS = {
    "high": "높음",
    "medium": "보통",
    "low": "낮음",
    "unrated": "미평가",
}
_METHOD_LABELS = {
    "bm25": "BM25 희소 검색",
    "semantic": "임베딩 기반 의미 검색",
    "vector": "임베딩 기반 의미 검색",
    "rrf": "순위 융합",
    "cross_encoder": "후보 재순위화",
}
_DISCLAIMER = (
    "이 보고서는 기술적 선행문헌 검토를 지원하기 위한 조사 자료입니다. 특허의 유효성, "
    "침해 여부, 실시 자유 또는 사업 진행 가능성에 관한 법률 의견이나 확정적 판단이 아닙니다."
)


@dataclass(frozen=True, slots=True)
class ReportCount:
    label: str
    count: int


@dataclass(frozen=True, slots=True)
class ReportQuery:
    source_label: str
    jurisdiction: str
    query_text: str
    result_count: int | None
    status: str
    failure_code: str | None

    @property
    def result_display(self) -> str:
        if self.status == "failed":
            return "실패(누락)"
        return "-" if self.result_count is None else str(self.result_count)


@dataclass(frozen=True, slots=True)
class ReportCandidate:
    rank: int
    publication_number: str
    title: str
    assignees: tuple[str, ...]
    jurisdiction: str
    filing_date: str
    publication_date: str
    classification_codes: tuple[str, ...]
    abstract: str
    summary: str
    relevance_band: str
    match_reasons: tuple[str, ...]
    external_url: str

    @property
    def relevance_label(self) -> str:
        return _RELEVANCE_LABELS[self.relevance_band]

    @property
    def publication_year(self) -> str:
        match = _YEAR_RE.match(self.publication_date)
        return match.group(0) if match else "미상"


@dataclass(frozen=True, slots=True)
class ReportTechnologyCluster:
    code: str
    candidate_count: int
    publications: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PatentPriorArtDetailedReport:
    title: str
    report_type: str
    schema_version: str
    jurisdictions: tuple[str, ...]
    category_ids: tuple[str, ...]
    technology_summary: str
    invention_text: str
    invention_text_truncated: bool
    search_rationale: tuple[tuple[str, str], ...]
    display_query: str
    executed_queries: tuple[ReportQuery, ...]
    selection_process: tuple[str, ...]
    candidates: tuple[ReportCandidate, ...]
    candidates_truncated: bool
    relevance_distribution: tuple[ReportCount, ...]
    applicant_distribution: tuple[ReportCount, ...]
    year_distribution: tuple[ReportCount, ...]
    technology_clusters: tuple[ReportTechnologyCluster, ...]
    technical_review: tuple[str, ...]
    sources_and_limits: tuple[str, ...]
    disclaimer: str


def build_result_payload(
    *,
    title: str,
    invention_text: str,
    technology_summary: str,
    jurisdictions: Sequence[str],
    search_plan: PatentPriorArtSearchPlanDraft,
    executed_queries: Sequence[PatentPriorArtExecutedQueryOut],
    candidates: Sequence[PatentPriorArtCandidateOut],
    ranking_profile: Mapping[str, object],
) -> dict[str, object]:
    """Build the stable renderer-independent artifact contract."""

    bounded_invention = invention_text[:MAX_REPORT_INVENTION_CHARS]
    return {
        "schema_version": "1.0",
        "report_type": "patent_prior_art_research",
        "title": title.strip(),
        "scope": {
            "jurisdictions": list(jurisdictions),
            "category_ids": list(search_plan.category_ids.values),
            "invention_text": bounded_invention,
            "invention_text_truncated": len(invention_text) > len(bounded_invention),
            "technology_summary": technology_summary,
        },
        "search_plan": search_plan.model_dump(mode="json"),
        "executed_queries": [query.model_dump(mode="json") for query in executed_queries],
        "selection": {
            "candidate_count": len(candidates),
            "ranking_profile": dict(ranking_profile),
        },
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "methodology": {
            "search": "caller-selected jurisdiction and typed provider criteria",
            "ranking": "platform sparse, semantic, fusion, and reranking services when available",
            "assessment": "bounded technical relevance assessment with deterministic fallback",
        },
        "sources_and_limits": [
            "Results depend on the selected jurisdictions, supplied scope, provider coverage, and query date.",
            "Publication metadata and abstracts may be incomplete or translated by the source provider.",
            "Candidate selection is a research aid and may omit relevant documents.",
        ],
        "disclaimer": (
            "This report is a technical prior-art research aid. It is not a legal opinion and "
            "does not determine patent validity, freedom to operate, infringement, or clearance."
        ),
    }


def serialise_result_payload(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_detailed_report(payload: Mapping[str, object]) -> PatentPriorArtDetailedReport:
    """Project a bounded structured report without exposing private ranking metrics."""

    scope = _mapping(payload.get("scope"))
    plan = _mapping(payload.get("search_plan"))
    raw_candidates = _sequence(payload.get("candidates"))
    candidates = tuple(
        _candidate(_mapping(item), default_rank=index)
        for index, item in enumerate(raw_candidates[:MAX_REPORT_CANDIDATES], start=1)
    )
    raw_queries = _sequence(payload.get("executed_queries"))
    queries = tuple(_query(_mapping(item)) for item in raw_queries[:MAX_REPORT_QUERIES])
    relevance_distribution = _relevance_distribution(candidates)
    applicant_distribution = _applicant_distribution(candidates)
    year_distribution = _year_distribution(candidates)
    technology_clusters = _technology_clusters(candidates)
    selection_process = _selection_process(payload, len(candidates))
    technical_review = _technical_review(
        candidates,
        relevance_distribution=relevance_distribution,
        applicant_distribution=applicant_distribution,
        year_distribution=year_distribution,
        technology_clusters=technology_clusters,
    )
    source_labels = tuple(
        dict.fromkeys(query.source_label for query in queries if query.source_label)
    )
    failed_scopes = tuple(
        f"{query.source_label}/{query.jurisdiction}"
        for query in queries
        if query.status == "failed"
    )
    sources = (
        "조사 범위와 검색식은 사용자가 제공하거나 입력 내용에서 도출된 조건에 한정됩니다.",
        "검색 결과는 선택 국가·권역, 조회 시점 및 원천 데이터 제공 범위에 따라 달라질 수 있습니다.",
        "공개번호, 출원인, 분류코드, 초록과 날짜 정보는 원천 데이터의 누락·번역·갱신 지연 영향을 받을 수 있습니다.",
        "관련도는 기술적 검토를 위한 범주형 표시이며 법률적 결론이나 수치형 평가점수가 아닙니다.",
        "후보 선별 결과는 조사 보조자료이며 관련 문헌을 모두 포함한다고 보장하지 않습니다.",
        *(
            (
                "일부 원천 검색이 실패하여 다음 범위가 보고서에서 누락되었습니다: "
                + ", ".join(failed_scopes),
            )
            if failed_scopes
            else ()
        ),
        *((f"실행 출처: {', '.join(source_labels)}",) if source_labels else ()),
    )
    return PatentPriorArtDetailedReport(
        title=_text(payload.get("title"), maximum=200) or "특허 선행기술 조사",
        report_type=_text(payload.get("report_type"), maximum=80) or "patent_prior_art_research",
        schema_version=_text(payload.get("schema_version"), maximum=20) or "1.0",
        jurisdictions=tuple(_strings(scope.get("jurisdictions"), maximum_items=10)),
        category_ids=tuple(_strings(scope.get("category_ids"), maximum_items=10)),
        technology_summary=_text(scope.get("technology_summary"), maximum=20_000) or "-",
        invention_text=_text(scope.get("invention_text"), maximum=MAX_REPORT_INVENTION_CHARS)
        or "-",
        invention_text_truncated=scope.get("invention_text_truncated") is True,
        search_rationale=_search_rationale(plan),
        display_query=_text(plan.get("display_query"), maximum=8_000) or "-",
        executed_queries=queries,
        selection_process=selection_process,
        candidates=candidates,
        candidates_truncated=len(raw_candidates) > len(candidates),
        relevance_distribution=relevance_distribution,
        applicant_distribution=applicant_distribution,
        year_distribution=year_distribution,
        technology_clusters=technology_clusters,
        technical_review=technical_review,
        sources_and_limits=sources,
        disclaimer=_DISCLAIMER,
    )


def render_markdown_report(payload: Mapping[str, object]) -> str:
    """Render the detailed report as neutral Markdown."""

    report = build_detailed_report(payload)
    lines = [
        f"# {_md(report.title)}",
        "",
        "## 1. 과제 개요",
        "",
        f"- 보고서 유형: {_md(report.report_type)}",
        f"- 스키마 버전: {_md(report.schema_version)}",
        f"- 조사 국가/권역: {_md(', '.join(report.jurisdictions) or '-')}",
        f"- 선택 카테고리: {_md(', '.join(report.category_ids) or '-')}",
        "",
        "### 기술 요약",
        "",
        _paragraph(report.technology_summary),
        "",
        "### 입력 발명 내용",
        "",
        _paragraph(report.invention_text),
    ]
    if report.invention_text_truncated:
        lines.extend(["", "> 입력 내용은 보고서 크기 제한에 따라 일부만 수록되었습니다."])

    lines.extend(["", "## 2. 검색식 도출 근거", ""])
    lines.extend(f"- {_md(label)}: {_md(value)}" for label, value in report.search_rationale)
    lines.extend(["", "### 표시 검색식", "", f"`{_code(report.display_query)}`"])
    lines.extend(
        [
            "",
            "### 실행 질의",
            "",
            "| 순번 | 출처 | 국가/권역 | 질의 | 결과 수 |",
            "| ---: | --- | --- | --- | ---: |",
        ]
    )
    for index, query in enumerate(report.executed_queries, start=1):
        lines.append(
            "| "
            + " | ".join(
                (
                    str(index),
                    _cell(query.source_label or "-"),
                    _cell(query.jurisdiction or "-"),
                    _cell(query.query_text or "-"),
                    query.result_display,
                )
            )
            + " |"
        )
    if not report.executed_queries:
        lines.append("| - | - | - | - | - |")

    lines.extend(["", "## 3. 선별 프로세스", ""])
    lines.extend(f"- {_md(item)}" for item in report.selection_process)
    lines.extend(
        [
            "",
            "## 4. 핵심 특허 표",
            "",
            "| 순위 | 공개번호 | 명칭 | 출원인 | 공개연도 | 분류코드 | 관련도 |",
            "| ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for candidate in report.candidates:
        lines.append(
            "| "
            + " | ".join(
                (
                    str(candidate.rank),
                    _cell(candidate.publication_number),
                    _cell(candidate.title),
                    _cell(", ".join(candidate.assignees) or "-"),
                    _cell(candidate.publication_year),
                    _cell(", ".join(candidate.classification_codes) or "-"),
                    _cell(candidate.relevance_label),
                )
            )
            + " |"
        )
    if not report.candidates:
        lines.append("| - | - | 검색 결과 없음 | - | - | - | - |")

    lines.extend(["", "## 5. 후보별 요지시트", ""])
    for candidate in report.candidates:
        lines.extend(
            [
                f"### {candidate.rank}. {_md(candidate.publication_number)}",
                "",
                f"- 명칭: {_md(candidate.title)}",
                f"- 국가/권역: {_md(candidate.jurisdiction)}",
                f"- 출원인: {_md(', '.join(candidate.assignees) or '-')}",
                f"- 출원일: {_md(candidate.filing_date)}",
                f"- 공개일: {_md(candidate.publication_date)}",
                f"- 분류코드: {_md(', '.join(candidate.classification_codes) or '-')}",
                f"- 기술 관련도: {_md(candidate.relevance_label)}",
                f"- 검토 근거: {_md('; '.join(candidate.match_reasons) or '-')}",
                f"- 원문 위치: {_md(candidate.external_url)}",
                "",
                _paragraph(candidate.summary or candidate.abstract or "-"),
                "",
            ]
        )
    if report.candidates_truncated:
        lines.extend(["> 보고서 후보 수 제한에 따라 일부 후보만 수록되었습니다.", ""])

    lines.extend(["## 6. 정량 분석", "", "### 관련도 분포", ""])
    lines.extend(_markdown_count_table(report.relevance_distribution))
    lines.extend(["", "### 출원인 분포", ""])
    lines.extend(_markdown_count_table(report.applicant_distribution))
    lines.extend(["", "### 공개연도 분포", ""])
    lines.extend(_markdown_count_table(report.year_distribution))
    lines.extend(
        [
            "",
            "## 7. 분류코드 기반 기술 클러스터",
            "",
            "| 분류 클러스터 | 후보 수 | 포함 공개번호 |",
            "| --- | ---: | --- |",
        ]
    )
    for cluster in report.technology_clusters:
        lines.append(
            f"| {_cell(cluster.code)} | {cluster.candidate_count} | "
            f"{_cell(', '.join(cluster.publications))} |"
        )
    if not report.technology_clusters:
        lines.append("| 미분류 | 0 | - |")

    lines.extend(["", "## 8. 종합 기술 검토", ""])
    lines.extend(f"- {_md(item)}" for item in report.technical_review)
    lines.extend(["", "## 9. 출처·한계 및 고지", ""])
    lines.extend(f"- {_md(item)}" for item in report.sources_and_limits)
    lines.extend(["", "### 고지", "", _paragraph(report.disclaimer), ""])
    return "\n".join(lines)


def _candidate(value: Mapping[str, Any], *, default_rank: int) -> ReportCandidate:
    relevance = _text(value.get("relevance_band"), maximum=16).lower()
    if relevance not in _RELEVANCE_LABELS:
        relevance = "unrated"
    raw_rank = value.get("rank")
    rank = raw_rank if isinstance(raw_rank, int) and raw_rank > 0 else default_rank
    return ReportCandidate(
        rank=rank,
        publication_number=_text(value.get("publication_number"), maximum=96) or "-",
        title=_text(value.get("title"), maximum=1_000) or "-",
        assignees=tuple(_strings(value.get("assignees"), maximum_items=20, maximum=320)),
        jurisdiction=_text(value.get("jurisdiction"), maximum=8) or "-",
        filing_date=_text(value.get("filing_date"), maximum=32) or "-",
        publication_date=_text(value.get("publication_date"), maximum=32) or "-",
        classification_codes=tuple(
            _strings(value.get("classification_codes"), maximum_items=30, maximum=64)
        ),
        abstract=_text(value.get("abstract"), maximum=20_000),
        summary=_text(value.get("summary"), maximum=20_000),
        relevance_band=relevance,
        match_reasons=tuple(_strings(value.get("match_reasons"), maximum_items=30, maximum=1_000)),
        external_url=_text(value.get("external_url"), maximum=2_048) or "-",
    )


def _query(value: Mapping[str, Any]) -> ReportQuery:
    result_count = value.get("result_count")
    status = _text(value.get("status"), maximum=16).lower()
    if status not in {"succeeded", "failed"}:
        status = "failed" if result_count is None else "succeeded"
    failure_code = _text(value.get("failure_code"), maximum=80) or None
    return ReportQuery(
        source_label=_text(value.get("source_label"), maximum=160) or "-",
        jurisdiction=_text(value.get("jurisdiction"), maximum=8) or "-",
        query_text=_text(value.get("query_text"), maximum=8_000) or "-",
        result_count=(
            result_count if isinstance(result_count, int) and result_count >= 0 else None
        ),
        status=status,
        failure_code=failure_code,
    )


def _search_rationale(plan: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    definitions = (
        ("선택 카테고리", "category_ids"),
        ("국문 핵심어", "keywords_ko"),
        ("영문 핵심어", "keywords_en"),
        ("IPC 분류", "ipc_codes"),
        ("CPC 분류", "cpc_codes"),
        ("명시 출원인", "applicants"),
        ("제외어", "excluded_terms"),
    )
    rows: list[tuple[str, str]] = []
    for label, field in definitions:
        field_payload = _mapping(plan.get(field))
        values = _strings(field_payload.get("values"), maximum_items=30)
        source = _text(field_payload.get("source"), maximum=32)
        source_label = {"user": "사용자 지정", "input_derived": "입력 내용 기반"}.get(
            source,
            "출처 미표시",
        )
        rows.append((label, f"{', '.join(values) or '-'} ({source_label})"))
    return tuple(rows)


def _selection_process(
    payload: Mapping[str, object],
    rendered_candidate_count: int,
) -> tuple[str, ...]:
    selection = _mapping(payload.get("selection"))
    profile = _mapping(selection.get("ranking_profile"))
    input_count = _safe_count(profile.get("input_candidate_count"))
    ranked_count = _safe_count(profile.get("ranked_candidate_count"))
    returned_count = _safe_count(profile.get("returned_candidate_count"))
    selected_count = _safe_count(selection.get("candidate_count")) or rendered_candidate_count
    methods = tuple(
        dict.fromkeys(
            _METHOD_LABELS[method]
            for method in _strings(profile.get("methods"), maximum_items=10, maximum=32)
            if method in _METHOD_LABELS
        )
    )
    steps = [
        "선택 국가·권역과 검색 계획에 따라 원천 검색을 실행하고 공개번호 중심으로 중복 후보를 정리했습니다.",
        (
            f"후보 {input_count}건을 입력받아 {ranked_count or input_count}건을 기술적으로 비교하고 "
            f"{returned_count or selected_count}건을 선별했습니다."
            if input_count
            else f"구조화된 후보 {selected_count}건을 선별 결과로 수록했습니다."
        ),
        (
            f"적용 절차: {', '.join(methods)}."
            if methods
            else "적용 절차는 구조화된 검색 결과의 순서와 범주형 기술 관련도 검토를 따릅니다."
        ),
        "관련도는 높음·보통·낮음·미평가의 범주로만 제시하며 내부 수치형 순위 값은 보고서에 포함하지 않습니다.",
    ]
    if profile.get("degraded") is True:
        steps.append(
            "일부 선택 절차를 사용할 수 없어 가용한 플랫폼 검색·정렬 절차로 결과를 구성했습니다."
        )
    return tuple(steps)


def _relevance_distribution(
    candidates: Sequence[ReportCandidate],
) -> tuple[ReportCount, ...]:
    counts = Counter(candidate.relevance_band for candidate in candidates)
    return tuple(
        ReportCount(label=label, count=counts[band]) for band, label in _RELEVANCE_LABELS.items()
    )


def _applicant_distribution(
    candidates: Sequence[ReportCandidate],
) -> tuple[ReportCount, ...]:
    counts: Counter[str] = Counter()
    for candidate in candidates:
        assignees = tuple(dict.fromkeys(candidate.assignees)) or ("미상",)
        counts.update(assignees)
    return tuple(
        ReportCount(label=label, count=count)
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]
    )


def _year_distribution(candidates: Sequence[ReportCandidate]) -> tuple[ReportCount, ...]:
    counts = Counter(candidate.publication_year for candidate in candidates)
    ordered = sorted(
        counts.items(),
        key=lambda item: (item[0] == "미상", item[0]),
    )
    return tuple(ReportCount(label=label, count=count) for label, count in ordered)


def _technology_clusters(
    candidates: Sequence[ReportCandidate],
) -> tuple[ReportTechnologyCluster, ...]:
    publications_by_code: dict[str, list[str]] = {}
    for candidate in candidates:
        codes = tuple(
            dict.fromkeys(_classification_cluster(code) for code in candidate.classification_codes)
        ) or ("미분류",)
        for code in codes:
            publications_by_code.setdefault(code, []).append(candidate.publication_number)
    return tuple(
        ReportTechnologyCluster(
            code=code,
            candidate_count=len(tuple(dict.fromkeys(publications))),
            publications=tuple(dict.fromkeys(publications)),
        )
        for code, publications in sorted(
            publications_by_code.items(),
            key=lambda item: (-len(set(item[1])), item[0]),
        )[:20]
    )


def _technical_review(
    candidates: Sequence[ReportCandidate],
    *,
    relevance_distribution: Sequence[ReportCount],
    applicant_distribution: Sequence[ReportCount],
    year_distribution: Sequence[ReportCount],
    technology_clusters: Sequence[ReportTechnologyCluster],
) -> tuple[str, ...]:
    if not candidates:
        return (
            "선별된 후보가 없어 기술 구성의 중복 정도나 문헌 분포를 추가로 해석할 수 없습니다.",
            "검색 범위, 핵심어, 분류코드와 국가·권역 조건을 검토한 뒤 보완 조사를 고려할 수 있습니다.",
        )
    relevance = {item.label: item.count for item in relevance_distribution}
    lines = [
        (
            f"총 {len(candidates)}건을 검토했으며 관련도 높음 {relevance.get('높음', 0)}건, "
            f"보통 {relevance.get('보통', 0)}건, 낮음 {relevance.get('낮음', 0)}건, "
            f"미평가 {relevance.get('미평가', 0)}건으로 구성됩니다."
        )
    ]
    if technology_clusters:
        cluster = technology_clusters[0]
        lines.append(
            f"가장 반복적으로 확인된 분류 클러스터는 {cluster.code}이며 후보 {cluster.candidate_count}건에 나타납니다."
        )
    known_years = [item.label for item in year_distribution if item.label != "미상"]
    if known_years:
        lines.append(
            f"확인 가능한 공개연도 범위는 {known_years[0]}년부터 {known_years[-1]}년까지입니다."
        )
    if applicant_distribution:
        leading = applicant_distribution[0]
        lines.append(
            f"가장 자주 표시된 출원인은 {leading.label}이며 {leading.count}건에서 확인됩니다."
        )
    lines.append(
        "후보별 요지와 구성요소 대응 근거를 원문 청구항·도면과 함께 재검토해야 하며, 범주형 관련도만으로 법률적 결론을 내릴 수 없습니다."
    )
    return tuple(lines)


def _classification_cluster(value: str) -> str:
    normalized = re.sub(r"\s+", "", value.upper())
    match = _CLASSIFICATION_SUBCLASS_RE.match(normalized)
    if match:
        return match.group(1)
    return normalized[:12] or "미분류"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _strings(
    value: object,
    *,
    maximum_items: int = 100,
    maximum: int = 256,
) -> list[str]:
    return [
        text for item in _sequence(value)[:maximum_items] if (text := _text(item, maximum=maximum))
    ]


def _text(value: object, *, maximum: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:maximum]


def _safe_count(value: object) -> int:
    return value if isinstance(value, int) and 0 <= value <= 1_000_000 else 0


def _markdown_count_table(items: Sequence[ReportCount]) -> list[str]:
    lines = ["| 구분 | 후보 수 |", "| --- | ---: |"]
    lines.extend(f"| {_cell(item.label)} | {item.count} |" for item in items)
    if not items:
        lines.append("| - | 0 |")
    return lines


def _md(value: str) -> str:
    flattened = " ".join(value.split())
    escaped = flattened.replace("\\", "\\\\")
    return _MARKDOWN_META_RE.sub(r"\\\1", escaped).strip()


def _cell(value: str) -> str:
    return _md(value).replace("|", "\\|").replace("\n", " ")


def _paragraph(value: str) -> str:
    return _md(value).replace("\n", " ")


def _code(value: str) -> str:
    return " ".join(value.split()).replace("`", "\\`")


__all__ = [
    "MAX_REPORT_CANDIDATES",
    "MAX_REPORT_INVENTION_CHARS",
    "PatentPriorArtDetailedReport",
    "ReportCandidate",
    "ReportCount",
    "ReportQuery",
    "ReportTechnologyCluster",
    "build_detailed_report",
    "build_result_payload",
    "render_markdown_report",
    "serialise_result_payload",
]
