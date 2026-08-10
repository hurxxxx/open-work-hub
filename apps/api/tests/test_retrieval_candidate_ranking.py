from __future__ import annotations

from collections.abc import Sequence

import pytest

from ai_do_api.domains.rag.contracts import RagVectorSearchHit
from ai_do_api.domains.retrieval.candidate_ranking import (
    MAX_CANDIDATES,
    MAX_CANDIDATE_TEXT_CHARS,
    MAX_QUERY_CHARS,
    MAX_TOP_K,
    CandidateDocument,
    CandidateRankingRequest,
    CandidateRankingService,
)


class _SemanticEmbeddingClient:
    provider_name = "test-semantic"

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.document_batches: list[list[str]] = []

    def embed_query(
        self,
        text: str,
        timeout_seconds: float | None = None,
    ) -> list[float]:
        del timeout_seconds
        self.queries.append(text)
        return [1.0, 0.0]

    def embed_texts(
        self,
        texts: list[str],
        timeout_seconds: float | None = None,
    ) -> list[list[float]]:
        del timeout_seconds
        self.document_batches.append(texts)
        return [[1.0, 0.0] if "semantic-target" in text else [0.0, 1.0] for text in texts]


class _RecordingRerankClient:
    provider_name = "test-reranker"

    def __init__(self) -> None:
        self.calls = 0
        self.candidate_counts: list[int] = []

    def rerank(
        self,
        *,
        query: str,
        hits: list[RagVectorSearchHit],
        timeout_seconds: float | None = None,
    ) -> list[RagVectorSearchHit]:
        del query, timeout_seconds
        self.calls += 1
        self.candidate_counts.append(len(hits))
        return [
            hit.model_copy(update={"score": float(index)})
            for index, hit in enumerate(reversed(hits), start=1)
        ]


def _request(
    *,
    query: str,
    candidates: Sequence[CandidateDocument],
    top_k: int = 10,
    enable_semantic: bool = False,
    enable_rerank: bool = False,
) -> CandidateRankingRequest:
    return CandidateRankingRequest(
        query=query,
        candidates=candidates,
        top_k=top_k,
        enable_semantic=enable_semantic,
        enable_rerank=enable_rerank,
    )


def test_bm25_uses_platform_sparse_terms_and_prioritizes_exact_evidence() -> None:
    service = CandidateRankingService()

    result = service.rank(
        _request(
            query="열교환기 냉매 압축기",
            candidates=(
                CandidateDocument(
                    candidate_id="exact",
                    title="열교환기 냉매 회로",
                    text="냉매 압축기와 열교환기를 연결한다.",
                ),
                CandidateDocument(
                    candidate_id="partial",
                    text="압축기를 제어한다.",
                ),
                CandidateDocument(
                    candidate_id="unrelated",
                    text="광학 센서의 신호를 처리한다.",
                ),
            ),
        )
    )

    assert [candidate.candidate.candidate_id for candidate in result.candidates] == [
        "exact",
        "partial",
        "unrelated",
    ]
    assert result.candidates[0].bm25_score > result.candidates[1].bm25_score > 0
    assert result.candidates[2].bm25_score == 0
    assert result.profile.methods == ("bm25",)
    assert result.profile.degraded_reasons == ()


def test_semantic_ranking_is_fused_with_bm25_using_rrf() -> None:
    embedding = _SemanticEmbeddingClient()
    service = CandidateRankingService(embedding_client=embedding)

    result = service.rank(
        _request(
            query="exact-token",
            candidates=(
                CandidateDocument(candidate_id="lexical", text="exact-token literal evidence"),
                CandidateDocument(candidate_id="semantic", text="semantic-target concept"),
                CandidateDocument(candidate_id="other", text="unrelated material"),
            ),
            enable_semantic=True,
        )
    )

    by_id = {item.candidate.candidate_id: item for item in result.candidates}
    assert result.profile.semantic_applied is True
    assert result.profile.semantic_provider == "test-semantic"
    assert result.profile.fusion_applied is True
    assert result.profile.methods == ("bm25", "semantic", "vector", "rrf")
    assert by_id["semantic"].semantic_score == pytest.approx(1.0)
    assert by_id["lexical"].semantic_score == pytest.approx(0.0)
    assert all(item.rrf_score is not None for item in result.candidates)
    assert all("rrf" in item.methods for item in result.candidates)


def test_zero_bm25_input_order_cannot_overpower_semantic_signal() -> None:
    embedding = _SemanticEmbeddingClient()
    service = CandidateRankingService(embedding_client=embedding)
    candidates = tuple(
        CandidateDocument(
            candidate_id=f"candidate-{index}",
            text="semantic-target" if index == 99 else f"unrelated-{index}",
        )
        for index in range(100)
    )

    result = service.rank(
        _request(
            query="query-with-no-lexical-overlap",
            candidates=candidates,
            top_k=100,
            enable_semantic=True,
        )
    )

    assert result.candidates[0].candidate.candidate_id == "candidate-99"
    assert result.profile.semantic_applied is True
    assert result.profile.fusion_applied is False
    assert all(item.rrf_score is None for item in result.candidates)


def test_flat_semantic_scores_are_excluded_as_no_signal() -> None:
    class _FlatEmbeddingClient:
        provider_name = "flat-semantic"

        def embed_query(self, *_args, **_kwargs):
            return [1.0, 0.0]

        def embed_texts(self, texts, *_args, **_kwargs):
            return [[1.0, 0.0] for _ in texts]

    service = CandidateRankingService(embedding_client=_FlatEmbeddingClient())
    result = service.rank(
        _request(
            query="needle",
            candidates=(
                CandidateDocument(candidate_id="match", text="needle evidence"),
                CandidateDocument(candidate_id="other", text="other evidence"),
            ),
            enable_semantic=True,
        )
    )

    assert result.candidates[0].candidate.candidate_id == "match"
    assert result.profile.semantic_applied is False
    assert result.profile.fusion_applied is False
    assert result.profile.degraded_reasons == ("semantic:NoSignal",)


