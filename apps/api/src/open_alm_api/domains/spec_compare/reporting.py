from __future__ import annotations

from collections import Counter
import json
import logging
import re

from sqlalchemy.orm import Session

from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.domains.ai.gateway import (
    LlmWorkloadContext,
    execute_llm,
)
from open_alm_api.domains.document_processing import DocumentExtractBundle
from open_alm_api.domains.spec_compare import (
    SPEC_COMPARE_APP_ID,
    SPEC_COMPARE_REPORT_TASK_KIND,
    SPEC_COMPARE_REPORT_WORKLOAD_ID,
)
from open_alm_api.domains.spec_compare.contracts import (
    ComparisonRow,
    RowStatus,
    SpecCompareCancelled,
    _compact_value,
    _key_similarity,
    _normalize_key,
    _normalize_value,
)
from open_alm_api.domains.spec_compare.extraction import (
    _GENERIC_TABLE_KEY_RE,
    _HEADING_ONLY_RE,
    _INDEXED_TABLE_KEY_RE,
    _MEASUREMENT_UNIT_RE,
    _NUMERIC_OR_UNIT_RE,
    _PART_NUMBER_RE,
    _REPORT_KEYWORD_RE,
)


logger = logging.getLogger(__name__)

_CURATION_THRESHOLD_ROWS = 120
_MAX_REPORT_ROWS = 160
_MAX_ONLY_IN_REPORT_ROWS = 30


def curate_report_rows(rows: list[ComparisonRow]) -> list[ComparisonRow]:
    """Keep exhaustive small results, but curate noisy large extraction outputs for the UI."""
    if len(rows) <= _CURATION_THRESHOLD_ROWS:
        return rows

    rows = _promote_similar_only_in_pairs(_drop_redundant_only_in_pairs(rows))
    candidates: list[ComparisonRow] = []
    for row in rows:
        normalized = _row_with_equivalent_values_fixed(row)
        if normalized.status == "same":
            continue
        if _is_low_value_report_row(normalized):
            continue
        candidates.append(normalized)

    ranked = _dedupe_report_rows(sorted(candidates, key=_report_row_rank))
    different_rows = [row for row in ranked if row.status == "different"]
    only_in_rows = [row for row in ranked if row.status in {"base_only", "target_only"}]
    unknown_rows = [row for row in ranked if row.status == "unknown"]
    remaining = max(0, _MAX_REPORT_ROWS - len(different_rows))
    only_limit = min(_MAX_ONLY_IN_REPORT_ROWS, remaining)
    unknown_limit = max(0, remaining - only_limit)
    return [
        *different_rows[:_MAX_REPORT_ROWS],
        *only_in_rows[:only_limit],
        *unknown_rows[:unknown_limit],
    ]


def build_raw_summary(
    raw_rows: list[ComparisonRow],
    *,
    display_rows: list[ComparisonRow],
) -> dict[str, object]:
    raw_counts = Counter(row.status for row in raw_rows)
    return {
        "raw_total_rows": len(raw_rows),
        "raw_same": raw_counts.get("same", 0),
        "raw_different": raw_counts.get("different", 0),
        "raw_base_only": raw_counts.get("base_only", 0),
        "raw_target_only": raw_counts.get("target_only", 0),
        "raw_unknown": raw_counts.get("unknown", 0),
        "display_rows": len(display_rows),
        "filtered_rows": max(0, len(raw_rows) - len(display_rows)),
    }


def build_summary(
    rows: list[ComparisonRow],
    base_bundle: DocumentExtractBundle,
    target_bundle: DocumentExtractBundle,
) -> dict[str, object]:
    counts = Counter(row.status for row in rows)
    return {
        "total_rows": len(rows),
        "same": counts.get("same", 0),
        "different": counts.get("different", 0),
        "base_only": counts.get("base_only", 0),
        "target_only": counts.get("target_only", 0),
        "unknown": counts.get("unknown", 0),
        "base_evidence_blocks": len(base_bundle.evidence_blocks),
        "target_evidence_blocks": len(target_bundle.evidence_blocks),
    }


