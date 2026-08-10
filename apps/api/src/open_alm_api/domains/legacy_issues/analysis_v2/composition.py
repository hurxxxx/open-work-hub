from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.orm import Session

from open_alm_api.core.settings import get_settings
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.legacy_issues.analysis_v2.execution import (
    AnalysisSqlScope,
    SafeAnalysisQueryService,
    SqlAlchemyReadOnlyGateway,
    postgres_scope_binder,
)
from open_alm_api.domains.legacy_issues.analysis_v2.native_evidence import (
    build_native_legacy_issue_evidence_retriever,
)
from open_alm_api.domains.legacy_issues.analysis_v2.recipes import (
    RecipeCatalog,
    default_recipe_catalog,
)
from open_alm_api.domains.legacy_issues.analysis_v2.retrieval import (
    AuthorizedRetriever,
    LlamaIndexRetrieverAdapter,
)
from open_alm_api.domains.legacy_issues.analysis_v2.tools import AnalysisToolset
from open_alm_api.domains.legacy_issues.analysis_v2.vector_index import (
    FinalAclHydrator,
    GenerationQueryScope,
    InferenceGatewayEmbeddingClient,
    PGVectorStoreConfig,
    VectorStoreProtocol,
    build_legacy_source_retriever,
    build_pgvector_store,
)
from open_alm_api.domains.retrieval.partitioning import (
    RetrievalReadScope,
    flatten_read_scope,
    resolve_read_scope,
)
from open_alm_api.domains.source_access import SourceAclPolicy


AnalysisRetrieverKind = Literal["analysis_metadata", "legacy_evidence"]


class AnalysisRunContext(Protocol):
    """Minimum durable-run identity required by the worker composition root."""

    run_id: str
    workspace_id: str
    requested_by_user_id: str


class AnalysisRuntimeResolver(Protocol):
    """Domain-owned resolvers; all scopes are derived server-side, never by the LLM."""

    def resolve_source_namespaces(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run: AnalysisRunContext,
        kind: AnalysisRetrieverKind,
    ) -> tuple[str, ...]: ...

    def resolve_sql_scope(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run: AnalysisRunContext,
        retrieval_scope: RetrievalReadScope,
    ) -> AnalysisSqlScope: ...

    def resolve_generation_scope(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run: AnalysisRunContext,
        kind: AnalysisRetrieverKind,
        retrieval_scope: RetrievalReadScope,
    ) -> GenerationQueryScope: ...

    def resolve_final_acl_hydrator(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run: AnalysisRunContext,
        kind: AnalysisRetrieverKind,
        acl_policy: SourceAclPolicy,
        generation_scope: GenerationQueryScope,
    ) -> FinalAclHydrator: ...

    def resolve_embedding_client(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run: AnalysisRunContext,
    ) -> InferenceGatewayEmbeddingClient: ...

    def resolve_pgvector_config(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run: AnalysisRunContext,
    ) -> PGVectorStoreConfig: ...


ReadScopeResolver = Callable[..., RetrievalReadScope]
AclPolicyFactory = Callable[[Session, Workspace, User], SourceAclPolicy]
VectorStoreFactory = Callable[[PGVectorStoreConfig], VectorStoreProtocol]
EvidenceRetrieverFactory = Callable[..., AuthorizedRetriever]


@dataclass(frozen=True, slots=True)
class AnalysisCompositionDependencies:
    resolver: AnalysisRuntimeResolver
    engine: Engine | None = None
    vector_store: VectorStoreProtocol | None = None
    catalog: RecipeCatalog | None = None
    read_scope_resolver: ReadScopeResolver = resolve_read_scope
    acl_policy_factory: AclPolicyFactory = (
        lambda db, workspace, user: SourceAclPolicy.for_workspace(
            db,
            workspace=workspace,
            user=user,
        )
    )
    vector_store_factory: VectorStoreFactory = build_pgvector_store
    evidence_retriever_factory: EvidenceRetrieverFactory = (
        build_native_legacy_issue_evidence_retriever
    )


