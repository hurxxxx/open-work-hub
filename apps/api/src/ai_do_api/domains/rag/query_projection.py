from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ai_do_api.domains.rag.contracts import (
    RagGroundedAnswer,
    RagGroundedCitation,
    RagQueryHit,
    RagVectorSearchHit,
)


def to_query_hit(hit: RagVectorSearchHit) -> RagQueryHit:
    projection = hit.projection
    return RagQueryHit(
        scope_kind=projection.scope_kind,
        source_kind=projection.source_kind,
        resource_type=projection.resource_type,
        resource_id=projection.resource_id,
        workspace_id=projection.workspace_id,
        title=projection.title,
        summary=hit.summary or projection.summary,
        excerpt=hit.text,
        score=hit.score,
        citation=hit.citation,
        owner_label=projection.owner_label,
        acl_summary=summarize_acl_refs(projection.visibility_refs),
        origin_ref=projection.metadata.get("origin_ref") if projection.metadata else None,
        metadata=dict(hit.metadata),
    )


def build_default_grounded_answer(
    *,
    query: str,
    hits: Sequence[RagQueryHit],
) -> RagGroundedAnswer | None:
    if not hits:
        return None
    lead_hits = list(hits[:3])
    text = " ".join(
        safe_result_text(hit.excerpt or hit.summary or hit.title or hit.resource_id, max_chars=280)
        for hit in lead_hits
        if hit.excerpt or hit.summary or hit.title
    )
    if not text:
        text = f"'{query}'와 관련된 검색 결과 {len(hits)}건을 찾았습니다."
    return RagGroundedAnswer(
        text=text,
        citations=[
            RagGroundedCitation(
                resource_id=hit.resource_id,
                source_kind=hit.source_kind,
                quote=safe_result_text(
                    hit.excerpt or hit.summary or hit.title or hit.resource_id,
                    max_chars=280,
                ),
                locator=hit.citation,
            )
            for hit in lead_hits
        ],
        sources_used=sorted({hit.source_kind for hit in hits}),
    )


def build_query_profile(
    *,
    vector_requested_top_k: int,
    vector_hit_count: int,
    post_filtered_hit_count: int,
    returned_hit_count: int,
    rerank_applied: bool,
    rerank_degraded: bool,
    post_filter_applied: bool,
    grounded_answer_degraded: bool,
    collections_consulted: Sequence[str],
    vector_search_mode: str | None = None,
) -> dict[str, Any]:
    return {
        "vector_requested_top_k": vector_requested_top_k,
        "vector_hit_count": vector_hit_count,
        "post_filtered_hit_count": post_filtered_hit_count,
        "returned_hit_count": returned_hit_count,
        "rerank_applied": rerank_applied,
        "rerank_degraded": rerank_degraded,
        "post_filter_applied": post_filter_applied,
        "grounded_answer_degraded": grounded_answer_degraded,
        "collections_consulted": list(collections_consulted),
        "legacy_collection_fallback_applied": len(collections_consulted) > 1,
        "vector_search_mode": vector_search_mode,
    }


def summarize_acl_refs(visibility_refs: Sequence[str]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for raw_ref in visibility_refs:
        prefix = raw_ref.split(":", 1)[0]
        label = _ACL_SUMMARY_LABELS.get(prefix, prefix.replace("_", " "))
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def safe_result_text(value: str, *, max_chars: int) -> str:
    normalized = " ".join(value.split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


_ACL_SUMMARY_LABELS = {
    "workspace": "workspace",
    "workspace_public": "workspace public",
    "owner": "owner",
    "target": "target access",
    "share_user": "direct share",
    "link_share_ref": "link share",
    "meeting_grant": "meeting grant",
    "meeting_source": "meeting source",
    "meeting_organizer": "meeting organizer",
    "meeting_attendee": "meeting attendee",
    "team": "team access",
    "list": "list access",
    "task_grant": "task grant",
}
