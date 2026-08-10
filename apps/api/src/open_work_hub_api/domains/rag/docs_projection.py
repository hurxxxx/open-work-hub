from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.domains.docs.content_text import extract_page_text
from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.docs.models import NativeDocPage
from open_work_hub_api.domains.rag.chunking import (
    DEFAULT_HARD_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_TARGET_CHARS,
    build_contextual_index_text,
    split_korean_aware_text_spans,
)
from open_work_hub_api.domains.rag.contracts import RagChunk
from open_work_hub_api.domains.rag.contracts import RagProjection
from open_work_hub_api.domains.rag.projection_builders import (
    build_projection_chunk,
    build_text_projection,
)
from open_work_hub_api.domains.rag.source_registry import RAG_SCOPE_OFFICIAL
from open_work_hub_api.domains.source_access.resource_types import NATIVE_DOC_RESOURCE_TYPE


DOCS_CHUNK_STRATEGY = "docs_structure_v1"


@dataclass(frozen=True)
class _DocTextUnit:
    text: str
    page: NativeDocPage
    page_path: list[str]
    section_path: list[str]
    start: int
    end: int


def load_native_doc_projection(
    db: Session,
    *,
    doc_id: str,
) -> RagProjection | None:
    doc = db.scalar(
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages),
            selectinload(NativeDoc.targets),
            selectinload(NativeDoc.user_shares),
            selectinload(NativeDoc.link_shares),
            selectinload(NativeDoc.meeting_access_grants),
        )
        .where(NativeDoc.id == doc_id, NativeDoc.trashed_at.is_(None))
    )
    if doc is None:
        return None
    if doc.rag_scope != RAG_SCOPE_OFFICIAL:
        return None
    return build_native_doc_projection(doc)


def build_native_doc_projection(doc: NativeDoc) -> RagProjection:
    active_pages = sorted(
        (page for page in doc.pages if page.trashed_at is None),
        key=lambda page: (page.sort_order, page.created_at, page.id),
    )
    page_sections: list[str] = []
    for page in active_pages:
        if page.title.strip():
            page_sections.append(page.title.strip())
        page_text = _extract_page_text(page.content_format, page)
        if page_text:
            page_sections.append(page_text)

    text_sections = [doc.title.strip(), *page_sections]
    summary = _summarize_text(page_sections[0] if page_sections else doc.title)
    target_refs = [
        f"{target.target_app}:{target.target_type}:{target.target_id}"
        for target in sorted(
            doc.targets,
            key=lambda target: (target.sort_order, target.target_app, target.id),
        )
    ]
    visibility_refs = _build_visibility_refs(doc)

    return build_text_projection(
        workspace_id=doc.workspace_id,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id=doc.id,
        source_kind=doc.source_kind,
        title=doc.title,
        summary=summary,
        text_sections=text_sections,
        owner_label=getattr(doc.owner, "full_name", None),
        visibility_refs=visibility_refs,
        metadata={
            "source_app": doc.source_app,
            "generation_kind": doc.generation_kind,
            "doc_type": doc.doc_type,
            "rag_scope": doc.rag_scope,
            "origin_ref": doc.source_ref,
            "page_count": len(active_pages),
            "target_refs": target_refs,
            "link_share_active": any(share.active for share in doc.link_shares),
        },
        chunks=_build_native_doc_chunks(
            doc=doc,
            active_pages=active_pages,
            doc_summary=summary,
        ),
    )


def _build_native_doc_chunks(
    *,
    doc: NativeDoc,
    active_pages: list[NativeDocPage],
    doc_summary: str | None,
) -> list[RagChunk]:
    pages_by_id = {page.id: page for page in active_pages}
    chunks: list[RagChunk] = []
    chunk_index = 0
    for page in active_pages:
        page_path = _page_title_path(page, pages_by_id)
        units = _page_text_units(page, page_path=page_path)
        if not units:
            chunks.append(
                _native_doc_chunk(
                    doc=doc,
                    page=page,
                    page_path=page_path,
                    section_path=page_path,
                    text=page.title.strip() or doc.title,
                    doc_summary=doc_summary,
                    chunk_index=chunk_index,
                    char_start=0,
                    char_end=len(page.title.strip()),
                )
            )
            chunk_index += 1
            continue

        grouped_units: list[_DocTextUnit] = []
        current_section_path: list[str] | None = None
        for unit in units:
            if current_section_path is not None and unit.section_path != current_section_path:
                chunk_index = _append_unit_group_chunks(
                    chunks,
                    doc=doc,
                    units=grouped_units,
                    doc_summary=doc_summary,
                    chunk_index=chunk_index,
                )
                grouped_units = []
            current_section_path = unit.section_path
            grouped_units.append(unit)
        chunk_index = _append_unit_group_chunks(
            chunks,
            doc=doc,
            units=grouped_units,
            doc_summary=doc_summary,
            chunk_index=chunk_index,
        )
    return chunks


def _append_unit_group_chunks(
    chunks: list[RagChunk],
    *,
    doc: NativeDoc,
    units: list[_DocTextUnit],
    doc_summary: str | None,
    chunk_index: int,
) -> int:
    if not units:
        return chunk_index
    raw_text = "\n\n".join(unit.text for unit in units if unit.text.strip()).strip()
    if not raw_text:
        return chunk_index
    pieces = split_korean_aware_text_spans(
        raw_text,
        target_chars=DEFAULT_TARGET_CHARS,
        hard_max_chars=DEFAULT_HARD_MAX_CHARS,
        overlap_chars=DEFAULT_OVERLAP_CHARS,
    )
    first_unit = units[0]
    last_unit = units[-1]
    for piece in pieces:
        if not piece.text.strip():
            continue
        chunks.append(
            _native_doc_chunk(
                doc=doc,
                page=first_unit.page,
                page_path=first_unit.page_path,
                section_path=first_unit.section_path,
                text=piece.text,
                doc_summary=doc_summary,
                chunk_index=chunk_index,
                char_start=first_unit.start + piece.start,
                char_end=min(first_unit.start + piece.end, last_unit.end),
            )
        )
        chunk_index += 1
    return chunk_index