@dataclass(frozen=True, slots=True)
class AnalysisToolsetComposition:
    """Inspectable worker composition without exposing secrets to the agent."""

    toolset: AnalysisToolset
    sql_scope: AnalysisSqlScope
    metadata_scope: GenerationQueryScope
    metadata_read_scope: RetrievalReadScope
    evidence_read_scope: RetrievalReadScope
    embed_dim: int


def compose_analysis_toolset(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    run: AnalysisRunContext,
    dependencies: AnalysisCompositionDependencies,
) -> AnalysisToolsetComposition:
    """Compose the real SQL/RAG tools from an authenticated durable worker run."""

    _validate_run_identity(workspace=workspace, user=user, run=run)
    resolver = dependencies.resolver
    metadata_read_scope = _resolve_common_scope(
        db,
        workspace=workspace,
        user=user,
        run=run,
        kind="analysis_metadata",
        resolver=resolver,
        read_scope_resolver=dependencies.read_scope_resolver,
    )
    evidence_read_scope = _resolve_common_scope(
        db,
        workspace=workspace,
        user=user,
        run=run,
        kind="legacy_evidence",
        resolver=resolver,
        read_scope_resolver=dependencies.read_scope_resolver,
    )
    sql_scope = resolver.resolve_sql_scope(
        db,
        workspace=workspace,
        user=user,
        run=run,
        retrieval_scope=evidence_read_scope,
    )
    _validate_sql_scope(
        sql_scope,
        workspace=workspace,
        read_scope=evidence_read_scope,
    )
    metadata_scope = resolver.resolve_generation_scope(
        db,
        workspace=workspace,
        user=user,
        run=run,
        kind="analysis_metadata",
        retrieval_scope=metadata_read_scope,
    )
    _validate_generation_scope(
        metadata_scope,
        workspace=workspace,
        read_scope=metadata_read_scope,
    )

    embedding_client = resolver.resolve_embedding_client(
        db,
        workspace=workspace,
        user=user,
        run=run,
    )
    vector_config = resolver.resolve_pgvector_config(
        db,
        workspace=workspace,
        user=user,
        run=run,
    )
    vector_store = dependencies.vector_store or dependencies.vector_store_factory(
        vector_config
    )
    acl_policy = dependencies.acl_policy_factory(db, workspace, user)
    metadata_hydrator = resolver.resolve_final_acl_hydrator(
        db,
        workspace=workspace,
        user=user,
        run=run,
        kind="analysis_metadata",
        acl_policy=acl_policy,
        generation_scope=metadata_scope,
    )

    metadata_retriever = build_legacy_source_retriever(
        vector_store=vector_store,
        embedding_client=embedding_client,
        scope=metadata_scope,
        embed_dim=vector_config.embed_dim,
        final_acl_hydrator=metadata_hydrator,
    )
    evidence_retriever = dependencies.evidence_retriever_factory(
        db=db,
        workspace=workspace,
        acl_policy=acl_policy,
        sql_scope=sql_scope,
        read_scope=evidence_read_scope,
    )
    engine = dependencies.engine or _session_engine(db)
    query_service = SafeAnalysisQueryService(
        gateway=SqlAlchemyReadOnlyGateway(
            engine=engine,
            scope_binder=postgres_scope_binder(sql_scope),
        ),
        scope=sql_scope,
    )
    toolset = AnalysisToolset(
        catalog=dependencies.catalog or default_recipe_catalog(),
        query_service=query_service,
        metadata_retriever=LlamaIndexRetrieverAdapter(
            backend=metadata_retriever,
            kind="analysis_metadata",
        ),
        evidence_retriever=LlamaIndexRetrieverAdapter(
            backend=evidence_retriever,
            kind="legacy_evidence",
        ),
    )
    return AnalysisToolsetComposition(
        toolset=toolset,
        sql_scope=sql_scope,
        metadata_scope=metadata_scope,
        metadata_read_scope=metadata_read_scope,
        evidence_read_scope=evidence_read_scope,
        embed_dim=vector_config.embed_dim,
    )


