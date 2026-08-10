from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from open_work_hub_api.domains.spec_compare.pipeline import (
    _GLOBAL_SEMANTIC_MATCH_THRESHOLD,
    _LLM_PAIR_CHUNK_SIZE,
    _SEMANTIC_MATCH_THRESHOLD,
    _key_similarity,
    _normalize_key,
    _normalize_value,
    CandidatePair,
    ComparisonRow,
    LlmSectionComparator,
    ProgressCallback,
    RowStatus,
    SpecCandidate,
    SpecCompareCancelled,
)


logger = logging.getLogger(__name__)


def compare_candidates(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    job_id: str,
    base_candidates: list[SpecCandidate],
    target_candidates: list[SpecCandidate],
    comparator: LlmSectionComparator,
    progress_callback: ProgressCallback | None = None,
) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    consumed_base: set[str] = set()
    consumed_target: set[str] = set()
    base_sections = _group_candidates(base_candidates)
    target_sections = _group_candidates(target_candidates)
    section_names = sorted(set(base_sections) | set(target_sections))

    _emit_progress(progress_callback, "matching", 48)
    for section in section_names:
        base_slice = base_sections.get(section, [])
        target_slice = target_sections.get(section, [])
        exact_rows = _deterministic_compare_exact_matches(base_slice, target_slice)
        for row in exact_rows:
            rows.append(row)
            consumed_base.update(
                _matched_candidate_ids(row, base_candidates, document_id="base")
            )
            consumed_target.update(
                _matched_candidate_ids(row, target_candidates, document_id="target")
            )

    global_exact_matches = _deterministic_compare_unique_remaining_matches(
        base_candidates,
        target_candidates,
        consumed_base=consumed_base,
        consumed_target=consumed_target,
    )
    for row, base, target in global_exact_matches:
        rows.append(row)
        consumed_base.add(base.candidate_id)
        consumed_target.add(target.candidate_id)

    semantic_chunks = _plan_semantic_chunks(
        base_sections,
        target_sections,
        consumed_base=consumed_base,
        consumed_target=consumed_target,
        chunk_size=_LLM_PAIR_CHUNK_SIZE,
    )
    if semantic_chunks:
        for chunk_index, pair_chunk in enumerate(semantic_chunks, start=1):
            progress = _interpolate_progress(
                58,
                86,
                chunk_index - 1,
                len(semantic_chunks),
            )
            _emit_progress(progress_callback, "comparing", progress)
            base_chunk = [pair.base for pair in pair_chunk]
            target_chunk = [pair.target for pair in pair_chunk]
            try:
                section_rows = comparator(
                    db,
                    workspace_id,
                    actor_user_id,
                    base_chunk,
                    target_chunk,
                )
            except SpecCompareCancelled:
                raise
            except Exception:
                logger.exception("spec_compare: LLM comparison failed for job %s", job_id)
                section_rows = _deterministic_compare_pairs(pair_chunk)
            for row in section_rows:
                rows.append(row)
                consumed_base.update(
                    _matched_candidate_ids(row, base_candidates, document_id="base")
                )
                consumed_target.update(
                    _matched_candidate_ids(row, target_candidates, document_id="target")
                )
            _emit_progress(
                progress_callback,
                "comparing",
                _interpolate_progress(58, 86, chunk_index, len(semantic_chunks)),
            )
    else:
        _emit_progress(progress_callback, "comparing", 86)

    _emit_progress(progress_callback, "finalizing", 88)
    for candidate in base_candidates:
        if candidate.candidate_id not in consumed_base:
            rows.append(
                ComparisonRow(
                    spec_name=candidate.spec_name,
                    base_value=candidate.value,
                    target_value="",
                    status="base_only",
                    summary="비교 문서에서 대응 항목을 찾지 못했습니다.",
                    base_evidence_ids=[candidate.evidence_id],
                    target_evidence_ids=[],
                )
            )
    for candidate in target_candidates:
        if candidate.candidate_id not in consumed_target:
            rows.append(
                ComparisonRow(
                    spec_name=candidate.spec_name,
                    base_value="",
                    target_value=candidate.value,
                    status="target_only",
                    summary="기준 문서에서 대응 항목을 찾지 못했습니다.",
                    base_evidence_ids=[],
                    target_evidence_ids=[candidate.evidence_id],
                )
            )
    return _dedupe_rows(rows)


