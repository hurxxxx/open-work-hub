from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry
from open_work_hub_api.domains.ai.tool_context import current_tool_execution_context
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.rag.default_source_adapters import registered_rag_app_ids
from open_work_hub_api.domains.retrieval import application
from open_work_hub_api.domains.retrieval.contracts import (
    RetrievalAnswerMode,
    RetrievalQueryRequest,
    RetrievalStrategy,
)
from open_work_hub_api.domains.retrieval.source_catalog import (
    registered_retrieval_source_app_ids,
)


class RetrievalSearchToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
    sources: list[str] = Field(default_factory=list, max_length=20)
    source_kinds: list[str] = Field(default_factory=list, max_length=50)
    top_k: int = Field(default=8, ge=1, le=100)
    answer_mode: RetrievalAnswerMode = RetrievalAnswerMode.SEARCH_ONLY
    include_binary_hits: bool = False
    dataset_keys: list[str] = Field(default_factory=list, max_length=20)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    field_hints: list[str] = Field(default_factory=list, max_length=20)


class RetrievalListSourcesToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def retrieval_discoverable_app_ids() -> frozenset[str]:
    return registered_retrieval_source_app_ids() | registered_rag_app_ids()


def _search(
    db,
    principal,
    user: User,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    tool_context = current_tool_execution_context()
    filters: dict[str, Any] = {}
    for key in ("dataset_keys", "keywords", "field_hints"):
        values = [str(value).strip() for value in arguments.get(key) or [] if str(value).strip()]
        if values:
            filters[key] = values
    response = application.query_retrieval(
        db,
        user=user,
        request=RetrievalQueryRequest(
            query=str(arguments["query"]),
            strategy=RetrievalStrategy(arguments.get("strategy", RetrievalStrategy.HYBRID)),
            sources=list(arguments.get("sources") or []),
            source_kinds=list(arguments.get("source_kinds") or []),
            filters=filters,
            top_k=int(arguments.get("top_k", 8)),
            answer_mode=RetrievalAnswerMode(
                arguments.get("answer_mode", RetrievalAnswerMode.SEARCH_ONLY)
            ),
            include_binary_hits=bool(arguments.get("include_binary_hits", False)),
        ),
        source=tool_context.source if tool_context is not None else "ai.tool.retrieval.search",
        principal_kind=principal.kind,
        principal_id=principal.principal_id,
        agent_run_id=tool_context.agent_run_id if tool_context is not None else None,
        conversation_id=tool_context.conversation_id if tool_context is not None else None,
    )
    return response.model_dump(mode="json")


def _list_sources(
    db,
    principal,
    user: User,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    del principal, arguments
    response = application.list_retrieval_sources(
        db,
        user=user,
    )
    return response.model_dump(mode="json")


def _retrieval_enabled(principal, entitlements) -> bool:
    if principal.kind != "user" or principal.user_id is None:
        return False
    enabled = entitlements.enabled_app_ids
    return bool(
        get_settings().retrieval_unified_enabled
        and (retrieval_discoverable_app_ids() & set(enabled))
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_discoverability_predicate(
        predicate_id="retrieval.enabled",
        predicate=_retrieval_enabled,
    )
    registry.register_tool(
        name="retrieval.search",
        description=(
            "Unified retrieval entrypoint for company keyword search and RAG. "
            "Prefer this when an agent needs one managed search surface."
        ),
        owner_domain="retrieval",
        owner_app_id="retrieval-search",
        handler=_search,
        args_model=RetrievalSearchToolArgs,
        discoverability_predicate_id="retrieval.enabled",
    )
    registry.register_tool(
        name="retrieval.list_sources",
        description="List unified retrieval sources and current user availability.",
        owner_domain="retrieval",
        owner_app_id="retrieval-search",
        handler=_list_sources,
        args_model=RetrievalListSourcesToolArgs,
        discoverability_predicate_id="retrieval.enabled",
    )
