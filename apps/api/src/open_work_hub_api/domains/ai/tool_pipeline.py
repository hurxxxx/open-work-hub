from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.ai.events import EnvelopeEncoder
from open_work_hub_api.domains.ai.tool_command_projection import (
    ToolChatCommandResult as ToolChatCommandResult,
    build_tool_chat_command_result,
    build_tool_chat_response_payload as build_tool_chat_response_payload,
    iter_tool_chat_command_events as iter_tool_chat_command_events,
    iter_tool_chat_command_sse_events,
    tool_done_meta as tool_done_meta,
)
from open_work_hub_api.domains.ai.tool_runtime import (
    execute_tool_call,
)
from open_work_hub_api.domains.auth.models import User, Workspace


class ToolCommandMessage(Protocol):
    role: str
    content: str


@dataclass(frozen=True)
class ToolChatCommand:
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolChatCommandError(ValueError):
    code: str
    params: dict[str, Any] = field(default_factory=dict)


def parse_tool_chat_command(messages: list[ToolCommandMessage]) -> ToolChatCommand | None:
    last_user_message = next(
        (message.content.strip() for message in reversed(messages) if message.role == "user"),
        None,
    )
    if not last_user_message or not last_user_message.startswith("/tool"):
        return None

    parts = last_user_message.split(maxsplit=2)
    if len(parts) < 2 or parts[0] != "/tool":
        raise ToolChatCommandError(code="ai.tool_command_syntax")

    arguments: dict[str, Any] = {}
    if len(parts) == 3 and parts[2].strip():
        try:
            parsed = json.loads(parts[2])
        except json.JSONDecodeError as error:
            raise ToolChatCommandError(
                code="ai.invalid_tool_argument_json",
                params={"error": error.msg},
            ) from error
        if not isinstance(parsed, dict):
            raise ToolChatCommandError(code="ai.tool_arguments_object_required")
        arguments = parsed

    return ToolChatCommand(tool_name=parts[1], arguments=arguments)


def execute_tool_chat_command(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    command: ToolChatCommand,
    source: str,
    conversation_id: str | None = None,
) -> ToolChatCommandResult:
    execution = execute_tool_call(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        tool_name=command.tool_name,
        arguments=command.arguments,
        source=source,
        conversation_id=conversation_id,
    )
    return build_tool_chat_command_result(execution)


def execute_tool_chat_command_sse_events(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    command: ToolChatCommand,
    source: str,
    encoder: EnvelopeEncoder,
    conversation_id: str | None = None,
) -> Iterator[dict[str, str]]:
    result = execute_tool_chat_command(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        command=command,
        source=source,
        conversation_id=conversation_id,
    )
    yield from iter_tool_chat_command_sse_events(
        encoder=encoder,
        execution=result.execution,
    )


__all__ = [
    "ToolChatCommand",
    "ToolChatCommandError",
    "ToolChatCommandResult",
    "ToolCommandMessage",
    "build_tool_chat_response_payload",
    "execute_tool_chat_command",
    "execute_tool_chat_command_sse_events",
    "iter_tool_chat_command_events",
    "parse_tool_chat_command",
    "tool_done_meta",
]
