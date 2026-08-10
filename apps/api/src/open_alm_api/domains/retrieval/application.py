from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
import logging
import time
from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_engine
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.settings import Settings, get_settings
from open_alm_api.core.telemetry import current_trace_id
from open_alm_api.domains.auth.access import resolve_workspace_runtime_enabled_app_ids
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.rag import application as rag_application
from open_alm_api.domains.rag.contracts import (
    RagAnswerMode,
    RagQueryResponse,
)
from open_alm_api.domains.rag.default_source_adapters import (
    ensure_rag_source_adapters_registered,
    registered_searchable_rag_app_ids,
)
from open_alm_api.domains.rag.runtime import (
    get_provider_bundle,
    get_retrieval_candidate_query_service,
)
from open_alm_api.domains.rag.query_service import RagQueryService
from open_alm_api.domains.retrieval.contracts import (
    RetrievalAnswerMode,
    RetrievalCitation,
    RetrievalGroundedAnswer,
    RetrievalHit,
    RetrievalProfile,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalSourceListResponse,
    RetrievalStrategy,
)
from open_alm_api.domains.retrieval.grounding import ground_ranked_hits
from open_alm_api.domains.retrieval.metrics import (
    record_retrieval_degraded,
    record_retrieval_query,
)
from open_alm_api.domains.retrieval.ranking import (
    candidate_limit,
    dedupe_ranked_hits,
    fuse_ranked_hits,
    rerank_hits,
)
from open_alm_api.domains.retrieval.source_catalog import (
    default_sources_for_strategy,
    iter_retrieval_source_catalog,
    source_catalog_item,
    source_descriptor,
)
from open_alm_api.domains.search import service as search_service
from open_alm_api.domains.search.backend_contracts import KeywordSearchClient
from open_alm_api.domains.search.entity_adapter_registry import (
    resolve_workspace_keyword_search_scope,
)
from open_alm_api.domains.search.schemas import KeywordSearchRequest, KeywordSearchResponse
from open_alm_api.domains.search.resource_mapping import resource_type_for_search_entity


_PRIMARY_BACKEND_TIMEOUT_SECONDS = 5.0
logger = logging.getLogger(__name__)
_PRIMARY_BACKEND_EXECUTOR = ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="retrieval-candidates",
)


