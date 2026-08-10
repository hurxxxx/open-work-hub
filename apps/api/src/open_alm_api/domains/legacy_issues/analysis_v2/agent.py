from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from open_alm_api.domains.ai.gateway import (
    AiGatewayContextPack,
    LlmWorkloadContext,
    execute_llm,
)
from open_alm_api.domains.legacy_issues.analysis_v2.tools import (
    AnalysisToolset,
    build_langchain_tools,
)


LEGACY_ISSUES_SQL_AGENT_WORKLOAD_ID = "legacy_issues.sql_agent"
MAX_AGENT_STEPS = 8
MAX_TOOL_RESULT_PROMPT_CHARS = 40_000
SQL_AGENT_SYSTEM_PROMPT = """\
You analyze legacy vehicle issues and vehicle checklists with authorized tools.
Search analysis metadata when the available fields or recipe is unclear.
Prefer a versioned recipe; use safe SQL only for a genuine recipe gap and explain it.
Use semantic evidence for examples and qualitative context, never as an exact count.
Treat module keys as a closed server-declared enum. A component, part, symptom, or
user synonym is not a module key. Do not add a module filter unless the user names
one of the declared module keys explicitly.
The query_text recipe filter is one literal contiguous substring. Never pass the
whole natural-language question or a concatenation of alternatives to query_text;
use semantic evidence when concept matching or synonyms are needed.
Base every number and claim on tool results. State uncertainty or missing data plainly.
Return a concise answer for the parent report workflow after gathering enough evidence.
"""


logger = logging.getLogger(__name__)


class _ModelAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{2,79}$")
    arguments: dict[str, Any] | None = None
    final: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def _exactly_one_action(self) -> _ModelAction:
        if self.tool is not None:
            if self.arguments is None or self.final is not None:
                raise ValueError("tool action requires only arguments")
        elif self.final is None or self.arguments is not None:
            raise ValueError("action must contain tool+arguments or final")
        return self


class AiDoModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = ""
    tool_calls: tuple[dict[str, Any], ...] = ()


class AnalysisToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    step: int = Field(ge=1)
    tool: str
    arguments: dict[str, Any]
    status: Literal["succeeded", "failed"]
    output: dict[str, Any] | None = None
    error_code: str | None = None
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_status(self) -> AnalysisToolCallRecord:
        if self.status == "succeeded":
            if self.output is None or self.error_code is not None:
                raise ValueError("successful tool record requires only output")
        elif self.error_code is None or self.output is not None:
            raise ValueError("failed tool record requires only error_code")
        return self


class AnalysisAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["completed", "max_steps", "model_error"]
    final_text: str
    transcript: tuple[AnalysisToolCallRecord, ...]
    tool_results: tuple[dict[str, Any], ...]
    steps: int = Field(ge=0, le=MAX_AGENT_STEPS)


CompletionExecutor = Callable[..., Any]


