from __future__ import annotations

import argparse
from pathlib import Path

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.retrieval.evaluation import (
    RetrievalQualityCorpus,
    RetrievalQualityGateArtifact,
    retrieval_quality_corpus_sha256,
    validate_quality_gate_artifact,
)
from open_work_hub_api.domains.search.backend_factory import build_keyword_search_client
from open_work_hub_api.domains.search.opensearch import OpenSearchKeywordClient
from open_work_hub_api.domains.search.projections import all_search_documents
from open_work_hub_api.domains.search.service import refresh_keyword_index


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild company keyword search from registered source projections."
    )
    parser.add_argument(
        "--index-generation", help="Build an isolated generation without changing the live alias."
    )
    parser.add_argument("--activate-existing-generation")
    parser.add_argument("--confirm-writes-quiesced", action="store_true")
    parser.add_argument("--quality-report")
    parser.add_argument("--quality-corpus")
    args = parser.parse_args()
    if args.activate_existing_generation:
        if args.index_generation:
            raise SystemExit("Backfill and activation must be separate.")
        if not args.confirm_writes_quiesced or not args.quality_report or not args.quality_corpus:
            raise SystemExit(
                "Activation requires stopped writers, --quality-report and --quality-corpus."
            )
        artifact = _validate_quality_report(
            Path(args.quality_report),
            corpus_path=Path(args.quality_corpus),
            generation=args.activate_existing_generation,
        )
        _versioned_client(args.activate_existing_generation).activate_versioned_index(
            writes_quiesced=True,
            expected_document_count=_current_source_document_count(),
            expected_index_uuid=artifact.keyword_index_uuid,
            expected_config_sha256=artifact.keyword_index_config_sha256,
            expected_content_sha256=artifact.keyword_index_sha256,
        )
        print(f"Activated keyword generation {args.activate_existing_generation}.")
        return
    if args.confirm_writes_quiesced or args.quality_report or args.quality_corpus:
        raise SystemExit(
            "Activation evidence is only accepted with --activate-existing-generation."
        )
    with get_session_factory()() as db:
        client = _versioned_client(args.index_generation) if args.index_generation else None
        summary = refresh_keyword_index(db, client=client)
        print(
            f"Rebuilt keyword index: total={summary.total}; entities={dict(summary.entity_counts)}."
        )


def _versioned_client(generation: str) -> OpenSearchKeywordClient:
    client = build_keyword_search_client(get_settings())
    if not isinstance(client, OpenSearchKeywordClient):
        raise SystemExit("Versioned index operations require the OpenSearch keyword backend.")
    return client.for_versioned_rebuild(generation=generation)


def _validate_quality_report(
    path: Path,
    *,
    corpus_path: Path,
    generation: str,
) -> RetrievalQualityGateArtifact:
    try:
        artifact = RetrievalQualityGateArtifact.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        corpus_bytes = corpus_path.read_bytes()
        corpus = RetrievalQualityCorpus.model_validate_json(corpus_bytes)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Invalid retrieval quality report or corpus: {error}") from error
    if artifact.artifact_version != 2:
        raise SystemExit("Legacy v2 activation requires quality artifact version 2.")
    gate = validate_quality_gate_artifact(
        artifact,
        expected_index_generation=generation,
        expected_corpus_id=corpus.corpus_id,
        expected_corpus_sha256=retrieval_quality_corpus_sha256(corpus_bytes),
    )
    if not gate.passed:
        raise SystemExit(f"Retrieval quality gate failed: {', '.join(gate.reasons)}")
    return artifact


def _current_source_document_count() -> int:
    with get_session_factory()() as db:
        return len(all_search_documents(db))


if __name__ == "__main__":
    main()
