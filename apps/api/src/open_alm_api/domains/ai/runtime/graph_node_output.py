from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GraphNodeOutput:
    agent_id: str
    status: str
    text: str = ""
    tool_results: tuple[str, ...] = ()
    error: str | None = None


@dataclass
class GraphNodeOutputCollector:
    agent_id: str
    content_parts: list[str]
    tool_results: list[str]
    errors: list[str]
    finish_reason: str | None = None

    @classmethod
    def for_agent(cls, agent_id: str) -> GraphNodeOutputCollector:
        return cls(agent_id=agent_id, content_parts=[], tool_results=[], errors=[])

    def collect_event(self, event: Any) -> None:
        if event.type == "content_delta":
            self.content_parts.append(event.data.text)
            return
        if event.type == "tool_result":
            if event.data.result_preview:
                self.tool_results.append(event.data.result_preview)
            if event.data.error:
                self.errors.append(event.data.error)
            return
        if event.type == "error":
            self.errors.append(event.data.message)
            return
        if event.type == "done":
            self.finish_reason = event.data.finish_reason

    def build(self) -> GraphNodeOutput:
        return build_graph_node_output(
            agent_id=self.agent_id,
            content_parts=self.content_parts,
            tool_results=self.tool_results,
            errors=self.errors,
            finish_reason=self.finish_reason,
        )


def build_graph_node_output(
    *,
    agent_id: str,
    content_parts: Iterable[str],
    tool_results: Iterable[str],
    errors: Iterable[str],
    finish_reason: str | None,
) -> GraphNodeOutput:
    output_errors = list(errors)
    if finish_reason == "length" and not output_errors:
        output_errors.append("finish_reason:length")
    return GraphNodeOutput(
        agent_id=agent_id,
        status="failed" if output_errors or finish_reason == "error" else "completed",
        text="".join(content_parts).strip(),
        tool_results=tuple(tool_results),
        error="; ".join(output_errors) if output_errors else None,
    )


__all__ = [
    "GraphNodeOutput",
    "GraphNodeOutputCollector",
    "build_graph_node_output",
]
