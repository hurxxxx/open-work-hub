from __future__ import annotations

from open_alm_api.domains.rag.chunking import DEFAULT_TARGET_CHARS, default_korean_aware_chunks
from open_alm_api.domains.rag.contracts import RagChunk, RagProjection, RagScopeKind
from open_alm_api.domains.rag.projection_builders import build_projection_record


def build_projection(
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
    visibility_refs: list[str] | None = None,
    metadata: dict[str, object] | None = None,
    chunks: list[RagChunk] | None = None,
) -> RagProjection:
    return build_projection_record(
        workspace_id=workspace_id,
        scope_kind=scope_kind,
        resource_type=resource_type,
        resource_id=resource_id,
        source_kind=source_kind,
        title=title,
        summary=summary,
        text_content=text_content,
        owner_label=owner_label,
        visibility_refs=visibility_refs,
        metadata=metadata,
        chunks=chunks,
    )


def projection_to_chunks(
    projection: RagProjection,
    *,
    max_chars: int = DEFAULT_TARGET_CHARS,
) -> list[RagChunk]:
    if projection.chunks:
        return list(projection.chunks)
    return default_korean_aware_chunks(projection, target_chars=max_chars)
