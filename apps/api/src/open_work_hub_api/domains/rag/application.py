from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.auth.access import (
    resolve_platform_enabled_app_ids,
    resolve_workspace_runtime_enabled_app_ids,
)
from open_work_hub_api.domains.auth.models import User, Workspace, WorkspaceUserBinding
from open_work_hub_api.domains.auth.workspace_apps import get_workspace_app_catalog_item
from open_work_hub_api.domains.conversations.app_catalog import CHATBOT_WORKSPACE_APP
from open_work_hub_api.domains.files.retrieval_contract import FILES_RAG_SOURCE_KIND
from open_work_hub_api.domains.rag.grounded_answer import LlmGroundedAnswerSynthesizer
from open_work_hub_api.domains.rag.providers import (
    RagProviderConfigurationError,
    RagProviderError,
    RagProviderTimeoutError,
    RagProviderTransientError,
)
from open_work_hub_api.domains.rag.access_filter import (
    build_company_rag_post_filter,
    build_user_rag_post_filter,
)
from open_work_hub_api.domains.rag.contracts import (
    RagAnswerMode,
    RagJobStatus,
    RagQueryRequest,
    RagQueryResponse,
    RagScopeKind,
    RagSyncLane,
    RagVectorSearchHit,
)
from open_work_hub_api.domains.rag.default_source_adapters import (
    company_reindex_resource_adapters,
    list_registered_workspace_rag_sources,
    registered_searchable_rag_app_ids,
    resolve_rag_resource_types_for_source_kinds,
    workspace_reindex_resource_adapters,
)
from open_work_hub_api.domains.rag.outbox import enqueue_rag_sync_job
from open_work_hub_api.domains.rag.query_service import RagQueryService
from open_work_hub_api.domains.rag.runtime import (
    build_rag_query_service,
    ensure_default_collection_ready,
    get_default_embedding_dimensions,
    get_provider_bundle,
    get_rag_query_service,
    resolve_default_collection_name,
)
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.retrieval.partitioning import (
    flatten_read_scope,
    resolve_resource_read_scope,
)
from open_work_hub_api.domains.source_access import SourceAclPolicy


class RagApplicationError(RuntimeError):
    default_code = "rag.unavailable"

    def __init__(
        self,
        reason: str | None = None,
        *,
        code: str | None = None,
        **params: Any,
    ) -> None:
        self.code = code or self.default_code
        self.params = dict(params)
        if reason is not None:
            self.params.setdefault("reason", reason)
        super().__init__(reason or self.code)


class RagUnavailableError(RagApplicationError):
    default_code = "rag.unavailable"


class RagAccessDeniedError(RagApplicationError):
    default_code = "rag.access_denied"


class RagReindexCooldownError(RagApplicationError):
    default_code = "rag.reindex_cooldown"


def rag_error_payload(
    error: RuntimeError,
    *,
    default_code: str,
) -> tuple[str, dict[str, Any]]:
    if isinstance(error, RagApplicationError):
        return error.code, dict(error.params)
    return default_code, {"reason": str(error)}


RAG_REINDEX_COOLDOWN = timedelta(minutes=5)
_DEFAULT_RAG_REQUIRED_APP_IDS = frozenset({CHATBOT_WORKSPACE_APP.app_id})
_RAG_QUERY_PROVIDER_ERRORS = (
    RagProviderConfigurationError,
    RagProviderError,
    RagProviderTransientError,
    RagProviderTimeoutError,
    TimeoutError,
)


def ensure_rag_enabled(settings: Settings | None = None) -> Settings:
    resolved = settings or get_settings()
    if not resolved.rag_enabled:
        raise RagUnavailableError(code="rag.disabled")
    return resolved


