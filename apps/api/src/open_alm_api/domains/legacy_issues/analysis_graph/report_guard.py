from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any


_CITATION_RE = re.compile(r"\[([A-Z][A-Z0-9_-]*\d+)\]")
_NUMBER_RE = re.compile(r"(?<![\w])-?\d+(?:,\d{3})*(?:\.\d+)?(?:%[pP]?)?")
_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})(?:-(\d{2}))?(?!\d)")
_INTERNAL_SOURCE_ID_RE = re.compile(r"\banalysis-[0-9a-f]{8,}\b", re.IGNORECASE)
_INTERNAL_SOURCE_LABEL_RE = re.compile(r"\bsource\s*:", re.IGNORECASE)
_INTERNAL_METADATA_RE = re.compile(
    r"\b(?:llm_rows_)?truncated\s*:",
    re.IGNORECASE,
)
_INTERNAL_PROCESS_RE = re.compile(
    r"분석\s*과정(?!에서\s*(?:계산|확인))",
)
_SPECULATIVE_ASSERTION_RE = re.compile(
    r"(?:것으로|듯이)\s*(?:보(?:이|입)|추정되)",
)
_MARKDOWN_TABLE_RE = re.compile(
    r"(?m)^\s*\|[^\n|]+\|[^\n|]+\|.*\n"
    r"\s*\|(?:\s*:?-{3,}:?\s*\|){2,}\s*$",
)
_INTERNAL_TERMS = (
    "scope_direct_response",
    "serverresolved",
    "retrieval_profile",
    "exact_analysis",
    "analysis artifact",
    "evidence artifact",
    "내부 처리",
    "프롬프트",
    "에이전트가",
)
_FALLBACK_RECIPE_PRIORITY = {
    "issue_period_comparison": 0,
    "issue_supplier_part_hotspots": 0,
    "issue_matrix": 0,
    "issue_cube": 0,
    "issue_checklist_coverage": 0,
    "issue_response_duration": 0,
    "issue_category_severity": 0,
    "issue_details": 1,
    "checklist_item_breakdown": 1,
    "issue_breakdown": 2,
    "issue_ranked_summary": 2,
    "issue_total": 2,
    "checklist_total": 2,
    "checklist_item_total": 2,
    "checklist_status_summary": 2,
}
_DIMENSION_LABELS = {
    "vehicle_model": "차종",
    "region_zone": "권역",
    "module_key": "모듈",
    "department": "부서",
    "major_category": "대분류",
    "middle_category": "중분류",
    "occurrence_stage": "발생 단계",
    "occurrence_type": "발생 유형",
    "issue_type": "문제 유형",
    "cause_type": "원인 유형",
    "supplier": "공급업체",
    "part_number": "부품번호",
    "process_name": "공정",
    "severity_grade": "중요도",
    "applied": "적용 여부",
    "checklist_status": "체크리스트 상태",
}
_COLUMN_LABELS = {
    "legacy_issue_number": "과거차 관리번호",
    "vehicle_model": "차종",
    "region_zone": "권역",
    "module_key": "모듈",
    "major_category": "대분류",
    "middle_category": "중분류",
    "occurrence_stage": "발생 단계",
    "occurrence_date": "발생일",
    "issue_type": "문제 유형",
    "cause_type": "원인 유형",
    "supplier": "공급업체",
    "part_number": "부품번호",
    "process_name": "공정",
    "severity_grade": "중요도",
    "symptom": "현상",
    "cause": "원인",
    "countermeasure": "대책",
    "applied": "적용 여부",
    "dimension_value": "구분",
    "dimension_missing": "미입력 여부",
    "row_value": "행 기준",
    "column_value": "열 기준",
    "detail_value": "세부 기준",
    "issue_count": "문제점 건수",
    "total_issue_count": "전체 문제점 건수",
    "linked_issue_count": "체크리스트 연결 문제점",
    "unlinked_issue_count": "체크리스트 미연결 문제점",
    "coverage_rate": "문제점 반영률(%)",
    "issue_share": "전체 문제점 대비 비중(%)",
    "row_total_count": "행 전체 건수",
    "row_share": "행 기준 비중(%)",
    "combination_total_count": "조합 전체 건수",
    "combination_share": "조합 비중(%)",
    "detail_share": "조합 내 세부 비중(%)",
    "overall_share": "전체 대비 비중(%)",
    "cumulative_issue_count": "누적 문제점 건수",
    "cumulative_share": "누적 비중(%)",
    "supplier_missing": "공급업체 미입력",
    "part_number_missing": "부품번호 미입력",
    "supplier_missing_issue_count": "공급업체 미입력 문제점",
    "supplier_missing_share": "공급업체 미입력 비중(%)",
    "checklist_count": "체크리스트 문서 수",
    "checklist_item_count": "체크리스트 항목 수",
    "linked_item_count": "문제점 연결 항목",
    "unlinked_item_count": "문제점 미연결 항목",
    "linkage_rate": "항목 연결률(%)",
    "completed_count": "완료 문서 수",
    "draft_count": "작성 중 문서 수",
    "completion_rate": "완료율(%)",
}
_NON_PUBLIC_COLUMNS = {
    "issue_id",
    "record_id",
    "stable_record_id",
    "revision_id",
}