def query_retrieval(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: RetrievalQueryRequest,
    source: str = "api.retrieval.query",
    principal_kind: str = "user",
    principal_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    gateway_workspace_id: str | None = None,
    keyword_search_client: KeywordSearchClient | None = None,
    keyword_evaluation_entity_types: tuple[str, ...] = (),
    keyword_strict_text_match: bool = False,
    rag_allowed_unlisted_source_kinds: frozenset[str] = frozenset(),
    rag_query_service: RagQueryService | None = None,
    rag_collection: str | None = None,
    partitioned_generation: bool = False,
) -> RetrievalQueryResponse:
    started = time.monotonic()
    enabled_app_ids = set(resolve_workspace_runtime_enabled_app_ids(db, workspace.id))
    resolved_sources, unavailable_default_sources = _resolve_request_sources(
        request,
        enabled_app_ids=enabled_app_ids,
    )
    profile = RetrievalProfile(
        strategy=request.strategy,
        requested_sources=list(request.sources),
        resolved_sources=resolved_sources,
        methods=[],
        backend_profiles={},
        degraded_reasons=[
            f"source_unavailable:{source_name}" for source_name in unavailable_default_sources
        ],
    )
    backend_hits: dict[str, list[RetrievalHit]] = {}
    candidate_k = candidate_limit(request.top_k)

    if request.strategy == RetrievalStrategy.GRAPH_HYBRID:
        profile.backend_profiles["graph_hybrid"] = {
            "persistent_graph_store": False,
            "mode": "query_time_fusion",
        }

    primary_sources = [
        source_name for source_name in ("keyword", "generic_rag") if source_name in resolved_sources
    ]
    primary_responses, primary_errors = _query_primary_candidate_backends(
        db,
        workspace=workspace,
        user=user,
        request=request,
        sources=primary_sources,
        candidate_k=candidate_k,
        source=source,
        principal_kind=principal_kind,
        principal_id=principal_id,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        keyword_search_client=keyword_search_client,
        keyword_evaluation_entity_types=keyword_evaluation_entity_types,
        keyword_strict_text_match=keyword_strict_text_match,
        rag_allowed_unlisted_source_kinds=rag_allowed_unlisted_source_kinds,
        rag_query_service=rag_query_service,
        rag_collection=rag_collection,
        partitioned_generation=partitioned_generation,
    )
    if request.sources and primary_errors:
        failed_source = sorted(primary_errors)[0]
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="retrieval.source_failed",
            source=failed_source,
        )
    for backend, error_name in primary_errors.items():
        profile.degraded_reasons.append(f"{backend}:{error_name}")
    keyword_response = primary_responses.get("keyword")
    if isinstance(keyword_response, KeywordSearchResponse):
        backend_hits["keyword"] = _keyword_response_to_hits(keyword_response)
        profile.backend_profiles["keyword"] = {
            "total": keyword_response.total,
            "has_more": keyword_response.has_more,
            "trace_id": keyword_response.trace_id,
            "candidate_k": candidate_k,
            "method": "bm25",
        }
        _add_methods(profile, ("bm25",))
    rag_response = primary_responses.get("generic_rag")
    if isinstance(rag_response, RagQueryResponse):
        backend_hits["generic_rag"] = _rag_response_to_hits(
            rag_response,
            source="generic_rag",
        )
        profile.backend_profiles["generic_rag"] = dict(rag_response.query_profile)
        profile.backend_profiles["generic_rag"].update(
            {
                "trace_id": rag_response.trace_id,
                "candidate_k": candidate_k,
                "search_mode": "dense",
                "backend_rerank_applied": False,
            }
        )
        _add_methods(profile, ("semantic", "vector", "dense_vector"))

    if "qna" in resolved_sources:
        try:
            qna_response = _query_qna_rag(
                db,
                user=user,
                query=request.query,
                answer_mode=RagAnswerMode.SEARCH_ONLY,
                filters=_rag_filters_from_retrieval(request.filters),
                top_k=candidate_k,
                include_binary_hits=request.include_binary_hits,
                query_service=get_retrieval_candidate_query_service(),
                source=source,
                principal_kind=principal_kind,
                principal_id=principal_id,
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
                gateway_workspace_id=gateway_workspace_id,
            )
        except Exception as error:  # noqa: BLE001 - retrieval aggregates degraded backends.
            if request.sources:
                raise localized_http_exception(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    code="retrieval.source_failed",
                    source="qna",
                ) from error
            profile.degraded_reasons.append(f"qna:{type(error).__name__}")
        else:
            backend_hits["qna"] = _rag_response_to_hits(qna_response, source="qna")
            profile.backend_profiles["qna"] = dict(qna_response.query_profile)
            profile.backend_profiles["qna"]["trace_id"] = qna_response.trace_id
            _add_methods(profile, ("semantic", "vector", "dense_vector", "company_rag"))

    if "legacy_issues" in resolved_sources:
        try:
            evidence, legacy_profile = _search_legacy_issue_evidence(
                db,
                workspace=workspace,
                request=request,
            )
        except Exception as error:  # noqa: BLE001 - retrieval aggregates degraded backends.
            if request.sources:
                raise localized_http_exception(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    code="retrieval.source_failed",
                    source="legacy_issues",
                ) from error
            profile.degraded_reasons.append(f"legacy_issues:{type(error).__name__}")
        else:
            backend_hits["legacy_issues"] = _legacy_evidence_to_hits(evidence)
            profile.backend_profiles["legacy_issues"] = _plain_payload(legacy_profile)
            _add_methods(
                profile,
                tuple(getattr(legacy_profile, "methods", ()) or ("legacy_issue",)),
            )

    nonempty_backend_hits = {backend: hits for backend, hits in backend_hits.items() if hits}
    if len(nonempty_backend_hits) > 1:
        ranking_result = fuse_ranked_hits(nonempty_backend_hits)
        _add_methods(profile, ("rrf", "hybrid_merge"))
    else:
        flat_hits = [hit for hits in nonempty_backend_hits.values() for hit in hits]
        ranking_result = dedupe_ranked_hits(flat_hits)
    profile.backend_profiles["fusion"] = ranking_result.profile

    ranked_hits = list(ranking_result.hits)
    if request.strategy != RetrievalStrategy.KEYWORD and ranked_hits:
        try:
            rerank_result = rerank_hits(
                query=request.query,
                hits=ranked_hits,
                rerank_client=get_provider_bundle().rerank,
                limit=candidate_k,
            )
        except Exception as error:  # noqa: BLE001 - fusion remains usable without rerank.
            profile.degraded_reasons.append(f"rerank:{type(error).__name__}")
            profile.backend_profiles["rerank"] = {
                "applied": False,
                "degraded": True,
                "candidate_count": len(ranked_hits),
            }
        else:
            ranked_hits = list(rerank_result.hits)
            profile.backend_profiles["rerank"] = rerank_result.profile
            if rerank_result.profile.get("applied"):
                _add_methods(profile, ("cross_encoder",))
            if rerank_result.profile.get("degraded"):
                error_type = str(rerank_result.profile.get("error_type") or "Unavailable")
                profile.degraded_reasons.append(f"rerank:{error_type}")

    merged_hits = ranked_hits[: request.top_k]
    grounded_answer: RetrievalGroundedAnswer | None = None
    citations: list[RetrievalCitation] = []
    if request.answer_mode == RetrievalAnswerMode.GROUNDED_ANSWER and merged_hits:
        try:
            grounding_result = ground_ranked_hits(
                db=db,
                workspace=workspace,
                user=user,
                query=request.query,
                hits=merged_hits,
                source=source,
                principal_kind=principal_kind,
                principal_id=principal_id,
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
            )
        except Exception as error:  # noqa: BLE001 - search results remain usable.
            profile.degraded_reasons.append(f"grounded_answer:{type(error).__name__}")
        else:
            grounded_answer = grounding_result.answer
            profile.backend_profiles["grounded_answer"] = {
                "applied": grounded_answer is not None,
                "degraded": grounding_result.degraded,
                "error_type": grounding_result.error_type,
                "evidence_count": len(merged_hits),
            }
            if grounded_answer is not None:
                citations = list(grounded_answer.citations)
            if grounding_result.degraded:
                profile.degraded_reasons.append(
                    f"grounded_answer:{grounding_result.error_type or 'default_fallback'}"
                )

    latency_ms = int((time.monotonic() - started) * 1000)
    for reason in profile.degraded_reasons:
        record_retrieval_degraded(strategy=request.strategy.value, reason=reason)
    record_retrieval_query(
        strategy=request.strategy.value,
        latency_ms=latency_ms,
        result_count=len(merged_hits),
    )
    return RetrievalQueryResponse(
        query=request.query,
        strategy=request.strategy,
        hits=merged_hits,
        citations=citations,
        methods=list(profile.methods),
        profile=profile,
        grounded_answer=grounded_answer,
        trace_id=current_trace_id(),
        latency_ms=latency_ms,
    )