def query_workspace_rag(
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
    query_service: RagQueryService | None = None,
    source: str = "api.rag.query",
    principal_kind: str = "user",
    principal_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    require_searchable_app: bool = True,
    allowed_unlisted_source_kinds: frozenset[str] = frozenset(),
    required_app_ids: frozenset[str] = _DEFAULT_RAG_REQUIRED_APP_IDS,
    collection: str | None = None,
    partitioned_generation: bool = False,
) -> RagQueryResponse:
    resolved_settings = ensure_rag_enabled(settings)
    effective_source_kinds, requested_source_kinds = _resolve_query_source_kinds(
        db=db,
        workspace=workspace,
        user=user,
        settings=resolved_settings,
        source_kinds=source_kinds,
        require_searchable_app=require_searchable_app,
        allowed_unlisted_source_kinds=allowed_unlisted_source_kinds,
        required_app_ids=required_app_ids,
    )
    if not effective_source_kinds:
        return _empty_query_response(
            query=query,
            answer_mode=answer_mode,
            reason="no_accessible_sources",
            requested_source_kinds=requested_source_kinds,
        )
    retrieval_partition_ids = _resolve_query_partition_ids(
        db,
        source_kinds=effective_source_kinds,
        workspace_id=workspace.id,
        user_id=user.id,
        partitioned_generation=partitioned_generation,
    )
    if partitioned_generation and not retrieval_partition_ids:
        return _empty_query_response(
            query=query,
            answer_mode=answer_mode,
            reason="no_authorized_partitions",
            requested_source_kinds=requested_source_kinds,
        )
    service = _prepare_query_runtime(
        resolved_settings,
        use_default_runtime=settings is None,
        query_service=query_service,
        ensure_default_collection=collection is None,
    )
    request = _project_query_request(
        settings=resolved_settings,
        workspace_id=workspace.id,
        query=query,
        answer_mode=answer_mode,
        source_kinds=effective_source_kinds,
        filters=filters,
        top_k=top_k,
        include_binary_hits=include_binary_hits,
        collection=collection,
        retrieval_partition_ids=retrieval_partition_ids,
    )
    return _query_rag_service(
        service,
        request,
        post_filter=build_user_rag_post_filter(
            db,
            user=user,
            workspace_id=workspace.id,
            authorized_partition_ids=request.retrieval_partition_ids,
        ),
        hit_hydrator=_build_files_hit_hydrator(
            db,
            source_kinds=effective_source_kinds,
            partitioned_generation=partitioned_generation,
        ),
        grounded_answer_synthesizer=_build_grounded_answer_synthesizer(
            db=db,
            workspace=workspace,
            user=user,
            answer_mode=answer_mode,
            source=source,
            principal_kind=principal_kind,
            principal_id=principal_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        ),
    )


def query_company_rag(
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
    query_service: RagQueryService | None = None,
    source: str = "api.rag.company_query",
    principal_kind: str = "user",
    principal_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    gateway_workspace_id: str | None = None,
    partitioned_generation: bool = False,
) -> RagQueryResponse:
    resolved_settings = ensure_rag_enabled(settings)
    effective_source_kinds = list(dict.fromkeys(source_kinds))
    if not effective_source_kinds:
        return _empty_query_response(
            query=query,
            answer_mode=answer_mode,
            reason="no_company_sources_requested",
            requested_source_kinds=[],
        )
    retrieval_partition_ids = _resolve_query_partition_ids(
        db,
        source_kinds=effective_source_kinds,
        workspace_id=None,
        user_id=None,
        partitioned_generation=partitioned_generation,
    )
    if partitioned_generation and not retrieval_partition_ids:
        return _empty_query_response(
            query=query,
            answer_mode=answer_mode,
            reason="no_authorized_partitions",
            requested_source_kinds=effective_source_kinds,
        )
    service = _prepare_query_runtime(
        resolved_settings,
        use_default_runtime=settings is None,
        query_service=query_service,
    )
    request = _project_query_request(
        settings=resolved_settings,
        scope_kind=RagScopeKind.COMPANY,
        workspace_id=None,
        query=query,
        answer_mode=answer_mode,
        source_kinds=effective_source_kinds,
        filters=filters,
        top_k=top_k,
        include_binary_hits=include_binary_hits,
        retrieval_partition_ids=retrieval_partition_ids,
    )
    return _query_rag_service(
        service,
        request,
        post_filter=build_company_rag_post_filter(
            db,
            user=user,
            source_kinds=effective_source_kinds,
            authorized_partition_ids=request.retrieval_partition_ids,
        ),
        hit_hydrator=_build_files_hit_hydrator(
            db,
            source_kinds=effective_source_kinds,
            partitioned_generation=partitioned_generation,
        ),
        grounded_answer_synthesizer=_build_grounded_answer_synthesizer_for_workspace_id(
            db=db,
            gateway_workspace_id=gateway_workspace_id,
            user=user,
            answer_mode=answer_mode,
            source=source,
            principal_kind=principal_kind,
            principal_id=principal_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        ),
    )