@dataclass(frozen=True)
class ReportValidationResult:
    valid: bool
    errors: tuple[str, ...]


def validate_report_markdown(
    markdown: str,
    *,
    question: str,
    query_results: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    source_revisions: Sequence[Mapping[str, Any]] = (),
    reviewed_unsupported_claims: Sequence[str] = (),
    reviewed_internal_commentary: Sequence[str] = (),
) -> ReportValidationResult:
    errors: list[str] = []
    normalized = markdown.strip()
    if not normalized:
        return ReportValidationResult(False, ("empty_report",))
    if not re.search(r"(?m)^#{1,3}\s+\S", normalized):
        errors.append("missing_markdown_heading")
    if _requests_table(question) and not _MARKDOWN_TABLE_RE.search(normalized):
        errors.append("missing_requested_table")
    if not any(
        str(item.get("status") or "succeeded") == "succeeded"
        and bool(item.get("rows"))
        for item in query_results
    ) and not evidence:
        errors.append("no_captured_sources")

    lower = normalized.casefold()
    if (
        _INTERNAL_SOURCE_ID_RE.search(normalized)
        or _INTERNAL_SOURCE_LABEL_RE.search(normalized)
    ):
        errors.append("internal_source_reference")
    if _INTERNAL_METADATA_RE.search(normalized):
        errors.append("internal_source_metadata")
    if _INTERNAL_PROCESS_RE.search(normalized):
        errors.append("internal_commentary:분석 과정")
    if _SPECULATIVE_ASSERTION_RE.search(normalized):
        errors.append("unsupported_speculation")
    for term in _INTERNAL_TERMS:
        if term.casefold() in lower:
            errors.append(f"internal_commentary:{term}")
    compact_report = _compact_text(normalized)
    for claim in reviewed_unsupported_claims:
        compact_claim = _compact_text(claim)
        if len(compact_claim) >= 8 and compact_claim in compact_report:
            errors.append("reviewed_unsupported_claim")
    for comment in reviewed_internal_commentary:
        compact_comment = _compact_text(comment)
        if len(compact_comment) >= 3 and compact_comment in compact_report:
            errors.append("reviewed_internal_commentary")

    allowed_citations = {
        str(item.get("evidence_id") or item.get("source_id") or "").strip()
        for item in evidence
    }
    allowed_citations.discard("")
    cited = set(_CITATION_RE.findall(normalized))
    for citation in cited:
        if citation not in allowed_citations:
            errors.append(f"unknown_citation:{citation}")
    if (
        allowed_citations
        and not cited.intersection(allowed_citations)
        and not any(
            str(item.get("status") or "succeeded") == "succeeded"
            and bool(item.get("rows"))
            for item in query_results
        )
    ):
        errors.append("missing_evidence_citation")
    if _cites_undisclosed_draft(normalized, evidence):
        errors.append("draft_status_omitted")
    if _uses_undisclosed_draft_query(
        normalized,
        query_results=query_results,
        source_revisions=source_revisions,
    ):
        errors.append("draft_status_omitted")
    if _has_citation_number_mismatch(normalized, evidence):
        errors.append("citation_source_mismatch")
    if _has_cross_row_numeric_mix(
        normalized,
        question=question,
        query_results=query_results,
    ):
        errors.append("cross_row_numeric_mix")
    if _has_universal_vehicle_claim_on_limited_result(
        normalized,
        query_results=query_results,
    ):
        errors.append("universal_claim_on_limited_result")

    report_literals = _NUMBER_RE.findall(_without_markdown_structure(normalized))
    allowed_numbers = _captured_numbers(
        question=question,
        query_results=query_results,
        evidence=evidence,
        requested_literals=report_literals,
    )
    for literal in report_literals:
        token = _number_token(literal)
        if (
            token is not None
            and token not in allowed_numbers
            and not _markdown_row_ordinal_allowed(
                markdown=normalized,
                literal=literal,
                max_ordinal=max(
                    (
                        len(
                            [
                                row
                                for row in item.get("rows") or ()
                                if isinstance(row, Mapping)
                            ]
                        )
                        for item in query_results
                    ),
                    default=0,
                ),
            )
            and not _citation_local_number_allowed(
                markdown=normalized,
                literal=literal,
                token=token,
                evidence=evidence,
            )
        ):
            errors.append(f"unsupported_number:{literal}")

    return ReportValidationResult(
        valid=not errors,
        errors=tuple(dict.fromkeys(errors)),
    )


