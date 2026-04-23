from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.tool_context import current_tool_execution_context
from aidoo_api.domains.ai.registry import AiCapabilityRegistry
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.rag.contracts import RagAnswerMode
from aidoo_api.domains.rag.filters import RagQueryFilters


SEARCHABLE_APP_IDS = frozenset({"docs", "meeting", "pms", "planner"})


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
    from aidoo_api.domains.rag import application as rag_application

    tool_context = current_tool_execution_context()
    try:
        response = rag_application.query_workspace_rag(
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
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
    except rag_application.RagAccessDeniedError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
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


_RAG_QUERY_INTENT_TERMS = (
    "검색",
    "찾",
    "근거",
    "출처",
    "정리",
    "요약",
    "보여",
    "알려",
    "확인",
    "search",
    "find",
    "lookup",
    "look up",
    "grounded",
    "citation",
    "evidence",
)

_RAG_SOURCE_HINT_TERMS = (
    "문서",
    "docs",
    "회의",
    "meeting",
    "pms",
    "이슈",
    "issue",
    "planner",
    "일정",
    "페이지",
    "page",
    "노트",
)


def should_expose_rag_tools_for_messages(messages: Sequence[Mapping[str, Any]] | None) -> bool:
    latest_user_text = _latest_user_text(messages)
    if not latest_user_text:
        return False
    lowered = latest_user_text.lower()
    if lowered.startswith("/tool "):
        return False
    has_intent_hint = any(term in lowered for term in _RAG_QUERY_INTENT_TERMS)
    has_source_hint = any(term in lowered for term in _RAG_SOURCE_HINT_TERMS)
    has_cross_source_hint = "기준으로" in lowered or "based on" in lowered or "바탕으로" in lowered
    return (has_intent_hint and has_source_hint) or (has_source_hint and has_cross_source_hint)


def _latest_user_text(messages: Sequence[Mapping[str, Any]] | None) -> str:
    if not messages:
        return ""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return " ".join(content.split())
        if isinstance(content, Sequence):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, Mapping):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            if parts:
                return " ".join(parts)
    return ""
