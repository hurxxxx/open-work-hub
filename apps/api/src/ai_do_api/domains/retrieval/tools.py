from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.ai.registry import AiCapabilityRegistry
from ai_do_api.domains.ai.tool_context import current_tool_execution_context
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.conversations.app_catalog import CHATBOT_WORKSPACE_APP
from ai_do_api.domains.rag.default_source_adapters import registered_rag_app_ids
from ai_do_api.domains.retrieval import application
from ai_do_api.domains.retrieval.contracts import (
    RetrievalAnswerMode,
    RetrievalQueryRequest,
    RetrievalStrategy,
)
from ai_do_api.domains.retrieval.source_catalog import (
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
    return (
        frozenset({CHATBOT_WORKSPACE_APP.app_id})
        | registered_retrieval_source_app_ids()
        | registered_rag_app_ids()
    )


def _search(
    db,
    workspace: Workspace,
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
        workspace=workspace,
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
    workspace: Workspace,
    principal,
    user: User,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    del principal, arguments
    response = application.list_retrieval_sources(
        db,
        workspace=workspace,
        user=user,
    )
    return response.model_dump(mode="json")


def _retrieval_enabled(_principal, _workspace, entitlements) -> bool:
    enabled = entitlements.effective_enabled_app_ids
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
            "Unified retrieval entrypoint for workspace keyword search, workspace RAG, "
            "company Q&A RAG, and legacy issue evidence search. Prefer this when an "
            "agent needs one managed search surface."
        ),
        owner_domain="chatbot",
        handler=_search,
        args_model=RetrievalSearchToolArgs,
        discoverability_predicate_id="retrieval.enabled",
    )
    registry.register_tool(
        name="retrieval.list_sources",
        description="List unified retrieval sources and current workspace availability.",
        owner_domain="chatbot",
        handler=_list_sources,
        args_model=RetrievalListSourcesToolArgs,
        discoverability_predicate_id="retrieval.enabled",
    )