def render_markdown_report(
    *,
    rows: list[ComparisonRow],
    summary: dict[str, object],
    base_filename: str,
    target_filename: str,
) -> str:
    lines = [
        "# 규격서 비교 보고서",
        "",
        "## 비교 대상",
        "",
        f"- 기준 문서: {base_filename}",
        f"- 비교 문서: {target_filename}",
        "",
        "## 요약",
        "",
        "| 항목 | 수량 |",
        "| --- | ---: |",
        f"| 보고서 표시 항목 | {summary['total_rows']} |",
        f"| 동일 | {summary['same']} |",
        f"| 상이 | {summary['different']} |",
        f"| 기준 문서에만 있음 | {summary['base_only']} |",
        f"| 비교 문서에만 있음 | {summary['target_only']} |",
        f"| 판단 보류 | {summary['unknown']} |",
        "",
        "## 상세 비교표",
        "",
        "| 판정 | 사양 항목 | 기준 문서 | 비교 문서 | 설명 | 근거 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        evidence = ", ".join([*row.base_evidence_ids, *row.target_evidence_ids])
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(_status_label(row.status)),
                    _md_cell(row.spec_name),
                    _md_cell(row.base_value),
                    _md_cell(row.target_value),
                    _md_cell(row.summary),
                    _md_cell(evidence),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 추출 감사",
            "",
            f"- 기준 문서 근거 블록: {summary['base_evidence_blocks']}개",
            f"- 비교 문서 근거 블록: {summary['target_evidence_blocks']}개",
        ]
    )
    if "raw_total_rows" in summary:
        lines.extend(
            [
                f"- 원시 비교 후보: {summary['raw_total_rows']}개",
                f"- 보고서 필터 제외: {summary['filtered_rows']}개",
            ]
        )
    return "\n".join(lines)


def enrich_markdown_report_with_llm(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    report_markdown: str,
    rows: list[ComparisonRow],
    summary: dict[str, object],
) -> str:
    if not rows:
        return report_markdown
    try:
        section = _render_report_analysis_with_llm(
            db,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            rows=rows,
            summary=summary,
        )
    except SpecCompareCancelled:
        raise
    except Exception:
        logger.exception("spec_compare: LLM report enrichment failed")
        return report_markdown
    if not section:
        return report_markdown
    marker = "\n## 상세 비교표"
    if marker not in report_markdown:
        return f"{report_markdown}\n\n{section}"
    return report_markdown.replace(marker, f"\n{section}\n{marker}", 1)


def _drop_redundant_only_in_pairs(rows: list[ComparisonRow]) -> list[ComparisonRow]:
    base_only_keys = {
        _only_in_equivalence_key(row)
        for row in rows
        if row.status == "base_only" and _only_in_equivalence_key(row)
    }
    target_only_keys = {
        _only_in_equivalence_key(row)
        for row in rows
        if row.status == "target_only" and _only_in_equivalence_key(row)
    }
    redundant = base_only_keys & target_only_keys
    if not redundant:
        return rows
    return [
        row
        for row in rows
        if row.status not in {"base_only", "target_only"}
        or _only_in_equivalence_key(row) not in redundant
    ]


def _only_in_equivalence_key(row: ComparisonRow) -> str:
    value = row.base_value or row.target_value or row.spec_name
    return _compact_value(_strip_leading_numbering(value))


