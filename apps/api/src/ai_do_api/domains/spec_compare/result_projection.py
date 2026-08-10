from __future__ import annotations

from ai_do_api.domains.spec_compare.extraction import SpecItem
from ai_do_api.domains.spec_compare.models import SpecCompareJob, SpecCompareSpecItem
from ai_do_api.domains.spec_compare.schemas import (
    SpecCompareFileOut,
    SpecCompareJobOut,
    SpecCompareResultResponse,
    SpecCompareRowOut,
)


def project_spec_compare_job(row: SpecCompareJob) -> SpecCompareJobOut:
    return SpecCompareJobOut(
        id=row.id,
        workspace_id=row.workspace_id,
        owner_id=row.owner_id,
        title=row.title,
        status=row.status,  # type: ignore[arg-type]
        progress=row.progress,
        status_message=row.status_message,
        failure_reason=row.failure_reason,
        base_file=SpecCompareFileOut(
            name=row.base_file_name,
            mime_type=row.base_mime_type,
            size_bytes=row.base_size_bytes,
        ),
        target_file=SpecCompareFileOut(
            name=row.target_file_name,
            mime_type=row.target_mime_type,
            size_bytes=row.target_size_bytes,
        ),
        result_summary=row.result_summary,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def project_spec_compare_result(
    row: SpecCompareJob, payload: dict
) -> SpecCompareResultResponse:
    return SpecCompareResultResponse(
        job=project_spec_compare_job(row),
        report_markdown=str(payload.get("report_markdown") or ""),
        comparison_rows=[
            SpecCompareRowOut.model_validate(item)
            for item in payload.get("comparison_rows") or []
            if isinstance(item, dict)
        ],
        evidence_blocks=[
            item for item in payload.get("evidence_blocks") or [] if isinstance(item, dict)
        ],
        summary=payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        spec_items=payload.get("spec_items") if isinstance(payload.get("spec_items"), dict) else {},
    )


def project_spec_item_record(
    row: SpecCompareJob, role: str, index: int, item: SpecItem
) -> SpecCompareSpecItem:
    return SpecCompareSpecItem(
        id=f"{row.id}:{role}:{index}",
        job_id=row.id,
        document_role=role,
        item_id=item.item_id,
        normalized_key=_normalize_spec_item_key(item),
        category=item.category,
        item_name=item.item_name,
        value=item.value,
        unit=item.unit,
        condition=item.condition,
        evidence_id=item.evidence_id,
        locator_label=item.locator_label,
        section_path=item.section_path,
        source_text=item.source_text,
        confidence=item.confidence,
        extraction_method=item.extraction_method,
    )


def _normalize_spec_item_key(item: SpecItem) -> str:
    return "".join(ch for ch in item.item_name.casefold() if ch.isalnum())[:300]
