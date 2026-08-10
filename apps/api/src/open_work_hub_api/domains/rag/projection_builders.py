from __future__ import annotations

from collections.abc import Iterable, Mapping

from open_work_hub_api.domains.rag.contracts import RagChunk, RagProjection, RagScopeKind


def build_text_content(sections: Iterable[str | None]) -> str:
    return "\n\n".join(section for section in sections if section)


def build_projection_record(
    *,
    workspace_id: str | None,
    scope_kind: RagScopeKind = RagScopeKind.WORKSPACE,
    resource_type: str,
    resource_id: str,
    source_kind: str,
    title: str | None = None,
    summary: str | None = None,
    text_content: str = "",
    owner_label: str | None = None,
    visibility_refs: Iterable[str] | None = None,
    metadata: Mapping[str, object] | None = None,
    chunks: Iterable[RagChunk] | None = None,
) -> RagProjection:
    return RagProjection(
        scope_kind=scope_kind,
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        source_kind=source_kind,
        title=title,
        summary=summary,
        text_content=text_content,
        owner_label=owner_label,
        visibility_refs=list(visibility_refs) if visibility_refs is not None else [],
        metadata=_projection_metadata(metadata),
        chunks=list(chunks) if chunks is not None else [],
    )


def build_text_projection(
    *,
    workspace_id: str | None,
    scope_kind: RagScopeKind = RagScopeKind.WORKSPACE,
    resource_type: str,
    resource_id: str,
    source_kind: str,
    title: str | None = None,
    summary: str | None = None,
    text_sections: Iterable[str | None] = (),
    owner_label: str | None = None,
    visibility_refs: Iterable[str] | None = None,
    metadata: Mapping[str, object] | None = None,
    chunks: Iterable[RagChunk] | None = None,
) -> RagProjection:
    return build_projection_record(
        workspace_id=workspace_id,
        scope_kind=scope_kind,
        resource_type=resource_type,
        resource_id=resource_id,
        source_kind=source_kind,
        title=title,
        summary=summary,
        text_content=build_text_content(text_sections),
        owner_label=owner_label,
        visibility_refs=visibility_refs,
        metadata=metadata,
        chunks=chunks,
    )


def build_projection_chunk(
    *,
    workspace_id: str | None,
    scope_kind: RagScopeKind = RagScopeKind.WORKSPACE,
    resource_type: str,
    resource_id: str,
    source_kind: str,
    chunk_id: str,
    text: str,
    chunk_index: int,
    summary: str | None = None,
    index_text: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> RagChunk:
    resolved_metadata = {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "source_kind": source_kind,
        "workspace_id": workspace_id,
        "scope_kind": scope_kind.value,
        "chunk_index": chunk_index,
    }
    resolved_metadata.update(dict(metadata or {}))
    return RagChunk(
        chunk_id=chunk_id,
        text=text,
        summary=summary,
        index_text=index_text,
        metadata=resolved_metadata,
    )


def _projection_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
    resolved_metadata = dict(metadata or {})
    resolved_metadata.setdefault("content_modality", "text")
    return resolved_metadata
