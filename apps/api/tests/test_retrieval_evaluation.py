from __future__ import annotations

from types import SimpleNamespace

import pytest

from open_alm_api.domains.retrieval.evaluation import (
    RetrievalEvaluationCase,
    RetrievalEvaluationReport,
    RetrievalQualityGateArtifact,
    retrieval_embedding_generation_identity,
    retrieval_reranker_generation_identity,
    evaluate_hybrid_quality_gate,
    evaluate_retrieval_cases,
    validate_quality_gate_artifact,
    retrieval_quality_corpus_sha256,
)


def _cases(*, first_rank: int, count: int = 60, latency_ms: int = 1200):
    cases = []
    for index in range(count):
        irrelevant = [f"irrelevant-{index}-{rank}" for rank in range(first_rank - 1)]
        cases.append(
            RetrievalEvaluationCase(
                query_id=f"query-{index}",
                relevant_resource_ids=[f"relevant-{index}"],
                ranked_resource_ids=[*irrelevant, f"relevant-{index}"],
                latency_ms=latency_ms,
            )
        )
    return cases


def test_retrieval_metrics_compute_recall_mrr_ndcg_and_p95() -> None:
    report = evaluate_retrieval_cases(
        [
            RetrievalEvaluationCase(
                query_id="q1",
                relevant_resource_ids=["a", "b"],
                ranked_resource_ids=["x", "a", "b"],
                latency_ms=100,
            ),
            RetrievalEvaluationCase(
                query_id="q2",
                relevant_resource_ids=["c"],
                ranked_resource_ids=["c"],
                latency_ms=500,
            ),
        ]
    )

    assert report.query_count == 2
    assert report.recall_at_k == 1.0
    assert report.mrr_at_k == 0.75
    assert 0 < report.ndcg_at_k < 1
    assert report.p95_latency_ms == 500


def test_files_quality_artifact_v3_requires_exact_vector_generation_identity() -> None:
    report = {
        "query_count": 60,
        "recall_at_k": 1.0,
        "mrr_at_k": 1.0,
        "ndcg_at_k": 1.0,
        "p95_latency_ms": 10,
        "acl_violation_count": 0,
        "citation_failure_count": 0,
    }

    with pytest.raises(ValueError, match="qdrant_physical_id"):
        RetrievalQualityGateArtifact(
            artifact_version=3,
            corpus_id="files-v3",
            corpus_sha256="a" * 64,
            index_generation="release_20260723",
            keyword_index_uuid="opensearch-uuid",
            keyword_index_config_sha256="b" * 64,
            keyword_index_sha256="c" * 64,
            bm25=report,
            dense=report,
            hybrid=report,
        )

    artifact = RetrievalQualityGateArtifact(
        artifact_version=3,
        corpus_id="files-v3",
        corpus_sha256="a" * 64,
        index_generation="release_20260723",
        keyword_index_uuid="opensearch-uuid",
        keyword_index_config_sha256="b" * 64,
        keyword_index_sha256="c" * 64,
        qdrant_physical_id="files-v1-release_20260723",
        qdrant_config_sha256="d" * 64,
        qdrant_content_sha256="e" * 64,
        embedding_model_identity="dragonkue/model@revision",
        embedding_config_sha256="f" * 64,
        reranker_model_identity="inference_gateway:example/reranker",
        reranker_config_sha256="1" * 64,
        source_files_event_watermark=7,
        source_resource_count=10,
        source_identity_sha256="2" * 64,
        source_artifact_sha256="3" * 64,
        source_acl_envelope_sha256="4" * 64,
        judgment_acl_sha256="5" * 64,
        bm25=report,
        dense=report,
        hybrid=report,
    )

    assert artifact.artifact_version == 3


def test_embedding_generation_identity_binds_model_revision_and_query_configuration() -> None:
    settings = SimpleNamespace(
        rag_embedding_provider="inference_gateway",
        rag_local_embedding_model="example/embedding-model",
        rag_local_embedding_revision="revision-a",
        rag_local_embedding_device="cuda",
        rag_local_embedding_dtype="bfloat16",
        rag_local_embedding_max_seq_length=1024,
        rag_local_embedding_normalize=True,
        rag_local_embedding_query_prompt_name="query",
        rag_local_embedding_query_prefix="search: ",
        rag_local_embedding_trust_remote_code=False,
    )

    identity = retrieval_embedding_generation_identity(settings)
    changed = retrieval_embedding_generation_identity(
        SimpleNamespace(**{**vars(settings), "rag_local_embedding_revision": "revision-b"})
    )

    assert identity.model_identity == "example/embedding-model"
    assert len(identity.config_sha256) == 64
    assert identity.config_sha256 != changed.config_sha256