def build_analysis_toolset(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    run: AnalysisRunContext,
    dependencies: AnalysisCompositionDependencies,
) -> AnalysisToolset:
    """Worker-facing convenience facade."""

    return compose_analysis_toolset(
        db,
        workspace=workspace,
        user=user,
        run=run,
        dependencies=dependencies,
    ).toolset


def default_inference_gateway_embedding_client() -> InferenceGatewayEmbeddingClient:
    """Resolve Open ALM's registered embedding client; vector code rejects other providers."""

    from open_alm_api.domains.rag.runtime import get_provider_bundle

    return cast(InferenceGatewayEmbeddingClient, get_provider_bundle().embedding)


def default_pgvector_config(*, embed_dim: int) -> PGVectorStoreConfig:
    """Build sync/async PG URLs from the shared database setting without logging them."""

    url = make_url(get_settings().postgres_dsn)
    if url.get_backend_name() != "postgresql":
        raise ValueError("analysis_v2 PGVector requires PostgreSQL")
    sync_url = url.set(drivername="postgresql+psycopg")
    async_url = url.set(drivername="postgresql+asyncpg")
    return PGVectorStoreConfig(
        connection_string=sync_url.render_as_string(hide_password=False),
        async_connection_string=async_url.render_as_string(hide_password=False),
        embed_dim=embed_dim,
    )


def _resolve_common_scope(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    run: AnalysisRunContext,
    kind: AnalysisRetrieverKind,
    resolver: AnalysisRuntimeResolver,
    read_scope_resolver: ReadScopeResolver,
) -> RetrievalReadScope:
    source_namespaces = resolver.resolve_source_namespaces(
        db,
        workspace=workspace,
        user=user,
        run=run,
        kind=kind,
    )
    if not source_namespaces:
        raise ValueError(f"{kind} requires at least one Retrieval source namespace")
    return read_scope_resolver(
        db,
        source_namespaces=source_namespaces,
        workspace_id=workspace.id,
        user_id=user.id,
    )


def _validate_run_identity(
    *,
    workspace: Workspace,
    user: User,
    run: AnalysisRunContext,
) -> None:
    if str(run.workspace_id) != str(workspace.id):
        raise ValueError("analysis run/workspace identity mismatch")
    if str(run.requested_by_user_id) != str(user.id):
        raise ValueError("analysis run/user identity mismatch")
    if not str(run.run_id).strip():
        raise ValueError("analysis run id is required")


def _validate_sql_scope(
    scope: AnalysisSqlScope,
    *,
    workspace: Workspace,
    read_scope: RetrievalReadScope,
) -> None:
    if scope.workspace_id != workspace.id:
        raise ValueError("analysis SQL scope escaped its workspace")
    allowed = {str(value) for value in flatten_read_scope(read_scope)}
    if not set(scope.partition_ids).issubset(allowed):
        raise ValueError("analysis SQL scope contains unauthorized partitions")


def _validate_generation_scope(
    scope: GenerationQueryScope,
    *,
    workspace: Workspace,
    read_scope: RetrievalReadScope,
) -> None:
    if scope.workspace_id != workspace.id:
        raise ValueError("analysis vector scope escaped its workspace")
    allowed = {str(value) for value in flatten_read_scope(read_scope)}
    if not set(scope.partition_ids).issubset(allowed):
        raise ValueError("analysis vector scope contains unauthorized partitions")


def _session_engine(db: Session) -> Engine:
    bind = db.get_bind()
    if isinstance(bind, Engine):
        return bind
    if isinstance(bind, Connection):
        return bind.engine
    raise TypeError("analysis_v2 requires a SQLAlchemy Engine-bound Session")


__all__ = [
    "AnalysisCompositionDependencies",
    "AnalysisRetrieverKind",
    "AnalysisRunContext",
    "AnalysisRuntimeResolver",
    "AnalysisToolsetComposition",
    "build_analysis_toolset",
    "compose_analysis_toolset",
    "default_inference_gateway_embedding_client",
    "default_pgvector_config",
]
