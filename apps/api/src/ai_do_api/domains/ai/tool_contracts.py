from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    strict: bool = True


@dataclass(frozen=True)
class AgentToolCallMessage:
    call_id: str
    tool_name: str
    arguments_json: str


@dataclass(frozen=True)
class AgentToolResultMessage:
    call_id: str
    content: str


def agent_tool_spec_to_openai_function(spec: AgentToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "strict": spec.strict,
            "parameters": dict(spec.input_schema),
        },
    }


def agent_tool_specs_to_openai_functions(
    specs: Sequence[AgentToolSpec],
) -> list[dict[str, Any]]:
    return [agent_tool_spec_to_openai_function(spec) for spec in specs]


def agent_tool_names(specs: Sequence[AgentToolSpec]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        name = spec.name.strip()
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def openai_tool_call_message(message: AgentToolCallMessage) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": message.call_id,
                "type": "function",
                "function": {
                    "name": message.tool_name,
                    "arguments": message.arguments_json,
                },
            }
        ],
    }


def openai_tool_result_message(message: AgentToolResultMessage) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": message.call_id,
        "content": message.content,
    }


__all__ = [
    "AgentToolCallMessage",
    "AgentToolResultMessage",
    "AgentToolSpec",
    "agent_tool_names",
    "agent_tool_spec_to_openai_function",
    "agent_tool_specs_to_openai_functions",
    "openai_tool_call_message",
    "openai_tool_result_message",
]
