from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ai_do_api.domains.legacy_issues.ai_evidence_payload import (
    selected_legacy_issue_evidence_values,
)
from ai_do_api.domains.legacy_issues.ai_search import LegacyIssueEvidence


_REPORT_ROW_LIMIT = 40
_FAMILY_TITLES = {
    "total_count": "전체 건수",
    "filtered_count": "조건별 건수",
    "distinct_count": "고유값 현황",
    "missing_populated_rate": "입력 품질",
    "single_distribution": "항목별 분포",
    "multidim_breakdown": "복합 분포",
    "share": "구성비",
    "top_bottom_n": "상위 항목",
    "top_n_within_parent": "그룹별 상위 항목",
    "severity": "중요도 분포",
    "time_series": "기간별 추이",
}


def render_grounded_legacy_issue_report(
    *,
    analysis_result: Mapping[str, Any] | None,
    evidence: Iterable[LegacyIssueEvidence],
    analysis_degraded: bool = False,
) -> str:
    """Render a report from server-owned facts without model-authored claims."""

    evidence_rows = list(evidence)
    lines = [
        "# 과거차 문제점 분석 보고서",
        "",
        "> 정형 집계 결과와 사례 근거를 바탕으로 작성한 검토용 초안입니다.",
        "",
        "## 1. 분석 범위",
        "",
    ]
    if analysis_result is None:
        lines.append("- 안전하게 확정된 정형 집계가 없습니다.")
    else:
        lines.extend(_scope_lines(analysis_result))
        if analysis_degraded:
            lines.extend(
                [
                    "- 현재 보고서에 표시된 데이터 범위와 집계 항목만 포함합니다.",
                    "- 확인되지 않은 항목은 제외했으며 추정값을 사용하지 않았습니다.",
                ]
            )

    lines.extend(["", "## 2. 핵심 요약", ""])
    summary_lines = _summary_lines(analysis_result)
    lines.extend(summary_lines or ["- 요약 가능한 정형 집계가 없습니다."])

    lines.extend(["", "## 3. 정형 집계", ""])
    queries = _queries(analysis_result)
    if not queries:
        lines.append("- 정형 집계 결과가 없습니다.")
    for index, query in enumerate(queries, start=1):
        lines.extend(_query_section(query, index=index))

    lines.extend(["", "## 4. 사례 근거", ""])
    if not evidence_rows:
        lines.append(
            "- 이번 보고서에는 의미 검색 사례가 포함되지 않았습니다. 정형 집계 수치와 "
            "사례 근거를 서로 대체해 해석하지 마세요."
        )
    else:
        lines.extend(_evidence_lines(evidence_rows))

    lines.extend(["", "## 5. 검토 권고", ""])
    lines.extend(_recommendation_lines(analysis_result, has_evidence=bool(evidence_rows)))
    lines.extend(
        [
            "",
            "## 6. 해석 유의사항",
            "",
            "- `원천 건수`는 허용된 전체 데이터 범위이고, 필터 후 모집단 및 그룹화 가능 "
            "모집단은 각 집계의 범위 정보로 구분합니다.",
            "- `미입력`과 형식 오류는 해당 필드의 데이터 품질이며 다른 필드의 결측치로 "
            "바꾸어 해석하지 않습니다.",
            "- 사례 근거 `[E#]`는 검색된 개별 사례이며 전체 모집단 통계를 의미하지 않습니다.",
            "- 근거 데이터에 없는 문서 메타데이터나 분석 기준 시점은 표시하지 않습니다.",
        ]
    )
    return "\n".join(lines).strip()


def grounded_report_direct_response() -> str:
    return (
        "확인된 데이터 범위로 검토용 보고서를 생성했습니다. "
        "주요 내용은 보고서에서 확인할 수 있으며 상세 집계와 사례 근거도 함께 제공합니다."
    )


