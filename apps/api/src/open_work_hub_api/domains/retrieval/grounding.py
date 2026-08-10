from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.rag.contracts import RagQueryHit, RagScopeKind
from open_work_hub_api.domains.rag.grounded_answer import LlmGroundedAnswerSynthesizer
from open_work_hub_api.domains.rag.query_projection import build_default_grounded_answer
from open_work_hub_api.domains.retrieval.contracts import (
    RetrievalCitation,
    RetrievalGroundedAnswer,
    RetrievalHit,
)


@dataclass(frozen=True, slots=True)
class RetrievalGroundingResult:
    answer: RetrievalGroundedAnswer | None
    degraded: bool
    error_type: str | None = None


def ground_ranked_hits(
    *,
    db: Session,
    workspace: Workspace,
    user: User,
    query: str,
    hits: Sequence[RetrievalHit],
    source: str,
    principal_kind: str,
    principal_id: str | None,
    agent_run_id: str | None,
    conversation_id: str | None,
) -> RetrievalGroundingResult:
    rag_hits = [_to_rag_query_hit(hit) for hit in hits]
    if not rag_hits:
        return RetrievalGroundingResult(answer=None, degraded=False)

    synthesizer = LlmGroundedAnswerSynthesizer(
        db=db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        principal_kind=principal_kind,
        principal_id=principal_id or user.id,
        source=source,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )
    error_type: str | None = None
    try:
        grounded = synthesizer.synthesize(query=query, hits=rag_hits)
    except Exception as error:  # noqa: BLE001 - evidence-only fallback remains safe.
        grounded = None
        error_type = type(error).__name__
    degraded = grounded is None
    if grounded is None:
        grounded = build_default_grounded_answer(query=query, hits=rag_hits)
    if grounded is None:
        return RetrievalGroundingResult(
            answer=None,
            degraded=True,
            error_type=error_type or "EmptyGroundedAnswer",
        )

    sources_by_resource = _citation_sources(hits)
    citations = [
        RetrievalCitation(
            resource_id=citation.resource_id,
            source=sources_by_resource.get(
                (citation.resource_id, citation.source_kind), citation.source_kind
            ),
            quote=citation.quote,
            locator=citation.locator,
        )
        for citation in grounded.citations
    ]
    return RetrievalGroundingResult(
        answer=RetrievalGroundedAnswer(
            text=grounded.text,
            citations=citations,
            unsupported_claims=list(grounded.unsupported_claims),
            sources_used=_sources_used(hits),
        ),
        degraded=degraded,
        error_type=error_type if degraded else None,
    )


def _to_rag_query_hit(hit: RetrievalHit) -> RagQueryHit:
    raw_scope = str(hit.metadata.get("scope_kind") or RagScopeKind.WORKSPACE.value)
    try:
        scope_kind = RagScopeKind(raw_scope)
    except ValueError:
        scope_kind = RagScopeKind.WORKSPACE
    return RagQueryHit(
        scope_kind=scope_kind,
        source_kind=hit.source_kind or hit.source,
        resource_type=hit.resource_type,
        resource_id=hit.resource_id,
        workspace_id=hit.workspace_id,
        title=hit.title,
        summary=hit.summary,
        excerpt=hit.excerpt,
        score=hit.score,
        citation=hit.citation,
        owner_label=_string_or_none(hit.metadata.get("owner_label")),
        acl_summary=_string_list(hit.metadata.get("acl_summary")),
        origin_ref=_string_or_none(hit.metadata.get("origin_ref")),
        metadata=dict(hit.metadata),
    )


def _string_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _citation_sources(hits: Sequence[RetrievalHit]) -> dict[tuple[str, str], str]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for hit in hits:
        key = (hit.resource_id, hit.source_kind or hit.source)
        grouped.setdefault(key, []).append(hit.source)
    return {key: sources[0] for key, sources in grouped.items() if len(set(sources)) == 1}


def _sources_used(hits: Sequence[RetrievalHit]) -> list[str]:
    sources: list[str] = []
    for hit in hits:
        retrieval = hit.metadata.get("retrieval") if hit.metadata else None
        backends = retrieval.get("backends") if isinstance(retrieval, dict) else None
        values = backends if isinstance(backends, list) else [hit.source]
        for value in values:
            source = str(value or "").strip()
            if source and source not in sources:
                sources.append(source)
    return sources
