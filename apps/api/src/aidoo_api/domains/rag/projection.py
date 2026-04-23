from __future__ import annotations

from aidoo_api.domains.rag.contracts import RagChunk, RagProjection


def build_projection(
    *,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
    source_kind: str,
    title: str | None = None,
    summary: str | None = None,
    text_content: str = "",
    owner_label: str | None = None,
    visibility_refs: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> RagProjection:
    resolved_metadata = dict(metadata or {})
    resolved_metadata.setdefault("content_modality", "text")
    return RagProjection(
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        source_kind=source_kind,
        title=title,
        summary=summary,
        text_content=text_content,
        owner_label=owner_label,
        visibility_refs=list(visibility_refs or []),
        metadata=resolved_metadata,
    )


def projection_to_chunks(
    projection: RagProjection,
    *,
    max_chars: int = 800,
) -> list[RagChunk]:
    raw_text = projection.text_content.strip() or (projection.summary or "").strip()
    if not raw_text:
        raw_text = projection.title or projection.resource_id

    chunks: list[RagChunk] = []
    cursor = 0
    index = 0
    while cursor < len(raw_text):
        piece = raw_text[cursor : cursor + max_chars].strip()
        if piece:
            chunks.append(
                RagChunk(
                    chunk_id=f"{projection.resource_id}:{index}",
                    text=piece,
                    summary=(piece[:160] + "...") if len(piece) > 160 else piece,
                    metadata={
                        "resource_type": projection.resource_type,
                        "resource_id": projection.resource_id,
                        "source_kind": projection.source_kind,
                        "workspace_id": projection.workspace_id,
                        "chunk_index": index,
                    },
                )
            )
            index += 1
        cursor += max_chars

    if chunks:
        return chunks

    return [
        RagChunk(
            chunk_id=f"{projection.resource_id}:0",
            text=projection.resource_id,
            summary=projection.title or projection.resource_id,
            metadata={
                "resource_type": projection.resource_type,
                "resource_id": projection.resource_id,
                "source_kind": projection.source_kind,
                "workspace_id": projection.workspace_id,
                "chunk_index": 0,
            },
        )
    ]
