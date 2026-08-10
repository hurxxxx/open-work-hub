from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.models import Workspace
from open_work_hub_api.domains.retrieval.evaluation import (
    RetrievalQualityCorpus,
    RetrievalQualityGateArtifact,
    retrieval_quality_corpus_sha256,
    validate_quality_gate_artifact,
)
from open_work_hub_api.domains.search.backend_factory import build_keyword_search_client
from open_work_hub_api.domains.search.opensearch import OpenSearchKeywordClient
from open_work_hub_api.domains.search.service import refresh_workspace_keyword_index
from open_work_hub_api.domains.search.projections import all_workspace_search_documents


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild OpenSearch keyword indexes for selected workspaces."
    )
    parser.add_argument(
        "--workspace-key",
        action="append",
        default=[],
        help="Workspace key to rebuild. Can be passed more than once.",
    )
    parser.add_argument(
        "--all-active",
        action="store_true",
        help="Rebuild all active workspaces.",
    )
    parser.add_argument(
        "--index-generation",
        help=(
            "Write a complete all-active backfill to an isolated v2 generation. "
            "Never changes the live alias."
        ),
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Deprecated and rejected; use --activate-existing-generation separately.",
    )
    parser.add_argument(
        "--activate-existing-generation",
        help="Promote an existing v2 generation after the same quality and source-count gates.",
    )
    parser.add_argument(
        "--rollback-legacy-v1",
        action="store_true",
        help="Atomically restore the canonical legacy v1 index after a source-count check.",
    )
    parser.add_argument(
        "--confirm-writes-quiesced",
        action="store_true",
        help=(
            "Required for activation. Confirms API and every search-index worker are stopped; "
            "this command does not stop them."
        ),
    )
    parser.add_argument(
        "--quality-report",
        help=("Versioned JSON quality-gate artifact for existing-generation activation."),
    )
    parser.add_argument(
        "--quality-corpus",
        help="Exact versioned JSON corpus whose raw SHA-256 is recorded by --quality-report.",
    )
    args = parser.parse_args()
    if args.activate:
        raise SystemExit(
            "Backfill and activation must be separate. Backfill the generation, evaluate it, "
            "then use --activate-existing-generation."
        )

    workspace_keys = [key.strip() for key in args.workspace_key if key.strip()]
    if args.activate_existing_generation:
        if (
            args.all_active
            or workspace_keys
            or args.index_generation
            or args.activate
            or args.rollback_legacy_v1
        ):
            raise SystemExit(
                "Use --activate-existing-generation without a backfill or rollback option."
            )
        if not args.confirm_writes_quiesced:
            raise SystemExit(
                "Activation requires --confirm-writes-quiesced after stopping all search writers."
            )
        if not args.quality_report or not args.quality_corpus:
            raise SystemExit(
                "Existing generation activation requires --quality-report and --quality-corpus."
            )
        artifact = _validate_quality_report(
            Path(args.quality_report),
            corpus_path=Path(args.quality_corpus),
            generation=args.activate_existing_generation,
        )
        expected_document_count = _current_source_document_count()
        _versioned_client(args.activate_existing_generation).activate_versioned_index(
            writes_quiesced=True,
            expected_document_count=expected_document_count,
            expected_index_uuid=artifact.keyword_index_uuid,
            expected_config_sha256=artifact.keyword_index_config_sha256,
            expected_content_sha256=artifact.keyword_index_sha256,
        )
        print(f"Activated keyword search index generation {args.activate_existing_generation}.")
        return
    if args.rollback_legacy_v1:
        if (
            args.all_active
            or workspace_keys
            or args.index_generation
            or args.activate
            or args.activate_existing_generation
            or args.quality_report
            or args.quality_corpus
        ):
            raise SystemExit("Use --rollback-legacy-v1 without backfill or quality options.")
        if not args.confirm_writes_quiesced:
            raise SystemExit(
                "Rollback requires --confirm-writes-quiesced after stopping all search writers."
            )
        expected_document_count = _current_source_document_count()
        client = build_keyword_search_client(get_settings())
        if not isinstance(client, OpenSearchKeywordClient):
            raise SystemExit("Legacy rollback requires the OpenSearch keyword backend.")
        client.rollback_to_legacy_index(
            writes_quiesced=True,
            expected_document_count=expected_document_count,
        )
        print("Rolled back keyword search alias to the canonical legacy v1 index.")
        return
    if args.all_active and workspace_keys:
        raise SystemExit("Use either --all-active or --workspace-key, not both.")
    if not args.all_active and not workspace_keys:
        raise SystemExit("Pass at least one --workspace-key or use --all-active.")
    if args.index_generation and not args.all_active:
        raise SystemExit("--index-generation requires --all-active for a complete index.")
    if args.confirm_writes_quiesced:
        raise SystemExit("--confirm-writes-quiesced is only valid with an activation option.")
    if args.quality_report or args.quality_corpus:
        raise SystemExit("--quality-report and --quality-corpus are only valid with activation.")

    versioned_client = _versioned_client(args.index_generation) if args.index_generation else None

    with get_session_factory()() as db:
        query = select(Workspace).where(Workspace.active.is_(True)).order_by(Workspace.key.asc())
        if not args.all_active:
            query = query.where(Workspace.key.in_(workspace_keys))
        workspaces = list(db.scalars(query))
        if not workspaces:
            raise SystemExit("No matching active workspaces found.")
        if not args.all_active:
            missing = sorted(set(workspace_keys) - {workspace.key for workspace in workspaces})
            if missing:
                raise SystemExit(f"No matching active workspaces: {', '.join(missing)}")

        for workspace in workspaces:
            if versioned_client is None:
                summary = refresh_workspace_keyword_index(db, workspace=workspace)
            else:
                summary = refresh_workspace_keyword_index(
                    db,
                    workspace=workspace,
                    client=versioned_client,
                )
            entity_counts = (
                ", ".join(
                    f"{entity_type}={count}"
                    for entity_type, count in summary.entity_counts.items()
                    if entity_type
                )
                or "none"
            )
            print(
                f"Rebuilt keyword search index for workspace {workspace.key} "
                f"({workspace.id}): total={summary.total}; entities={entity_counts}."
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
    count = 0
    with get_session_factory()() as db:
        workspaces = list(
            db.scalars(
                select(Workspace).where(Workspace.active.is_(True)).order_by(Workspace.key.asc())
            )
        )
        if not workspaces:
            raise SystemExit("No active workspaces found for source-count validation.")
        for workspace in workspaces:
            count += len(all_workspace_search_documents(db, workspace=workspace))
    return count


if __name__ == "__main__":
    main()