def _emit_progress(callback: ProgressCallback | None, message: str, progress: int) -> None:
    if callback is not None:
        callback(message, max(0, min(100, progress)))


def _interpolate_progress(start: int, end: int, index: int, total: int) -> int:
    if total <= 0:
        return end
    return round(start + ((end - start) * min(index, total) / total))


def _deterministic_compare_exact_matches(
    base_candidates: list[SpecCandidate],
    target_candidates: list[SpecCandidate],
) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    base_by_key = _candidate_groups(base_candidates)
    target_by_key = _candidate_groups(target_candidates)
    for key in sorted(set(base_by_key) & set(target_by_key)):
        if not key:
            continue
        base_group = base_by_key[key]
        target_group = target_by_key[key]
        for base, target in zip(base_group, target_group, strict=False):
            status: RowStatus = (
                "same"
                if _normalize_value(base.value) == _normalize_value(target.value)
                else "different"
            )
            rows.append(
                ComparisonRow(
                    spec_name=base.spec_name or target.spec_name,
                    base_value=base.value,
                    target_value=target.value,
                    status=status,
                    summary="동일합니다." if status == "same" else "값이 다릅니다.",
                    base_evidence_ids=[base.evidence_id],
                    target_evidence_ids=[target.evidence_id],
                )
            )
    return rows


def _deterministic_compare_unique_remaining_matches(
    base_candidates: list[SpecCandidate],
    target_candidates: list[SpecCandidate],
    *,
    consumed_base: set[str],
    consumed_target: set[str],
) -> list[tuple[ComparisonRow, SpecCandidate, SpecCandidate]]:
    rows: list[tuple[ComparisonRow, SpecCandidate, SpecCandidate]] = []
    base_by_key = _candidate_groups(
        [
            candidate
            for candidate in base_candidates
            if candidate.candidate_id not in consumed_base
        ]
    )
    target_by_key = _candidate_groups(
        [
            candidate
            for candidate in target_candidates
            if candidate.candidate_id not in consumed_target
        ]
    )
    for key in sorted(set(base_by_key) & set(target_by_key)):
        base_group = base_by_key[key]
        target_group = target_by_key[key]
        if len(base_group) != 1 or len(target_group) != 1:
            continue
        base = base_group[0]
        target = target_group[0]
        status: RowStatus = (
            "same"
            if _normalize_value(base.value) == _normalize_value(target.value)
            else "different"
        )
        rows.append(
            (
                ComparisonRow(
                    spec_name=base.spec_name or target.spec_name,
                    base_value=base.value,
                    target_value=target.value,
                    status=status,
                    summary="동일합니다." if status == "same" else "값이 다릅니다.",
                    base_evidence_ids=[base.evidence_id],
                    target_evidence_ids=[target.evidence_id],
                ),
                base,
                target,
            )
        )
    return rows


def _candidate_groups(candidates: list[SpecCandidate]) -> dict[str, list[SpecCandidate]]:
    out: dict[str, list[SpecCandidate]] = {}
    for candidate in candidates:
        out.setdefault(_normalize_key(candidate.spec_name), []).append(candidate)
    return out