def list_retrieval_sources(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
) -> RetrievalSourceListResponse:
    del user
    enabled_app_ids = set(resolve_workspace_runtime_enabled_app_ids(db, workspace.id))
    return RetrievalSourceListResponse(
        sources=[
            source_descriptor(
                item,
                available=_source_available(item.source, item.required_app_ids, enabled_app_ids),
            )
            for item in iter_retrieval_source_catalog()
        ]
    )


def query_workspace_rag_response(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    query: str,
    answer_mode,
    source_kinds: list[str],
    filters: dict[str, Any],
    top_k: int,
    include_binary_hits: bool,
    settings: Settings | None = None,
    query_service=None,
    source: str = "api.rag.query",
    principal_kind: str = "user",
    principal_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    require_searchable_app: bool = True,
    allowed_unlisted_source_kinds: frozenset[str] = frozenset(),
    required_app_ids: frozenset[str] = frozenset(),
) -> RagQueryResponse:
    if not _unified_enabled(settings):
        return rag_application.query_workspace_rag(
            db,
            workspace=workspace,
            user=user,
            query=query,
            answer_mode=answer_mode,
            source_kinds=source_kinds,
            filters=filters,
            top_k=top_k,
            include_binary_hits=include_binary_hits,
            settings=settings,
            query_service=query_service,
            source=source,
            principal_kind=principal_kind,
            principal_id=principal_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            require_searchable_app=require_searchable_app,
            allowed_unlisted_source_kinds=allowed_unlisted_source_kinds,
            required_app_ids=required_app_ids,
        )
    return _query_generic_rag(
        db,
        workspace=workspace,
        user=user,
        query=query,
        answer_mode=answer_mode,
        source_kinds=source_kinds,
        filters=filters,
        top_k=top_k,
        include_binary_hits=include_binary_hits,
        settings=settings,
        query_service=query_service,
        source=source,
        principal_kind=principal_kind,
        principal_id=principal_id,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        require_searchable_app=require_searchable_app,
        allowed_unlisted_source_kinds=allowed_unlisted_source_kinds,
        required_app_ids=required_app_ids,
    )


