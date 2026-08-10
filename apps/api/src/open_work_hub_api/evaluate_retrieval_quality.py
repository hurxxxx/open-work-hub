from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.files.rag_projection import load_file_rag_projection
from open_work_hub_api.domains.files.search_projection import (
    load_workspace_file_search_documents,
)
from open_work_hub_api.domains.retrieval.application import query_retrieval
from open_work_hub_api.domains.retrieval.contracts import (
    RetrievalAnswerMode,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalStrategy,
)
from open_work_hub_api.domains.retrieval.evaluation import (
    RetrievalEvaluationCase,
    RetrievalQualityCorpus,
    RetrievalQualityCorpusCase,
    RetrievalQualityGateArtifact,
    evaluate_hybrid_quality_gate,
    evaluate_retrieval_cases,
    retrieval_quality_corpus_sha256,
)
from open_work_hub_api.domains.rag.contracts import RagVectorSearchMode
from open_work_hub_api.domains.rag.query_service import RagQueryService
from open_work_hub_api.domains.rag.runtime import (
    get_provider_bundle,
    get_rag_service,
    resolve_default_collection_name,
)
from open_work_hub_api.domains.rag.service import RagService
from open_work_hub_api.domains.search.backend_factory import build_keyword_search_client
from open_work_hub_api.domains.search.index_gateway import search_index_document_id
from open_work_hub_api.domains.search.opensearch import OpenSearchKeywordClient
from open_work_hub_api.domains.search.projections import all_workspace_search_documents


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate BM25, dense, and canonical hybrid retrieval against a versioned corpus."
        )
    )
    parser.add_argument("--corpus", required=True, help="Versioned judged corpus JSON path.")
    parser.add_argument(
        "--index-generation",
        required=True,
        help="Isolated OpenSearch v2 generation used by BM25 and hybrid queries.",
    )
    parser.add_argument("--output", required=True, help="Quality artifact JSON output path.")
    parser.add_argument(
        "--prepare-staged-files",
        action="store_true",
        help=(
            "Extract and index hidden Files projections into the named OpenSearch generation "
            "and Qdrant before evaluation. This never moves the live alias."
        ),
    )
    parser.add_argument(
        "--retain-staged-files",
        action="store_true",
        help="Retain the isolated evaluation Qdrant collection for diagnostics.",
    )
    args = parser.parse_args()
    if not args.prepare_staged_files:
        raise SystemExit(
            "--prepare-staged-files is required so evaluation cannot reuse stale vectors."
        )
    corpus_path = Path(args.corpus)
    try:
        corpus_bytes = corpus_path.read_bytes()
        corpus = RetrievalQualityCorpus.model_validate_json(corpus_bytes)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Invalid retrieval evaluation corpus: {error}") from error

    staging_client = _staging_client(args.index_generation)
    rag_service = get_rag_service()
    evaluation_collection = _evaluation_collection_name(args.index_generation)
    query_service = _evaluation_query_service()
    if args.prepare_staged_files:
        rag_service.delete_collection(collection=evaluation_collection)
    try:
        if args.prepare_staged_files:
            _prepare_staged_files(
                corpus=corpus,
                staging_client=staging_client,
                rag_service=rag_service,
                rag_collection=evaluation_collection,
            )

        reports = {
            strategy: evaluate_retrieval_cases(
                _evaluate_strategy(
                    corpus=corpus,
                    strategy=strategy,
                    staging_client=staging_client,
                    rag_query_service=query_service,
                    rag_collection=evaluation_collection,
                )
            )
            for strategy in (
                RetrievalStrategy.KEYWORD,
                RetrievalStrategy.SEMANTIC,
                RetrievalStrategy.HYBRID,
            )
        }
        keyword_index_uuid, keyword_index_config_sha256 = staging_client.quality_identity()
        artifact = RetrievalQualityGateArtifact(
            artifact_version=2,
            corpus_id=corpus.corpus_id,
            corpus_sha256=retrieval_quality_corpus_sha256(corpus_bytes),
            index_generation=args.index_generation,
            keyword_index_uuid=keyword_index_uuid,
            keyword_index_config_sha256=keyword_index_config_sha256,
            keyword_index_sha256=staging_client.content_sha256(),
            bm25=reports[RetrievalStrategy.KEYWORD],
            dense=reports[RetrievalStrategy.SEMANTIC],
            hybrid=reports[RetrievalStrategy.HYBRID],
        )
        output_path = Path(args.output)
        output_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")

        gate = evaluate_hybrid_quality_gate(
            hybrid=artifact.hybrid,
            bm25=artifact.bm25,
            dense=artifact.dense,
        )
        if not gate.passed:
            raise SystemExit(
                f"Retrieval quality gate failed: {', '.join(gate.reasons)}; artifact={output_path}"
            )
        print(f"Retrieval quality gate passed: artifact={output_path}")
    finally:
        if args.prepare_staged_files and not args.retain_staged_files:
            rag_service.delete_collection(collection=evaluation_collection)


def _staging_client(generation: str) -> OpenSearchKeywordClient:
    client = build_keyword_search_client(get_settings())
    if not isinstance(client, OpenSearchKeywordClient):
        raise SystemExit("Retrieval quality evaluation requires the OpenSearch keyword backend.")
    return client.for_versioned_rebuild(generation=generation)