class AiDoChatModel:
    """LangChain-facing model Adapter that keeps all calls on execute_llm.

    Open ALM's provider-neutral completion currently exposes text only. bind_tools
    therefore supplies a compact JSON action schema and this Adapter synthesizes
    LangChain-style tool_calls from a strictly parsed completion object.
    """

    def __init__(
        self,
        *,
        db: Session,
        context: LlmWorkloadContext,
        workload_id: str = LEGACY_ISSUES_SQL_AGENT_WORKLOAD_ID,
        completion_executor: CompletionExecutor = execute_llm,
        agent_run_id: str | None = None,
        conversation_id: str | None = None,
        action_schemas: tuple[dict[str, Any], ...] = (),
    ) -> None:
        if workload_id != LEGACY_ISSUES_SQL_AGENT_WORKLOAD_ID:
            raise ValueError("analysis_v2 SQL agent workload id is fixed")
        self._db = db
        self._context = context
        self._workload_id = workload_id
        self._execute = completion_executor
        self._agent_run_id = agent_run_id
        self._conversation_id = conversation_id
        self._action_schemas = action_schemas

    def bind_tools(
        self,
        tools: Sequence[Any],
        **_kwargs: Any,
    ) -> AiDoChatModel:
        return replace(
            _as_dataclass(self),
            action_schemas=tuple(_compact_tool_schema(tool) for tool in tools),
        ).to_model()

    @property
    def action_schemas(self) -> tuple[dict[str, Any], ...]:
        return self._action_schemas

    def invoke(self, messages: Sequence[Any]) -> Any:
        normalized_messages = _normalize_messages(messages)
        prompt_messages = _compose_prompt_messages(
            action_schemas=self._action_schemas,
            normalized_messages=normalized_messages,
        )
        result = self._execute(
            self._workload_id,
            self._context,
            self._db,
            messages=prompt_messages,
            context_pack=AiGatewayContextPack(
                messages=prompt_messages,
                context_strategy="legacy_issues_sql_agent_tools",
                source_kinds=("legacy_issues", "analysis_metadata"),
                sensitivity_labels=("internal",),
                content_origin="internal_context",
            ),
            temperature=0,
            max_tokens=2_000,
            reasoning_effort="none",
            agent_run_id=self._agent_run_id,
            conversation_id=self._conversation_id,
        )
        action = _parse_action(result.completion.text)
        message = _message_from_action(action)
        return _as_langchain_message(message)

    def as_langchain_chat_model(self) -> Any:
        """Return a native BaseChatModel for LangGraph/LangChain composition."""

        try:
            from langchain_core.language_models.chat_models import BaseChatModel
            from langchain_core.messages import AIMessage
            from langchain_core.outputs import ChatGeneration, ChatResult
        except ImportError as exc:
            raise RuntimeError("langchain-core is required for analysis_v2 agent") from exc

        adapter = self

        class _NativeAiDoChatModel(BaseChatModel):
            @property
            def _llm_type(self) -> str:
                return "open-alm-execute-llm"

            def _generate(
                self,
                messages: list[Any],
                stop: list[str] | None = None,
                run_manager: Any | None = None,
                **kwargs: Any,
            ) -> ChatResult:
                del stop, run_manager, kwargs
                message = adapter.invoke(messages)
                if not isinstance(message, AIMessage):
                    message = AIMessage(
                        content=message.content,
                        tool_calls=list(message.tool_calls),
                    )
                return ChatResult(generations=[ChatGeneration(message=message)])

            def bind_tools(
                self,
                tools: Sequence[Any],
                *,
                tool_choice: str | None = None,
                **kwargs: Any,
            ) -> Any:
                del tool_choice, kwargs
                return adapter.bind_tools(tools).as_langchain_chat_model()

        return _NativeAiDoChatModel()


@dataclass(frozen=True, slots=True)
class AnalysisSqlAgent:
    """Thin facade around LangChain's compiled agent graph."""

    graph: Any


def build_sql_agent(
    *,
    model: AiDoChatModel,
    toolset: AnalysisToolset,
) -> AnalysisSqlAgent:
    """Build the native LangChain SQL/RAG agent used by a parent graph node."""

    try:
        from langchain.agents import create_agent
    except ImportError as exc:
        raise RuntimeError("langchain is required for analysis_v2 agent") from exc
    graph = create_agent(
        model.as_langchain_chat_model(),
        build_langchain_tools(toolset),
        system_prompt=SQL_AGENT_SYSTEM_PROMPT,
        name="legacy_issues_sql_agent",
    )
    return AnalysisSqlAgent(graph=graph)