def _resolve_query_source_kinds(
    *,
    db: Session,
    workspace: Workspace,
    user: User,
    settings: Settings,
    source_kinds: list[str],
    require_searchable_app: bool,
    allowed_unlisted_source_kinds: frozenset[str],
    required_app_ids: frozenset[str],
) -> tuple[list[str], list[str]]:
    requested_source_kinds = list(dict.fromkeys(source_kinds))
    if allowed_unlisted_source_kinds:
        enabled_app_ids = _resolve_workspace_rag_enabled_app_ids(
            db,
            workspace.id,
            require_searchable_app=require_searchable_app,
            required_app_ids=required_app_ids,
        )
        policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
        visible_sources = list_registered_workspace_rag_sources(policy, enabled_app_ids)
        allowed_source_kinds = {item["source_kind"] for item in visible_sources}
        allowed_source_kinds.update(
            _allowed_unlisted_query_source_kinds(
                policy=policy,
                requested_source_kinds=requested_source_kinds,
                allowed_unlisted_source_kinds=allowed_unlisted_source_kinds,
            )
        )
    else:
        _resolve_workspace_rag_enabled_app_ids(
            db,
            workspace.id,
            require_searchable_app=require_searchable_app,
            required_app_ids=required_app_ids,
        )
        visible_sources = list_workspace_rag_sources(
            db,
            workspace=workspace,
            user=user,
            settings=settings,
            require_searchable_app=require_searchable_app,
            required_app_ids=required_app_ids,
        )
        allowed_source_kinds = {item["source_kind"] for item in visible_sources}
    if requested_source_kinds:
        return (
            [
                source_kind
                for source_kind in requested_source_kinds
                if source_kind in allowed_source_kinds
            ],
            requested_source_kinds,
        )
    return sorted(allowed_source_kinds), requested_source_kinds


def _allowed_unlisted_query_source_kinds(
    *,
    policy: SourceAclPolicy,
    requested_source_kinds: list[str],
    allowed_unlisted_source_kinds: frozenset[str],
) -> set[str]:
    allowed: set[str] = set()
    if not allowed_unlisted_source_kinds:
        return allowed

    for source_kind in requested_source_kinds:
        if source_kind not in allowed_unlisted_source_kinds:
            continue
        resource_types = resolve_rag_resource_types_for_source_kinds([source_kind])
        if any(policy.has_accessible_source(resource_type) for resource_type in resource_types):
            allowed.add(source_kind)
    return allowed


def _prepare_query_runtime(
    settings: Settings,
    *,
    use_default_runtime: bool,
    query_service: RagQueryService | None,
    ensure_default_collection: bool = True,
) -> RagQueryService:
    try:
        providers = get_provider_bundle() if use_default_runtime else None
        service = query_service or (
            get_rag_query_service() if use_default_runtime else build_rag_query_service(settings)
        )
        if ensure_default_collection:
            ensure_default_collection_ready(
                settings,
                providers=providers,
                dense_dimensions=(
                    get_default_embedding_dimensions() if use_default_runtime else None
                ),
            )
    except Exception as error:
        raise RagUnavailableError(str(error), code="rag.runtime_unavailable") from error
    return service


def _project_query_request(
    *,
    settings: Settings,
    scope_kind: RagScopeKind = RagScopeKind.WORKSPACE,
    workspace_id: str | None,
    query: str,
    answer_mode: RagAnswerMode,
    source_kinds: list[str],
    filters: dict[str, Any],
    top_k: int,
    include_binary_hits: bool,
    collection: str | None = None,
    retrieval_partition_ids: list[str] | None = None,
) -> RagQueryRequest:
    return RagQueryRequest(
        collection=collection or resolve_default_collection_name(settings),
        scope_kind=scope_kind,
        workspace_id=workspace_id,
        retrieval_partition_ids=retrieval_partition_ids,
        query=query,
        answer_mode=answer_mode,
        source_kinds=source_kinds,
        filters=_resolve_query_filters(
            filters=filters,
            include_binary_hits=include_binary_hits,
        ),
        top_k=top_k,
        include_binary_hits=include_binary_hits,
    )