def _scope_lines(analysis_result: Mapping[str, Any]) -> list[str]:
    scope = analysis_result.get("scope")
    scope = scope if isinstance(scope, Mapping) else {}
    lines: list[str] = []
    source_counts = scope.get("source_counts")
    if isinstance(source_counts, Mapping) and source_counts:
        rendered = ", ".join(
            f"{_source_label(str(key))} {_format_number(value)}건"
            for key, value in source_counts.items()
            if _is_number(value)
        )
        if rendered:
            lines.append(f"- 데이터 원천: {rendered}")
    elif _is_number(scope.get("source_count")):
        lines.append(f"- 허용된 원천 건수: {_format_number(scope['source_count'])}건")

    exactness = str(analysis_result.get("exactness") or "")
    if exactness == "exact":
        lines.append("- 집계 기준: 등록 데이터의 유효값 기준")
    elif exactness:
        lines.append("- 집계 기준: 제공된 분석 결과 기준(업무 검토 필요)")
    return lines or ["- 분석 범위 정보가 제공되지 않았습니다."]


def _summary_lines(
    analysis_result: Mapping[str, Any] | None,
) -> list[str]:
    queries = _queries(analysis_result)
    summaries: list[str] = []
    total_query = next(
        (query for query in queries if query.get("family_id") == "total_count"),
        None,
    )
    total_value = _first_metric_value(total_query)
    if _is_number(total_value):
        summaries.append(f"- 전체 문제 건수: **{_format_number(total_value)}건**")

    severity = next(
        (query for query in queries if query.get("family_id") == "severity"),
        None,
    )
    severity_text = _distribution_summary(severity, limit=6)
    if severity_text:
        summaries.append(f"- 중요도 분포: {severity_text}")

    top_query = next(
        (query for query in queries if query.get("family_id") == "top_bottom_n"),
        None,
    )
    top_text = _distribution_summary(top_query, limit=5)
    if top_text:
        summaries.append(f"- 상위 항목: {top_text}")

    time_query = next(
        (query for query in queries if query.get("family_id") == "time_series"),
        None,
    )
    peak = _peak_summary(time_query)
    if peak:
        summaries.append(f"- 입력된 기간값 기준 최다 구간: {peak}")

    for label, present, missing, invalid in _coverage_facts(queries)[:4]:
        denominator = present + missing + invalid
        rate = (present / denominator * 100) if denominator else 0.0
        suffix = f", 형식 오류 {invalid:,}건" if invalid else ""
        summaries.append(
            f"- {label}: 입력 {present:,}건 / 미입력 {missing:,}건"
            f"{suffix} / 입력률 {rate:.2f}%"
        )
    return summaries


def _query_section(query: Mapping[str, Any], *, index: int) -> list[str]:
    family_id = str(query.get("family_id") or "")
    title = _FAMILY_TITLES.get(family_id) or str(
        query.get("title") or query.get("id") or f"집계 {index}"
    )
    lines = [f"### 3.{index} {_escape_text(title)}", ""]
    totals = query.get("totals")
    if isinstance(totals, Mapping):
        population_bits = []
        for key, label in (
            ("filtered_population_count", "필터 후 모집단"),
            ("population_count", "그룹화 가능 모집단"),
        ):
            value = totals.get(key)
            if _is_number(value):
                population_bits.append(f"{label} {_format_number(value)}건")
        if population_bits:
            lines.extend([f"- 범위: {', '.join(population_bits)}", ""])

    rows = query.get("rows")
    rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    columns = query.get("columns")
    columns = (
        [column for column in columns if isinstance(column, Mapping)]
        if isinstance(columns, list)
        else []
    )
    if rows:
        lines.extend(_markdown_table(columns=columns, rows=rows[:_REPORT_ROW_LIMIT]))
        if len(rows) > _REPORT_ROW_LIMIT or query.get("truncated") is True:
            lines.extend(["", "- 표시 한도에 따라 일부 행만 보고서에 포함했습니다."])
    else:
        lines.append("- 결과 행이 없습니다.")

    coverage = query.get("coverage")
    if isinstance(coverage, list) and coverage:
        lines.extend(["", "데이터 품질:"])
        for item in coverage:
            if not isinstance(item, Mapping):
                continue
            label = _escape_text(str(item.get("label") or item.get("field_key") or "필드"))
            present = _as_nonnegative_int(item.get("present_count"))
            missing = _as_nonnegative_int(item.get("missing_count"))
            invalid = _as_nonnegative_int(item.get("invalid_count"))
            lines.append(
                f"- {label}: 입력 {present:,}건, 미입력 {missing:,}건, "
                f"형식 오류 {invalid:,}건"
            )
    warnings = query.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            if isinstance(warning, str) and warning.strip():
                lines.append(f"- 주의: {_escape_text(warning)}")
    lines.append("")
    return lines


