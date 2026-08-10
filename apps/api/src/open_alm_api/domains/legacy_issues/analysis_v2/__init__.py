"""Greenfield analysis contracts for the Legacy Issues SQL/RAG graph.

The package is intentionally independent from the legacy query-family compiler.
Its public surface is safe to use from a LangGraph/LangChain orchestration layer;
database and retrieval access remain behind server-bound dependency injection.
"""

from open_alm_api.domains.legacy_issues.analysis_v2.agent import (
    AiDoChatModel,
    AnalysisAgentResult,
    AnalysisToolCallRecord,
    build_sql_agent,
    run_analysis_tools,
)
from open_alm_api.domains.legacy_issues.analysis_v2.composition import (
    AnalysisCompositionDependencies,
    AnalysisRunContext,
    AnalysisRuntimeResolver,
    AnalysisToolsetComposition,
    build_analysis_toolset,
    compose_analysis_toolset,
    default_inference_gateway_embedding_client,
    default_pgvector_config,
)
from open_alm_api.domains.legacy_issues.analysis_v2.contracts import (
    AnalysisRoute,
    AnalysisRouteDecision,
    FallbackReason,
    QueryResult,
    RecipeInvocation,
    RecipeReference,
)
from open_alm_api.domains.legacy_issues.analysis_v2.execution import (
    AnalysisSqlScope,
    SafeAnalysisQueryService,
    SafeQueryLimits,
    SqlAlchemyReadOnlyGateway,
    postgres_scope_binder,
)
from open_alm_api.domains.legacy_issues.analysis_v2.recipes import (
    RecipeCatalog,
    default_recipe_catalog,
)
from open_alm_api.domains.legacy_issues.analysis_v2.retrieval import (
    AuthorizedRetriever,
    LlamaIndexRetrieverAdapter,
)
from open_alm_api.domains.legacy_issues.analysis_v2.sql_policy import (
    SafeSqlPolicy,
    SafeSqlPolicyError,
)
from open_alm_api.domains.legacy_issues.analysis_v2.tools import (
    AnalysisToolset,
    build_langchain_tools,
)
from open_alm_api.domains.legacy_issues.analysis_v2.vector_index import (
    PGVECTOR_PHYSICAL_TABLE,
    GenerationIndexNode,
    GenerationQueryScope,
    PGVectorAuthorizedRetriever,
    PGVectorGenerationIndex,
    PGVectorStoreConfig,
    build_legacy_source_retriever,
    build_pgvector_store,
)
from open_alm_api.domains.legacy_issues.analysis_v2.views import (
    ANALYSIS_VIEW_SCHEMA,
    ANALYSIS_VIEW_CONTRACTS,
    CHECKLIST_ITEMS_VIEW_V1,
    CHECKLISTS_VIEW_V1,
    ISSUE_RECORDS_VIEW_V1,
)

__all__ = [
    "ANALYSIS_VIEW_CONTRACTS",
    "ANALYSIS_VIEW_SCHEMA",
    "CHECKLIST_ITEMS_VIEW_V1",
    "CHECKLISTS_VIEW_V1",
    "ISSUE_RECORDS_VIEW_V1",
    "AiDoChatModel",
    "AnalysisAgentResult",
    "AnalysisCompositionDependencies",
    "AnalysisRoute",
    "AnalysisRouteDecision",
    "AnalysisRunContext",
    "AnalysisRuntimeResolver",
    "AnalysisSqlScope",
    "AnalysisToolCallRecord",
    "AnalysisToolsetComposition",
    "AnalysisToolset",
    "AuthorizedRetriever",
    "FallbackReason",
    "GenerationIndexNode",
    "GenerationQueryScope",
    "LlamaIndexRetrieverAdapter",
    "PGVECTOR_PHYSICAL_TABLE",
    "PGVectorAuthorizedRetriever",
    "PGVectorGenerationIndex",
    "PGVectorStoreConfig",
    "QueryResult",
    "RecipeCatalog",
    "RecipeInvocation",
    "RecipeReference",
    "SafeAnalysisQueryService",
    "SafeQueryLimits",
    "SafeSqlPolicy",
    "SafeSqlPolicyError",
    "SqlAlchemyReadOnlyGateway",
    "build_legacy_source_retriever",
    "build_analysis_toolset",
    "build_langchain_tools",
    "build_pgvector_store",
    "build_sql_agent",
    "compose_analysis_toolset",
    "default_inference_gateway_embedding_client",
    "default_pgvector_config",
    "default_recipe_catalog",
    "postgres_scope_binder",
    "run_analysis_tools",
]