def query_workspace_keyword_search_response(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: KeywordSearchRequest,
    settings: Settings | None = None,
) -> KeywordSearchResponse:
    if not _unified_enabled(settings):
        return search_service.query_workspace_keyword_search(
            db,
            workspace=workspace,
            user=user,
            request=request,
        )
    return search_service.query_workspace_keyword_search(
        db,
        workspace=workspace,
        user=user,
        request=request,
    )


def list_workspace_rag_sources_response(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    settings: Settings | None = None,
) -> list[dict[str, str]]:
    return rag_application.list_workspace_rag_sources(
        db,
        workspace=workspace,
        user=user,
        settings=settings,
    )


def query_company_qna_rag_response(
    db: Session,
    *,
    user: User,
    query: str,
    answer_mode,
    source_kinds: list[str],
    filters: dict[str, Any],
    top_k: int,
    include_binary_hits: bool,
    settings: Settings | None = None,
    query_service=None,
    source: str = "api.rag.company_query",
    principal_kind: str = "user",
    principal_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    gateway_workspace_id: str | None = None,
) -> RagQueryResponse:
    if not _unified_enabled(settings):
        return rag_application.query_company_rag(
            db,
            user=user,
            query=query,
            answer_mode=answer_mode,
            source_kinds=source_kinds,
            filters=filters,
            top_k=top_k,
            include_binary_hits=include_binary_hits,
            settings=settings,
            query_service=query_service,
            source=source,
            principal_kind=principal_kind,
            principal_id=principal_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            gateway_workspace_id=gateway_workspace_id,
        )
    return rag_application.query_company_rag(
        db,
        user=user,
        query=query,
        answer_mode=answer_mode,
        source_kinds=source_kinds,
        filters=filters,
        top_k=top_k,
        include_binary_hits=include_binary_hits,
        settings=settings,
        query_service=query_service,
        source=source,
        principal_kind=principal_kind,
        principal_id=principal_id,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        gateway_workspace_id=gateway_workspace_id,
    )


def search_legacy_issue_evidence_response(
    db: Session,
    *,
    workspace: Workspace,
    plan,
    limit: int,
    module_keys: frozenset[str] | None = None,
):
    from open_alm_api.domains.legacy_issues.ai_search import search_legacy_issue_evidence

    return search_legacy_issue_evidence(
        db,
        workspace=workspace,
        plan=plan,
        limit=limit,
        module_keys=module_keys,
    )