def build_source_markdown_fallback(
    *,
    title: str,
    question: str,
    query_results: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    source_revisions: Sequence[Mapping[str, Any]] = (),
    capability_limitations: Sequence[str] = (),
    analysis_degraded: bool = False,
    max_query_tables: int = 5,
    max_rows_per_query: int = 10,
) -> str:
    """Render only captured values with a layout derived from available sources."""

    lines = [f"# {title.strip() or '과거차 문제점 분석 보고서'}", "", question.strip()]
    public_limitations = [
        " ".join(str(item).split()) for item in capability_limitations if str(item).strip()
    ]
    if public_limitations:
        lines.extend(["", "## 분석 가능 여부"])
        lines.extend(f"- {item}" for item in public_limitations)
        lines.extend(
            [
                "",
                "요청한 핵심 지표를 확인 가능한 데이터로 산출할 수 없어, "
                "유사한 지표나 날짜로 대체한 수치와 사례 분류는 제시하지 않았습니다.",
            ]
        )
        return "\n".join(lines).strip()

    if analysis_degraded:
        lines.extend(
            [
                "",
                "## 분석 상태",
                "자동 분석이 완전히 끝나지 않아 정형 수치는 결론에 사용하지 않고, "
                "현재 접근 가능한 원문 사례만 표시합니다.",
            ]
        )

    successful_queries = _select_fallback_queries(
        query_results,
        limit=max_query_tables,
    )
    if successful_queries:
        lines.extend(["", "## 정형 데이터"])
        if _contains_draft_revision(source_revisions):
            lines.extend(
                [
                    "",
                    "> 아래 정형 결과에는 작성 중 초안 데이터가 포함되어 있습니다.",
                ]
            )
        for item in successful_queries:
            heading = _fallback_query_heading(item)
            source_columns = [
                str(column)
                for column in item.get("columns") or []
                if str(column) not in _NON_PUBLIC_COLUMNS
            ]
            columns = [_COLUMN_LABELS.get(column, column) for column in source_columns]
            rows = [
                row for row in item.get("rows") or [] if isinstance(row, Mapping)
            ][:max_rows_per_query]
            lines.extend(["", f"### {heading}"])
            if source_columns and rows:
                public_rows = [
                    {
                        label: _public_cell_value(row.get(source_column))
                        for source_column, label in zip(
                            source_columns,
                            columns,
                            strict=True,
                        )
                    }
                    for row in rows
                ]
                lines.extend(_markdown_table(columns, public_rows))
            else:
                lines.append("조건에 맞는 정형 결과가 없습니다.")

    if evidence:
        lines.extend(["", "## 확인된 사례 근거"])
        for item in evidence:
            evidence_id = str(
                item.get("evidence_id") or item.get("source_id") or ""
            ).strip()
            title_value = str(item.get("title") or "근거").strip()
            excerpt = " ".join(str(item.get("excerpt") or "").split())
            citation = f" [{evidence_id}]" if evidence_id else ""
            metadata = item.get("metadata")
            revision_status = (
                str(metadata.get("revision_status") or "").strip().casefold()
                if isinstance(metadata, Mapping)
                else str(item.get("source_status") or "").strip().casefold()
            )
            status_label = (
                " (작성 중 초안)"
                if revision_status == "draft"
                else " (게시됨)"
                if revision_status == "published"
                else ""
            )
            lines.append(
                f"- {title_value}{status_label}{citation}: "
                f"{excerpt or '상세 근거 데이터 참조'}"
            )

    if not successful_queries and not evidence:
        lines.extend(
            [
                "",
                "## 확인 결과",
                "현재 접근 가능한 데이터에서 요청을 뒷받침할 근거를 확인하지 못했습니다.",
            ]
        )
    return "\n".join(lines).strip()