def test_embedding_failure_degrades_to_bm25_without_exposing_error_text() -> None:
    class _FailingEmbeddingClient:
        provider_name = "failing-embedding"

        def embed_query(self, *_args, **_kwargs):
            raise TimeoutError("secret upstream URL and credential")

        def embed_texts(self, *_args, **_kwargs):
            raise AssertionError("embed_texts must not run after query embedding fails")

    service = CandidateRankingService(embedding_client=_FailingEmbeddingClient())

    result = service.rank(
        _request(
            query="needle",
            candidates=(
                CandidateDocument(candidate_id="match", text="needle evidence"),
                CandidateDocument(candidate_id="other", text="other evidence"),
            ),
            enable_semantic=True,
        )
    )

    assert result.candidates[0].candidate.candidate_id == "match"
    assert result.profile.semantic_applied is False
    assert result.profile.fusion_applied is False
    assert result.profile.degraded_reasons == ("semantic:TimeoutError",)
    assert "secret" not in repr(result.profile)


def test_reranker_runs_once_and_failure_preserves_pre_rerank_order() -> None:
    class _FailingRerankClient:
        provider_name = "failing-reranker"

        def __init__(self) -> None:
            self.calls = 0

        def rerank(self, **_kwargs):
            self.calls += 1
            raise TimeoutError("provider timed out")

    reranker = _FailingRerankClient()
    service = CandidateRankingService(rerank_client=reranker)

    result = service.rank(
        _request(
            query="needle",
            candidates=(
                CandidateDocument(candidate_id="match", text="needle evidence"),
                CandidateDocument(candidate_id="other", text="other evidence"),
            ),
            enable_rerank=True,
        )
    )

    assert reranker.calls == 1
    assert [item.candidate.candidate_id for item in result.candidates] == ["match", "other"]
    assert result.profile.rerank_applied is False
    assert result.profile.degraded_reasons == ("rerank:TimeoutError",)


def test_candidate_text_query_and_top_k_caps_are_enforced_before_providers() -> None:
    embedding = _SemanticEmbeddingClient()
    reranker = _RecordingRerankClient()
    service = CandidateRankingService(
        embedding_client=embedding,
        rerank_client=reranker,
    )
    candidates = tuple(
        CandidateDocument(
            candidate_id=f"candidate-{index}",
            text="semantic-target " + ("x" * MAX_CANDIDATE_TEXT_CHARS),
        )
        for index in range(MAX_CANDIDATES + 5)
    )

    result = service.rank(
        _request(
            query="q" * (MAX_QUERY_CHARS + 20),
            candidates=candidates,
            top_k=MAX_TOP_K + 50,
            enable_semantic=True,
            enable_rerank=True,
        )
    )

    assert len(embedding.queries) == 1
    assert len(embedding.queries[0]) == MAX_QUERY_CHARS
    assert len(embedding.document_batches) == 1
    assert len(embedding.document_batches[0]) == MAX_CANDIDATES
    assert all(len(text) <= MAX_CANDIDATE_TEXT_CHARS for text in embedding.document_batches[0])
    assert reranker.calls == 1
    assert reranker.candidate_counts == [MAX_CANDIDATES]
    assert len(result.candidates) == MAX_TOP_K
    assert result.profile.input_candidate_count == MAX_CANDIDATES + 5
    assert result.profile.ranked_candidate_count == MAX_CANDIDATES
    assert result.profile.candidate_limit_applied is True
    assert result.profile.truncated_text_count == MAX_CANDIDATES
    assert result.profile.query_truncated is True
    assert result.profile.applied_top_k == MAX_TOP_K


def test_candidate_metadata_is_preserved_but_does_not_affect_ranking() -> None:
    service = CandidateRankingService()
    common = (
        CandidateDocument(
            candidate_id="first",
            text="same technical evidence",
            metadata={"applicant": "alpha"},
        ),
        CandidateDocument(
            candidate_id="second",
            text="same technical evidence",
            metadata={"applicant": "beta"},
        ),
    )
    swapped_metadata = (
        CandidateDocument(
            candidate_id="first",
            text="same technical evidence",
            metadata={"applicant": "beta"},
        ),
        CandidateDocument(
            candidate_id="second",
            text="same technical evidence",
            metadata={"applicant": "alpha"},
        ),
    )

    first_result = service.rank(_request(query="technical", candidates=common))
    second_result = service.rank(_request(query="technical", candidates=swapped_metadata))

    assert [item.candidate.candidate_id for item in first_result.candidates] == [
        item.candidate.candidate_id for item in second_result.candidates
    ]
    assert first_result.candidates[0].candidate.metadata == {"applicant": "alpha"}


@pytest.mark.parametrize(
    ("ranking_request", "message"),
    [
        (_request(query=" ", candidates=()), "query must not be blank"),
        (_request(query="query", candidates=(), top_k=0), "top_k must be positive"),
        (
            _request(
                query="query",
                candidates=(
                    CandidateDocument(candidate_id="duplicate", text="one"),
                    CandidateDocument(candidate_id="duplicate", text="two"),
                ),
            ),
            "duplicate candidate_id",
        ),
    ],
)
def test_invalid_public_inputs_are_rejected(
    ranking_request: CandidateRankingRequest,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        CandidateRankingService().rank(ranking_request)