def _reranker_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "rag_rerank_provider": "inference_gateway",
        "rag_local_reranker_model": "example/reranker",
        "rag_local_reranker_revision": "revision-a",
        "rag_local_reranker_device": "cuda",
        "rag_local_reranker_dtype": "bfloat16",
        "rag_local_reranker_batch_size": 16,
        "rag_local_reranker_max_length": 512,
        "rag_local_reranker_trust_remote_code": False,
        "rag_rerank_candidate_k": 80,
        "inference_gateway_base_url": "https://gateway.example/internal",
        "inference_gateway_api_key": "gateway-secret-a",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_disabled_reranker_identity_ignores_unused_runtime_settings() -> None:
    disabled = retrieval_reranker_generation_identity(
        _reranker_settings(rag_rerank_provider="disabled")
    )
    changed_unused_settings = retrieval_reranker_generation_identity(
        _reranker_settings(
            rag_rerank_provider="disabled",
            rag_local_reranker_model="other/reranker",
            rag_local_reranker_revision="revision-b",
            rag_local_reranker_batch_size=2,
            rag_local_reranker_max_length=2048,
            rag_rerank_candidate_k=20,
            inference_gateway_base_url="https://other.example",
            inference_gateway_api_key="gateway-secret-b",
        )
    )
    other_disabled_provider = retrieval_reranker_generation_identity(
        _reranker_settings(rag_rerank_provider="none")
    )

    assert disabled.model_identity == "disabled"
    assert disabled.config_sha256 == changed_unused_settings.config_sha256
    assert disabled.config_sha256 != other_disabled_provider.config_sha256


@pytest.mark.parametrize(
    ("setting", "changed_value"),
    [
        ("rag_local_reranker_model", "other/reranker"),
        ("rag_local_reranker_revision", "revision-b"),
        ("rag_local_reranker_device", "cpu"),
        ("rag_local_reranker_dtype", "float32"),
        ("rag_local_reranker_batch_size", 8),
        ("rag_local_reranker_max_length", 1024),
        ("rag_local_reranker_trust_remote_code", True),
        ("rag_rerank_candidate_k", 40),
    ],
)
def test_local_reranker_identity_binds_every_runtime_setting(
    setting: str,
    changed_value: object,
) -> None:
    baseline = retrieval_reranker_generation_identity(
        _reranker_settings(rag_rerank_provider="local")
    )
    changed = retrieval_reranker_generation_identity(
        _reranker_settings(rag_rerank_provider="local", **{setting: changed_value})
    )

    assert baseline.model_identity == "local:example/reranker"
    assert baseline.config_sha256 != changed.config_sha256


def test_inference_gateway_reranker_identity_binds_endpoint_model_and_candidate_budget() -> None:
    baseline = retrieval_reranker_generation_identity(_reranker_settings())
    equivalent_endpoint = retrieval_reranker_generation_identity(
        _reranker_settings(inference_gateway_base_url="https://gateway.example/internal/v1/")
    )
    changed_endpoint = retrieval_reranker_generation_identity(
        _reranker_settings(inference_gateway_base_url="https://other.example/internal")
    )
    changed_model = retrieval_reranker_generation_identity(
        _reranker_settings(rag_local_reranker_model="other/reranker")
    )
    changed_budget = retrieval_reranker_generation_identity(
        _reranker_settings(rag_rerank_candidate_k=40)
    )

    assert baseline.model_identity == "inference_gateway:example/reranker"
    assert baseline.config_sha256 == equivalent_endpoint.config_sha256
    assert baseline.config_sha256 != changed_endpoint.config_sha256
    assert baseline.config_sha256 != changed_model.config_sha256
    assert baseline.config_sha256 != changed_budget.config_sha256


def test_inference_gateway_reranker_identity_ignores_local_only_settings_and_secrets() -> None:
    baseline = retrieval_reranker_generation_identity(_reranker_settings())
    changed_unused_and_secret_settings = retrieval_reranker_generation_identity(
        _reranker_settings(
            rag_local_reranker_revision="revision-b",
            rag_local_reranker_device="cpu",
            rag_local_reranker_dtype="float32",
            rag_local_reranker_batch_size=2,
            rag_local_reranker_max_length=2048,
            rag_local_reranker_trust_remote_code=True,
            inference_gateway_api_key="rotated-gateway-secret",
            inference_gateway_token="unused-token",
        )
    )

    assert baseline == changed_unused_and_secret_settings
    assert "secret" not in baseline.model_identity
    assert "token" not in baseline.model_identity


def test_hybrid_quality_gate_requires_sixty_judged_queries_and_five_percent_uplift() -> None:
    bm25 = evaluate_retrieval_cases(_cases(first_rank=3))
    dense = evaluate_retrieval_cases(_cases(first_rank=2))
    hybrid = evaluate_retrieval_cases(_cases(first_rank=1))

    result = evaluate_hybrid_quality_gate(hybrid=hybrid, bm25=bm25, dense=dense)

    assert result.passed is True
    assert result.reasons == ()


def test_hybrid_quality_gate_rejects_sixty_all_zero_judgments() -> None:
    zero = evaluate_retrieval_cases(_cases(first_rank=11))

    result = evaluate_hybrid_quality_gate(hybrid=zero, bm25=zero, dense=zero)

    assert result.passed is False
    assert set(result.reasons) >= {
        "hybrid_recall_at_k<0.8",
        "hybrid_mrr_at_k<0.5",
        "hybrid_ndcg_at_k<0.5",
    }


