from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_work_hub_api import evaluate_retrieval_quality
from open_work_hub_api.evaluate_retrieval_quality import _evaluation_case, _retrieval_request
from open_work_hub_api.domains.retrieval.contracts import (
    RetrievalHit,
    RetrievalProfile,
    RetrievalQueryResponse,
    RetrievalStrategy,
)
from open_work_hub_api.domains.retrieval.evaluation import RetrievalQualityCorpusCase
from open_work_hub_api.domains.retrieval.evaluation import RetrievalEvaluationCase


def _corpus_case() -> RetrievalQualityCorpusCase:
    return RetrievalQualityCorpusCase(
        query_id="heater-pressure",
        workspace_id="workspace-1",
        user_id="user-1",
        query="히터 비상 정지 압력",
        relevant_resource_ids=["file-1"],
        forbidden_resource_ids=["file-private"],
        source_kinds=["files"],
    )


def test_evaluation_requests_keep_staged_files_filters_per_strategy() -> None:
    case = _corpus_case()

    keyword = _retrieval_request(case=case, strategy=RetrievalStrategy.KEYWORD)
    dense = _retrieval_request(case=case, strategy=RetrievalStrategy.SEMANTIC)
    hybrid = _retrieval_request(case=case, strategy=RetrievalStrategy.HYBRID)

    assert keyword.sources == ["keyword"]
    assert dense.sources == ["generic_rag"]
    assert hybrid.sources == ["keyword", "generic_rag"]
    assert hybrid.source_kinds == ["files"]
    assert hybrid.filters == {"keyword": {"entity_types": ["file"]}}


def test_evaluation_case_counts_acl_and_citation_failures() -> None:
    case = _corpus_case()
    response = RetrievalQueryResponse(
        query=case.query,
        strategy=RetrievalStrategy.HYBRID,
        hits=[
            RetrievalHit(
                source="generic_rag",
                resource_type="file_manager_file",
                resource_id="file-1",
                citation="file-1:slide:7",
            ),
            RetrievalHit(
                source="keyword",
                resource_type="file_manager_file",
                resource_id="file-private",
                citation=None,
            ),
        ],
        profile=RetrievalProfile(strategy=RetrievalStrategy.HYBRID),
        latency_ms=1250,
    )

    result = _evaluation_case(case=case, response=response)

    assert result.ranked_resource_ids == ["file-1", "file-private"]
    assert result.acl_violation_count == 1
    assert result.citation_failure_count == 1
    assert result.latency_ms == 1250


def test_main_uses_and_cleans_generation_scoped_qdrant_collection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    corpus_path = tmp_path / "corpus.json"
    output_path = tmp_path / "quality.json"
    corpus_path.write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "corpus_id": "files-rag-v1",
                "cases": [
                    {
                        "query_id": f"query-{index}",
                        "workspace_id": "workspace-1",
                        "user_id": "user-1",
                        "query": f"heater query {index}",
                        "relevant_resource_ids": ["file-1"],
                    }
                    for index in range(60)
                ],
            }
        ),
        encoding="utf-8",
    )
    deleted: list[str] = []
    prepared: list[str] = []
    queried: list[str] = []
    rag_service = SimpleNamespace(
        delete_collection=lambda *, collection: deleted.append(collection),
    )
    staging_client = SimpleNamespace(
        quality_identity=lambda: ("uuid-1", "c" * 64),
        content_sha256=lambda: "a" * 64,
    )

    def prepare_staged_files(**kwargs) -> None:
        prepared.append(kwargs["rag_collection"])

    def evaluate_strategy(*, corpus, strategy, **kwargs):
        queried.append(kwargs["rag_collection"])
        relevant_rank = {
            RetrievalStrategy.KEYWORD: 3,
            RetrievalStrategy.SEMANTIC: 2,
            RetrievalStrategy.HYBRID: 1,
        }[strategy]
        ranked = ["irrelevant-1", "irrelevant-2"]
        ranked.insert(relevant_rank - 1, "file-1")
        return [
            RetrievalEvaluationCase(
                query_id=case.query_id,
                relevant_resource_ids=["file-1"],
                ranked_resource_ids=ranked,
                latency_ms=10,
            )
            for case in corpus.cases
        ]

    monkeypatch.setattr(
        evaluate_retrieval_quality, "_staging_client", lambda _generation: staging_client
    )
    monkeypatch.setattr(evaluate_retrieval_quality, "get_rag_service", lambda: rag_service)
    monkeypatch.setattr(
        evaluate_retrieval_quality,
        "_evaluation_collection_name",
        lambda generation: f"rag-evaluation-{generation}",
    )
    monkeypatch.setattr(
        evaluate_retrieval_quality,
        "_evaluation_query_service",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(evaluate_retrieval_quality, "_prepare_staged_files", prepare_staged_files)
    monkeypatch.setattr(evaluate_retrieval_quality, "_evaluate_strategy", evaluate_strategy)
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_retrieval_quality",
            "--corpus",
            str(corpus_path),
            "--index-generation",
            "release_20260721",
            "--output",
            str(output_path),
            "--prepare-staged-files",
        ],
    )

    evaluate_retrieval_quality.main()

    collection = "rag-evaluation-release_20260721"
    assert prepared == [collection]
    assert queried == [collection, collection, collection]
    assert deleted == [collection, collection]
    assert json.loads(output_path.read_text(encoding="utf-8"))["keyword_index_sha256"] == ("a" * 64)


def test_main_rejects_evaluation_without_fresh_staged_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_retrieval_quality",
            "--corpus",
            "corpus.json",
            "--index-generation",
            "release_20260721",
            "--output",
            "quality.json",
        ],
    )

    with pytest.raises(SystemExit, match="prepare-staged-files is required"):
        evaluate_retrieval_quality.main()