def _prepare_staged_files(
    *,
    corpus: RetrievalQualityCorpus,
    staging_client: OpenSearchKeywordClient,
    rag_service: RagService,
    rag_collection: str,
) -> None:
    workspace_ids = sorted({case.workspace_id for case in corpus.cases})
    with get_session_factory()() as db:
        workspaces = list(
            db.scalars(
                select(Workspace).where(Workspace.active.is_(True)).order_by(Workspace.id.asc())
            )
        )
        missing = sorted(set(workspace_ids) - {workspace.id for workspace in workspaces})
        if missing:
            raise SystemExit(f"Evaluation workspaces not found: {', '.join(missing)}")

        for workspace in workspaces:
            file_ids = list(
                db.scalars(
                    select(FileManagerFile.id)
                    .where(
                        FileManagerFile.workspace_id == workspace.id,
                        FileManagerFile.deleted_at.is_(None),
                    )
                    .order_by(FileManagerFile.created_at.asc(), FileManagerFile.id.asc())
                )
            )
            for file_id in file_ids:
                projection = load_file_rag_projection(
                    db,
                    file_id=file_id,
                    rag_service=rag_service,
                )
                if projection is not None:
                    rag_service.sync_projection(projection, collection=rag_collection)
                db.commit()

            active_documents = all_workspace_search_documents(db, workspace=workspace)
            staged_file_documents = load_workspace_file_search_documents(
                db,
                workspace=workspace,
            )
            documents_by_id = {
                search_index_document_id(document): document
                for document in (*active_documents, *staged_file_documents)
            }
            staging_client.rebuild_workspace(
                workspace_id=workspace.id,
                documents=list(documents_by_id.values()),
            )


def _evaluate_strategy(
    *,
    corpus: RetrievalQualityCorpus,
    strategy: RetrievalStrategy,
    staging_client: OpenSearchKeywordClient,
    rag_query_service: RagQueryService,
    rag_collection: str,
) -> list[RetrievalEvaluationCase]:
    cases: list[RetrievalEvaluationCase] = []
    with get_session_factory()() as db:
        for case in corpus.cases:
            workspace = db.get(Workspace, case.workspace_id)
            user = db.get(User, case.user_id)
            if workspace is None or not workspace.active:
                raise SystemExit(f"Evaluation workspace not found: {case.workspace_id}")
            if user is None:
                raise SystemExit(f"Evaluation user not found: {case.user_id}")
            response = query_retrieval(
                db,
                workspace=workspace,
                user=user,
                request=_retrieval_request(case=case, strategy=strategy),
                source="cli.retrieval_quality_evaluation",
                keyword_search_client=staging_client,
                keyword_evaluation_entity_types=("file",),
                rag_allowed_unlisted_source_kinds=frozenset({"files"}),
                rag_query_service=rag_query_service,
                rag_collection=rag_collection,
            )
            cases.append(_evaluation_case(case=case, response=response))
    return cases


def _evaluation_collection_name(generation: str) -> str:
    return f"{resolve_default_collection_name(get_settings())}-evaluation-{generation}"


def _evaluation_query_service() -> RagQueryService:
    settings = get_settings()
    providers = get_provider_bundle()
    return RagQueryService(
        vector_index=providers.vector_index,
        embedding_client=providers.embedding,
        rerank_client=None,
        query_timeout_ms=min(settings.rag_query_timeout_ms, 5_000),
        rerank_candidate_k=settings.rag_rerank_candidate_k,
        vector_search_mode=RagVectorSearchMode.DENSE,
        legacy_collection_resolver=None,
    )


def _retrieval_request(
    *,
    case: RetrievalQualityCorpusCase,
    strategy: RetrievalStrategy,
) -> RetrievalQueryRequest:
    sources_by_strategy = {
        RetrievalStrategy.KEYWORD: ["keyword"],
        RetrievalStrategy.SEMANTIC: ["generic_rag"],
        RetrievalStrategy.HYBRID: ["keyword", "generic_rag"],
    }
    return RetrievalQueryRequest(
        query=case.query,
        strategy=strategy,
        sources=sources_by_strategy[strategy],
        source_kinds=case.source_kinds or ["files"],
        filters={"keyword": {"entity_types": ["file"]}},
        top_k=10,
        answer_mode=RetrievalAnswerMode.SEARCH_ONLY,
    )


def _evaluation_case(
    *,
    case: RetrievalQualityCorpusCase,
    response: RetrievalQueryResponse,
) -> RetrievalEvaluationCase:
    forbidden = set(case.forbidden_resource_ids)
    return RetrievalEvaluationCase(
        query_id=case.query_id,
        relevant_resource_ids=case.relevant_resource_ids,
        ranked_resource_ids=list(dict.fromkeys(hit.resource_id for hit in response.hits)),
        latency_ms=response.latency_ms,
        acl_violation_count=sum(hit.resource_id in forbidden for hit in response.hits),
        citation_failure_count=sum(not hit.citation for hit in response.hits),
    )


if __name__ == "__main__":
    main()
