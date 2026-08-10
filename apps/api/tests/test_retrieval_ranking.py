from __future__ import annotations

import pytest
from types import SimpleNamespace

from open_alm_api.domains.rag.contracts import RagGroundedAnswer, RagGroundedCitation
from open_alm_api.domains.rag.providers.fake import FakeRerankClient
from open_alm_api.domains.retrieval.contracts import RetrievalHit
from open_alm_api.domains.retrieval import grounding
from open_alm_api.domains.retrieval.ranking import (
    candidate_limit,
    canonical_resource_identity,
    dedupe_ranked_hits,
    fuse_ranked_hits,
    rerank_hits,
)


def _hit(
    *,
    source: str,
    resource_id: str,
    score: float,
    excerpt: str,
    methods: list[str],
    source_kind: str = "manual",
) -> RetrievalHit:
    return RetrievalHit(
        source=source,
        source_kind=source_kind,
        resource_type="docs_native_doc",
        resource_id=resource_id,
        workspace_id="workspace-1",
        title=f"Document {resource_id}",
        excerpt=excerpt,
        score=score,
        citation=f"/docs/{resource_id}" if source == "keyword" else f"{resource_id}:0",
        methods=methods,
        metadata={"scope_kind": "workspace"},
    )


def test_candidate_limit_uses_bounded_oversampling() -> None:
    assert candidate_limit(1) == 80
    assert candidate_limit(25) == 100
    assert candidate_limit(100) == 100


def test_rrf_fuses_incomparable_backend_scores_and_dedupes_resource() -> None:
    keyword = [
        _hit(
            source="keyword",
            resource_id="shared",
            score=42.0,
            excerpt="lexical excerpt",
            methods=["bm25"],
        ),
        _hit(
            source="keyword",
            resource_id="keyword-only",
            score=41.0,
            excerpt="keyword only",
            methods=["bm25"],
        ),
    ]
    dense = [
        _hit(
            source="generic_rag",
            resource_id="dense-only",
            score=0.99,
            excerpt="dense only",
            methods=["semantic", "vector"],
        ),
        _hit(
            source="generic_rag",
            resource_id="shared",
            score=0.12,
            excerpt="specific vector passage",
            methods=["semantic", "vector"],
        ),
    ]

    result = fuse_ranked_hits({"keyword": keyword, "generic_rag": dense})

    assert len(result.hits) == 3
    shared = next(hit for hit in result.hits if hit.resource_id == "shared")
    assert shared.excerpt == "lexical excerpt\n\nspecific vector passage"
    assert shared.citation == "/docs/shared"
    assert shared.methods == ["bm25", "semantic", "vector", "rrf"]
    assert shared.metadata["retrieval"]["backend_ranks"] == {
        "generic_rag": 2,
        "keyword": 1,
    }
    assert shared.score == pytest.approx((1 / 61) + (1 / 62))


def test_fused_rerank_receives_keyword_and_vector_evidence() -> None:
    keyword = _hit(
        source="keyword",
        resource_id="shared",
        score=42.0,
        excerpt="SAE J3109 J3174 exact lexical evidence",
        methods=["bm25"],
    )
    dense = _hit(
        source="generic_rag",
        resource_id="shared",
        score=0.99,
        excerpt="vehicle heater semantic passage",
        methods=["semantic", "vector"],
    )
    fused = fuse_ranked_hits({"keyword": [keyword], "generic_rag": [dense]})

    class _CapturingReranker:
        provider_name = "capturing-reranker"

        def rerank(self, *, query, hits, timeout_seconds):
            del query, timeout_seconds
            assert "SAE J3109 J3174 exact lexical evidence" in hits[0].text
            assert "vehicle heater semantic passage" in hits[0].text
            return hits

    result = rerank_hits(
        query="SAE J3109 J3174",
        hits=fused.hits,
        rerank_client=_CapturingReranker(),
    )

    assert result.profile["applied"] is True


def test_fused_excerpts_are_bounded_and_do_not_accumulate_vector_duplicates() -> None:
    keyword = _hit(
        source="keyword",
        resource_id="shared",
        score=42.0,
        excerpt="exact lexical evidence",
        methods=["bm25"],
    )
    dense = [
        _hit(
            source="generic_rag",
            resource_id="shared",
            score=0.99,
            excerpt="first vector passage " * 100,
            methods=["semantic", "vector"],
        ),
        _hit(
            source="generic_rag",
            resource_id="shared",
            score=0.98,
            excerpt="second vector passage",
            methods=["semantic", "vector"],
        ),
    ]

    shared = fuse_ranked_hits({"keyword": [keyword], "generic_rag": dense}).hits[0]

    assert shared.excerpt is not None
    assert shared.excerpt.startswith("exact lexical evidence\n\nfirst vector passage")
    assert "second vector passage" not in shared.excerpt
    assert len(shared.excerpt) == 1400