def _query_primary_candidate_backends(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: RetrievalQueryRequest,
    sources: list[str],
    candidate_k: int,
    source: str,
    principal_kind: str,
    principal_id: str | None,
    agent_run_id: str | None,
    conversation_id: str | None,
    keyword_search_client: KeywordSearchClient | None = None,
    keyword_evaluation_entity_types: tuple[str, ...] = (),
    keyword_strict_text_match: bool = False,
    rag_allowed_unlisted_source_kinds: frozenset[str] = frozenset(),
    rag_query_service: RagQueryService | None = None,
    rag_collection: str | None = None,
    partitioned_generation: bool = False,
) -> tuple[dict[str, object], dict[str, str]]:
    if not sources:
        return {}, {}
    if len(sources) == 1:
        backend = sources[0]
        try:
            response = _query_primary_candidate_backend(
                db,
                backend=backend,
                workspace=workspace,
                user=user,
                request=request,
                candidate_k=candidate_k,
                source=source,
                principal_kind=principal_kind,
                principal_id=principal_id,
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
                keyword_search_client=keyword_search_client,
                keyword_evaluation_entity_types=keyword_evaluation_entity_types,
                keyword_strict_text_match=keyword_strict_text_match,
                rag_allowed_unlisted_source_kinds=rag_allowed_unlisted_source_kinds,
                rag_query_service=rag_query_service,
                rag_collection=rag_collection,
                partitioned_generation=partitioned_generation,
            )
        except Exception as error:  # noqa: BLE001 - caller returns a degraded response.
            logger.warning(
                "Retrieval candidate backend failed: %s",
                backend,
                exc_info=True,
            )
            return {}, {backend: type(error).__name__}
        return {backend: response}, {}

    futures: dict[Future[object], str] = {
        _PRIMARY_BACKEND_EXECUTOR.submit(
            _query_primary_candidate_backend_in_fresh_session,
            backend=backend,
            workspace_id=workspace.id,
            user_id=user.id,
            request=request,
            candidate_k=candidate_k,
            source=source,
            principal_kind=principal_kind,
            principal_id=principal_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            keyword_search_client=keyword_search_client,
            keyword_evaluation_entity_types=keyword_evaluation_entity_types,
            keyword_strict_text_match=keyword_strict_text_match,
            rag_allowed_unlisted_source_kinds=rag_allowed_unlisted_source_kinds,
            rag_query_service=rag_query_service,
            rag_collection=rag_collection,
            partitioned_generation=partitioned_generation,
        ): backend
        for backend in sources
    }
    completed, pending = wait(futures, timeout=_PRIMARY_BACKEND_TIMEOUT_SECONDS)
    responses: dict[str, object] = {}
    errors: dict[str, str] = {}
    for future in completed:
        backend = futures[future]
        try:
            responses[backend] = future.result()
        except Exception as error:  # noqa: BLE001 - caller returns a degraded response.
            logger.warning(
                "Retrieval candidate backend failed: %s",
                backend,
                exc_info=True,
            )
            errors[backend] = type(error).__name__
    for future in pending:
        backend = futures[future]
        future.cancel()
        errors[backend] = "TimeoutError"
    return responses, errors


def _query_primary_candidate_backend_in_fresh_session(
    *,
    backend: str,
    workspace_id: str,
    user_id: str,
    request: RetrievalQueryRequest,
    candidate_k: int,
    source: str,
    principal_kind: str,
    principal_id: str | None,
    agent_run_id: str | None,
    conversation_id: str | None,
    keyword_search_client: KeywordSearchClient | None = None,
    keyword_evaluation_entity_types: tuple[str, ...] = (),
    keyword_strict_text_match: bool = False,
    rag_allowed_unlisted_source_kinds: frozenset[str] = frozenset(),
    rag_query_service: RagQueryService | None = None,
    rag_collection: str | None = None,
    partitioned_generation: bool = False,
) -> object:
    with Session(get_engine()) as isolated_db:
        workspace = isolated_db.get(Workspace, workspace_id)
        user = isolated_db.get(User, user_id)
        if workspace is None or user is None:
            raise RuntimeError("Retrieval execution context no longer exists.")
        return _query_primary_candidate_backend(
            isolated_db,
            backend=backend,
            workspace=workspace,
            user=user,
            request=request,
            candidate_k=candidate_k,
            source=source,
            principal_kind=principal_kind,
            principal_id=principal_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            keyword_search_client=keyword_search_client,
            keyword_evaluation_entity_types=keyword_evaluation_entity_types,
            keyword_strict_text_match=keyword_strict_text_match,
            rag_allowed_unlisted_source_kinds=rag_allowed_unlisted_source_kinds,
            rag_query_service=rag_query_service,
            rag_collection=rag_collection,
            partitioned_generation=partitioned_generation,
        )