def _cites_undisclosed_draft(
    markdown: str,
    evidence: Sequence[Mapping[str, Any]],
) -> bool:
    cited = set(_CITATION_RE.findall(markdown))
    if not cited:
        return False
    draft_ids = {
        str(item.get("evidence_id") or item.get("source_id") or "").strip()
        for item in evidence
        if (
            isinstance(item.get("metadata"), Mapping)
            and str(item["metadata"].get("revision_status") or "").casefold()
            == "draft"
        )
        or str(item.get("source_status") or "").casefold() == "draft"
    }
    if not cited.intersection(draft_ids):
        return False
    normalized = markdown.casefold()
    return not any(term in normalized for term in ("작성 중", "초안", "draft"))


def _uses_undisclosed_draft_query(
    markdown: str,
    *,
    query_results: Sequence[Mapping[str, Any]],
    source_revisions: Sequence[Mapping[str, Any]],
) -> bool:
    if not _contains_draft_revision(source_revisions):
        return False
    if not any(
        str(item.get("status") or "succeeded") == "succeeded"
        and bool(item.get("rows"))
        for item in query_results
    ):
        return False
    normalized = markdown.casefold()
    return not any(term in normalized for term in ("작성 중", "초안", "draft"))


def _contains_draft_revision(
    source_revisions: Sequence[Mapping[str, Any]],
) -> bool:
    return any(
        str(item.get("status") or "").strip().casefold() == "draft"
        for item in source_revisions
    )


