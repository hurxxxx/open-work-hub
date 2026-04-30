from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from pydantic import ValidationError
from sqlalchemy.orm import Session

from aidoo_api.core.llm import LlmTaskContext, complete_chat
from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.internal_agent_contracts import LocalAgentResult, LocalAgentTask
from aidoo_api.domains.ai.runtime.agent_definitions import AgentDefinitionResolver
from aidoo_api.domains.ai.tool_runtime import ToolCallExecution, execute_tool_call
from aidoo_api.domains.auth.models import User, Workspace


INTERNAL_DATA_AGENT_IDS = frozenset(
    {
        "domain.docs",
        "domain.meeting",
        "domain.pms",
        "domain.planner",
        "domain.rag",
        "search.executor",
        "search.planner",
        "verifier.grounding",
        "writer.template",
    }
)
class LocalAgentRunner(Protocol):
    def run(self, task: LocalAgentTask) -> LocalAgentResult:
        """Execute a validated internal agent task and return a safe result."""


@dataclass(frozen=True, slots=True)
class LocalAgentRuntimeContext:
    enabled_app_ids: frozenset[str]
    allowed_app_ids: frozenset[str] | None = None
    available_tool_names: frozenset[str] = frozenset()
    approval_required_tool_names: frozenset[str] = frozenset()
    agent_definition_resolver: AgentDefinitionResolver = field(
        default_factory=AgentDefinitionResolver
    )


@dataclass(frozen=True, slots=True)
class StaticLocalAgentRunner:
    redacted_summary: str = "Local agent completed with redacted summary."

    def run(self, task: LocalAgentTask) -> LocalAgentResult:
        return LocalAgentResult(
            agent_id=task.agent_id,
            status="completed",
            redacted_summary=self.redacted_summary,
            coverage={"covered": [task.objective], "missing": []},
            sensitivity_labels=["internal"],
        )


@dataclass(frozen=True, slots=True)
class LocalModelAgentRunner:
    db: Session
    llm_context: LlmTaskContext
    temperature: float | None = 0.1
    max_tokens: int | None = 2048
    conversation_id: str | None = None

    def run(self, task: LocalAgentTask) -> LocalAgentResult:
        response, _decision, _config = complete_chat(
            replace(
                self.llm_context,
                source=f"{self.llm_context.source}.local_agent",
            ),
            self.db,
            messages=_local_agent_messages(task),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort="none",
            pool_hint="local",
            conversation_id=self.conversation_id,
        )
        summary = _response_content(response).strip()
        return LocalAgentResult(
            agent_id=task.agent_id,
            status="completed" if summary else "failed",
            redacted_summary=summary or "Local agent returned no usable summary.",
            coverage={"covered": [task.objective], "missing": []},
            sensitivity_labels=["internal"],
            blocked_reason=None if summary else "empty_local_summary",
        )


@dataclass(frozen=True, slots=True)
class ToolGatewayLocalAgentRunner:
    db: Session
    workspace: Workspace
    principal: CallerPrincipal
    user: User
    llm_context: LlmTaskContext
    available_tool_names: frozenset[str]
    temperature: float | None = 0.1
    max_tokens: int | None = 2048
    conversation_id: str | None = None
    agent_run_id: str | None = None

    def run(self, task: LocalAgentTask) -> LocalAgentResult:
        tool_name = _select_gateway_tool(
            task=task,
            available_tool_names=self.available_tool_names,
        )
        if tool_name is None:
            return LocalModelAgentRunner(
                db=self.db,
                llm_context=self.llm_context,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                conversation_id=self.conversation_id,
            ).run(task)

        execution = execute_tool_call(
            self.db,
            workspace=self.workspace,
            principal=self.principal,
            user=self.user,
            tool_name=tool_name,
            arguments=_gateway_tool_arguments(tool_name=tool_name, task=task),
            source="internal.local_agent",
            agent_run_id=self.agent_run_id,
            conversation_id=self.conversation_id,
            approved_call_id=task.approved_call_id,
        )
        if execution.status == "blocked":
            return LocalAgentResult(
                agent_id=task.agent_id,
                status="blocked",
                blocked_reason="approval_required",
                sensitivity_labels=["internal"],
            )
        if execution.status != "ok" or execution.response is None:
            return LocalAgentResult(
                agent_id=task.agent_id,
                status="failed",
                redacted_summary="Local agent tool execution failed.",
                blocked_reason=execution.error_message or "tool_execution_failed",
                sensitivity_labels=["internal"],
            )

        return _summarize_tool_execution(
            db=self.db,
            llm_context=self.llm_context,
            task=task,
            execution=execution,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            conversation_id=self.conversation_id,
        )