def _resolve_query_partition_ids(
    db: Session,
    *,
    source_kinds: list[str],
    workspace_id: str | None,
    user_id: str | None,
    partitioned_generation: bool,
) -> list[str] | None:
    if not partitioned_generation:
        return None
    resource_types = resolve_rag_resource_types_for_source_kinds(source_kinds)
    scope = resolve_resource_read_scope(
        db,
        resource_types=list(resource_types),
        workspace_id=workspace_id,
        user_id=user_id,
    )
    return [str(partition_id) for partition_id in flatten_read_scope(scope)]


def _build_grounded_answer_synthesizer(
    *,
    db: Session,
    workspace: Workspace,
    user: User,
    answer_mode: RagAnswerMode,
    source: str,
    principal_kind: str,
    principal_id: str | None,
    agent_run_id: str | None,
    conversation_id: str | None,
) -> LlmGroundedAnswerSynthesizer | None:
    if answer_mode != RagAnswerMode.GROUNDED_ANSWER:
        return None
    return LlmGroundedAnswerSynthesizer(
        db=db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        principal_kind=principal_kind,
        principal_id=principal_id or user.id,
        source=source,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )


def _build_grounded_answer_synthesizer_for_workspace_id(
    *,
    db: Session,
    gateway_workspace_id: str | None,
    user: User,
    answer_mode: RagAnswerMode,
    source: str,
    principal_kind: str,
    principal_id: str | None,
    agent_run_id: str | None,
    conversation_id: str | None,
) -> LlmGroundedAnswerSynthesizer | None:
    if answer_mode != RagAnswerMode.GROUNDED_ANSWER or gateway_workspace_id is None:
        return None
    return LlmGroundedAnswerSynthesizer(
        db=db,
        workspace_id=gateway_workspace_id,
        actor_user_id=user.id,
        principal_kind=principal_kind,
        principal_id=principal_id or user.id,
        source=source,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )


def resolve_ai_gateway_workspace_id(db: Session, user: User) -> str | None:
    if user.default_workspace_id:
        active_default = db.scalar(
            select(Workspace.id).where(
                Workspace.id == user.default_workspace_id,
                Workspace.active.is_(True),
            )
        )
        if active_default is not None:
            return active_default
    return db.scalar(
        select(WorkspaceUserBinding.workspace_id)
        .join(Workspace, Workspace.id == WorkspaceUserBinding.workspace_id)
        .where(
            WorkspaceUserBinding.user_id == user.id,
            Workspace.active.is_(True),
        )
        .order_by(WorkspaceUserBinding.created_at.asc())
        .limit(1)
    )


def _query_rag_service(
    service: RagQueryService,
    request: RagQueryRequest,
    *,
    post_filter: Any,
    hit_hydrator: (
        Callable[[Sequence[RagVectorSearchHit]], Sequence[RagVectorSearchHit]] | None
    ),
    grounded_answer_synthesizer: LlmGroundedAnswerSynthesizer | None,
) -> RagQueryResponse:
    try:
        query_kwargs: dict[str, Any] = {
            "post_filter": post_filter,
            "grounded_answer_synthesizer": grounded_answer_synthesizer,
        }
        if hit_hydrator is not None:
            query_kwargs["hit_hydrator"] = hit_hydrator
        return service.query(request, **query_kwargs)
    except _RAG_QUERY_PROVIDER_ERRORS as error:
        raise RagUnavailableError(str(error), code="rag.query_unavailable") from error


def _build_files_hit_hydrator(
    db: Session,
    *,
    source_kinds: Sequence[str],
    partitioned_generation: bool,
) -> Callable[[Sequence[RagVectorSearchHit]], Sequence[RagVectorSearchHit]] | None:
    if not partitioned_generation or FILES_RAG_SOURCE_KIND not in source_kinds:
        return None

    from open_work_hub_api.domains.files.rag_projection import (
        hydrate_file_rag_hits_from_source,
    )

    return lambda hits: hydrate_file_rag_hits_from_source(db, hits=hits)