def _markdown_table(
    *,
    columns: list[Mapping[str, Any]],
    rows: list[Mapping[str, Any]],
) -> list[str]:
    keys = [
        str(column.get("key"))
        for column in columns
        if isinstance(column.get("key"), str)
    ]
    if not keys and rows:
        keys = [str(key) for key in rows[0].keys()]
    labels = {
        str(column.get("key")): str(column.get("label") or column.get("key"))
        for column in columns
        if isinstance(column.get("key"), str)
    }
    value_types = {
        str(column.get("key")): str(column.get("type") or "")
        for column in columns
        if isinstance(column.get("key"), str)
    }
    header = "| " + " | ".join(_escape_cell(labels.get(key, key)) for key in keys) + " |"
    divider = "| " + " | ".join("---" for _ in keys) + " |"
    body = [
        "| "
        + " | ".join(
            _escape_cell(_format_cell(row.get(key), value_type=value_types.get(key)))
            for key in keys
        )
        + " |"
        for row in rows
    ]
    return [header, divider, *body]


def _evidence_lines(evidence: list[LegacyIssueEvidence]) -> list[str]:
    lines = [
        "| 근거 | 데이터셋 | 레코드 | 사례 |",
        "| --- | --- | --- | --- |",
    ]
    for item in evidence[:12]:
        values = selected_legacy_issue_evidence_values(
            item.values,
            plan=None,
            matched_field_keys=item.matched_fields,
        )
        summary_parts = []
        for key in (
            "vehicle_model",
            "severity_grade",
            "problem",
            "symptom",
            "cause",
            "countermeasure",
        ):
            value = values.get(key)
            if value not in (None, ""):
                summary_parts.append(f"{key}: {value}")
            if len(summary_parts) >= 3:
                break
        summary = " / ".join(summary_parts) or item.label
        record_id = item.stable_record_id or item.record_id
        lines.append(
            "| "
            + " | ".join(
                (
                    _escape_cell(f"[{item.evidence_id}]"),
                    _escape_cell(item.dataset_title),
                    _escape_cell(record_id),
                    _escape_cell(summary),
                )
            )
            + " |"
        )
    return lines


def _recommendation_lines(
    analysis_result: Mapping[str, Any] | None,
    *,
    has_evidence: bool,
) -> list[str]:
    queries = _queries(analysis_result)
    coverage = sorted(
        _coverage_facts(queries),
        key=lambda item: (item[2] + item[3], item[0]),
        reverse=True,
    )
    quality_issues = [item for item in coverage if item[2] + item[3] > 0]
    lines: list[str] = []
    if quality_issues:
        labels = ", ".join(item[0] for item in quality_issues[:3])
        lines.append(
            f"- 데이터 품질: 결측 또는 형식 오류가 확인된 `{_escape_text(labels)}` 필드의 "
            "원본 보완 우선순위를 검토하세요."
        )
    if any(query.get("family_id") == "top_bottom_n" for query in queries):
        lines.append(
            "- 집중 검토: 상위 항목부터 관련 원인·대책 사례를 확인하되, 순위 자체를 "
            "인과관계로 해석하지 마세요."
        )
    if any(query.get("family_id") == "time_series" for query in queries):
        lines.append(
            "- 추이 검토: 기간별 수치는 해당 날짜 필드가 유효한 행만 반영될 수 있으므로 "
            "같은 집계의 입력 품질과 함께 판단하세요."
        )
    if has_evidence:
        lines.append(
            "- 사례 확인: 의사결정 전 `[E#]` 근거 행의 원본 레코드에서 원인과 개선대책을 "
            "재확인하세요."
        )
    return lines or ["- 추가 조치 제안은 현재 근거만으로 확정하지 않았습니다."]