def test_identity_is_stable_across_scope_and_source_kind_changes() -> None:
    base = _hit(
        source="keyword",
        resource_id="same",
        score=1.0,
        excerpt="one",
        methods=["bm25"],
    )
    moved = base.model_copy(
        update={
            "workspace_id": None,
            "source_kind": "guide",
            "metadata": {"scope_kind": "company"},
        }
    )

    assert canonical_resource_identity(base) == canonical_resource_identity(moved)
    assert len(dedupe_ranked_hits([base, moved]).hits) == 1


def test_identity_keeps_different_resource_types_separate() -> None:
    base = _hit(
        source="keyword",
        resource_id="same",
        score=1.0,
        excerpt="one",
        methods=["bm25"],
    )
    other_type = base.model_copy(update={"resource_type": "qna_document"})

    assert canonical_resource_identity(base) != canonical_resource_identity(other_type)
    assert len(dedupe_ranked_hits([base, other_type]).hits) == 2


def test_cross_encoder_reranks_fused_candidates_and_preserves_metadata() -> None:
    hits = [
        _hit(
            source="keyword",
            resource_id="low-overlap",
            score=0.2,
            excerpt="unrelated text",
            methods=["bm25", "rrf"],
        ),
        _hit(
            source="generic_rag",
            resource_id="high-overlap",
            score=0.15,
            excerpt="hybrid retrieval",
            methods=["vector", "rrf"],
        ),
    ]

    result = rerank_hits(
        query="hybrid retrieval",
        hits=hits,
        rerank_client=FakeRerankClient(),
    )

    assert result.profile["applied"] is True
    assert result.hits[0].resource_id == "high-overlap"
    assert "cross_encoder" in result.hits[0].methods
    assert result.hits[0].metadata["retrieval"]["pre_rerank_score"] == 0.15


def test_rerank_falls_back_when_normalized_scores_are_low_confidence() -> None:
    hits = [
        _hit(
            source="keyword",
            resource_id="consensus-first",
            score=0.032,
            excerpt="strong keyword and vector consensus",
            methods=["bm25", "vector", "rrf"],
        ),
        _hit(
            source="keyword",
            resource_id="reranker-first",
            score=0.025,
            excerpt="weak candidate",
            methods=["bm25", "vector", "rrf"],
        ),
    ]

    class _LowConfidenceReranker:
        provider_name = "normalized-reranker"
        score_semantics = "normalized_relevance"

        def rerank(self, *, query, hits, timeout_seconds):
            del query, timeout_seconds
            return [
                hits[1].model_copy(update={"score": 0.000131607}),
                hits[0].model_copy(update={"score": 0.000005424}),
            ]

    result = rerank_hits(
        query="short search query",
        hits=hits,
        rerank_client=_LowConfidenceReranker(),
    )

    assert [hit.resource_id for hit in result.hits] == [
        "consensus-first",
        "reranker-first",
    ]
    assert [hit.score for hit in result.hits] == [0.032, 0.025]
    assert all("cross_encoder" not in hit.methods for hit in result.hits)
    assert result.profile == {
        "applied": False,
        "degraded": True,
        "provider": "normalized-reranker",
        "score_semantics": "normalized_relevance",
        "error_type": "LowConfidenceRerankScores",
        "candidate_count": 2,
    }


