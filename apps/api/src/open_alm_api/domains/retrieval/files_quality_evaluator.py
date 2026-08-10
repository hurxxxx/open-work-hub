from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.rag.query_service import RagQueryService
from open_alm_api.domains.rag.runtime import (
    build_partitioned_retrieval_candidate_query_service,
    resolve_default_collection_name,
    resolve_partitioned_rag_collection_alias,
    resolve_partitioned_rag_collection_name,
)
from open_alm_api.domains.retrieval.application import query_retrieval
from open_alm_api.domains.retrieval.contracts import (
    RetrievalAnswerMode,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalStrategy,
)
from open_alm_api.domains.retrieval.evaluation import (
    RetrievalEvaluationCase,
    RetrievalQualityCorpus,
    RetrievalQualityCorpusCase,
    RetrievalQualityGateArtifact,
    evaluate_retrieval_cases,
    retrieval_embedding_generation_identity,
    retrieval_quality_corpus_sha256,
    retrieval_reranker_generation_identity,
)
from open_alm_api.domains.retrieval.files_generation_runner import (
    FilesBackendPairInspection,
    FilesGenerationPairSpec,
    FilesSourceProjectionSnapshot,
    SourceSnapshotLoader,
    load_files_source_snapshot,
)
from open_alm_api.domains.retrieval.files_quality_judgments import (
    FilesQualityJudgmentError,
    FilesQualityJudgmentSnapshot,
    validate_files_quality_judgments,
)
from open_alm_api.domains.search.backend_contracts import KeywordSearchClient
from open_alm_api.domains.search.backend_factory import (
    build_partitioned_keyword_search_client,
)
from open_alm_api.domains.search.index_gateway import (
    keyword_search_index_alias,
    keyword_search_partitioned_index_alias,
    keyword_search_partitioned_index_name,
)
from open_alm_api.domains.source_access import SourceAclPolicy


