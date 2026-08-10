from __future__ import annotations

from types import SimpleNamespace
import json

import pytest

from open_alm_api import backfill_keyword_search
from open_alm_api.domains.retrieval.evaluation import (
    RetrievalEvaluationReport,
    RetrievalQualityGateArtifact,
    retrieval_quality_corpus_sha256,
)


class _Session:
    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def scalars(self, _query: object) -> list[SimpleNamespace]:
        return [SimpleNamespace(id="workspace-valid", key="valid")]


def _quality_corpus_bytes() -> bytes:
    return json.dumps(
        {
            "artifact_version": 1,
            "corpus_id": "files-rag-v1",
            "cases": [
                {
                    "query_id": f"query-{index}",
                    "workspace_id": "workspace-valid",
                    "user_id": "user-valid",
                    "query": f"heater query {index}",
                    "relevant_resource_ids": ["file-valid"],
                }
                for index in range(60)
            ],
        },
        separators=(",", ":"),
    ).encode()


def _passing_quality_artifact(*, corpus_sha256: str) -> RetrievalQualityGateArtifact:
    bm25 = RetrievalEvaluationReport(
        query_count=60,
        recall_at_k=0.8,
        mrr_at_k=0.7,
        ndcg_at_k=0.7,
        p95_latency_ms=1000,
        acl_violation_count=0,
        citation_failure_count=0,
    )
    dense = bm25.model_copy(update={"mrr_at_k": 0.72, "ndcg_at_k": 0.72})
    hybrid = bm25.model_copy(update={"recall_at_k": 0.9, "mrr_at_k": 0.9, "ndcg_at_k": 0.9})
    return RetrievalQualityGateArtifact(
        artifact_version=2,
        corpus_id="files-rag-v1",
        corpus_sha256=corpus_sha256,
        index_generation="release_20260721",
        keyword_index_uuid="uuid-1",
        keyword_index_config_sha256="c" * 64,
        keyword_index_sha256="b" * 64,
        hybrid=hybrid,
        bm25=bm25,
        dense=dense,
    )


def test_backfill_rejects_missing_workspace_keys_before_reindex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refreshed: list[str] = []

    monkeypatch.setattr(
        backfill_keyword_search,
        "get_session_factory",
        lambda: lambda: _Session(),
    )
    monkeypatch.setattr(
        backfill_keyword_search,
        "refresh_workspace_keyword_index",
        lambda _db, *, workspace: refreshed.append(workspace.key),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_keyword_search",
            "--workspace-key",
            "valid",
            "--workspace-key",
            "missing",
        ],
    )

    with pytest.raises(SystemExit, match="No matching active workspaces: missing"):
        backfill_keyword_search.main()

    assert refreshed == []


def test_versioned_backfill_requires_all_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_keyword_search",
            "--workspace-key",
            "valid",
            "--index-generation",
            "release_20260721",
        ],
    )

    with pytest.raises(SystemExit, match="requires --all-active"):
        backfill_keyword_search.main()


def test_versioned_backfill_and_activation_must_be_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_keyword_search",
            "--all-active",
            "--index-generation",
            "release_20260721",
            "--activate",
            "--confirm-writes-quiesced",
            "--quality-report",
            "quality.json",
            "--quality-corpus",
            "corpus.json",
        ],
    )

    with pytest.raises(SystemExit, match="Backfill and activation must be separate"):
        backfill_keyword_search.main()


def test_activate_existing_generation_requires_quality_and_validates_source_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activated: list[tuple[bool, int | None, str | None, str | None, str | None]] = []
    staged_client = SimpleNamespace(
        activate_versioned_index=lambda *,
        writes_quiesced,
        expected_document_count=None,
        expected_index_uuid=None,
        expected_config_sha256=None,
        expected_content_sha256=None: (
            activated.append(
                (
                    writes_quiesced,
                    expected_document_count,
                    expected_index_uuid,
                    expected_config_sha256,
                    expected_content_sha256,
                )
            )
        ),
    )
    monkeypatch.setattr(
        backfill_keyword_search,
        "_versioned_client",
        lambda generation: staged_client
        if generation == "release_20260720"
        else pytest.fail("unexpected generation"),
    )
    monkeypatch.setattr(backfill_keyword_search, "_current_source_document_count", lambda: 7)
    monkeypatch.setattr(
        backfill_keyword_search,
        "_validate_quality_report",
        lambda *_args, **_kwargs: SimpleNamespace(
            keyword_index_uuid="uuid-1",
            keyword_index_config_sha256="c" * 64,
            keyword_index_sha256="b" * 64,
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_keyword_search",
            "--activate-existing-generation",
            "release_20260720",
            "--confirm-writes-quiesced",
            "--quality-report",
            "quality.json",
            "--quality-corpus",
            "corpus.json",
        ],
    )

    backfill_keyword_search.main()

    assert activated == [(True, 7, "uuid-1", "c" * 64, "b" * 64)]