def test_hybrid_quality_gate_accepts_the_normalized_metric_ceiling() -> None:
    perfect = evaluate_retrieval_cases(_cases(first_rank=1))

    result = evaluate_hybrid_quality_gate(
        hybrid=perfect,
        bm25=perfect,
        dense=perfect,
    )

    assert result.passed is True
    assert result.reasons == ()


def test_hybrid_quality_gate_fails_closed_for_small_or_unsafe_corpus() -> None:
    baseline = evaluate_retrieval_cases(_cases(first_rank=1, count=10))
    unsafe_cases = _cases(first_rank=1, count=10, latency_ms=6000)
    unsafe_cases[0] = unsafe_cases[0].model_copy(
        update={"acl_violation_count": 1, "citation_failure_count": 1}
    )
    hybrid = evaluate_retrieval_cases(unsafe_cases)

    result = evaluate_hybrid_quality_gate(
        hybrid=hybrid,
        bm25=baseline,
        dense=baseline,
    )

    assert result.passed is False
    assert set(result.reasons) >= {
        "hybrid_query_count<60",
        "bm25_query_count<60",
        "dense_query_count<60",
        "acl_violations",
        "citation_failures",
        "p95_latency_ms>5000",
    }


def test_quality_gate_rejects_acl_or_citation_failures_in_each_strategy() -> None:
    safe = evaluate_retrieval_cases(_cases(first_rank=1))
    unsafe_keyword = safe.model_copy(update={"acl_violation_count": 1, "p95_latency_ms": 6_000})
    unsafe_dense = safe.model_copy(update={"citation_failure_count": 1})

    result = evaluate_hybrid_quality_gate(
        hybrid=safe,
        bm25=unsafe_keyword,
        dense=unsafe_dense,
    )

    assert result.passed is False
    assert set(result.reasons) >= {
        "acl_violations",
        "citation_failures",
        "p95_latency_ms>5000",
    }


def test_hybrid_quality_gate_keeps_uplift_requirement_below_metric_ceiling() -> None:
    baseline = evaluate_retrieval_cases(_cases(first_rank=2))

    result = evaluate_hybrid_quality_gate(
        hybrid=baseline,
        bm25=baseline,
        dense=baseline,
    )

    assert result.passed is False
    assert "ranking_uplift_below_target" in result.reasons


def test_hybrid_quality_gate_rejects_missing_or_mismatched_baselines() -> None:
    hybrid = evaluate_retrieval_cases(_cases(first_rank=1))
    empty = RetrievalEvaluationReport(
        query_count=0,
        recall_at_k=0,
        mrr_at_k=0,
        ndcg_at_k=0,
        p95_latency_ms=0,
        acl_violation_count=0,
        citation_failure_count=0,
    )

    result = evaluate_hybrid_quality_gate(hybrid=hybrid, bm25=empty, dense=empty)

    assert result.passed is False
    assert set(result.reasons) >= {
        "bm25_query_count<60",
        "dense_query_count<60",
        "corpus_query_count_mismatch",
    }


def test_quality_artifact_is_bound_to_index_generation() -> None:
    bm25 = evaluate_retrieval_cases(_cases(first_rank=3))
    dense = evaluate_retrieval_cases(_cases(first_rank=2))
    hybrid = evaluate_retrieval_cases(_cases(first_rank=1))
    artifact = RetrievalQualityGateArtifact(
        artifact_version=2,
        corpus_id="files-rag-v1",
        corpus_sha256="a" * 64,
        index_generation="release_20260721",
        keyword_index_uuid="uuid-1",
        keyword_index_config_sha256="c" * 64,
        keyword_index_sha256="b" * 64,
        hybrid=hybrid,
        bm25=bm25,
        dense=dense,
    )

    result = validate_quality_gate_artifact(
        artifact,
        expected_index_generation="release_20260722",
    )

    assert result.passed is False
    assert "index_generation_mismatch" in result.reasons


def test_quality_artifact_is_bound_to_exact_corpus_bytes() -> None:
    bm25 = evaluate_retrieval_cases(_cases(first_rank=3))
    dense = evaluate_retrieval_cases(_cases(first_rank=2))
    hybrid = evaluate_retrieval_cases(_cases(first_rank=1))
    corpus_bytes = b'{"artifact_version":1,"corpus_id":"files-rag-v1","cases":[]}'
    artifact = RetrievalQualityGateArtifact(
        artifact_version=2,
        corpus_id="files-rag-v1",
        corpus_sha256=retrieval_quality_corpus_sha256(corpus_bytes),
        index_generation="release_20260721",
        keyword_index_uuid="uuid-1",
        keyword_index_config_sha256="c" * 64,
        keyword_index_sha256="b" * 64,
        hybrid=hybrid,
        bm25=bm25,
        dense=dense,
    )

    result = validate_quality_gate_artifact(
        artifact,
        expected_index_generation="release_20260721",
        expected_corpus_id="files-rag-v1",
        expected_corpus_sha256=retrieval_quality_corpus_sha256(corpus_bytes + b"\n"),
    )

    assert result.passed is False
    assert result.reasons == ("corpus_sha256_mismatch",)