def _promote_similar_only_in_pairs(rows: list[ComparisonRow]) -> list[ComparisonRow]:
    base_rows = [row for row in rows if row.status == "base_only"]
    target_rows = [row for row in rows if row.status == "target_only"]
    existing_pairs = {
        (_compact_value(row.base_value), _compact_value(row.target_value))
        for row in rows
        if row.status == "different" and row.base_value and row.target_value
    }
    used_base: set[int] = set()
    used_target: set[int] = set()
    promoted: list[ComparisonRow] = []

    for base_index, base in enumerate(base_rows):
        if _is_pairing_noise(base):
            continue
        best: tuple[int, ComparisonRow, float] | None = None
        for target_index, target in enumerate(target_rows):
            if target_index in used_target or _is_pairing_noise(target):
                continue
            score = _key_similarity(base.spec_name, target.spec_name)
            if score < 0.9:
                continue
            if best is None or score > best[2]:
                best = (target_index, target, score)
        if best is None:
            continue
        target_index, target, _score = best
        used_base.add(base_index)
        used_target.add(target_index)
        status: RowStatus = (
            "same"
            if _normalize_value(base.base_value) == _normalize_value(target.target_value)
            else "different"
        )
        pair_key = (_compact_value(base.base_value), _compact_value(target.target_value))
        if status == "different" and pair_key in existing_pairs:
            used_base.add(base_index)
            used_target.add(target_index)
            continue
        promoted.append(
            ComparisonRow(
                spec_name=(
                    base.spec_name
                    if _normalize_key(base.spec_name) == _normalize_key(target.spec_name)
                    else f"{base.spec_name} / {target.spec_name}"
                ),
                base_value=base.base_value,
                target_value=target.target_value,
                status=status,
                summary=(
                    "유사 항목으로 자동 대응했으며 값은 동일합니다."
                    if status == "same"
                    else "유사 항목으로 자동 대응했으며 값이 다릅니다."
                ),
                base_evidence_ids=base.base_evidence_ids,
                target_evidence_ids=target.target_evidence_ids,
            )
        )

    output = [row for row in rows if row.status not in {"base_only", "target_only"}]
    output.extend(promoted)
    output.extend(row for index, row in enumerate(base_rows) if index not in used_base)
    output.extend(row for index, row in enumerate(target_rows) if index not in used_target)
    return output


def _is_pairing_noise(row: ComparisonRow) -> bool:
    name = row.spec_name.strip()
    return bool(_GENERIC_TABLE_KEY_RE.search(name) or _INDEXED_TABLE_KEY_RE.search(name))


def _row_with_equivalent_values_fixed(row: ComparisonRow) -> ComparisonRow:
    if row.status != "different":
        return row
    if not row.base_value or not row.target_value:
        return row
    if _compact_value(row.base_value) != _compact_value(row.target_value):
        return row
    return ComparisonRow(
        spec_name=row.spec_name,
        base_value=row.base_value,
        target_value=row.target_value,
        status="same",
        summary="표기 차이만 있고 값은 동일합니다.",
        base_evidence_ids=row.base_evidence_ids,
        target_evidence_ids=row.target_evidence_ids,
    )


def _is_low_value_report_row(row: ComparisonRow) -> bool:
    name = row.spec_name.strip()
    joined_values = f"{row.base_value} {row.target_value}".strip()
    if not name and not joined_values:
        return True
    if _GENERIC_TABLE_KEY_RE.search(name) or _INDEXED_TABLE_KEY_RE.search(name):
        return True
    if row.status == "different" and _is_section_number_only_change(row):
        return True
    if (
        row.status == "different"
        and _HEADING_ONLY_RE.match(name)
        and not _MEASUREMENT_UNIT_RE.search(joined_values)
    ):
        return True
    if (
        row.status == "different"
        and _is_date_or_identifier_only(row.base_value)
        and _is_date_or_identifier_only(row.target_value)
    ):
        return True
    if row.status in {"base_only", "target_only"} and _HEADING_ONLY_RE.match(name):
        return True
    if row.status in {"base_only", "target_only"} and _is_date_or_identifier_only(joined_values):
        return True
    if row.status in {"base_only", "target_only"} and joined_values.strip() in {"-", "↑", "○"}:
        return True
    if row.status in {"base_only", "target_only"} and _is_value_repeated_heading(row):
        return True
    if row.status in {"base_only", "target_only"} and not (
        _MEASUREMENT_UNIT_RE.search(joined_values) or _PART_NUMBER_RE.search(joined_values)
    ):
        return True
    if not _NUMERIC_OR_UNIT_RE.search(joined_values) and not _REPORT_KEYWORD_RE.search(
        f"{name} {joined_values}"
    ):
        return True
    return False


def _is_date_or_identifier_only(value: str) -> bool:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return bool(
        re.fullmatch(r"\d{4}\.\s*\d{1,2}\.\s*\d{1,2}", cleaned)
        or re.fullmatch(r"[A-Z]{1,5}\d?[A-Z]?", cleaned)
        or re.fullmatch(r"(?:XV|LW)[A-Z0-9()’.'\-\s]+", cleaned)
    )