def _native_doc_chunk(
    *,
    doc: NativeDoc,
    page: NativeDocPage,
    page_path: list[str],
    section_path: list[str],
    text: str,
    doc_summary: str | None,
    chunk_index: int,
    char_start: int,
    char_end: int,
) -> RagChunk:
    page_title = " > ".join(page_path) if page_path else page.title
    section_title = section_path[-1] if section_path else page.title
    return build_projection_chunk(
        workspace_id=doc.workspace_id,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id=doc.id,
        source_kind=doc.source_kind,
        chunk_id=f"{doc.id}:{chunk_index}",
        text=text.strip(),
        chunk_index=chunk_index,
        summary=_summarize_text(f"{section_title}: {text}", max_chars=180),
        index_text=build_contextual_index_text(
            title=doc.title,
            summary=doc_summary,
            page_title=page_title,
            section_path=section_path,
            body=text,
        ),
        metadata={
            "chunk_strategy": DOCS_CHUNK_STRATEGY,
            "doc_id": doc.id,
            "page_id": page.id,
            "page_title": page.title,
            "page_title_path": page_path,
            "section_title": section_title,
            "section_path": section_path,
            "char_start": max(char_start, 0),
            "char_end": max(char_end, char_start),
        },
    )


def _page_title_path(page: NativeDocPage, pages_by_id: dict[str, NativeDocPage]) -> list[str]:
    path = [page.title.strip() or page.id]
    current = page
    visited = {page.id}
    while current.parent_id and current.parent_id not in visited:
        parent = pages_by_id.get(current.parent_id)
        if parent is None:
            break
        visited.add(parent.id)
        path.append(parent.title.strip() or parent.id)
        current = parent
    return list(reversed(path))


def _page_text_units(page: NativeDocPage, *, page_path: list[str]) -> list[_DocTextUnit]:
    units: list[_DocTextUnit] = []
    section_path = list(page_path)
    cursor = 0
    content_format = page.content_format
    if content_format != "block":
        text = _extract_page_text(content_format, page)
        if not text:
            return units
        units.append(
            _DocTextUnit(
                text=text,
                page=page,
                page_path=page_path,
                section_path=section_path,
                start=0,
                end=len(text),
            )
        )
        return units
    for block in page.content_blocks or []:
        text = _extract_blocks_text([block])
        if not text:
            continue
        block_type = str(block.get("type") or "").lower() if isinstance(block, dict) else ""
        if block_type == "heading":
            section_path = [*page_path, text]
            start = cursor
            end = cursor + len(text)
            units.append(
                _DocTextUnit(
                    text=text,
                    page=page,
                    page_path=page_path,
                    section_path=list(section_path),
                    start=start,
                    end=end,
                )
            )
            cursor += len(text) + 2
            continue
        start = cursor
        end = cursor + len(text)
        units.append(
            _DocTextUnit(
                text=text,
                page=page,
                page_path=page_path,
                section_path=list(section_path),
                start=start,
                end=end,
            )
        )
        cursor += len(text) + 2
    return units


def _extract_page_text(content_format: str, page: NativeDocPage) -> str:
    return extract_page_text(
        content_format=content_format,
        content_blocks=page.content_blocks,
        content_text=page.content_text,
        block_extractor=_extract_blocks_text,
    )


def _build_visibility_refs(doc: NativeDoc) -> list[str]:
    refs = {
        f"workspace:{doc.workspace_id}",
        f"owner:{doc.owner_id}",
    }

    for target in doc.targets:
        refs.add(f"target:{target.target_app}:{target.target_type}:{target.target_id}")

    for share in doc.user_shares:
        refs.add(f"share_user:{share.user_id}")

    for share in doc.link_shares:
        if share.active:
            refs.add(f"link_share_ref:{share.id}")

    for grant in doc.meeting_access_grants:
        if grant.revoked_at is not None:
            continue
        refs.add(f"meeting_grant:{grant.user_id}")
        if grant.granted_by_meeting_id:
            refs.add(f"meeting_source:{grant.granted_by_meeting_id}")

    return sorted(refs)


def _extract_blocks_text(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""

    parts: list[str] = []
    for block in blocks:
        block_parts: list[str] = []
        _collect_text_parts(block, block_parts)
        block_text = " ".join(part for part in block_parts if part).strip()
        if block_text:
            parts.append(block_text)
    return "\n\n".join(part for part in parts if part).strip()


def _collect_text_parts(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        if normalized:
            parts.append(normalized)
        return

    if isinstance(value, list):
        for item in value:
            _collect_text_parts(item, parts)
        return

    if not isinstance(value, dict):
        return

    if isinstance(value.get("text"), str):
        normalized = " ".join(value["text"].split()).strip()
        if normalized:
            parts.append(normalized)

    for key in ("content", "children"):
        nested = value.get(key)
        if nested is not None:
            _collect_text_parts(nested, parts)


def _summarize_text(text: str, *, max_chars: int = 240) -> str | None:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return None
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
