from __future__ import annotations

from dataclasses import replace
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_work_hub_api import evaluate_files_partitioned_quality as quality_cli
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.retrieval import files_quality_judgments as quality_judgments

from open_work_hub_api.domains.retrieval.contracts import (
    RetrievalHit,
    RetrievalProfile,
    RetrievalQueryResponse,
    RetrievalStrategy,
)
from open_work_hub_api.domains.retrieval.evaluation import (
    RetrievalEvaluationReport,
    RetrievalQualityGateArtifact,
)
from open_work_hub_api.domains.retrieval.files_generation_runner import (
    FilesBackendPairInspection,
    FilesPhysicalProjectionInventory,
    FilesSourceProjectionSnapshot,
)
from open_work_hub_api.domains.retrieval.files_quality_evaluator import (
    FilesQualityEvaluationError,
    evaluate_files_partitioned_quality,
)


@pytest.fixture(autouse=True)
def _allow_admitted_evaluation_user(monkeypatch):
    def admitted(_db, *, user_id, app_id):
        assert user_id == "user-sensitive" and app_id == "files"
        return True

    monkeypatch.setattr(quality_judgments, "can_use_app", admitted)


class _Session:
    def __init__(self, active_file_ids: set[str] | None = None) -> None:
        self.user = SimpleNamespace(
            id="user-sensitive",
            status="active",
            login_blocked=False,
        )
        self.active_file_ids = active_file_ids or {
            "file-sensitive",
            "file-forbidden-sensitive",
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get(self, model, identity):
        if model is User and identity == self.user.id:
            return self.user
        return None

    def scalars(self, _query):
        return sorted(self.active_file_ids)


class _JudgmentPolicy:
    def __init__(self, allowed_ids: set[str] | None = None) -> None:
        self.allowed_ids = {"file-sensitive"} if allowed_ids is None else allowed_ids
        self.rag_modes: list[bool] = []

    def authorize_many_resources(self, resources, *, rag: bool = False):
        self.rag_modes.append(rag)
        return {identity for identity in resources if identity[1] in self.allowed_ids}


class _Backends:
    def __init__(self, inspection: FilesBackendPairInspection) -> None:
        self.inspection = inspection
        self.inspected_specs = []

    def inspect_pair(self, spec):
        self.inspected_specs.append(spec)
        return self.inspection


def _corpus_bytes() -> bytes:
    return json.dumps(
        {
            "artifact_version": 1,
            "corpus_id": "files-judged-v1",
            "cases": [
                {
                    "query_id": f"query-{index}",
                    "user_id": "user-sensitive",
                    "query": f"sensitive query body {index}",
                    "relevant_resource_ids": ["file-sensitive"],
                    "forbidden_resource_ids": ["file-forbidden-sensitive"],
                    "source_kinds": ["files"],
                }
                for index in range(60)
            ],
        },
        ensure_ascii=False,
    ).encode()


def _settings():
    return SimpleNamespace(
        opensearch_index_prefix="open-work-hub-search",
        rag_qdrant_collection_prefix="open-work-hub-rag",
        rag_embedding_provider="inference_gateway",
        rag_local_embedding_model="example/embedding-model",
        rag_local_embedding_revision="revision-a",
        rag_local_embedding_device="cuda",
        rag_local_embedding_dtype="bfloat16",
        rag_local_embedding_batch_size=16,
        rag_local_embedding_max_seq_length=1024,
        rag_local_embedding_normalize=True,
        rag_local_embedding_query_prompt_name="query",
        rag_local_embedding_query_prefix="",
        rag_local_embedding_trust_remote_code=False,
        rag_rerank_provider="inference_gateway",
        inference_gateway_base_url="http://127.0.0.1:18080/v1",
        rag_local_reranker_model="example/reranker",
        rag_local_reranker_revision="reranker-revision-a",
        rag_local_reranker_device="cuda",
        rag_local_reranker_dtype="bfloat16",
        rag_local_reranker_batch_size=16,
        rag_local_reranker_max_length=512,
        rag_local_reranker_trust_remote_code=False,
        rag_rerank_candidate_k=80,
    )


def _source_snapshot() -> FilesSourceProjectionSnapshot:
    return FilesSourceProjectionSnapshot(
        event_watermark=7,
        files_event_watermark=7,
        resource_count=1,
        identity_sha256="1" * 64,
        artifact_sha256="8" * 64,
        acl_envelope_sha256="9" * 64,
        unsupported_count=0,
        unavailable_count=0,
    )


def test_evaluator_queries_only_the_exact_partitioned_physical_pair() -> None:
    opensearch = FilesPhysicalProjectionInventory(
        resource_count=1,
        record_count=1,
        identity_sha256="1" * 64,
        content_sha256="2" * 64,
        config_sha256="3" * 64,
        physical_id="opensearch-uuid",
    )
    qdrant = FilesPhysicalProjectionInventory(
        resource_count=1,
        record_count=2,
        identity_sha256="1" * 64,
        content_sha256="4" * 64,
        config_sha256="5" * 64,
        physical_id="open-work-hub-rag-example-embedding-model-v1-release_20260723",
    )
    backends = _Backends(FilesBackendPairInspection(opensearch=opensearch, qdrant=qdrant))
    keyword_bindings: list[str] = []
    vector_bindings: list[str] = []
    calls: list[dict[str, object]] = []
    keyword_client = object()
    rag_query_service = object()
    judgment_policy = _JudgmentPolicy()

    def query_retrieval(_db, **kwargs):
        calls.append(kwargs)
        request = kwargs["request"]
        return RetrievalQueryResponse(
            query=request.query,
            strategy=request.strategy,
            hits=[
                RetrievalHit(
                    source="keyword",
                    source_kind="files",
                    resource_type="file_manager_file",
                    resource_id="file-sensitive",
                    citation="/files/file-sensitive",
                )
            ],
            profile=RetrievalProfile(strategy=request.strategy),
            latency_ms=10,
        )

    artifact = evaluate_files_partitioned_quality(
        corpus_bytes=_corpus_bytes(),
        generation_key="release_20260723",
        settings=_settings(),
        session_factory=_Session,
        backends=backends,
        keyword_client_factory=lambda _settings, physical_name: (
            keyword_bindings.append(physical_name) or keyword_client
        ),
        rag_query_service_factory=lambda _settings, physical_name: (
            vector_bindings.append(physical_name) or rag_query_service
        ),
        source_acl_policy_factory=lambda *_args: judgment_policy,
        source_snapshot_loader=lambda _db: _source_snapshot(),
        retrieval_query=query_retrieval,
    )

    assert keyword_bindings == ["open-work-hub-search_keyword_search_documents_v3_release_20260723"]
    assert vector_bindings == ["open-work-hub-rag-example-embedding-model-v1-release_20260723"]
    assert len(backends.inspected_specs) == 2
    assert backends.inspected_specs[0] == backends.inspected_specs[1]
    assert len(calls) == 180
    assert {call["request"].strategy for call in calls} == {
        RetrievalStrategy.KEYWORD,
        RetrievalStrategy.SEMANTIC,
        RetrievalStrategy.HYBRID,
    }
    assert all(call["partitioned_generation"] is True for call in calls)
    assert all(call["keyword_search_client"] is keyword_client for call in calls)
    assert all(call["rag_query_service"] is rag_query_service for call in calls)
    assert all(
        call["rag_collection"] == "open-work-hub-rag-example-embedding-model-v1-release_20260723"
        for call in calls
    )
    assert all(call["rag_allowed_unlisted_source_kinds"] == frozenset({"files"}) for call in calls)
    assert artifact.artifact_version == 3
    assert artifact.corpus_sha256
    assert artifact.keyword_index_uuid == "opensearch-uuid"
    assert artifact.keyword_index_config_sha256 == "3" * 64
    assert artifact.keyword_index_sha256 == "2" * 64
    assert artifact.qdrant_physical_id == qdrant.physical_id
    assert artifact.qdrant_config_sha256 == "5" * 64
    assert artifact.qdrant_content_sha256 == "4" * 64
    assert artifact.embedding_model_identity == "example/embedding-model"
    assert artifact.reranker_model_identity == "inference_gateway:example/reranker"
    assert artifact.source_files_event_watermark == 7
    assert artifact.source_acl_envelope_sha256 == "9" * 64
    assert artifact.judgment_acl_sha256
    assert judgment_policy.rag_modes == [False, True, False, True]


def test_evaluator_fails_closed_if_the_physical_generation_changes_mid_run() -> None:
    stable = FilesPhysicalProjectionInventory(
        resource_count=1,
        record_count=1,
        identity_sha256="1" * 64,
        content_sha256="2" * 64,
        config_sha256="3" * 64,
        physical_id="opensearch-uuid",
    )
    vector = FilesPhysicalProjectionInventory(
        resource_count=1,
        record_count=1,
        identity_sha256="1" * 64,
        content_sha256="4" * 64,
        config_sha256="5" * 64,
        physical_id="open-work-hub-rag-example-embedding-model-v1-release_20260723",
    )

    class ChangingBackends:
        calls = 0

        def inspect_pair(self, _spec):
            self.calls += 1
            if self.calls == 1:
                return FilesBackendPairInspection(opensearch=stable, qdrant=vector)
            return FilesBackendPairInspection(
                opensearch=replace(stable, content_sha256="9" * 64),
                qdrant=vector,
            )

    def query_retrieval(_db, **kwargs):
        request = kwargs["request"]
        return RetrievalQueryResponse(
            query=request.query,
            strategy=request.strategy,
            hits=[
                RetrievalHit(
                    source="keyword",
                    resource_type="file_manager_file",
                    resource_id="file-sensitive",
                    citation="/files/file-sensitive",
                )
            ],
            profile=RetrievalProfile(strategy=request.strategy),
            latency_ms=10,
        )

    with pytest.raises(
        FilesQualityEvaluationError,
        match="physical_generation_changed_during_evaluation",
    ):
        evaluate_files_partitioned_quality(
            corpus_bytes=_corpus_bytes(),
            generation_key="release_20260723",
            settings=_settings(),
            session_factory=_Session,
            backends=ChangingBackends(),
            keyword_client_factory=lambda *_args: object(),
            rag_query_service_factory=lambda *_args: object(),
            source_acl_policy_factory=lambda *_args: _JudgmentPolicy(),
            source_snapshot_loader=lambda _db: _source_snapshot(),
            retrieval_query=query_retrieval,
        )


def test_evaluator_fails_closed_if_principal_acl_universe_changes_mid_run() -> None:
    opensearch = FilesPhysicalProjectionInventory(
        resource_count=1,
        record_count=1,
        identity_sha256="1" * 64,
        content_sha256="2" * 64,
        config_sha256="3" * 64,
        physical_id="opensearch-uuid",
    )
    qdrant = FilesPhysicalProjectionInventory(
        resource_count=1,
        record_count=1,
        identity_sha256="1" * 64,
        content_sha256="4" * 64,
        config_sha256="5" * 64,
        physical_id="open-work-hub-rag-example-embedding-model-v1-release_20260723",
    )
    policies = iter(
        (
            _JudgmentPolicy({"file-sensitive"}),
            _JudgmentPolicy({"file-sensitive", "file-newly-visible"}),
        )
    )

    def query_retrieval(_db, **kwargs):
        request = kwargs["request"]
        return RetrievalQueryResponse(
            query=request.query,
            strategy=request.strategy,
            hits=[
                RetrievalHit(
                    source="keyword",
                    resource_type="file_manager_file",
                    resource_id="file-sensitive",
                    citation="/files/file-sensitive",
                )
            ],
            profile=RetrievalProfile(strategy=request.strategy),
            latency_ms=10,
        )

    with pytest.raises(
        FilesQualityEvaluationError,
        match="quality_acl_changed_during_evaluation",
    ):
        evaluate_files_partitioned_quality(
            corpus_bytes=_corpus_bytes(),
            generation_key="release_20260723",
            settings=_settings(),
            session_factory=lambda: _Session(
                {
                    "file-sensitive",
                    "file-forbidden-sensitive",
                    "file-newly-visible",
                }
            ),
            backends=_Backends(FilesBackendPairInspection(opensearch=opensearch, qdrant=qdrant)),
            keyword_client_factory=lambda *_args: object(),
            rag_query_service_factory=lambda *_args: object(),
            source_acl_policy_factory=lambda *_args: next(policies),
            source_snapshot_loader=lambda _db: _source_snapshot(),
            retrieval_query=query_retrieval,
        )


def test_evaluator_rejects_non_files_judgments_before_backend_access() -> None:
    payload = json.loads(_corpus_bytes())
    payload["cases"][0]["source_kinds"] = ["files", "docs"]

    class UntouchedBackends:
        def inspect_pair(self, _spec):
            raise AssertionError("backend must remain untouched")

    with pytest.raises(FilesQualityEvaluationError, match="quality_corpus_source_invalid"):
        evaluate_files_partitioned_quality(
            corpus_bytes=json.dumps(payload).encode(),
            generation_key="release_20260723",
            settings=_settings(),
            session_factory=_Session,
            backends=UntouchedBackends(),
        )


def test_evaluator_rejects_nonadmitted_principal_before_backend_access(monkeypatch) -> None:
    class UntouchedBackends:
        def inspect_pair(self, _spec):
            raise AssertionError("backend must remain untouched")

    policy = _JudgmentPolicy()
    monkeypatch.setattr(quality_judgments, "can_use_app", lambda *_args, **_kwargs: False)
    with pytest.raises(FilesQualityEvaluationError, match="evaluation_context_unavailable"):
        evaluate_files_partitioned_quality(
            corpus_bytes=_corpus_bytes(),
            generation_key="release_20260723",
            settings=_settings(),
            session_factory=_Session,
            backends=UntouchedBackends(),
            source_acl_policy_factory=lambda *_args: policy,
        )


@pytest.mark.parametrize(
    ("active_ids", "allowed_ids", "expected_error"),
    [
        (
            {"file-sensitive"},
            {"file-sensitive"},
            "quality_judgment_resource_missing",
        ),
        (
            {"file-sensitive", "file-forbidden-sensitive"},
            set(),
            "quality_judgment_relevant_not_authorized",
        ),
        (
            {"file-sensitive", "file-forbidden-sensitive"},
            {"file-sensitive", "file-forbidden-sensitive"},
            "quality_judgment_forbidden_authorized",
        ),
    ],
)
def test_evaluator_rejects_invalid_database_backed_acl_judgments(
    active_ids: set[str],
    allowed_ids: set[str],
    expected_error: str,
) -> None:
    class UntouchedBackends:
        def inspect_pair(self, _spec):
            raise AssertionError("backend must remain untouched")

    with pytest.raises(FilesQualityEvaluationError, match=expected_error):
        evaluate_files_partitioned_quality(
            corpus_bytes=_corpus_bytes(),
            generation_key="release_20260723",
            settings=_settings(),
            session_factory=lambda: _Session(active_ids),
            backends=UntouchedBackends(),
            source_acl_policy_factory=lambda *_args: _JudgmentPolicy(allowed_ids),
        )


def _passing_artifact() -> RetrievalQualityGateArtifact:
    report = RetrievalEvaluationReport(
        query_count=60,
        recall_at_k=1.0,
        mrr_at_k=1.0,
        ndcg_at_k=1.0,
        p95_latency_ms=10,
        acl_violation_count=0,
        citation_failure_count=0,
    )
    return RetrievalQualityGateArtifact(
        artifact_version=3,
        corpus_id="sensitive-corpus-id",
        corpus_sha256="1" * 64,
        index_generation="release_20260723",
        keyword_index_uuid="opensearch-uuid",
        keyword_index_config_sha256="2" * 64,
        keyword_index_sha256="3" * 64,
        qdrant_physical_id="qdrant-physical",
        qdrant_config_sha256="4" * 64,
        qdrant_content_sha256="5" * 64,
        embedding_model_identity="example/embedding-model",
        embedding_config_sha256="6" * 64,
        reranker_model_identity="inference_gateway:example/reranker",
        reranker_config_sha256="7" * 64,
        source_files_event_watermark=0,
        source_resource_count=1,
        source_identity_sha256="8" * 64,
        source_artifact_sha256="9" * 64,
        source_acl_envelope_sha256="a" * 64,
        judgment_acl_sha256="b" * 64,
        bm25=report,
        dense=report,
        hybrid=report,
    )


def test_cli_writes_artifact_atomically_without_overwriting_or_echoing_identifiers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    corpus_path = tmp_path / "corpus.json"
    output_path = tmp_path / "quality.json"
    corpus_path.write_bytes(_corpus_bytes())
    closed: list[bool] = []

    class Backends:
        def __init__(self, _settings) -> None:
            pass

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(quality_cli, "get_settings", _settings)
    monkeypatch.setattr(quality_cli, "FilesPhysicalGenerationBackends", Backends)
    monkeypatch.setattr(
        quality_cli,
        "evaluate_files_partitioned_quality",
        lambda **_kwargs: _passing_artifact(),
    )

    result = quality_cli.main(
        [
            "--corpus",
            str(corpus_path),
            "--generation",
            "release_20260723",
            "--output",
            str(output_path),
        ]
    )

    output = capsys.readouterr()
    assert result == 0
    assert closed == [True]
    assert output_path.exists()
    assert os.stat(output_path).st_mode & 0o777 == 0o600
    assert json.loads(output_path.read_text())["artifact_version"] == 3
    assert "sensitive query" not in output.out + output.err
    assert "user-sensitive" not in output.out + output.err
    assert "file-sensitive" not in output.out + output.err
    original = output_path.read_bytes()

    second = quality_cli.main(
        [
            "--corpus",
            str(corpus_path),
            "--generation",
            "release_20260723",
            "--output",
            str(output_path),
        ]
    )

    second_output = capsys.readouterr()
    assert second == 1
    assert output_path.read_bytes() == original
    assert second_output.err.strip() == "status=failed reason=artifact_output_exists"


def test_cli_sanitizes_unexpected_evaluation_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_bytes(_corpus_bytes())

    class Backends:
        def __init__(self, _settings) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(quality_cli, "get_settings", _settings)
    monkeypatch.setattr(quality_cli, "FilesPhysicalGenerationBackends", Backends)

    def fail(**_kwargs):
        logging.getLogger("open_work_hub_api.domains.retrieval.application").warning(
            "sensitive query user-sensitive file-sensitive"
        )
        raise RuntimeError("sensitive query user-sensitive file-sensitive")

    monkeypatch.setattr(quality_cli, "evaluate_files_partitioned_quality", fail)

    result = quality_cli.main(
        [
            "--corpus",
            str(corpus_path),
            "--generation",
            "release_20260723",
            "--output",
            str(tmp_path / "quality.json"),
        ]
    )

    output = capsys.readouterr()
    assert result == 1
    assert output.err.strip() == "status=failed reason=evaluation_failed"
    assert "sensitive" not in output.out + output.err
    assert "sensitive" not in caplog.text
