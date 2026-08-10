from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class ToolExecutionContext:
    source: str
    workspace_id: str
    tool_name: str
    call_id: str | None = None
    agent_run_id: str | None = None
    conversation_id: str | None = None


_CURRENT_TOOL_EXECUTION_CONTEXT: ContextVar[ToolExecutionContext | None] = ContextVar(
    "current_tool_execution_context",
    default=None,
)


def current_tool_execution_context() -> ToolExecutionContext | None:
    return _CURRENT_TOOL_EXECUTION_CONTEXT.get()


@contextmanager
def bind_tool_execution_context(
    context: ToolExecutionContext,
) -> Iterator[ToolExecutionContext]:
    token = _CURRENT_TOOL_EXECUTION_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CURRENT_TOOL_EXECUTION_CONTEXT.reset(token)