def list_workspace_rag_sources(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    settings: Settings | None = None,
    require_searchable_app: bool = True,
    required_app_ids: frozenset[str] = _DEFAULT_RAG_REQUIRED_APP_IDS,
) -> list[dict[str, str]]:
    ensure_rag_enabled(settings)
    enabled_app_ids = _resolve_workspace_rag_enabled_app_ids(
        db,
        workspace.id,
        require_searchable_app=require_searchable_app,
        required_app_ids=required_app_ids,
    )
    policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
    return list_registered_workspace_rag_sources(policy, enabled_app_ids)


def enqueue_workspace_rag_reindex(
    db: Session,
    *,
    workspace: Workspace,
    settings: Settings | None = None,
    force: bool = False,
) -> dict[str, Any]:
    resolved_settings = ensure_rag_enabled(settings)
    enabled_app_ids = _resolve_workspace_rag_enabled_app_ids(db, workspace.id)
    if not force:
        _ensure_workspace_reindex_available(db, workspace=workspace)
    try:
        ensure_default_collection_ready(
            resolved_settings,
            providers=get_provider_bundle() if settings is None else None,
            dense_dimensions=get_default_embedding_dimensions() if settings is None else None,
        )
    except Exception as error:
        raise RagUnavailableError(str(error), code="rag.runtime_unavailable") from error
    resource_counts: dict[str, int] = {}
    for adapter in workspace_reindex_resource_adapters(enabled_app_ids):
        if adapter.workspace_resource_ids is None:
            continue
        resource_ids = adapter.workspace_resource_ids(db, workspace)
        resource_counts[adapter.resource_type] = _enqueue_ids(
            db,
            workspace=workspace,
            resource_type=adapter.resource_type,
            resource_ids=resource_ids,
        )
    return {
        "lane": RagSyncLane.BACKFILL.value,
        "queued_count": sum(resource_counts.values()),
        "resource_counts": resource_counts,
    }


def count_workspace_rag_reindex_resources(
    db: Session,
    *,
    workspace: Workspace,
    settings: Settings | None = None,
) -> dict[str, int]:
    ensure_rag_enabled(settings)
    enabled_app_ids = _resolve_workspace_rag_enabled_app_ids(db, workspace.id)
    resource_counts: dict[str, int] = {}
    for adapter in workspace_reindex_resource_adapters(enabled_app_ids):
        if adapter.workspace_resource_ids is None:
            continue
        resource_counts[adapter.resource_type] = sum(
            1 for _resource_id in adapter.workspace_resource_ids(db, workspace)
        )
    return resource_counts


def enqueue_company_rag_reindex(
    db: Session,
    *,
    settings: Settings | None = None,
    app_ids: set[str] | None = None,
) -> dict[str, Any]:
    resolved_settings = ensure_rag_enabled(settings)
    adapters = _enabled_company_reindex_resource_adapters(db, app_ids)
    if adapters:
        try:
            ensure_default_collection_ready(
                resolved_settings,
                providers=get_provider_bundle() if settings is None else None,
                dense_dimensions=get_default_embedding_dimensions() if settings is None else None,
            )
        except Exception as error:
            raise RagUnavailableError(str(error), code="rag.runtime_unavailable") from error

    resource_counts: dict[str, int] = {}
    for adapter in adapters:
        if adapter.company_resource_ids is None:
            continue
        resource_counts[adapter.resource_type] = _enqueue_company_ids(
            db,
            resource_type=adapter.resource_type,
            resource_ids=adapter.company_resource_ids(db),
        )
    return {
        "lane": RagSyncLane.BACKFILL.value,
        "scope_kind": RagScopeKind.COMPANY.value,
        "queued_count": sum(resource_counts.values()),
        "resource_counts": resource_counts,
    }


def count_company_rag_reindex_resources(
    db: Session,
    *,
    settings: Settings | None = None,
    app_ids: set[str] | None = None,
) -> dict[str, int]:
    ensure_rag_enabled(settings)
    resource_counts: dict[str, int] = {}
    for adapter in _enabled_company_reindex_resource_adapters(db, app_ids):
        if adapter.company_resource_ids is None:
            continue
        resource_counts[adapter.resource_type] = sum(
            1 for _resource_id in adapter.company_resource_ids(db)
        )
    return resource_counts