def _is_section_number_only_change(row: ComparisonRow) -> bool:
    base = _strip_leading_numbering(row.base_value)
    target = _strip_leading_numbering(row.target_value)
    if not base or not target:
        return False
    if _compact_value(base) == _compact_value(target):
        return True
    summary = row.summary.strip()
    return "번호 차이" in summary or "내용 동일" in summary


def _strip_leading_numbering(value: str) -> str:
    return re.sub(r"^\s*\d+(?:\.\d+)*(?:[.)])?\s*", "", value).strip()


def _is_value_repeated_heading(row: ComparisonRow) -> bool:
    value = row.base_value or row.target_value
    if not value:
        return False
    return _compact_value(value) == _compact_value(
        row.spec_name
    ) and not _MEASUREMENT_UNIT_RE.search(value)


def _report_row_rank(row: ComparisonRow) -> tuple[int, int, str]:
    text = f"{row.spec_name} {row.base_value} {row.target_value}"
    status_rank = {"different": 0, "base_only": 1, "target_only": 1, "unknown": 2, "same": 3}
    has_number = 0 if _NUMERIC_OR_UNIT_RE.search(text) else 1
    has_keyword = 0 if _REPORT_KEYWORD_RE.search(text) else 1
    return (status_rank.get(row.status, 9), has_number + has_keyword, _normalize_key(row.spec_name))


def _dedupe_report_rows(rows: list[ComparisonRow]) -> list[ComparisonRow]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[ComparisonRow] = []
    for row in rows:
        key = (
            row.status,
            _normalize_key(row.spec_name),
            _compact_value(row.base_value),
            _compact_value(row.target_value),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _render_report_analysis_with_llm(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    rows: list[ComparisonRow],
    summary: dict[str, object],
) -> str:
    row_payload = [
        {
            "status": row.status,
            "spec_name": row.spec_name,
            "base_value": row.base_value,
            "target_value": row.target_value,
            "summary": row.summary,
        }
        for row in rows[:120]
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You write Korean product specification comparison report sections. "
                "Use only supplied comparison rows. Do not invent facts, numbers, or causes. "
                "Return markdown only."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": (
                        "Write a concise markdown section headed '## AI 분석 요약'. "
                        "Summarize major value differences, items present only in one document, "
                        "and any rows that need human verification. Keep the detailed table out; "
                        "it will be rendered by code."
                    ),
                    "summary": summary,
                    "comparison_rows": row_payload,
                },
                ensure_ascii=False,
            ),
        },
    ]
    context = LlmTaskContext(
        source="spec_compare",
        actor_user_id=actor_user_id,
        workspace_id=workspace_id,
        task_kind=SPEC_COMPARE_REPORT_TASK_KIND,
        app_id=SPEC_COMPARE_APP_ID,
        principal_kind="user",
        principal_id=actor_user_id,
    )
    completion = execute_llm(
        SPEC_COMPARE_REPORT_WORKLOAD_ID,
        LlmWorkloadContext.from_task_context(context),
        db,
        messages=messages,
        temperature=0,
        max_tokens=2500,
        reasoning_effort="none",
        timeout_seconds=120.0,
    ).completion
    text = completion.text.strip()
    if not text:
        return ""
    fenced = re.search(r"```(?:markdown|md)?\s*([\s\S]*?)\s*```", text, flags=re.I)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("## AI 분석 요약"):
        text = f"## AI 분석 요약\n\n{text}"
    return text


def _status_label(status: RowStatus) -> str:
    # Colored circle prefixes give an at-a-glance verdict cue in the Markdown
    # report table (the renderer strips raw HTML, so emoji is the portable way
    # to add color). Kept consistent with the table tab's status badge colors.
    return {
        "same": "🟢 동일",
        "different": "🔴 상이",
        "base_only": "🔵 기준만",
        "target_only": "🟣 비교만",
        "unknown": "🟡 판단 보류",
    }[status]


def _md_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", "<br />")