def run_analysis_tools(
    agent: AnalysisSqlAgent,
    *,
    messages: Sequence[Any],
    max_steps: int = MAX_AGENT_STEPS,
    graph_run_id: str | None = None,
) -> AnalysisAgentResult:
    if max_steps < 1 or max_steps > MAX_AGENT_STEPS:
        raise ValueError(f"max_steps must be between 1 and {MAX_AGENT_STEPS}")
    input_messages = _as_langchain_messages(messages)
    output_messages: tuple[Any, ...] = tuple(input_messages)
    try:
        for state in agent.graph.stream(
            {"messages": input_messages},
            config={"recursion_limit": (max_steps * 2) + 2},
            stream_mode="values",
        ):
            candidate = tuple(state.get("messages") or ())
            if candidate:
                output_messages = candidate
    except Exception as exc:
        try:
            from langgraph.errors import GraphRecursionError
        except ImportError:
            GraphRecursionError = ()  # type: ignore[assignment,misc]
        status: Literal["max_steps", "model_error"] = (
            "max_steps" if isinstance(exc, GraphRecursionError) else "model_error"
        )
        partial = _result_from_langchain_messages(
            output_messages[len(input_messages) :],
            max_steps=max_steps,
        )
        logger.warning(
            "Legacy issue analysis agent stopped before final action",
            extra={
                "graph_run_id": graph_run_id,
                "analysis_agent_status": status,
                "error_type": type(exc).__name__,
                "max_steps": max_steps,
                "completed_tool_calls": len(partial.transcript),
            },
        )
        return partial.model_copy(
            update={
                "status": status,
                "final_text": "",
            }
        )
    return _result_from_langchain_messages(
        output_messages[len(input_messages) :],
        max_steps=max_steps,
    )


@dataclass(frozen=True, slots=True)
class _ChatModelState:
    db: Session
    context: LlmWorkloadContext
    workload_id: str
    completion_executor: CompletionExecutor
    agent_run_id: str | None
    conversation_id: str | None
    action_schemas: tuple[dict[str, Any], ...]

    def to_model(self) -> AiDoChatModel:
        return AiDoChatModel(
            db=self.db,
            context=self.context,
            workload_id=self.workload_id,
            completion_executor=self.completion_executor,
            agent_run_id=self.agent_run_id,
            conversation_id=self.conversation_id,
            action_schemas=self.action_schemas,
        )


def _as_dataclass(model: AiDoChatModel) -> _ChatModelState:
    return _ChatModelState(
        db=model._db,
        context=model._context,
        workload_id=model._workload_id,
        completion_executor=model._execute,
        agent_run_id=model._agent_run_id,
        conversation_id=model._conversation_id,
        action_schemas=model._action_schemas,
    )


def _compact_tool_schema(tool: Any) -> dict[str, Any]:
    if isinstance(tool, dict):
        name = str(tool.get("name") or "")
        description = str(tool.get("description") or "")
        schema = tool.get("input_schema") or tool.get("args_schema") or {}
    else:
        name = str(getattr(tool, "name", "") or "")
        description = str(getattr(tool, "description", "") or "")
        args_schema = getattr(tool, "args_schema", None)
        schema = (
            args_schema.model_json_schema()
            if args_schema is not None and hasattr(args_schema, "model_json_schema")
            else getattr(tool, "args", {})
        )
    if not name:
        raise ValueError("bound tool requires a name")
    properties = dict(schema.get("properties") or {}) if isinstance(schema, dict) else {}
    definitions = dict(schema.get("$defs") or {}) if isinstance(schema, dict) else {}
    compact_properties = {
        key: _compact_property(dict(spec), definitions=definitions)
        for key, spec in properties.items()
        if isinstance(spec, dict)
    }
    return {
        "name": name,
        "description": description[:300],
        "parameters": {
            "type": "object",
            "properties": compact_properties,
            "required": list(schema.get("required") or ()) if isinstance(schema, dict) else [],
            "additionalProperties": False,
        },
    }


def _compact_property(
    spec: dict[str, Any],
    *,
    definitions: dict[str, Any],
) -> dict[str, Any]:
    if "$ref" in spec:
        name = str(spec["$ref"]).rsplit("/", 1)[-1]
        resolved = definitions.get(name)
        if isinstance(resolved, dict):
            spec = {**resolved, **{key: value for key, value in spec.items() if key != "$ref"}}
    if "anyOf" in spec and isinstance(spec["anyOf"], list):
        variants = [
            item
            for item in spec["anyOf"]
            if isinstance(item, dict) and item.get("type") != "null"
        ]
        if len(variants) == 1:
            spec = {**variants[0], **{key: value for key, value in spec.items() if key != "anyOf"}}
    compact = {
        field: value
        for field, value in spec.items()
        if field
        in {
            "type",
            "description",
            "enum",
            "default",
            "minimum",
            "maximum",
            "minLength",
            "maxLength",
        }
    }
    if not compact.get("type") and "additionalProperties" in spec:
        compact["type"] = "object"
    return compact