def build_local_agent_runtime_context(
    *,
    enabled_app_ids: Iterable[str],
    allowed_app_ids: Iterable[str] | None = None,
    available_tool_names: Iterable[str] = (),
    approval_required_tool_names: Iterable[str] = (),
    agent_definition_resolver: AgentDefinitionResolver | None = None,
) -> LocalAgentRuntimeContext:
    return LocalAgentRuntimeContext(
        enabled_app_ids=_normalize_string_set(enabled_app_ids),
        allowed_app_ids=(
            _normalize_string_set(allowed_app_ids) if allowed_app_ids is not None else None
        ),
        available_tool_names=_normalize_string_set(available_tool_names),
        approval_required_tool_names=_normalize_string_set(approval_required_tool_names),
        agent_definition_resolver=agent_definition_resolver or AgentDefinitionResolver(),
    )


def run_local_agent_task(
    *,
    task: LocalAgentTask,
    context: LocalAgentRuntimeContext,
    runner: LocalAgentRunner,
) -> LocalAgentResult:
    blocked_reason = validate_local_agent_task(task=task, context=context)
    if blocked_reason is not None:
        return LocalAgentResult(
            agent_id=task.agent_id,
            status="blocked",
            blocked_reason=blocked_reason,
            sensitivity_labels=["internal"],
        )

    try:
        result = runner.run(task)
    except ValidationError:
        return LocalAgentResult(
            agent_id=task.agent_id,
            status="failed",
            redacted_summary="Local agent returned an unsafe result.",
            blocked_reason="unsafe_local_result",
            sensitivity_labels=["internal"],
        )
    except Exception:  # noqa: BLE001 - external manager must receive a clear boundary failure
        return LocalAgentResult(
            agent_id=task.agent_id,
            status="failed",
            redacted_summary="Local agent execution failed.",
            blocked_reason="local_agent_failed",
            sensitivity_labels=["internal"],
        )

    if result.agent_id != task.agent_id:
        return LocalAgentResult(
            agent_id=task.agent_id,
            status="failed",
            redacted_summary="Local agent returned a mismatched result.",
            blocked_reason="agent_result_mismatch",
            sensitivity_labels=["internal"],
        )
    return result


def validate_local_agent_task(
    *,
    task: LocalAgentTask,
    context: LocalAgentRuntimeContext,
) -> str | None:
    resolved_agents = context.agent_definition_resolver.resolve(
        enabled_app_ids=context.enabled_app_ids,
        allowed_app_ids=context.allowed_app_ids,
    )
    if task.agent_id not in resolved_agents.agent_ids:
        return "agent_not_available"

    requested_tools = frozenset(task.allowed_tool_names)
    if not requested_tools:
        return None

    if not context.available_tool_names:
        return "tool_not_available"

    unavailable_tools = sorted(requested_tools - context.available_tool_names)
    if unavailable_tools:
        return "tool_not_available"

    approval_required_tools = requested_tools & context.approval_required_tool_names
    if approval_required_tools and not task.approved_call_id:
        return "approval_required"
    return None


def _normalize_string_set(values: Iterable[str]) -> frozenset[str]:
    return frozenset(str(value).strip() for value in values if str(value).strip())


def _local_agent_messages(task: LocalAgentTask) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": (
                "You are an internal local agent running inside the workspace data "
                "boundary on the configured local model profile. "
                "Use only local context and local tools made available by the server. "
                "Return a concise Korean evidence summary. Do not include raw customer "
                "names, order numbers, product codes, prices, contracts, credentials, "
                "internal URLs, or long raw document excerpts. If evidence is missing, "
                "state the gap clearly."
            ),
        },
        {
            "role": "user",
            "content": task.model_dump_json(exclude_none=True),
        },
    ]


def _tool_grounded_summary_messages(
    *,
    task: LocalAgentTask,
    execution: ToolCallExecution,
) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": (
                "You are an internal local evidence summarizer inside the workspace "
                "boundary on the configured local model profile. "
                "Summarize the provided internal tool result into a concise Korean "
                "LocalAgentResult summary. Do not include raw customer names, order "
                "numbers, product codes, prices, contracts, credentials, internal URLs, "
                "or long raw excerpts. Mention coverage and gaps in plain text."
            ),
        },
        {
            "role": "user",
            "content": (
                "Local agent task JSON:\n"
                f"{task.model_dump_json(exclude_none=True)}\n\n"
                f"Tool name: {execution.tool_name}\n"
                "Tool result preview JSON:\n"
                f"{_preview_text(_dump_json(execution.response), limit=5000)}"
            ),
        },
    ]