def _select_fallback_queries(
    query_results: Sequence[Mapping[str, Any]],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    candidates: list[tuple[int, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for index, item in enumerate(query_results):
        if str(item.get("status") or "succeeded") != "succeeded":
            continue
        signature = json.dumps(
            [
                item.get("recipe_id"),
                item.get("recipe_arguments"),
                item.get("columns"),
                item.get("rows"),
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        if signature in seen:
            continue
        seen.add(signature)
        candidates.append((index, item))
    candidates.sort(
        key=lambda pair: (
            not bool(pair[1].get("rows")),
            _FALLBACK_RECIPE_PRIORITY.get(str(pair[1].get("recipe_id") or ""), 3),
            -_fallback_scope_specificity(pair[1]),
            pair[0],
        )
    )
    return [item for _index, item in candidates[: max(1, limit)]]


def _fallback_scope_specificity(item: Mapping[str, Any]) -> int:
    arguments = item.get("recipe_arguments")
    if not isinstance(arguments, Mapping):
        return 0
    return sum(
        1
        for key, value in arguments.items()
        if key not in {"limit", "top_n", "sort_direction"}
        and value not in (None, "", [], ())
    )


def _fallback_query_heading(item: Mapping[str, Any]) -> str:
    heading = str(item.get("source_label") or item.get("title") or "조회 결과").strip()
    arguments = item.get("recipe_arguments")
    if not isinstance(arguments, Mapping):
        return heading
    descriptors: list[str] = []
    for key, prefix in (
        ("dimension", "기준"),
        ("row_dimension", "행"),
        ("column_dimension", "열"),
        ("detail_dimension", "세부"),
    ):
        value = str(arguments.get(key) or "").strip()
        if value:
            descriptors.append(f"{prefix}: {_DIMENSION_LABELS.get(value, value)}")
    for key, prefix in (
        ("date_from", "시작일"),
        ("date_to", "종료일"),
        ("vehicle_models", "차종"),
        ("regions", "권역"),
        ("module_keys", "모듈"),
        ("suppliers", "공급업체"),
        ("part_numbers", "부품번호"),
        ("checklist_statuses", "상태"),
    ):
        value = arguments.get(key)
        if value not in (None, "", [], ()):
            descriptors.append(f"{prefix}: {_public_argument_value(value)}")
    if arguments.get("supplier_missing") is True:
        descriptors.append("공급업체: 미입력")
    if arguments.get("part_number_missing") is True:
        descriptors.append("부품번호: 미입력")
    return f"{heading} ({' · '.join(descriptors)})" if descriptors else heading


def _public_argument_value(value: Any) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _public_cell_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if value is None or value == "":
        return "미입력"
    return value


def _captured_numbers(
    *,
    question: str,
    query_results: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    requested_literals: Sequence[str] = (),
) -> set[tuple[str, str]]:
    payloads: list[str] = [question]
    captured_numbers: set[tuple[str, str]] = set()
    arithmetic_groups: list[
        tuple[set[Decimal], set[Decimal], set[Decimal]]
    ] = []
    for item in query_results:
        for values in (
            item.get("params"),
            item.get("recipe_arguments"),
        ):
            if not isinstance(values, Mapping):
                continue
            for key in ("date_from", "date_to"):
                if key in values:
                    payloads.append(str(values[key]))
        rows = [row for row in item.get("rows") or () if isinstance(row, Mapping)]
        series_by_column: dict[str, list[Decimal]] = {}
        arithmetic_values: set[Decimal] = set()
        explicit_percent_values: set[Decimal] = set()
        for row in rows:
            for column, value in row.items():
                if isinstance(value, bool) or not isinstance(
                    value, (int, float, Decimal)
                ):
                    payloads.append(str(value if value is not None else ""))
                    continue
                try:
                    decimal_value = Decimal(str(value))
                except InvalidOperation:
                    continue
                kind = _numeric_column_kind(str(column))
                captured_numbers.add((kind, _decimal_text(decimal_value)))
                if kind == "scalar":
                    arithmetic_values.add(decimal_value)
                    if _is_count_column(str(column)):
                        series_by_column.setdefault(str(column), []).append(
                            decimal_value
                        )
                elif kind == "percent":
                    explicit_percent_values.add(decimal_value)
        prefix_eligible = str(item.get("recipe_id") or "") in {
            "issue_breakdown",
            "issue_trend",
            "issue_category_severity",
        }
        base_values = set(arithmetic_values)
        if prefix_eligible:
            for series in series_by_column.values():
                running_total = Decimal(0)
                for value in series:
                    running_total += value
                    base_values.add(running_total)
        delta_values = {
            left - right
            for series in series_by_column.values()
            for left in series
            for right in series
        }
        ratio_values: set[Decimal] = set(explicit_percent_values)
        if not explicit_percent_values:
            for numerator in base_values.union(delta_values):
                for denominator in base_values:
                    if denominator == 0:
                        continue
                    percentage = numerator * Decimal(100) / denominator
                    for precision in (0, 1, 2):
                        quantum = Decimal(1).scaleb(-precision)
                        ratio_values.add(
                            percentage.quantize(quantum, rounding=ROUND_HALF_UP)
                        )
        arithmetic_groups.append(
            (
                base_values,
                delta_values,
                ratio_values,
            )
        )
    numbers = set(captured_numbers)
    for payload in payloads:
        for match in _DATE_RE.finditer(payload):
            year, month, day = match.groups()
            numbers.add(("scalar", _canonical_number(year) or year))
            numbers.add(("scalar", _canonical_number(month) or month))
            numbers.add(
                ("scalar", _canonical_number(f"{year}.{month}") or f"{year}.{month}")
            )
            if day is not None:
                numbers.add(("scalar", _canonical_number(day) or day))
        without_dates = _DATE_RE.sub(" ", payload)
        for literal in _NUMBER_RE.findall(without_dates):
            token = _number_token(literal)
            if token is not None:
                numbers.add(token)
    for literal in requested_literals:
        token = _number_token(literal)
        if token is None:
            continue
        kind, canonical = token
        target = Decimal(canonical)
        if kind == "scalar" and any(
            target in base_values or target in delta_values
            for base_values, delta_values, _ratios in arithmetic_groups
        ):
            numbers.add(token)
            continue
        if kind == "scalar":
            continue
        if kind == "percent" and any(
            target in ratio_values
            for _base, _delta, ratio_values in arithmetic_groups
        ):
            numbers.add(token)
            continue
        if kind == "percentage_point" and any(
            any(left - target in ratio_values for left in ratio_values)
            for _base, _delta, ratio_values in arithmetic_groups
        ):
            numbers.add(token)
    return numbers


def _markdown_row_ordinal_allowed(
    *,
    markdown: str,
    literal: str,
    max_ordinal: int,
) -> bool:
    canonical = _canonical_number(literal)
    if canonical is None:
        return False
    try:
        ordinal = int(Decimal(canonical))
    except (InvalidOperation, ValueError):
        return False
    if ordinal < 1 or ordinal > min(max_ordinal, 50):
        return False
    lines = markdown.splitlines()
    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.count("|") < 3:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or _canonical_number(cells[0]) != canonical:
            continue
        table_start = line_index
        while table_start > 0 and lines[table_start - 1].strip().startswith("|"):
            table_start -= 1
        header_cells = [
            cell.strip()
            for cell in lines[table_start].strip().strip("|").split("|")
        ]
        if not header_cells or header_cells[0].casefold() not in {"순위", "rank"}:
            continue
        data_index = line_index - table_start - 1
        if data_index == ordinal:
            return True
    return False


def _citation_local_number_allowed(
    *,
    markdown: str,
    literal: str,
    token: tuple[str, str],
    evidence: Sequence[Mapping[str, Any]],
) -> bool:
    evidence_by_id = {
        str(item.get("evidence_id") or item.get("source_id") or "").strip(): item
        for item in evidence
    }
    lines = markdown.splitlines()
    for line_index, line in enumerate(lines):
        if literal not in line:
            continue
        block = _markdown_list_item_block(lines, line_index)
        citations = _CITATION_RE.findall("\n".join(block))
        for citation in citations:
            source = evidence_by_id.get(citation)
            if source is None:
                continue
            source_text = " ".join(
                (
                    str(source.get("title") or ""),
                    str(source.get("excerpt") or ""),
                )
            )
            if token in {
                parsed
                for value in _NUMBER_RE.findall(source_text)
                if (parsed := _number_token(value)) is not None
            }:
                return True
    return False


def _has_citation_number_mismatch(
    markdown: str,
    evidence: Sequence[Mapping[str, Any]],
) -> bool:
    evidence_numbers = {
        str(item.get("evidence_id") or item.get("source_id") or "").strip(): {
            token
            for value in _NUMBER_RE.findall(
                " ".join(
                    (
                        str(item.get("title") or ""),
                        str(item.get("excerpt") or ""),
                    )
                )
            )
            if (token := _number_token(value)) is not None
        }
        for item in evidence
    }
    for line in markdown.splitlines():
        citations = _CITATION_RE.findall(line)
        if not citations:
            continue
        business_line = re.sub(
            r"^\s*(?:[-*+]|\d+[.)])\s+",
            "",
            line,
        )
        line_numbers = {
            token
            for value in _NUMBER_RE.findall(_CITATION_RE.sub("", business_line))
            if (token := _number_token(value)) is not None
        }
        if line_numbers and not line_numbers.issubset(
            set().union(*(evidence_numbers.get(item, set()) for item in citations))
        ):
            return True
    return False


def _markdown_list_item_block(lines: Sequence[str], line_index: int) -> list[str]:
    bullet_re = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+")
    nearest_start: int | None = None
    nearest_indent: int | None = None
    evidence_start: int | None = None
    evidence_indent: int | None = None
    for index in range(line_index, -1, -1):
        match = bullet_re.match(lines[index])
        if match is None:
            continue
        indent = len(match.group(1).expandtabs(4))
        if nearest_start is None:
            nearest_start = index
            nearest_indent = indent
        if (
            nearest_indent is not None
            and indent <= nearest_indent
            and re.search(r"(?:\[|\b)E\d+\]?", lines[index], re.IGNORECASE)
        ):
            evidence_start = index
            evidence_indent = indent
            break
        nearest_indent = min(nearest_indent or indent, indent)
    start = evidence_start if evidence_start is not None else nearest_start
    base_indent = evidence_indent if evidence_indent is not None else nearest_indent
    if start is None or base_indent is None:
        return [lines[line_index]]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].lstrip().startswith("#"):
            end = index
            break
        match = bullet_re.match(lines[index])
        if match is not None and len(match.group(1).expandtabs(4)) <= base_indent:
            end = index
            break
    return list(lines[start:end])


def _has_cross_row_numeric_mix(
    markdown: str,
    *,
    question: str,
    query_results: Sequence[Mapping[str, Any]],
) -> bool:
    question_tokens = {
        token
        for value in _NUMBER_RE.findall(question)
        if (token := _number_token(value)) is not None
    }
    fact_rows: list[tuple[set[str], set[tuple[str, str]]]] = []
    for item in query_results:
        if str(item.get("status") or "succeeded") != "succeeded":
            continue
        for row in item.get("rows") or ():
            if not isinstance(row, Mapping):
                continue
            labels = {
                str(value).strip().casefold()
                for value in row.values()
                if isinstance(value, str)
                and len(str(value).strip()) >= 2
                and _number_token(str(value).strip()) is None
            }
            numbers = {
                (
                    _numeric_column_kind(str(column)),
                    _decimal_text(Decimal(str(value))),
                )
                for column, value in row.items()
                if isinstance(value, (int, float, Decimal))
                and not isinstance(value, bool)
            }
            numbers.update(
                token
                for value in row.values()
                if isinstance(value, str)
                for literal in _NUMBER_RE.findall(value)
                if (token := _number_token(literal)) is not None
            )
            if labels and numbers:
                fact_rows.append((labels, numbers))
    lines = markdown.splitlines()
    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or set(stripped) <= {"|", "-", ":", " "}:
            continue
        business_line = re.sub(
            r"^\s*(?:[-*+]|\d+[.)])\s+",
            "",
            line,
        )
        line_numbers = {
            token
            for value in _NUMBER_RE.findall(_CITATION_RE.sub("", business_line))
            if (token := _number_token(value)) is not None
        }
        if not line_numbers:
            continue
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and _markdown_row_ordinal_allowed(
                markdown=markdown,
                literal=cells[0],
                max_ordinal=50,
            ):
                ordinal_token = _number_token(cells[0])
                if ordinal_token is not None:
                    line_numbers.discard(ordinal_token)
        normalized_line = line.casefold()
        candidates = [
            numbers
            for labels, numbers in fact_rows
            if any(label in normalized_line for label in labels)
        ]
        if candidates and not any(
            line_numbers.issubset(numbers | question_tokens)
            for numbers in candidates
        ):
            return True
    return False


def _has_universal_vehicle_claim_on_limited_result(
    markdown: str,
    *,
    query_results: Sequence[Mapping[str, Any]],
) -> bool:
    if not re.search(
        r"(?:모든|전체|전)\s*(?:분석\s*대상\s*)?차종|전\s*차종",
        markdown,
    ):
        return False
    for item in query_results:
        arguments = item.get("recipe_arguments")
        if not isinstance(arguments, Mapping):
            continue
        if str(arguments.get("dimension") or "") != "vehicle_model":
            continue
        limit = arguments.get("limit") or arguments.get("top_n")
        row_count = item.get("row_count")
        if (
            isinstance(limit, int)
            and not isinstance(limit, bool)
            and isinstance(row_count, int)
            and row_count >= limit
        ):
            return True
    return False


def sanitize_report_markdown(
    markdown: str,
    *,
    errors: Sequence[str],
) -> str:
    """Remove only lines that contain validator-identified unsupported literals."""

    literals = [
        error.partition(":")[2]
        for error in errors
        if error.startswith("unsupported_number:") and error.partition(":")[2]
    ]
    if not markdown.strip() or not literals:
        return markdown.strip()
    retained = [
        line
        for line in markdown.splitlines()
        if not any(literal in line for literal in literals)
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(retained)).strip()


def _number_token(value: str) -> tuple[str, str] | None:
    canonical = _canonical_number(value)
    if canonical is None:
        return None
    normalized = value.casefold()
    if normalized.endswith("%p"):
        return ("percentage_point", canonical)
    if normalized.endswith("%"):
        return ("percent", canonical)
    return ("scalar", canonical)


def _canonical_number(value: str) -> str | None:
    stripped = value.replace(",", "").rstrip("%pP")
    try:
        decimal = Decimal(stripped)
    except InvalidOperation:
        return None
    return format(decimal.normalize(), "f")


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _numeric_column_kind(column: str) -> str:
    normalized = column.casefold()
    if "percentage_point" in normalized or normalized.endswith("_pp"):
        return "percentage_point"
    if any(
        marker in normalized
        for marker in ("rate", "ratio", "percent", "percentage", "share")
    ):
        return "percent"
    return "scalar"


def _is_count_column(column: str) -> bool:
    normalized = column.casefold()
    return normalized == "count" or normalized.endswith("_count")


def _without_markdown_structure(markdown: str) -> str:
    text = _INTERNAL_SOURCE_ID_RE.sub("", markdown)
    text = _INTERNAL_SOURCE_LABEL_RE.sub("", text)
    text = re.sub(
        r"(?m)^\s*#{1,6}\s+(?:\d+(?:\.\d+)*(?:[.)])?\s+)?",
        "",
        text,
    )
    text = re.sub(r"\[[A-Z][A-Z0-9_-]*\d+\]", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", "", text)
    return text


def _requests_table(question: str) -> bool:
    normalized = "".join(str(question or "").casefold().split())
    return any(term in normalized for term in ("표로", "표를", "표형태", "테이블"))


def _compact_text(value: Any) -> str:
    return "".join(str(value or "").casefold().split())


def _markdown_table(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    safe_columns = [_escape_cell(column) for column in columns]
    lines = [
        "| " + " | ".join(safe_columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(_escape_cell(row.get(column)) for column in columns)
            + " |"
        )
    return lines


def _escape_cell(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split()).replace("|", "\\|")


__all__ = [
    "ReportValidationResult",
    "build_source_markdown_fallback",
    "sanitize_report_markdown",
    "validate_report_markdown",
]
