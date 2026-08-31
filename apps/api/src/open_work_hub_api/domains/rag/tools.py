from __future__ import annotations

from typing import Any

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.tool_context import current_tool_execution_context
from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.rag.contracts import RagAnswerMode
from open_work_hub_api.domains.rag.filters import RagQueryFilters
from open_work_hub_api.domains.rag.default_source_adapters import (
    ensure_rag_source_adapters_registered,
    registered_searchable_rag_app_ids,
)


class RagQueryToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    answer_mode: RagAnswerMode = RagAnswerMode.GROUNDED_ANSWER
    source_kinds: list[str] = Field(default_factory=list)
    filters: RagQueryFilters = Field(default_factory=RagQueryFilters)
    top_k: int = Field(default=8, ge=1, le=100)
    include_binary_hits: bool = False


class RagListSourcesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _query(
    db,
    workspace: Workspace,
    principal,
    user: User,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    from open_work_hub_api.domains.rag import application as rag_application
    from open_work_hub_api.domains.retrieval import application as retrieval_application

    tool_context = current_tool_execution_context()
    try:
        response = retrieval_application.query_workspace_rag_response(
            db,
            workspace=workspace,
            user=user,
            query=str(arguments["query"]),
            answer_mode=RagAnswerMode(arguments.get("answer_mode", RagAnswerMode.SEARCH_ONLY)),
            source_kinds=list(arguments.get("source_kinds") or []),
            filters=RagQueryFilters.model_validate(arguments.get("filters") or {}).to_flat_dict(),
            top_k=int(arguments.get("top_k", 8)),
            include_binary_hits=bool(arguments.get("include_binary_hits", False)),
            source=tool_context.source if tool_context is not None else "ai.tool.rag.query",
            principal_kind=principal.kind,
            principal_id=principal.principal_id,
            agent_run_id=tool_context.agent_run_id if tool_context is not None else None,
            conversation_id=tool_context.conversation_id if tool_context is not None else None,
        )
    except rag_application.RagAccessDeniedError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.access_denied")
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=code,
            **params,
        ) from error
    except rag_application.RagUnavailableError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.unavailable")
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=code,
            **params,
        ) from error
    return response.model_dump(mode="json")


def _list_sources(
    db,
    workspace: Workspace,
    principal,
    user: User,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    del principal, arguments
    from open_work_hub_api.domains.rag import application as rag_application
    from open_work_hub_api.domains.retrieval import application as retrieval_application

    try:
        sources = retrieval_application.list_workspace_rag_sources_response(
            db,
            workspace=workspace,
            user=user,
        )
    except rag_application.RagAccessDeniedError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.access_denied")
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=code,
            **params,
        ) from error
    except rag_application.RagUnavailableError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.unavailable")
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=code,
            **params,
        ) from error
    return {"sources": sources}


def _rag_enabled(_principal, _workspace, entitlements) -> bool:
    ensure_rag_source_adapters_registered()
    return bool(
        get_settings().rag_enabled
        and registered_searchable_rag_app_ids().intersection(entitlements.enabled_app_ids)
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_discoverability_predicate(
        predicate_id="rag.enabled",
        predicate=_rag_enabled,
    )
    registry.register_llm_task(
        task_kind="rag_grounded_answer",
        default_policy="local_only",
        description="Grounded answer synthesis for workspace RAG queries.",
        app_ids=("retrieval-search",),
    )
    registry.register_tool(
        name="rag.query",
        description=(
            "Search workspace-readable official Docs sources when the user asks for "
            "internal document or knowledge evidence. "
            "Results are limited by the current workspace, app enablement, and ACL."
        ),
        owner_domain="rag",
        workspace_app_id="retrieval-search",
        handler=_query,
        args_model=RagQueryToolArgs,
        discoverability_predicate_id="rag.enabled",
    )
    registry.register_tool(
        name="rag.list_sources",
        description=(
            "List source kinds the current user can search in the current workspace. "
            "Use this before RAG search when the user asks what internal document "
            "sources are available."
        ),
        owner_domain="rag",
        workspace_app_id="retrieval-search",
        handler=_list_sources,
        args_model=RagListSourcesArgs,
        discoverability_predicate_id="rag.enabled",
    )
