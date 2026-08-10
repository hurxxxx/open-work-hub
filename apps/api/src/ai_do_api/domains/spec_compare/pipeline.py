from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ai_do_api.core.llm import (
    LlmRuntimeError,
    LlmTaskContext,
)
from ai_do_api.domains.ai.gateway import (
    LlmWorkloadContext,
    execute_llm,
)
from ai_do_api.domains.document_processing import (
    DocumentExtractBundle,
    EvidenceBlock,
    extract_document,
)
from ai_do_api.domains.spec_compare import (
    SPEC_COMPARE_APP_ID,
    SPEC_COMPARE_COMPARE_TASK_KIND,
    SPEC_COMPARE_COMPARE_WORKLOAD_ID,
    SPEC_COMPARE_EXTRACT_TASK_KIND,
    SPEC_COMPARE_EXTRACT_WORKLOAD_ID,
    reporting as spec_compare_reporting,
)
from ai_do_api.domains.spec_compare.contracts import (
    ComparisonRow as ComparisonRow,
    RowStatus as RowStatus,
    SpecCompareCancelled as SpecCompareCancelled,
    _compact_value as _compact_value,
    _key_similarity as _key_similarity,
    _normalize_key as _normalize_key,
    _normalize_value as _normalize_value,
)
from ai_do_api.domains.spec_compare.extraction import (
    DocumentMarkdownChunk,
    SpecCandidate,
    SpecItem,
    build_deterministic_spec_items,
    build_document_markdown_chunks,
    build_spec_candidates as build_spec_candidates,
    merge_spec_items,
    split_value_unit,
)
from ai_do_api.domains.spec_compare.reporting import (
    build_raw_summary as build_raw_summary,
    build_summary as build_summary,
    curate_report_rows as curate_report_rows,
    enrich_markdown_report_with_llm as enrich_markdown_report_with_llm,
    render_markdown_report as render_markdown_report,
)


logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int], None]

_SEMANTIC_MATCH_THRESHOLD = 0.60
_GLOBAL_SEMANTIC_MATCH_THRESHOLD = 0.78
_LLM_PAIR_CHUNK_SIZE = 12
_LLM_COMPARISON_MAX_TOKENS = 1800
_LLM_COMPARISON_TIMEOUT_SECONDS = 180.0
_SPEC_EXTRACTION_MAX_TOKENS = 4000
_SPEC_EXTRACTION_TIMEOUT_SECONDS = 180.0


@dataclass(frozen=True)
class CandidatePair:
    base: SpecCandidate
    target: SpecCandidate
    score: float


@dataclass(frozen=True)
class SpecComparePipelineResult:
    report_markdown: str
    comparison_rows: list[ComparisonRow]
    evidence_blocks: list[EvidenceBlock]
    summary: dict[str, object]
    raw_comparison_rows: list[ComparisonRow] | None = None
    base_spec_items: list[SpecItem] | None = None
    target_spec_items: list[SpecItem] | None = None
    markdown_chunks: dict[str, list[DocumentMarkdownChunk]] | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "report_markdown": self.report_markdown,
            "comparison_rows": [row.to_dict() for row in self.comparison_rows],
            "evidence_blocks": [block.to_dict() for block in self.evidence_blocks],
            "summary": self.summary,
        }
        if self.raw_comparison_rows is not None:
            payload["raw_comparison_rows"] = [row.to_dict() for row in self.raw_comparison_rows]
        if self.base_spec_items is not None or self.target_spec_items is not None:
            payload["spec_items"] = {
                "base": [item.to_dict() for item in self.base_spec_items or []],
                "target": [item.to_dict() for item in self.target_spec_items or []],
            }
        if self.markdown_chunks is not None:
            payload["markdown_chunks"] = {
                role: [chunk.to_dict() for chunk in chunks]
                for role, chunks in self.markdown_chunks.items()
            }
        return payload


class LlmComparisonRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    spec_name: str = Field(max_length=300)
    base_value: str = ""
    target_value: str = ""
    status: RowStatus = "unknown"
    summary: str = ""
    base_evidence_ids: list[str] = Field(default_factory=list)
    target_evidence_ids: list[str] = Field(default_factory=list)


class LlmComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rows: list[LlmComparisonRow] = Field(default_factory=list)


class LlmSpecItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str = Field(default="", max_length=300)
    item_name: str = Field(max_length=300)
    value: str = Field(default="", max_length=1000)
    unit: str = Field(default="", max_length=80)
    condition: str = Field(default="", max_length=500)
    evidence_id: str = Field(default="", max_length=160)
    source_text: str = Field(default="", max_length=1200)
    confidence: float = Field(default=0.5, ge=0, le=1)


class LlmSpecExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[LlmSpecItem] = Field(default_factory=list)


LlmSectionComparator = Callable[
    [Session, str, str, list[SpecCandidate], list[SpecCandidate]], list[ComparisonRow]
]


def compare_spec_documents(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    job_id: str,
    base_filename: str,
    base_mime_type: str,
    base_content: bytes,
    target_filename: str,
    target_mime_type: str,
    target_content: bytes,
    llm_comparator: LlmSectionComparator | None = None,
    progress_callback: ProgressCallback | None = None,
) -> SpecComparePipelineResult:
    _emit_progress(progress_callback, "extracting", 15)
    base_bundle = extract_document(
        document_id="base",
        filename=base_filename,
        mime_type=base_mime_type,
        content=base_content,
    )
    _emit_progress(progress_callback, "extracting", 28)
    target_bundle = extract_document(
        document_id="target",
        filename=target_filename,
        mime_type=target_mime_type,
        content=target_content,
    )
    _emit_progress(progress_callback, "structuring", 34)
    base_chunks = build_document_markdown_chunks(base_bundle)
    target_chunks = build_document_markdown_chunks(target_bundle)
    base_spec_items = build_spec_items(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        bundle=base_bundle,
        markdown_chunks=base_chunks,
    )
    _emit_progress(progress_callback, "structuring", 38)
    target_spec_items = build_spec_items(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        bundle=target_bundle,
        markdown_chunks=target_chunks,
    )
    _emit_progress(progress_callback, "matching", 42)
    base_candidates = [item.to_candidate() for item in base_spec_items]
    target_candidates = [item.to_candidate() for item in target_spec_items]
    comparator = llm_comparator or _compare_section_with_llm
    rows = compare_candidates(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        job_id=job_id,
        base_candidates=base_candidates,
        target_candidates=target_candidates,
        comparator=comparator,
        progress_callback=progress_callback,
    )
    _emit_progress(progress_callback, "rendering", 92)
    raw_rows = rows
    rows = spec_compare_reporting.curate_report_rows(raw_rows)
    evidence_blocks = [*base_bundle.evidence_blocks, *target_bundle.evidence_blocks]
    summary = spec_compare_reporting.build_summary(rows, base_bundle, target_bundle)
    summary.update(spec_compare_reporting.build_raw_summary(raw_rows, display_rows=rows))
    summary.update(
        {
            "base_spec_items": len(base_spec_items),
            "target_spec_items": len(target_spec_items),
            "base_markdown_chunks": len(base_chunks),
            "target_markdown_chunks": len(target_chunks),
        }
    )
    report = spec_compare_reporting.render_markdown_report(
        rows=rows,
        summary=summary,
        base_filename=base_filename,
        target_filename=target_filename,
    )
    if db is not None:
        report = spec_compare_reporting.enrich_markdown_report_with_llm(
            db,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            report_markdown=report,
            rows=rows,
            summary=summary,
        )
    return SpecComparePipelineResult(
        report_markdown=report,
        comparison_rows=rows,
        evidence_blocks=evidence_blocks,
        summary=summary,
        raw_comparison_rows=raw_rows,
        base_spec_items=base_spec_items,
        target_spec_items=target_spec_items,
        markdown_chunks={"base": base_chunks, "target": target_chunks},
    )


def build_spec_items(
    db: Session | None,
    *,
    workspace_id: str,
    actor_user_id: str,
    bundle: DocumentExtractBundle,
    markdown_chunks: list[DocumentMarkdownChunk] | None = None,
) -> list[SpecItem]:
    deterministic_items = build_deterministic_spec_items(bundle)
    llm_items: list[SpecItem] = []
    chunks = (
        markdown_chunks if markdown_chunks is not None else build_document_markdown_chunks(bundle)
    )
    if db is not None and chunks:
        try:
            llm_items = _extract_spec_items_with_llm(
                db,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                bundle=bundle,
                chunks=chunks,
            )
        except SpecCompareCancelled:
            raise
        except Exception:
            logger.exception("spec_compare: LLM spec extraction failed for %s", bundle.document_id)
    return merge_spec_items(llm_items, deterministic_items)