class FilesQualityEvaluationError(RuntimeError):
    """Stable, non-sensitive operator error raised by the read-only evaluator."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class FilesGenerationInspectionBackend(Protocol):
    def inspect_pair(self, spec: FilesGenerationPairSpec) -> FilesBackendPairInspection: ...


SessionFactory = Callable[[], Session]
KeywordClientFactory = Callable[[object, str], KeywordSearchClient]
RagQueryServiceFactory = Callable[[object, str], RagQueryService]
RetrievalQuery = Callable[..., RetrievalQueryResponse]
SourceAclPolicyFactory = Callable[[Session, Workspace, User], SourceAclPolicy]


def evaluate_files_partitioned_quality(
    *,
    corpus_bytes: bytes,
    generation_key: str,
    settings: object,
    session_factory: SessionFactory,
    backends: FilesGenerationInspectionBackend,
    keyword_client_factory: KeywordClientFactory | None = None,
    rag_query_service_factory: RagQueryServiceFactory | None = None,
    source_acl_policy_factory: SourceAclPolicyFactory | None = None,
    source_snapshot_loader: SourceSnapshotLoader = load_files_source_snapshot,
    retrieval_query: RetrievalQuery = query_retrieval,
) -> RetrievalQualityGateArtifact:
    """Evaluate an immutable, already-materialized Files physical generation pair."""

    try:
        corpus = RetrievalQualityCorpus.model_validate_json(corpus_bytes)
    except (TypeError, ValueError) as error:
        raise FilesQualityEvaluationError("quality_corpus_invalid") from error
    if any(set(case.source_kinds) - {"files"} for case in corpus.cases):
        raise FilesQualityEvaluationError("quality_corpus_source_invalid")
    judgment_before = _quality_judgment_snapshot(
        corpus=corpus,
        session_factory=session_factory,
        source_acl_policy_factory=source_acl_policy_factory,
    )
    source_before = _source_snapshot(
        session_factory=session_factory,
        source_snapshot_loader=source_snapshot_loader,
    )

    spec = files_quality_generation_spec(settings, generation_key=generation_key)
    before = _inspect_complete_pair(backends, spec)
    _require_source_matches_pair(source_before, before)
    resolved_keyword_factory = keyword_client_factory or _build_keyword_client
    resolved_rag_factory = rag_query_service_factory or _build_rag_query_service
    try:
        keyword_client = resolved_keyword_factory(settings, spec.opensearch_physical_name)
        rag_query_service = resolved_rag_factory(settings, spec.qdrant_physical_name)
        embedding_identity = retrieval_embedding_generation_identity(settings)
        reranker_identity = retrieval_reranker_generation_identity(settings)
    except Exception as error:
        raise FilesQualityEvaluationError("physical_generation_binding_failed") from error

    reports = {
        strategy: evaluate_retrieval_cases(
            _evaluate_strategy(
                corpus=corpus,
                strategy=strategy,
                session_factory=session_factory,
                keyword_client=keyword_client,
                rag_query_service=rag_query_service,
                rag_collection=spec.qdrant_physical_name,
                retrieval_query=retrieval_query,
            )
        )
        for strategy in (
            RetrievalStrategy.KEYWORD,
            RetrievalStrategy.SEMANTIC,
            RetrievalStrategy.HYBRID,
        )
    }
    after = _inspect_complete_pair(backends, spec)
    if after != before:
        raise FilesQualityEvaluationError("physical_generation_changed_during_evaluation")
    judgment_after = _quality_judgment_snapshot(
        corpus=corpus,
        session_factory=session_factory,
        source_acl_policy_factory=source_acl_policy_factory,
    )
    if judgment_after != judgment_before:
        raise FilesQualityEvaluationError("quality_acl_changed_during_evaluation")
    source_after = _source_snapshot(
        session_factory=session_factory,
        source_snapshot_loader=source_snapshot_loader,
    )
    if source_after != source_before:
        raise FilesQualityEvaluationError("source_changed_during_evaluation")
    _require_source_matches_pair(source_after, after)

    opensearch = before.opensearch
    qdrant = before.qdrant
    assert opensearch is not None and qdrant is not None
    return RetrievalQualityGateArtifact(
        artifact_version=3,
        corpus_id=corpus.corpus_id,
        corpus_sha256=retrieval_quality_corpus_sha256(corpus_bytes),
        index_generation=spec.generation_key,
        keyword_index_uuid=opensearch.physical_id,
        keyword_index_config_sha256=opensearch.config_sha256,
        keyword_index_sha256=opensearch.content_sha256,
        qdrant_physical_id=qdrant.physical_id,
        qdrant_config_sha256=qdrant.config_sha256,
        qdrant_content_sha256=qdrant.content_sha256,
        embedding_model_identity=embedding_identity.model_identity,
        embedding_config_sha256=embedding_identity.config_sha256,
        reranker_model_identity=reranker_identity.model_identity,
        reranker_config_sha256=reranker_identity.config_sha256,
        source_files_event_watermark=source_before.files_event_watermark,
        source_resource_count=source_before.resource_count,
        source_identity_sha256=source_before.identity_sha256,
        source_artifact_sha256=source_before.artifact_sha256,
        source_acl_envelope_sha256=source_before.acl_envelope_sha256,
        judgment_acl_sha256=judgment_before.acl_sha256,
        bm25=reports[RetrievalStrategy.KEYWORD],
        dense=reports[RetrievalStrategy.SEMANTIC],
        hybrid=reports[RetrievalStrategy.HYBRID],
    )


def files_quality_generation_spec(
    settings: object,
    *,
    generation_key: str,
) -> FilesGenerationPairSpec:
    raw_generation = str(generation_key or "")
    normalized = raw_generation.strip().lower()
    if not normalized or raw_generation != normalized:
        raise FilesQualityEvaluationError("generation_identity_invalid")
    try:
        spec = FilesGenerationPairSpec(
            generation_key=normalized,
            opensearch_physical_name=keyword_search_partitioned_index_name(
                str(getattr(settings, "opensearch_index_prefix")),
                generation=normalized,
            ),
            opensearch_alias_name=keyword_search_partitioned_index_alias(
                str(getattr(settings, "opensearch_index_prefix"))
            ),
            qdrant_physical_name=resolve_partitioned_rag_collection_name(
                settings,
                generation=normalized,
            ),
            qdrant_alias_name=resolve_partitioned_rag_collection_alias(settings),
        )
    except Exception as error:
        raise FilesQualityEvaluationError("generation_identity_invalid") from error
    if spec.opensearch_alias_name == keyword_search_index_alias(
        str(getattr(settings, "opensearch_index_prefix"))
    ) or spec.qdrant_alias_name == resolve_default_collection_name(settings):
        raise FilesQualityEvaluationError("shared_legacy_alias_forbidden")
    return spec


def _inspect_complete_pair(
    backends: FilesGenerationInspectionBackend,
    spec: FilesGenerationPairSpec,
) -> FilesBackendPairInspection:
    try:
        inspection = backends.inspect_pair(spec)
    except Exception as error:
        raise FilesQualityEvaluationError("physical_generation_inspection_failed") from error
    opensearch = inspection.opensearch
    qdrant = inspection.qdrant
    if opensearch is None and qdrant is None:
        raise FilesQualityEvaluationError("physical_generation_missing")
    if opensearch is None or qdrant is None:
        raise FilesQualityEvaluationError("partial_physical_generation")
    if (
        opensearch.resource_count <= 0
        or opensearch.record_count != opensearch.resource_count
        or qdrant.resource_count != opensearch.resource_count
        or qdrant.record_count < qdrant.resource_count
        or qdrant.identity_sha256 != opensearch.identity_sha256
        or qdrant.physical_id != spec.qdrant_physical_name
    ):
        raise FilesQualityEvaluationError("physical_generation_inventory_invalid")
    return inspection


def _require_source_matches_pair(
    source: FilesSourceProjectionSnapshot,
    inspection: FilesBackendPairInspection,
) -> None:
    opensearch = inspection.opensearch
    qdrant = inspection.qdrant
    assert opensearch is not None and qdrant is not None
    if (
        source.unavailable_count
        or source.resource_count != opensearch.resource_count
        or source.resource_count != qdrant.resource_count
        or source.identity_sha256 != opensearch.identity_sha256
        or source.identity_sha256 != qdrant.identity_sha256
        or (
            source.opensearch_projection_sha256 is not None
            and source.opensearch_projection_sha256 != opensearch.projection_sha256
        )
        or (
            source.qdrant_record_count is not None
            and source.qdrant_record_count != qdrant.record_count
        )
        or (
            source.qdrant_projection_sha256 is not None
            and source.qdrant_projection_sha256 != qdrant.projection_sha256
        )
    ):
        raise FilesQualityEvaluationError("source_generation_mismatch")


def _quality_judgment_snapshot(
    *,
    corpus: RetrievalQualityCorpus,
    session_factory: SessionFactory,
    source_acl_policy_factory: SourceAclPolicyFactory | None,
) -> FilesQualityJudgmentSnapshot:
    try:
        return validate_files_quality_judgments(
            corpus=corpus,
            session_factory=session_factory,
            source_acl_policy_factory=source_acl_policy_factory,
        )
    except FilesQualityJudgmentError as error:
        raise FilesQualityEvaluationError(error.code) from error


def _source_snapshot(
    *,
    session_factory: SessionFactory,
    source_snapshot_loader: SourceSnapshotLoader,
) -> FilesSourceProjectionSnapshot:
    try:
        with session_factory() as db:
            return source_snapshot_loader(db)
    except Exception as error:
        raise FilesQualityEvaluationError("source_snapshot_failed") from error


def _evaluate_strategy(
    *,
    corpus: RetrievalQualityCorpus,
    strategy: RetrievalStrategy,
    session_factory: SessionFactory,
    keyword_client: KeywordSearchClient,
    rag_query_service: RagQueryService,
    rag_collection: str,
    retrieval_query: RetrievalQuery,
) -> list[RetrievalEvaluationCase]:
    cases: list[RetrievalEvaluationCase] = []
    for case in corpus.cases:
        try:
            with session_factory() as db:
                workspace, user = _evaluation_context(db, case)
                response = retrieval_query(
                    db,
                    workspace=workspace,
                    user=user,
                    request=_retrieval_request(case=case, strategy=strategy),
                    source="cli.files_partitioned_quality_evaluation",
                    keyword_search_client=keyword_client,
                    keyword_evaluation_entity_types=("file",),
                    rag_allowed_unlisted_source_kinds=frozenset({"files"}),
                    rag_query_service=rag_query_service,
                    rag_collection=rag_collection,
                    partitioned_generation=True,
                )
        except FilesQualityEvaluationError:
            raise
        except Exception as error:
            raise FilesQualityEvaluationError("retrieval_query_failed") from error
        if response.profile.degraded_reasons:
            raise FilesQualityEvaluationError("retrieval_query_degraded")
        cases.append(_evaluation_case(case=case, response=response))
    return cases


def _evaluation_context(
    db: Session,
    case: RetrievalQualityCorpusCase,
) -> tuple[Workspace, User]:
    workspace = db.get(Workspace, case.workspace_id)
    user = db.get(User, case.user_id)
    if workspace is None or not workspace.active:
        raise FilesQualityEvaluationError("evaluation_context_unavailable")
    if user is None or user.status != "active" or user.login_blocked:
        raise FilesQualityEvaluationError("evaluation_context_unavailable")
    return workspace, user


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


def _build_keyword_client(settings: object, physical_name: str) -> KeywordSearchClient:
    return build_partitioned_keyword_search_client(
        settings,
        physical_index_name=physical_name,
    )


def _build_rag_query_service(settings: object, physical_name: str) -> RagQueryService:
    return build_partitioned_retrieval_candidate_query_service(
        settings,
        collection=physical_name,
    )


__all__ = [
    "FilesQualityEvaluationError",
    "evaluate_files_partitioned_quality",
    "files_quality_generation_spec",
]