def _distribution_summary(
    query: Mapping[str, Any] | None,
    *,
    limit: int,
) -> str | None:
    if query is None:
        return None
    rows = query.get("rows")
    if not isinstance(rows, list):
        return None
    columns = query.get("columns")
    columns = columns if isinstance(columns, list) else []
    dimension_keys = [
        str(column.get("key"))
        for column in columns
        if isinstance(column, Mapping) and column.get("role") == "dimension"
    ]
    metric_keys = [
        str(column.get("key"))
        for column in columns
        if isinstance(column, Mapping) and column.get("role") == "metric"
    ]
    if not dimension_keys or not metric_keys:
        return None
    rendered = []
    for row in rows[:limit]:
        if not isinstance(row, Mapping):
            continue
        label = " / ".join(str(row.get(key, "-")) for key in dimension_keys)
        value = row.get(metric_keys[0])
        if _is_number(value):
            rendered.append(f"{_escape_text(label)} {_format_number(value)}건")
    return ", ".join(rendered) or None


def _peak_summary(query: Mapping[str, Any] | None) -> str | None:
    if query is None:
        return None
    rows = query.get("rows")
    columns = query.get("columns")
    if not isinstance(rows, list) or not isinstance(columns, list):
        return None
    dimension_keys = [
        str(column.get("key"))
        for column in columns
        if isinstance(column, Mapping) and column.get("role") == "dimension"
    ]
    metric_keys = [
        str(column.get("key"))
        for column in columns
        if isinstance(column, Mapping) and column.get("role") == "metric"
    ]
    if not dimension_keys or not metric_keys:
        return None
    candidates = [
        row
        for row in rows
        if isinstance(row, Mapping) and _is_number(row.get(metric_keys[0]))
    ]
    if not candidates:
        return None
    peak = max(candidates, key=lambda row: float(row[metric_keys[0]]))
    period = " / ".join(str(peak.get(key, "-")) for key in dimension_keys)
    return f"{_escape_text(period)} · {_format_number(peak[metric_keys[0]])}건"


def _coverage_facts(
    queries: list[Mapping[str, Any]],
) -> list[tuple[str, int, int, int]]:
    facts: list[tuple[str, int, int, int]] = []
    seen: set[tuple[str, int, int, int]] = set()
    for query in queries:
        coverage = query.get("coverage")
        if not isinstance(coverage, list):
            continue
        for item in coverage:
            if not isinstance(item, Mapping):
                continue
            field_key = str(item.get("field_key") or "")
            present = _as_nonnegative_int(item.get("present_count"))
            missing = _as_nonnegative_int(item.get("missing_count"))
            invalid = _as_nonnegative_int(item.get("invalid_count"))
            identity = (field_key, present, missing, invalid)
            if identity in seen:
                continue
            seen.add(identity)
            facts.append(
                (
                    str(item.get("label") or field_key or "필드"),
                    present,
                    missing,
                    invalid,
                )
            )
    return facts


def _queries(
    analysis_result: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    if analysis_result is None:
        return []
    queries = analysis_result.get("queries")
    if not isinstance(queries, list):
        return []
    return [query for query in queries if isinstance(query, Mapping)]


def _first_metric_value(query: Mapping[str, Any] | None) -> Any:
    if query is None:
        return None
    rows = query.get("rows")
    columns = query.get("columns")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], Mapping):
        return None
    metric_keys = [
        str(column.get("key"))
        for column in columns
        if isinstance(column, Mapping) and column.get("role") == "metric"
    ] if isinstance(columns, list) else []
    if metric_keys:
        return rows[0].get(metric_keys[0])
    return next((value for value in rows[0].values() if _is_number(value)), None)


def _source_label(source: str) -> str:
    return {
        "legacy_issues": "과거차 문제",
        "vehicle_checklists": "차량 체크리스트",
    }.get(source, source)


def _format_cell(value: Any, *, value_type: str | None) -> str:
    if value is None:
        return "-"
    if _is_number(value):
        rendered = _format_number(value)
        return f"{rendered}%" if value_type == "percent" else rendered
    return str(value)


def _format_number(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_nonnegative_int(value: Any) -> int:
    if _is_number(value):
        return max(0, int(value))
    return 0


def _escape_cell(value: Any) -> str:
    return _escape_text(str(value)).replace("\n", " ")


def _escape_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").strip()


__all__ = [
    "grounded_report_direct_response",
    "render_grounded_legacy_issue_report",
]