def _extract_spec_items_with_llm(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    bundle: DocumentExtractBundle,
    chunks: list[DocumentMarkdownChunk],
) -> list[SpecItem]:
    items: list[SpecItem] = []
    valid_evidence_ids = {block.block_id for block in bundle.evidence_blocks}
    for chunk_index, chunk in enumerate(chunks, start=1):
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract product/component specification facts from Korean technical "
                    "document markdown. Return only compact JSON. Use only supplied text. "
                    "Ignore table-of-contents headings, revision dates, pure section titles, "
                    "and cells that are not product specification facts."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": (
                            "Extract only meaningful product specification items as key/value "
                            "facts. Preserve the evidence_id that supports each fact. If a unit "
                            "or operating condition is present, split it into unit/condition."
                        ),
                        "schema": {
                            "items": [
                                {
                                    "category": "section or component category",
                                    "item_name": "stable spec key",
                                    "value": "spec value",
                                    "unit": "unit when explicit",
                                    "condition": "condition or trim/package/market when explicit",
                                    "evidence_id": "one supplied evidence id",
                                    "source_text": "short original source fragment",
                                    "confidence": 0.0,
                                }
                            ]
                        },
                        "document_id": bundle.document_id,
                        "chunk": chunk.to_prompt_dict(),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        context = LlmTaskContext(
            source="spec_compare",
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            task_kind=SPEC_COMPARE_EXTRACT_TASK_KIND,
            app_id=SPEC_COMPARE_APP_ID,
            principal_kind="user",
            principal_id=actor_user_id,
        )
        completion = execute_llm(
            SPEC_COMPARE_EXTRACT_WORKLOAD_ID,
            LlmWorkloadContext.from_task_context(context),
            db,
            messages=messages,
            temperature=0,
            max_tokens=_SPEC_EXTRACTION_MAX_TOKENS,
            reasoning_effort="none",
            timeout_seconds=_SPEC_EXTRACTION_TIMEOUT_SECONDS,
        ).completion
        raw_content = completion.text.strip()
        parsed = LlmSpecExtractionResponse.model_validate(
            json.loads(_extract_json_object(raw_content))
        )
        for row in parsed.items:
            item = _normalize_llm_spec_item(
                row,
                bundle=bundle,
                valid_evidence_ids=valid_evidence_ids,
                ordinal=len(items) + 1,
                extraction_method=f"llm:chunk:{chunk_index}",
            )
            if item is not None:
                items.append(item)
    return items


def _normalize_llm_spec_item(
    row: LlmSpecItem,
    *,
    bundle: DocumentExtractBundle,
    valid_evidence_ids: set[str],
    ordinal: int,
    extraction_method: str,
) -> SpecItem | None:
    item_name = re.sub(r"\s+", " ", row.item_name).strip()
    value = re.sub(r"\s+", " ", row.value).strip()
    if len(item_name) < 2 or not value:
        return None
    evidence_id = row.evidence_id.strip()
    if evidence_id not in valid_evidence_ids:
        return None
    if not evidence_id:
        return None
    value, unit = split_value_unit(value, preferred_unit=row.unit)
    block = _evidence_by_id(bundle, evidence_id)
    if block is not None and not _value_supported_by_evidence(
        value,
        source_text=row.source_text,
        evidence_text=block.text,
    ):
        return None
    return SpecItem(
        item_id=f"{bundle.document_id}:llm-spec:{ordinal}",
        document_id=bundle.document_id,
        category=(row.category.strip() or (block.section_path if block else ""))[:300],
        item_name=item_name[:300],
        value=value[:1000],
        unit=unit[:80],
        condition=row.condition.strip()[:500],
        evidence_id=evidence_id,
        locator_label=block.locator_label if block else "",
        section_path=block.section_path if block else "",
        source_text=(row.source_text.strip() or value)[:1200],
        confidence=row.confidence,
        extraction_method=extraction_method,
    )


def _value_supported_by_evidence(
    value: str,
    *,
    source_text: str,
    evidence_text: str,
) -> bool:
    compact_value = _compact_value(value)
    if len(compact_value) < 2:
        return True
    return compact_value in _compact_value(source_text) or compact_value in _compact_value(
        evidence_text
    )