def _query_primary_candidate_backend(
    db: Session,
    *,
    backend: str,
    workspace: Workspace,
    user: User,
    request: RetrievalQueryRequest,
    candidate_k: int,
    source: str,
    principal_kind: str,
    principal_id: str | None,
    agent_run_id: str | None,
    conversation_id: str | None,
    keyword_search_client: KeywordSearchClient | None = None,
    keyword_evaluation_entity_types: tuple[str, ...] = (),
    keyword_strict_text_match: bool = False,
    rag_allowed_unlisted_source_kinds: frozenset[str] = frozenset(),
    rag_query_service: RagQueryService | None = None,
    rag_collection: str | None = None,
    partitioned_generation: bool = False,
) -> object:
    if backend == "keyword":
        return _query_keyword_search(
            db,
            workspace=workspace,
            user=user,
            request=request,
            candidate_k=candidate_k,
            client=keyword_search_client,
            evaluation_entity_types=keyword_evaluation_entity_types,
            strict_text_match=keyword_strict_text_match,
            partitioned_generation=partitioned_generation,
        )
    if backend == "generic_rag":
        return _query_generic_rag(
            db,
            workspace=workspace,
            user=user,
            query=request.query,
            answer_mode=RagAnswerMode.SEARCH_ONLY,
            source_kinds=request.source_kinds,
            filters=_rag_filters_from_retrieval(request.filters),
            top_k=candidate_k,
            include_binary_hits=request.include_binary_hits,
            query_service=rag_query_service or get_retrieval_candidate_query_service(),
            collection=rag_collection,
            partitioned_generation=partitioned_generation,
            source=source,
            principal_kind=principal_kind,
            principal_id=principal_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            require_searchable_app=True,
            allowed_unlisted_source_kinds=rag_allowed_unlisted_source_kinds,
            required_app_ids=frozenset(),
        )
    raise ValueError(f"Unsupported primary retrieval backend: {backend}")


def _query_generic_rag(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    query: str,
    answer_mode,
    source_kinds: list[str],
    filters: dict[str, Any],
    top_k: int,
    include_binary_hits: bool,
    settings: Settings | None = None,
    query_service=None,
    source: str = "api.retrieval.query",
    principal_kind: str = "user",
    principal_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    require_searchable_app: bool = True,
    allowed_unlisted_source_kinds: frozenset[str] = frozenset(),
    required_app_ids: frozenset[str] = frozenset(),
    collection: str | None = None,
    partitioned_generation: bool = False,
) -> RagQueryResponse:
    return rag_application.query_workspace_rag(
        db,
        workspace=workspace,
        user=user,
        query=query,
        answer_mode=answer_mode,
        source_kinds=source_kinds,
        filters=filters,
        top_k=top_k,
        include_binary_hits=include_binary_hits,
        settings=settings,
        query_service=query_service,
        source=source,
        principal_kind=principal_kind,
        principal_id=principal_id,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        require_searchable_app=require_searchable_app,
        allowed_unlisted_source_kinds=allowed_unlisted_source_kinds,
        required_app_ids=required_app_ids,
        collection=collection,
        partitioned_generation=partitioned_generation,
    )


def _query_qna_rag(
    db: Session,
    *,
    user: User,
    query: str,
    answer_mode,
    filters: dict[str, Any],
    top_k: int,
    include_binary_hits: bool,
    query_service,
    source: str,
    principal_kind: str,
    principal_id: str | None,
    agent_run_id: str | None,
    conversation_id: str | None,
    gateway_workspace_id: str | None,
) -> RagQueryResponse:
    from open_alm_api.domains.qna.constants import QNA_DOC_SOURCE_KIND

    return query_company_qna_rag_response(
        db,
        user=user,
        query=query,
        answer_mode=answer_mode,
        source_kinds=[QNA_DOC_SOURCE_KIND],
        filters=filters,
        top_k=top_k,
        include_binary_hits=include_binary_hits,
        query_service=query_service,
        source=source,
        principal_kind=principal_kind,
        principal_id=principal_id,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        gateway_workspace_id=gateway_workspace_id,
    )


def _query_keyword_search(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: RetrievalQueryRequest,
    candidate_k: int | None = None,
    client: KeywordSearchClient | None = None,
    evaluation_entity_types: tuple[str, ...] = (),
    strict_text_match: bool = False,
    partitioned_generation: bool = False,
) -> KeywordSearchResponse:
    keyword_request = _keyword_request_from_retrieval(
        workspace=workspace,
        request=request,
        candidate_k=candidate_k,
    )
    return search_service.query_workspace_keyword_search(
        db,
        workspace=workspace,
        user=user,
        request=keyword_request,
        backend_timeout_seconds=_PRIMARY_BACKEND_TIMEOUT_SECONDS,
        client=client,
        evaluation_entity_types=evaluation_entity_types,
        # Retrieval questions are natural language by default. Search-engine
        # keyword surfaces can opt into the regular strict-AND contract.
        text_operator="and" if strict_text_match else "or",
        text_minimum_should_match=None if strict_text_match else "30%",
        backend_candidate_size=candidate_k or request.top_k,
        partitioned_generation=partitioned_generation,
    )