def test_activation_rejects_missing_writer_quiesce_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backfill_keyword_search,
        "_versioned_client",
        lambda _generation: pytest.fail("must fail before creating an index client"),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_keyword_search",
            "--activate-existing-generation",
            "release_20260721",
        ],
    )

    with pytest.raises(SystemExit, match="confirm-writes-quiesced"):
        backfill_keyword_search.main()


def test_activation_rejects_missing_quality_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backfill_keyword_search,
        "_versioned_client",
        lambda _generation: pytest.fail("must fail before creating an index client"),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_keyword_search",
            "--activate-existing-generation",
            "release_20260721",
            "--confirm-writes-quiesced",
        ],
    )

    with pytest.raises(SystemExit, match="quality-report and --quality-corpus"):
        backfill_keyword_search.main()


def test_activation_rejects_missing_quality_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_keyword_search",
            "--activate-existing-generation",
            "release_20260721",
            "--confirm-writes-quiesced",
            "--quality-report",
            "quality.json",
        ],
    )

    with pytest.raises(SystemExit, match="quality-report and --quality-corpus"):
        backfill_keyword_search.main()


def test_legacy_v1_rollback_rejects_missing_writer_quiesce_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backfill_keyword_search,
        "build_keyword_search_client",
        lambda _settings: pytest.fail("must fail before creating an index client"),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_keyword_search",
            "--rollback-legacy-v1",
        ],
    )

    with pytest.raises(SystemExit, match="confirm-writes-quiesced"):
        backfill_keyword_search.main()


def test_legacy_v1_rollback_uses_source_count(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bool, int]] = []
    client = backfill_keyword_search.OpenSearchKeywordClient(
        base_url="http://opensearch",
        index_prefix="test",
    )
    monkeypatch.setattr(
        client,
        "rollback_to_legacy_index",
        lambda *, writes_quiesced, expected_document_count: calls.append(
            (writes_quiesced, expected_document_count)
        ),
    )
    monkeypatch.setattr(
        backfill_keyword_search,
        "build_keyword_search_client",
        lambda _settings: client,
    )
    monkeypatch.setattr(backfill_keyword_search, "_current_source_document_count", lambda: 11)
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_keyword_search",
            "--rollback-legacy-v1",
            "--confirm-writes-quiesced",
        ],
    )

    backfill_keyword_search.main()

    assert calls == [(True, 11)]


def test_quality_report_rejects_actual_corpus_hash_mismatch(tmp_path) -> None:
    corpus_bytes = _quality_corpus_bytes()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_bytes(corpus_bytes)
    artifact = _passing_quality_artifact(corpus_sha256="0" * 64)
    report_path = tmp_path / "report.json"
    report_path.write_text(artifact.model_dump_json(), encoding="utf-8")

    with pytest.raises(SystemExit, match="corpus_sha256_mismatch"):
        backfill_keyword_search._validate_quality_report(
            report_path,
            corpus_path=corpus_path,
            generation="release_20260721",
        )

    valid_artifact = _passing_quality_artifact(
        corpus_sha256=retrieval_quality_corpus_sha256(corpus_bytes)
    )
    report_path.write_text(valid_artifact.model_dump_json(), encoding="utf-8")
    backfill_keyword_search._validate_quality_report(
        report_path,
        corpus_path=corpus_path,
        generation="release_20260721",
    )


def test_legacy_v2_activation_rejects_files_v3_quality_artifact(tmp_path) -> None:
    corpus_bytes = _quality_corpus_bytes()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_bytes(corpus_bytes)
    artifact = _passing_quality_artifact(
        corpus_sha256=retrieval_quality_corpus_sha256(corpus_bytes)
    ).model_copy(
        update={
            "artifact_version": 3,
            "qdrant_physical_id": "qdrant-physical",
            "qdrant_config_sha256": "d" * 64,
            "qdrant_content_sha256": "e" * 64,
            "embedding_model_identity": "example/embedding-model",
            "embedding_config_sha256": "f" * 64,
                "reranker_model_identity": "disabled",
                "reranker_config_sha256": "1" * 64,
                "source_files_event_watermark": 0,
                "source_resource_count": 1,
                "source_identity_sha256": "2" * 64,
                "source_artifact_sha256": "3" * 64,
                "source_acl_envelope_sha256": "4" * 64,
                "judgment_acl_sha256": "5" * 64,
            }
        )
    report_path = tmp_path / "report.json"
    report_path.write_text(artifact.model_dump_json(), encoding="utf-8")

    with pytest.raises(SystemExit, match="artifact version 2"):
        backfill_keyword_search._validate_quality_report(
            report_path,
            corpus_path=corpus_path,
            generation="release_20260721",
        )