def _summarize_tool_execution(
    *,
    db: Session,
    llm_context: LlmTaskContext,
    task: LocalAgentTask,
    execution: ToolCallExecution,
    temperature: float | None,
    max_tokens: int | None,
    conversation_id: str | None,
) -> LocalAgentResult:
    response, _decision, _config = complete_chat(
        replace(
            llm_context,
            source=f"{llm_context.source}.local_agent.tool_summary",
        ),
        db,
        messages=_tool_grounded_summary_messages(task=task, execution=execution),
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort="none",
        pool_hint="local",
        conversation_id=conversation_id,
    )
    summary = _response_content(response).strip()
    return LocalAgentResult(
        agent_id=task.agent_id,
        status="completed" if summary else "failed",
        redacted_summary=summary or "Local agent returned no usable summary.",
        artifact_refs=_artifact_refs_from_tool_response(execution.response),
        coverage={"covered": [execution.tool_name, task.objective], "missing": []},
        sensitivity_labels=["internal"],
        blocked_reason=None if summary else "empty_local_summary",
    )


def _select_gateway_tool(
    *,
    task: LocalAgentTask,
    available_tool_names: frozenset[str],
) -> str | None:
    requested = [name for name in task.allowed_tool_names if name in available_tool_names]
    if task.tool_arguments and requested:
        return requested[0]
    for name in requested:
        if name in _READ_GATEWAY_TOOL_BUILDERS:
            return name

    preferred = _DEFAULT_TOOLS_BY_AGENT.get(task.agent_id, ())
    for name in preferred:
        if name in available_tool_names:
            return name
    return None


def _gateway_tool_arguments(*, tool_name: str, task: LocalAgentTask) -> dict[str, Any]:
    if task.tool_arguments:
        return dict(task.tool_arguments)
    builder = _READ_GATEWAY_TOOL_BUILDERS.get(tool_name)
    if builder is None:
        raise ValueError(f"unsupported local gateway tool: {tool_name}")
    return builder(task)


def _rag_query_args(task: LocalAgentTask) -> dict[str, Any]:
    source_kinds = []
    if task.agent_id == "domain.docs":
        source_kinds = ["docs"]
    elif task.agent_id == "domain.meeting":
        source_kinds = ["meeting"]
    elif task.agent_id == "domain.pms":
        source_kinds = ["pms"]
    elif task.agent_id == "domain.planner":
        source_kinds = ["planner"]
    return {
        "query": _search_query_from_objective(task.objective),
        "answer_mode": "grounded-answer",
        "source_kinds": source_kinds,
        "top_k": 5,
        "include_binary_hits": False,
    }


def _docs_list_hub_args(task: LocalAgentTask) -> dict[str, Any]:
    return {"q": _search_query_from_objective(task.objective), "page_size": 10}


def _pms_search_issues_args(task: LocalAgentTask) -> dict[str, Any]:
    return {"q": _search_query_from_objective(task.objective), "limit": 10}


def _meeting_list_args(task: LocalAgentTask) -> dict[str, Any]:
    del task
    return {"scope": "all"}


def _planner_list_args(task: LocalAgentTask) -> dict[str, Any]:
    del task
    return {}


def _search_query_from_objective(objective: str) -> str:
    tokens = re.findall(r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣_-]*", objective)
    significant: list[str] = []
    for token in tokens:
        normalized = _normalize_query_token(token)
        if not normalized or normalized in _QUERY_STOPWORDS:
            continue
        significant.append(normalized)
        if len(significant) >= 3:
            break
    return " ".join(significant) if significant else objective


def _normalize_query_token(token: str) -> str:
    normalized = token.strip().strip(".,:;!?()[]{}<>\"'")
    for suffix in ("에서", "으로", "에게", "부터", "까지", "와", "과", "을", "를", "은", "는", "이", "가", "의", "에"):
        if len(normalized) > len(suffix) + 1 and normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _artifact_refs_from_tool_response(response: dict[str, Any] | None) -> list[str]:
    if not isinstance(response, dict):
        return []
    result = response.get("result")
    if not isinstance(result, dict):
        return []
    refs: list[str] = []
    for key in ("sources", "hits", "items", "results"):
        values = result.get(key)
        if not isinstance(values, list):
            continue
        for index, item in enumerate(values[:5]):
            if isinstance(item, dict):
                value = item.get("id") or item.get("source_id") or item.get("ref")
                if value:
                    refs.append(str(value))
                    continue
            refs.append(f"{key}:{index}")
    return refs


def _response_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else ""


def _dump_json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _preview_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


_READ_GATEWAY_TOOL_BUILDERS = {
    "rag.query": _rag_query_args,
    "docs.list_hub": _docs_list_hub_args,
    "pms.search_issues": _pms_search_issues_args,
    "meeting.list_meetings": _meeting_list_args,
    "planner.list_events": _planner_list_args,
}

_QUERY_STOPWORDS = frozenset(
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

_DEFAULT_TOOLS_BY_AGENT = {
    "domain.rag": ("rag.query",),
    "search.executor": ("rag.query",),
    "domain.docs": ("rag.query", "docs.list_hub"),
    "domain.meeting": ("rag.query", "meeting.list_meetings"),
    "domain.pms": ("rag.query", "pms.search_issues"),
    "domain.planner": ("rag.query", "planner.list_events"),
}