def _search_legacy_issue_evidence(
    db: Session,
    *,
    workspace: Workspace,
    request: RetrievalQueryRequest,
):
    from open_alm_api.domains.legacy_issues.ai_search import (
        sanitize_legacy_issue_search_plan,
        search_legacy_issue_evidence,
    )
    from open_alm_api.domains.legacy_issues.module_access import (
        enabled_legacy_issue_module_keys,
    )

    filters = dict(request.filters)
    plan = sanitize_legacy_issue_search_plan(
        question=request.query,
        dataset_keys=_string_list(
            filters.get("dataset_keys")
            or filters.get("legacy_issue_dataset_keys")
            or filters.get("legacy_dataset_keys")
        ),
        primary_keywords=_string_list(filters.get("primary_keywords")),
        keywords=_string_list(filters.get("keywords")),
        supporting_keywords=_string_list(filters.get("supporting_keywords")),
        field_hints=_string_list(filters.get("field_hints")),
        intent=str(filters.get("intent") or "investigate"),
        report_focus=_string_list(filters.get("report_focus")),
        related_field_expansions=_string_list(filters.get("related_field_expansions")),
    )
    return search_legacy_issue_evidence(
        db,
        workspace=workspace,
        plan=plan,
        limit=request.top_k,
        module_keys=enabled_legacy_issue_module_keys(
            compressor_enabled=get_settings().legacy_issue_compressor_enabled,
        ),
    )


def _keyword_request_from_retrieval(
    *,
    workspace: Workspace,
    request: RetrievalQueryRequest,
    candidate_k: int | None = None,
) -> KeywordSearchRequest:
    raw: dict[str, Any] = {}
    keyword_filters = request.filters.get("keyword")
    if isinstance(keyword_filters, dict):
        raw.update(keyword_filters)
    for key in KeywordSearchRequest.model_fields:
        if key in request.filters:
            raw[key] = request.filters[key]
    raw["workspace_id"] = workspace.id
    raw["query"] = request.query
    raw["limit"] = candidate_k or request.top_k
    raw.setdefault("offset", 0)
    return KeywordSearchRequest.model_validate(raw)