def _plan_semantic_chunks(
    base_sections: dict[str, list[SpecCandidate]],
    target_sections: dict[str, list[SpecCandidate]],
    *,
    consumed_base: set[str],
    consumed_target: set[str],
    chunk_size: int,
) -> list[list[CandidatePair]]:
    pairs: list[CandidatePair] = []
    used_targets: set[str] = set(consumed_target)
    used_bases: set[str] = set(consumed_base)
    for section in sorted(set(base_sections) | set(target_sections)):
        base_slice = [
            candidate
            for candidate in base_sections.get(section, [])
            if candidate.candidate_id not in used_bases
        ]
        target_slice = [
            candidate
            for candidate in target_sections.get(section, [])
            if candidate.candidate_id not in used_targets
        ]
        for base in base_slice:
            best = _best_semantic_target(base, target_slice, used_targets)
            if best is None:
                continue
            target, score = best
            if score < _SEMANTIC_MATCH_THRESHOLD:
                continue
            pairs.append(CandidatePair(base=base, target=target, score=score))
            used_bases.add(base.candidate_id)
            used_targets.add(target.candidate_id)

    remaining_base = [
        candidate
        for candidates in base_sections.values()
        for candidate in candidates
        if candidate.candidate_id not in used_bases
    ]
    remaining_target = [
        candidate
        for candidates in target_sections.values()
        for candidate in candidates
        if candidate.candidate_id not in used_targets
    ]
    for base in remaining_base:
        best = _best_semantic_target(base, remaining_target, used_targets)
        if best is None:
            continue
        target, score = best
        if score < _GLOBAL_SEMANTIC_MATCH_THRESHOLD:
            continue
        pairs.append(CandidatePair(base=base, target=target, score=score))
        used_bases.add(base.candidate_id)
        used_targets.add(target.candidate_id)
    return [pairs[start : start + chunk_size] for start in range(0, len(pairs), chunk_size)]


def _best_semantic_target(
    base: SpecCandidate,
    target_candidates: list[SpecCandidate],
    used_targets: set[str],
) -> tuple[SpecCandidate, float] | None:
    best: tuple[SpecCandidate, float] | None = None
    for target in target_candidates:
        if target.candidate_id in used_targets:
            continue
        score = _key_similarity(base.spec_name, target.spec_name)
        if best is None or score > best[1]:
            best = (target, score)
    return best


def _deterministic_compare_pairs(pairs: list[CandidatePair]) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    for pair in pairs:
        status: RowStatus = (
            "same"
            if _normalize_value(pair.base.value) == _normalize_value(pair.target.value)
            else "different"
        )
        rows.append(
            ComparisonRow(
                spec_name=pair.base.spec_name or pair.target.spec_name,
                base_value=pair.base.value,
                target_value=pair.target.value,
                status=status,
                summary=(
                    "항목명이 유사해 자동 대응했으며 값은 동일합니다."
                    if status == "same"
                    else "항목명이 유사해 자동 대응했으며 값이 다릅니다."
                ),
                base_evidence_ids=[pair.base.evidence_id],
                target_evidence_ids=[pair.target.evidence_id],
            )
        )
    return rows


def _matched_candidate_ids(
    row: ComparisonRow,
    candidates: list[SpecCandidate],
    *,
    document_id: str,
) -> set[str]:
    evidence_ids = set(row.base_evidence_ids if document_id == "base" else row.target_evidence_ids)
    value = row.base_value if document_id == "base" else row.target_value
    if not evidence_ids:
        return set()
    normalized_value = _normalize_value(value)
    normalized_name = _normalize_key(row.spec_name)
    out: set[str] = set()
    for candidate in candidates:
        if candidate.evidence_id not in evidence_ids:
            continue
        if normalized_value and _normalize_value(candidate.value) == normalized_value:
            out.add(candidate.candidate_id)
            continue
        if normalized_name and _normalize_key(candidate.spec_name) == normalized_name:
            out.add(candidate.candidate_id)
    return out


def _group_candidates(candidates: list[SpecCandidate]) -> dict[str, list[SpecCandidate]]:
    grouped: dict[str, list[SpecCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.section_path or "Document", []).append(candidate)
    return grouped


def _dedupe_rows(rows: list[ComparisonRow]) -> list[ComparisonRow]:
    seen: set[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = set()
    out: list[ComparisonRow] = []
    for row in rows:
        key = (
            _normalize_key(row.spec_name),
            row.base_value.casefold(),
            row.target_value.casefold(),
            tuple(sorted(row.base_evidence_ids)),
            tuple(sorted(row.target_evidence_ids)),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
