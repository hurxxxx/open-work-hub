from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from ai_do_api.domains.ai.internal_agent_contracts import LocalAgentTask
from ai_do_api.domains.rag.source_registry import OFFICIAL_NATIVE_DOC_SOURCE_KINDS


GatewayArgumentBuilder = Callable[[LocalAgentTask], dict[str, Any]]
_read_gateway_tool_builders: dict[str, GatewayArgumentBuilder] = {}
_default_tools_by_agent: dict[str, tuple[str, ...]] = {}
_rag_source_kinds_by_agent: dict[str, tuple[str, ...]] = {}


def register_read_gateway_tool_builder(
    tool_name: str,
    builder: GatewayArgumentBuilder,
) -> None:
    if tool_name in _read_gateway_tool_builders:
        raise ValueError(f"Read gateway tool builder already registered: {tool_name}")
    _read_gateway_tool_builders[tool_name] = builder


def register_default_gateway_tools(agent_id: str, tool_names: tuple[str, ...]) -> None:
    if agent_id in _default_tools_by_agent:
        raise ValueError(f"Default gateway tools already registered for agent: {agent_id}")
    _default_tools_by_agent[agent_id] = tool_names


def register_rag_source_kinds_for_agent(agent_id: str, source_kinds: tuple[str, ...]) -> None:
    normalized_source_kinds = tuple(dict.fromkeys(source_kinds))
    existing = _rag_source_kinds_by_agent.get(agent_id)
    if existing is not None and existing != normalized_source_kinds:
        raise ValueError(f"RAG source kinds already registered for agent: {agent_id}")
    _rag_source_kinds_by_agent[agent_id] = normalized_source_kinds


def read_gateway_tool_builders() -> Mapping[str, GatewayArgumentBuilder]:
    return MappingProxyType(_read_gateway_tool_builders)


def default_gateway_tools_by_agent() -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType(_default_tools_by_agent)


def default_gateway_tools_for_agent(agent_id: str) -> tuple[str, ...]:
    return _default_tools_by_agent.get(agent_id, ())


def rag_source_kinds_for_agent(agent_id: str) -> tuple[str, ...]:
    return _rag_source_kinds_by_agent.get(agent_id, ())


def rag_query_args(task: LocalAgentTask) -> dict[str, Any]:
    return {
        "query": search_query_from_objective(task.objective),
        "answer_mode": "grounded-answer",
        "source_kinds": list(rag_source_kinds_for_agent(task.agent_id)),
        "top_k": 5,
        "include_binary_hits": False,
    }


def retrieval_search_args(task: LocalAgentTask) -> dict[str, Any]:
    source_kinds = list(rag_source_kinds_for_agent(task.agent_id))
    arguments: dict[str, Any] = {
        "query": search_query_from_objective(task.objective),
        "strategy": "hybrid",
        "top_k": 5,
        "answer_mode": "grounded-answer",
        "include_binary_hits": False,
    }
    if source_kinds:
        arguments["sources"] = ["generic_rag"]
        arguments["source_kinds"] = source_kinds
    return arguments


def docs_list_hub_args(task: LocalAgentTask) -> dict[str, Any]:
    return {"q": search_query_from_objective(task.objective), "page_size": 10}


def pms_search_tasks_args(task: LocalAgentTask) -> dict[str, Any]:
    return {"q": search_query_from_objective(task.objective), "limit": 10}


def meeting_list_args(task: LocalAgentTask) -> dict[str, Any]:
    del task
    return {"scope": "all"}


def planner_list_args(task: LocalAgentTask) -> dict[str, Any]:
    del task
    return {}


def search_query_from_objective(objective: str) -> str:
    tokens = re.findall(r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣_-]*", objective)
    significant: list[str] = []
    for token in tokens:
        normalized = normalize_query_token(token)
        if not normalized or normalized in QUERY_STOPWORDS:
            continue
        significant.append(normalized)
        if len(significant) >= 3:
            break
    return " ".join(significant) if significant else objective


def normalize_query_token(token: str) -> str:
    normalized = token.strip().strip(".,:;!?()[]{}<>\"'")
    for suffix in (
        "에서",
        "으로",
        "에게",
        "부터",
        "까지",
        "와",
        "과",
        "을",
        "를",
        "은",
        "는",
        "이",
        "가",
        "의",
        "에",
    ):
        if len(normalized) > len(suffix) + 1 and normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


for _tool_name, _builder in {
    "retrieval.search": retrieval_search_args,
    "rag.query": rag_query_args,
    "docs.list_hub": docs_list_hub_args,
    "pms.search_tasks": pms_search_tasks_args,
    "meeting.list_meetings": meeting_list_args,
    "planner.list_events": planner_list_args,
}.items():
    register_read_gateway_tool_builder(_tool_name, _builder)

READ_GATEWAY_TOOL_BUILDERS = read_gateway_tool_builders()

for _agent_id, _source_kinds in {
    "domain.docs": tuple(sorted(OFFICIAL_NATIVE_DOC_SOURCE_KINDS)),
}.items():
    register_rag_source_kinds_for_agent(_agent_id, _source_kinds)

QUERY_STOPWORDS = frozenset(
    {
        "관련",
        "문서",
        "운영",
        "남은",
        "후속조치",
        "누락된",
        "근거",
        "요약",
        "요약해줘",
        "확인",
        "확인하고",
        "현재",
        "상태",
        "우선순위",
        "패턴",
        "실행",
        "과제",
        "일정",
        "있는지",
        "시간대",
        "공개",
        "범위",
        "관점",
        "gap",
        "Gap",
    }
)

for _agent_id, _tool_names in {
    "domain.rag": ("retrieval.search", "rag.query"),
    "search.executor": ("retrieval.search", "rag.query"),
    "domain.docs": ("docs.list_hub", "retrieval.search", "rag.query"),
    "domain.meeting": ("meeting.list_meetings",),
    "domain.pms": ("pms.search_tasks",),
    "domain.planner": ("planner.list_events",),
}.items():
    register_default_gateway_tools(_agent_id, _tool_names)

DEFAULT_TOOLS_BY_AGENT = default_gateway_tools_by_agent()


__all__ = [
    "DEFAULT_TOOLS_BY_AGENT",
    "GatewayArgumentBuilder",
    "QUERY_STOPWORDS",
    "READ_GATEWAY_TOOL_BUILDERS",
    "default_gateway_tools_by_agent",
    "default_gateway_tools_for_agent",
    "docs_list_hub_args",
    "meeting_list_args",
    "normalize_query_token",
    "planner_list_args",
    "pms_search_tasks_args",
    "rag_query_args",
    "rag_source_kinds_for_agent",
    "read_gateway_tool_builders",
    "register_default_gateway_tools",
    "register_rag_source_kinds_for_agent",
    "register_read_gateway_tool_builder",
    "retrieval_search_args",
    "search_query_from_objective",
]