def _rag_filters_from_retrieval(filters: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    nested = filters.get("rag")
    if isinstance(nested, dict):
        raw.update(nested)
    allowed_flat_keys = {
        "content_modality",
        "resource_id",
        "resource_type",
        "source_kind",
        "visibility_refs_contains",
    }
    for key, value in filters.items():
        if key in allowed_flat_keys or key.startswith("metadata."):
            raw[key] = value
    return raw


def _resolve_request_sources(
    request: RetrievalQueryRequest,
    *,
    enabled_app_ids: set[str],
) -> tuple[list[str], list[str]]:
    requested = list(request.sources) or list(default_sources_for_strategy(request.strategy))
    explicit = bool(request.sources)
    resolved: list[str] = []
    unavailable: list[str] = []
    for source in requested:
        item = source_catalog_item(source)
        if item is None or not item.active:
            if explicit:
                raise localized_http_exception(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    code="retrieval.invalid_source",
                    source=source,
                )
            unavailable.append(source)
            continue
        if not _source_available(item.source, item.required_app_ids, enabled_app_ids):
            if explicit:
                raise localized_http_exception(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code="retrieval.source_unavailable",
                    source=source,
                )
            unavailable.append(source)
            continue
        if item.source not in resolved:
            resolved.append(item.source)
    return resolved, unavailable


def _rag_response_to_hits(response: RagQueryResponse, *, source: str) -> list[RetrievalHit]:
    return [
        RetrievalHit(
            source=source,
            source_kind=hit.source_kind,
            resource_type=hit.resource_type,
            resource_id=hit.resource_id,
            workspace_id=hit.workspace_id,
            title=hit.title,
            summary=hit.summary,
            excerpt=hit.excerpt,
            score=hit.score,
            citation=hit.citation,
            methods=["semantic", "vector", "dense_vector"],
            metadata={
                **dict(hit.metadata),
                "scope_kind": str(hit.scope_kind),
                "owner_label": hit.owner_label,
                "acl_summary": list(hit.acl_summary),
                "origin_ref": hit.origin_ref,
            },
        )
        for hit in response.hits
    ]


def _keyword_response_to_hits(response: KeywordSearchResponse) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    for hit in response.hits:
        hits.append(
            RetrievalHit(
                source="keyword",
                source_kind=str(hit.metadata.get("source_kind") or hit.entity_type),
                resource_type=resource_type_for_search_entity(hit.entity_type),
                resource_id=hit.entity_id,
                workspace_id=hit.workspace_id,
                title=hit.title,
                summary=hit.summary,
                excerpt=hit.snippet.text,
                score=hit.score,
                citation=hit.deep_link,
                methods=["bm25"],
                metadata={
                    "scope_kind": "workspace",
                    "status": hit.status,
                    "status_label": hit.status_label,
                    "visibility": hit.visibility,
                    "deep_link": hit.deep_link,
                    "preview_url": hit.preview_url,
                    "targets": [target.model_dump(mode="json") for target in hit.targets],
                    "people": [person.model_dump(mode="json") for person in hit.people],
                    **dict(hit.metadata),
                },
            )
        )
    return hits


def _legacy_evidence_to_hits(evidence: list[Any]) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    for item in evidence:
        matched_chunks = tuple(getattr(item, "matched_chunks", ()) or ())
        excerpt = "\n".join(
            str(getattr(chunk, "excerpt", "") or "").strip()
            for chunk in matched_chunks[:3]
            if str(getattr(chunk, "excerpt", "") or "").strip()
        )
        methods = sorted(set(getattr(item, "methods", ()) or ()))
        hits.append(
            RetrievalHit(
                source="legacy_issues",
                source_kind=str(getattr(item, "dataset_key", "") or "legacy_issues"),
                resource_type="legacy_issue_record",
                resource_id=str(getattr(item, "record_id", "") or getattr(item, "evidence_id", "")),
                workspace_id=None,
                title=str(getattr(item, "label", "") or getattr(item, "dataset_title", "")),
                summary=str(getattr(item, "dataset_title", "") or ""),
                excerpt=excerpt,
                score=float(getattr(item, "score", 0.0) or 0.0),
                citation=str(getattr(item, "evidence_id", "") or ""),
                methods=methods,
                metadata={
                    "dataset_key": getattr(item, "dataset_key", None),
                    "dataset_title": getattr(item, "dataset_title", None),
                    "revision_id": getattr(item, "revision_id", None),
                    "revision_no": getattr(item, "revision_no", None),
                    "stable_record_id": getattr(item, "stable_record_id", None),
                    "matched_fields": list(getattr(item, "matched_fields", ()) or ()),
                    "values": dict(getattr(item, "values", {}) or {}),
                    "matched_chunks": [_plain_payload(chunk) for chunk in matched_chunks],
                },
            )
        )
    return hits


def _add_methods(profile: RetrievalProfile, methods: tuple[str, ...]) -> None:
    for method in methods:
        if method and method not in profile.methods:
            profile.methods.append(method)


def _source_available(
    source: str,
    required_app_ids: tuple[str, ...],
    enabled_app_ids: set[str],
) -> bool:
    if source == "generic_rag":
        ensure_rag_source_adapters_registered()
        return bool(
            get_settings().rag_enabled
            and registered_searchable_rag_app_ids().intersection(enabled_app_ids)
        )
    if source == "qna":
        return bool(
            get_settings().rag_enabled and _source_apps_available(required_app_ids, enabled_app_ids)
        )
    if source == "keyword":
        return resolve_workspace_keyword_search_scope(enabled_app_ids).has_sources
    return _source_apps_available(required_app_ids, enabled_app_ids)


def _source_apps_available(required_app_ids: tuple[str, ...], enabled_app_ids: set[str]) -> bool:
    return not required_app_ids or all(app_id in enabled_app_ids for app_id in required_app_ids)


def _unified_enabled(settings: Settings | None = None) -> bool:
    resolved = settings or get_settings()
    return bool(getattr(resolved, "retrieval_unified_enabled", True))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _plain_payload(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return [_plain_payload(item) for item in value]
    if isinstance(value, list):
        return [_plain_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain_payload(item) for key, item in value.items()}
    return value