@pytest.mark.parametrize(
    ("scores", "expected_error_type"),
    [
        ([0.4, 0.4000004], "UninformativeRerankScores"),
        ([float("nan"), 0.7], "InvalidRerankScores"),
    ],
)
def test_rerank_falls_back_when_scores_cannot_rank_candidates(
    scores: list[float],
    expected_error_type: str,
) -> None:
    hits = [
        _hit(
            source="keyword",
            resource_id="first",
            score=0.032,
            excerpt="first",
            methods=["bm25", "rrf"],
        ),
        _hit(
            source="generic_rag",
            resource_id="second",
            score=0.025,
            excerpt="second",
            methods=["vector", "rrf"],
        ),
    ]

    class _UnusableReranker:
        provider_name = "unusable-reranker"

        def rerank(self, *, query, hits, timeout_seconds):
            del query, timeout_seconds
            return [
                hit.model_copy(update={"score": score})
                for hit, score in zip(reversed(hits), scores, strict=True)
            ]

    result = rerank_hits(
        query="query",
        hits=hits,
        rerank_client=_UnusableReranker(),
    )

    assert [hit.resource_id for hit in result.hits] == ["first", "second"]
    assert result.profile["error_type"] == expected_error_type


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_rerank_rejects_scores_outside_declared_normalized_range(score: float) -> None:
    hit = _hit(
        source="keyword",
        resource_id="first",
        score=0.032,
        excerpt="first",
        methods=["bm25", "rrf"],
    )

    class _InvalidNormalizedReranker:
        provider_name = "normalized-reranker"
        score_semantics = "normalized_relevance"

        def rerank(self, *, query, hits, timeout_seconds):
            del query, timeout_seconds
            return [hits[0].model_copy(update={"score": score})]

    result = rerank_hits(
        query="query",
        hits=[hit],
        rerank_client=_InvalidNormalizedReranker(),
    )

    assert result.hits == (hit,)
    assert result.profile["error_type"] == "InvalidRerankScores"


def test_rerank_accepts_normalized_scores_at_confidence_boundary() -> None:
    hits = [
        _hit(
            source="keyword",
            resource_id="first",
            score=0.032,
            excerpt="first",
            methods=["bm25", "rrf"],
        ),
        _hit(
            source="generic_rag",
            resource_id="second",
            score=0.025,
            excerpt="second",
            methods=["vector", "rrf"],
        ),
    ]

    class _BoundaryReranker:
        provider_name = "boundary-reranker"
        score_semantics = "normalized_relevance"

        def rerank(self, *, query, hits, timeout_seconds):
            del query, timeout_seconds
            return [
                hits[1].model_copy(update={"score": 0.001}),
                hits[0].model_copy(update={"score": 0.0001}),
            ]

    result = rerank_hits(
        query="query",
        hits=hits,
        rerank_client=_BoundaryReranker(),
    )

    assert [hit.resource_id for hit in result.hits] == ["second", "first"]
    assert result.profile["applied"] is True


@pytest.mark.parametrize("mode", ["missing", "error", "empty"])
def test_rerank_falls_back_to_fusion_order(mode: str) -> None:
    hits = [
        _hit(
            source="keyword",
            resource_id="first",
            score=0.2,
            excerpt="first",
            methods=["bm25", "rrf"],
        ),
        _hit(
            source="generic_rag",
            resource_id="second",
            score=0.1,
            excerpt="second",
            methods=["vector", "rrf"],
        ),
    ]

    class _Reranker:
        provider_name = "broken-reranker"

        def rerank(self, **_kwargs):
            if mode == "error":
                raise TimeoutError("timeout")
            return []

    client = None if mode == "missing" else _Reranker()
    result = rerank_hits(query="query", hits=hits, rerank_client=client)

    assert [hit.resource_id for hit in result.hits] == ["first", "second"]
    assert result.profile["applied"] is False
    assert result.profile["degraded"] is (mode != "missing")


def test_grounding_keeps_collision_safe_citation_source_and_fused_provenance(
    monkeypatch,
) -> None:
    hits = [
        _hit(
            source="keyword",
            source_kind="manual",
            resource_id="same-id",
            score=0.2,
            excerpt="manual evidence",
            methods=["bm25"],
        ).model_copy(
            update={
                "metadata": {
                    "scope_kind": "workspace",
                    "retrieval": {"backends": ["keyword", "generic_rag"]},
                }
            }
        ),
        _hit(
            source="qna",
            source_kind="qna_document",
            resource_id="same-id",
            score=0.1,
            excerpt="qna evidence",
            methods=["vector"],
        ),
    ]

    class _Synthesizer:
        def __init__(self, **_kwargs):
            pass

        def synthesize(self, **_kwargs):
            return RagGroundedAnswer(
                text="answer",
                citations=[
                    RagGroundedCitation(
                        resource_id="same-id",
                        source_kind="qna_document",
                        quote="qna evidence",
                    )
                ],
            )

    monkeypatch.setattr(grounding, "LlmGroundedAnswerSynthesizer", _Synthesizer)

    result = grounding.ground_ranked_hits(
        db=object(),
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        query="question",
        hits=hits,
        source="test",
        principal_kind="user",
        principal_id="user-1",
        agent_run_id=None,
        conversation_id=None,
    )

    assert result.answer is not None
    assert result.answer.citations[0].source == "qna"
    assert result.answer.sources_used == ["keyword", "generic_rag", "qna"]