def _enabled_company_reindex_resource_adapters(
    db: Session,
    app_ids: set[str] | None,
):
    adapters = tuple(company_reindex_resource_adapters(app_ids))
    platform_app_ids = {
        catalog_item.app_id
        for adapter in adapters
        if (app_id := getattr(adapter, "app_id", None))
        and (catalog_item := get_workspace_app_catalog_item(app_id)) is not None
        and catalog_item.availability_scope == "platform"
    }
    if not platform_app_ids:
        return adapters
    enabled_platform_app_ids = set(resolve_platform_enabled_app_ids(db))
    return tuple(
        adapter
        for adapter in adapters
        if (
            (app_id := getattr(adapter, "app_id", None)) not in platform_app_ids
            or app_id in enabled_platform_app_ids
        )
    )


def _resolve_workspace_rag_enabled_app_ids(
    db: Session,
    workspace_id: str,
    *,
    require_searchable_app: bool = True,
    required_app_ids: frozenset[str] = _DEFAULT_RAG_REQUIRED_APP_IDS,
) -> set[str]:
    enabled_app_ids = set(resolve_workspace_runtime_enabled_app_ids(db, workspace_id))
    if required_app_ids and not required_app_ids.intersection(enabled_app_ids):
        raise RagAccessDeniedError(code="rag.access_denied_not_enabled")
    if require_searchable_app and not registered_searchable_rag_app_ids().intersection(
        enabled_app_ids
    ):
        raise RagAccessDeniedError(code="rag.access_denied_not_enabled")
    return enabled_app_ids


def _enqueue_ids(
    db: Session,
    *,
    workspace: Workspace,
    resource_type: str,
    resource_ids: Iterable[str],
) -> int:
    count = 0
    for resource_id in resource_ids:
        enqueue_rag_sync_job(
            db,
            workspace_id=workspace.id,
            resource_type=resource_type,
            resource_id=resource_id,
            lane=RagSyncLane.BACKFILL,
        )
        count += 1
    return count


def _enqueue_company_ids(
    db: Session,
    *,
    resource_type: str,
    resource_ids: Iterable[str],
) -> int:
    count = 0
    for resource_id in resource_ids:
        enqueue_rag_sync_job(
            db,
            scope_kind=RagScopeKind.COMPANY,
            workspace_id=None,
            resource_type=resource_type,
            resource_id=resource_id,
            lane=RagSyncLane.BACKFILL,
        )
        count += 1
    return count


def _empty_query_response(
    *,
    query: str,
    answer_mode: RagAnswerMode,
    reason: str,
    requested_source_kinds: list[str],
) -> RagQueryResponse:
    return RagQueryResponse(
        query=query,
        answer_mode=answer_mode,
        query_profile={
            "vector_requested_top_k": 0,
            "vector_hit_count": 0,
            "post_filtered_hit_count": 0,
            "returned_hit_count": 0,
            "rerank_applied": False,
            "rerank_degraded": False,
            "post_filter_applied": True,
            "grounded_answer_degraded": False,
            "reason": reason,
            "requested_source_kinds": requested_source_kinds,
        },
    )


def _resolve_query_filters(
    *,
    filters: dict[str, Any],
    include_binary_hits: bool,
) -> dict[str, Any]:
    effective_filters = dict(filters)
    if not include_binary_hits and "content_modality" not in effective_filters:
        effective_filters["content_modality"] = "text"
    return effective_filters


def _ensure_workspace_reindex_available(
    db: Session,
    *,
    workspace: Workspace,
) -> None:
    cutoff = _utcnow() - RAG_REINDEX_COOLDOWN
    existing = db.scalar(
        select(RagSyncJob.id)
        .where(
            RagSyncJob.workspace_id == workspace.id,
            RagSyncJob.lane == RagSyncLane.BACKFILL.value,
            RagSyncJob.created_at >= cutoff,
            RagSyncJob.status.in_(
                [
                    RagJobStatus.PENDING.value,
                    RagJobStatus.PROCESSING.value,
                    RagJobStatus.SUCCEEDED.value,
                ]
            ),
        )
        .limit(1)
    )
    if existing is not None:
        raise RagReindexCooldownError(code="rag.reindex_cooldown_recent")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