def _tool_result_prompt(tool_name: str, payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        {"tool_result": {"tool": tool_name, **payload}},
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    if len(serialized) <= MAX_TOOL_RESULT_PROMPT_CHARS:
        return serialized
    output = payload.get("output")
    compact_output: dict[str, Any] = {}
    if isinstance(output, dict):
        result = output.get("result")
        if isinstance(result, dict):
            compact_output["result"] = {
                key: value
                for key, value in result.items()
                if key
                in {
                    "query_id",
                    "status",
                    "error_code",
                    "recipe",
                    "columns",
                    "row_count",
                    "truncated",
                    "elapsed_ms",
                    "referenced_views",
                }
            }
            compact_output["result"]["rows"] = list(result.get("rows") or ())[:20]
        hits = output.get("hits")
        if isinstance(hits, list):
            compact_output["hits"] = [
                {
                    **{key: value for key, value in hit.items() if key != "text"},
                    "text": str(hit.get("text") or "")[:2_000],
                }
                for hit in hits[:8]
                if isinstance(hit, dict)
            ]
    return json.dumps(
        {
            "tool_result": {
                "tool": tool_name,
                "status": payload.get("status"),
                "output": compact_output,
                "prompt_truncated": True,
            }
        },
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )


def _action_protocol(schemas: tuple[dict[str, Any], ...]) -> str:
    return (
        "Choose exactly one next action. Prefer run_recipe whenever a versioned recipe "
        "can express the request. Use run_safe_sql only with an explicit catalog gap. "
        "Return only one compact JSON object, with no markdown: "
        '{"tool":"tool_name","arguments":{...}} or {"final":"answer"}. '
        f"Available tools: {json.dumps(schemas, ensure_ascii=False, separators=(',', ':'))}"
    )


def _compose_prompt_messages(
    *,
    action_schemas: tuple[dict[str, Any], ...],
    normalized_messages: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep one provider-compatible system message at the beginning."""

    system_contents = [_action_protocol(action_schemas)]
    system_contents.extend(
        str(message.get("content") or "").strip()
        for message in normalized_messages
        if message.get("role") == "system"
        and str(message.get("content") or "").strip()
    )
    return [
        {
            "role": "system",
            "content": "\n\n".join(system_contents),
        },
        *[
            message
            for message in normalized_messages
            if message.get("role") != "system"
        ],
    ]


def _parse_action(text: str) -> _ModelAction:
    try:
        payload = json.loads(str(text or "").strip())
    except json.JSONDecodeError as exc:
        raise ValueError("SQL agent completion must be one JSON action") from exc
    if not isinstance(payload, dict):
        raise ValueError("SQL agent completion must be a JSON object")
    return _ModelAction.model_validate(payload)


def _message_from_action(action: _ModelAction) -> AiDoModelMessage:
    if action.tool is None:
        return AiDoModelMessage(content=action.final or "")
    return AiDoModelMessage(
        content="",
        tool_calls=(
            {
                "name": action.tool,
                "args": action.arguments or {},
                "id": f"call_{uuid4().hex}",
                "type": "tool_call",
            },
        ),
    )


def _as_langchain_message(message: AiDoModelMessage) -> Any:
    try:
        from langchain_core.messages import AIMessage
    except ImportError:
        return message
    return AIMessage(
        content=message.content,
        tool_calls=list(message.tool_calls),
    )


def _as_langchain_messages(messages: Sequence[Any]) -> list[Any]:
    try:
        from langchain_core.messages.utils import convert_to_messages
    except ImportError as exc:
        raise RuntimeError("langchain-core is required for analysis_v2 agent") from exc
    return list(convert_to_messages(messages))


def _result_from_langchain_messages(
    messages: Sequence[Any],
    *,
    max_steps: int,
) -> AnalysisAgentResult:
    """Normalize a standard create_agent message trace into a stable public result."""

    pending: dict[str, tuple[int, str, dict[str, Any]]] = {}
    transcript: list[AnalysisToolCallRecord] = []
    tool_results: list[dict[str, Any]] = []
    final_text = ""
    model_steps = 0
    for message in messages:
        message_type = str(getattr(message, "type", "") or "")
        if message_type == "ai":
            model_steps += 1
            tool_calls = tuple(getattr(message, "tool_calls", ()) or ())
            if not tool_calls:
                final_text = _string_content(getattr(message, "content", ""))
                continue
            for tool_call in tool_calls:
                call = dict(tool_call)
                call_id = str(call.get("id") or "")
                tool_name = str(call.get("name") or "")
                arguments = dict(call.get("args") or {})
                if not call_id or not tool_name:
                    continue
                pending[call_id] = (model_steps, tool_name, arguments)
            continue
        if message_type != "tool":
            continue
        call_id = str(getattr(message, "tool_call_id", "") or "")
        matched = pending.pop(call_id, None)
        if matched is None:
            continue
        step, tool_name, arguments = matched
        status = str(getattr(message, "status", "success") or "success")
        if status == "error":
            transcript.append(
                AnalysisToolCallRecord(
                    call_id=call_id,
                    step=step,
                    tool=tool_name,
                    arguments=arguments,
                    status="failed",
                    error_code="analysis_v2.tool_execution_failed",
                    duration_ms=0,
                )
            )
            continue
        output = _tool_message_output(getattr(message, "content", ""))
        transcript.append(
            AnalysisToolCallRecord(
                call_id=call_id,
                step=step,
                tool=tool_name,
                arguments=arguments,
                status="succeeded",
                output=output,
                duration_ms=0,
            )
        )
        tool_results.append(output)
    bounded_steps = min(model_steps, max_steps)
    return AnalysisAgentResult(
        status="completed" if final_text else "max_steps",
        final_text=final_text,
        transcript=tuple(transcript),
        tool_results=tuple(tool_results),
        steps=bounded_steps,
    )


def _tool_message_output(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return dict(content)
    if not isinstance(content, str):
        return {"content": content}
    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return {"content": content}
    return dict(payload) if isinstance(payload, dict) else {"content": payload}


def _string_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


def _normalize_messages(messages: Sequence[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, dict):
            role = str(message.get("role") or "")
            content = message.get("content")
            tool_calls = tuple(message.get("tool_calls") or ())
            tool_name = str(message.get("name") or "")
            tool_status = str(message.get("status") or "success")
        else:
            message_type = str(getattr(message, "type", "") or "")
            role = {
                "human": "user",
                "ai": "assistant",
                "system": "system",
                "tool": "tool",
            }.get(message_type, message_type)
            content = getattr(message, "content", "")
            tool_calls = tuple(getattr(message, "tool_calls", ()) or ())
            tool_name = str(getattr(message, "name", "") or "")
            tool_status = str(getattr(message, "status", "success") or "success")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"unsupported analysis agent message role: {role}")
        if role == "assistant" and tool_calls:
            if len(tool_calls) != 1:
                raise ValueError("analysis_v2 accepts one tool action per model step")
            tool_call = dict(tool_calls[0])
            normalized.append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "tool": str(tool_call.get("name") or ""),
                            "arguments": dict(tool_call.get("args") or {}),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
            continue
        if role == "tool":
            output = _tool_message_output(content)
            payload: dict[str, Any]
            if tool_status == "error":
                payload = {
                    "status": "failed",
                    "error_code": "analysis_v2.tool_execution_failed",
                }
            else:
                payload = {"status": "succeeded", "output": output}
            # execute_llm is text-only and did not emit a provider-native tool
            # call, so replay tool results as a compact user protocol message.
            normalized.append(
                {
                    "role": "user",
                    "content": _tool_result_prompt(tool_name or "unknown_tool", payload),
                }
            )
            continue
        normalized.append({"role": role, "content": _string_content(content)})
    return normalized


__all__ = [
    "LEGACY_ISSUES_SQL_AGENT_WORKLOAD_ID",
    "AiDoChatModel",
    "AnalysisAgentResult",
    "AnalysisSqlAgent",
    "AnalysisToolCallRecord",
    "SQL_AGENT_SYSTEM_PROMPT",
    "build_sql_agent",
    "run_analysis_tools",
]