def _evidence_by_id(bundle: DocumentExtractBundle, evidence_id: str) -> EvidenceBlock | None:
    for block in bundle.evidence_blocks:
        if block.block_id == evidence_id:
            return block
    return None


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
    from ai_do_api.domains.spec_compare.matching import (
        compare_candidates as compare_spec_candidates,
    )

    return compare_spec_candidates(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        job_id=job_id,
        base_candidates=base_candidates,
        target_candidates=target_candidates,
        comparator=comparator,
        progress_callback=progress_callback,
    )


def _emit_progress(callback: ProgressCallback | None, message: str, progress: int) -> None:
    if callback is not None:
        callback(message, max(0, min(100, progress)))


def _compare_section_with_llm(
    db: Session,
    workspace_id: str,
    actor_user_id: str,
    base_candidates: list[SpecCandidate],
    target_candidates: list[SpecCandidate],
) -> list[ComparisonRow]:
    if not base_candidates and not target_candidates:
        return []
    messages = [
        {
            "role": "system",
            "content": (
                "You compare Korean product specification candidates. "
                "Return only compact JSON. Do not use markdown. "
                "Do not invent values; use only supplied candidate values and evidence ids."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": (
                        "Align equivalent specification items between base and target. "
                        "For every meaningful spec, emit one row with status: same, different, "
                        "base_only, target_only, or unknown. The caller already filtered exact "
                        "matches; focus on the supplied possible semantic pairs."
                    ),
                    "schema": {
                        "rows": [
                            {
                                "spec_name": "string",
                                "base_value": "string",
                                "target_value": "string",
                                "status": "same|different|base_only|target_only|unknown",
                                "summary": "short Korean explanation",
                                "base_evidence_ids": ["base evidence ids"],
                                "target_evidence_ids": ["target evidence ids"],
                            }
                        ]
                    },
                    "base_candidates": [
                        candidate.to_prompt_dict() for candidate in base_candidates
                    ],
                    "target_candidates": [
                        candidate.to_prompt_dict() for candidate in target_candidates
                    ],
                    "candidate_pair_hints": [
                        {
                            "base_candidate_id": base.candidate_id,
                            "target_candidate_id": target.candidate_id,
                        }
                        for base, target in zip(base_candidates, target_candidates, strict=False)
                    ],
                },
                ensure_ascii=False,
            ),
        },
    ]
    context = LlmTaskContext(
        source="spec_compare",
        actor_user_id=actor_user_id,
        workspace_id=workspace_id,
        task_kind=SPEC_COMPARE_COMPARE_TASK_KIND,
        app_id=SPEC_COMPARE_APP_ID,
        principal_kind="user",
        principal_id=actor_user_id,
    )
    completion = execute_llm(
        SPEC_COMPARE_COMPARE_WORKLOAD_ID,
        LlmWorkloadContext.from_task_context(context),
        db,
        messages=messages,
        temperature=0,
        max_tokens=_LLM_COMPARISON_MAX_TOKENS,
        reasoning_effort="none",
        timeout_seconds=_LLM_COMPARISON_TIMEOUT_SECONDS,
    ).completion
    raw_content = completion.text.strip()
    try:
        parsed = LlmComparisonResponse.model_validate(json.loads(_extract_json_object(raw_content)))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LlmRuntimeError("LLM returned invalid comparison JSON") from exc
    return [_normalize_llm_row(row, base_candidates, target_candidates) for row in parsed.rows]


def _extract_json_object(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.I)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return text[start : end + 1]


def _normalize_llm_row(
    row: LlmComparisonRow,
    base_candidates: list[SpecCandidate],
    target_candidates: list[SpecCandidate],
) -> ComparisonRow:
    base_ids = _valid_evidence_ids(row.base_evidence_ids, base_candidates)
    target_ids = _valid_evidence_ids(row.target_evidence_ids, target_candidates)
    status = row.status
    if status == "same" and row.base_value.strip() != row.target_value.strip():
        status = "different"
    if not base_ids and not target_ids:
        status = "unknown"
    return ComparisonRow(
        spec_name=row.spec_name.strip() or "미분류 사양",
        base_value=row.base_value.strip(),
        target_value=row.target_value.strip(),
        status=status,
        summary=row.summary.strip(),
        base_evidence_ids=base_ids,
        target_evidence_ids=target_ids,
    )


def _valid_evidence_ids(ids: list[str], candidates: list[SpecCandidate]) -> list[str]:
    allowed = {candidate.evidence_id for candidate in candidates}
    return [evidence_id for evidence_id in ids if evidence_id in allowed]
