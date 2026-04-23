from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.registry import AiCapabilityRegistry
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.rag.contracts import RagAnswerMode
from aidoo_api.domains.rag.filters import RagQueryFilters


SEARCHABLE_APP_IDS = frozenset({"docs", "meeting", "pms", "planner"})


class RagQueryToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    answer_mode: RagAnswerMode = RagAnswerMode.SEARCH_ONLY
    source_kinds: list[str] = Field(default_factory=list)
    filters: RagQueryFilters = Field(default_factory=RagQueryFilters)
    top_k: int = Field(default=10, ge=1, le=100)
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
    del principal
    from aidoo_api.domains.rag import application as rag_application

    try:
        response = rag_application.query_workspace_rag(
            db,
            workspace=workspace,
            user=user,
            query=str(arguments["query"]),
            answer_mode=RagAnswerMode(arguments.get("answer_mode", RagAnswerMode.SEARCH_ONLY)),
            source_kinds=list(arguments.get("source_kinds") or []),
            filters=RagQueryFilters.model_validate(arguments.get("filters") or {}).to_flat_dict(),
            top_k=int(arguments.get("top_k", 10)),
            include_binary_hits=bool(arguments.get("include_binary_hits", False)),
        )
    except rag_application.RagUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
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
    from aidoo_api.domains.rag import application as rag_application

    try:
        sources = rag_application.list_workspace_rag_sources(
            db,
            workspace=workspace,
            user=user,
        )
    except rag_application.RagUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    return {"sources": sources}


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    if not get_settings().rag_enabled:
        return
    registry.register_discoverability_predicate(
        predicate_id="rag.enabled",
        predicate=lambda principal, workspace, entitlements: (
            "ai" in entitlements.enabled_app_ids
            and any(app_id in entitlements.enabled_app_ids for app_id in SEARCHABLE_APP_IDS)
        ),
    )
    registry.register_llm_task(
        task_kind="rag_grounded_answer",
        default_policy="local_only",
        description="Grounded answer synthesis for workspace RAG queries.",
    )
    registry.register_tool(
        name="rag.query",
        description="Search indexed workspace knowledge across docs, meetings, PMS, and planner data.",
        owner_domain="ai",
        handler=_query,
        args_model=RagQueryToolArgs,
        discoverability_predicate_id="rag.enabled",
    )
    registry.register_tool(
        name="rag.list_sources",
        description="List searchable source kinds for the current workspace.",
        owner_domain="ai",
        handler=_list_sources,
        args_model=RagListSourcesArgs,
        discoverability_predicate_id="rag.enabled",
    )
