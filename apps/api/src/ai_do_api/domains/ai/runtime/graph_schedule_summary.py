from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai_do_api.domains.ai.runtime.contracts import (
    GraphExecutionSchedule,
    GraphScheduleStep,
)
from ai_do_api.domains.ai.runtime.graph_projection_values import graph_string_list


_SCHEDULE_STATE_KEYS = ("state", "execution_enabled", "step_count")


@dataclass(frozen=True)
class GraphScheduleSummaryView:
    raw: Mapping[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> GraphScheduleSummaryView | None:
        if not isinstance(value, Mapping):
            return None
        return cls(raw=value)

    @property
    def state(self) -> str | None:
        state = self.raw.get("state")
        return state if isinstance(state, str) else None

    @property
    def is_planned(self) -> bool:
        return self.state == "planned"

    @property
    def planned_agent_ids(self) -> list[str]:
        return graph_string_list(self.raw.get("planned_agent_ids"))

    @property
    def ordered_steps(self) -> list[dict[str, Any]]:
        steps = self.raw.get("steps")
        if not isinstance(steps, list):
            return []
        normalized: list[dict[str, Any]] = []
        for step in steps:
            normalized_step = _normalize_step(step)
            if normalized_step is not None:
                normalized.append(normalized_step)
        return sorted(normalized, key=lambda item: int(item["invocation_seq"]))

    def public_state(self) -> dict[str, Any]:
        return {
            key: self.raw.get(key)
            for key in _SCHEDULE_STATE_KEYS
            if key in self.raw
        }

    def with_execution_enabled(self) -> dict[str, Any]:
        updated = dict(self.raw)
        updated["execution_enabled"] = True
        return updated

    def step_descriptions(self) -> list[str]:
        descriptions: list[str] = []
        for step in self.ordered_steps:
            agent_id = step["agent_id"]
            depends_on = ", ".join(
                graph_string_list(step.get("depends_on_agent_ids"))
            )
            suffix = f" after [{depends_on}]" if depends_on else ""
            descriptions.append(f"{agent_id}{suffix}")
        return descriptions or self.planned_agent_ids


def project_graph_schedule_step(step: GraphScheduleStep) -> dict[str, object]:
    return {
        "invocation_seq": step.invocation_seq,
        "agent_id": step.agent_id,
        "state": step.state,
        "depends_on_agent_ids": list(step.depends_on_agent_ids),
    }


def project_graph_execution_schedule(
    schedule: GraphExecutionSchedule,
) -> dict[str, object]:
    return {
        "state": schedule.state,
        "execution_enabled": schedule.execution_enabled,
        "step_count": len(schedule.steps),
        "planned_agent_ids": [step.agent_id for step in schedule.steps],
        "steps": [project_graph_schedule_step(step) for step in schedule.steps],
    }


def project_graph_schedule_failure(error: Exception) -> dict[str, object]:
    return {
        "state": "failed",
        "execution_enabled": False,
        "fallback_reason": "graph_schedule_failed",
        "error_type": type(error).__name__,
        "error": str(error),
        "step_count": 0,
        "planned_agent_ids": [],
        "steps": [],
    }


def project_graph_schedule_state(schedule_summary: Any) -> dict[str, Any]:
    view = GraphScheduleSummaryView.from_value(schedule_summary)
    if view is None:
        return {}
    return view.public_state()


def enable_graph_schedule_summary_execution(
    schedule_summary: dict[str, Any],
) -> dict[str, Any]:
    return GraphScheduleSummaryView(schedule_summary).with_execution_enabled()


def graph_schedule_is_planned(schedule_summary: Any) -> bool:
    view = GraphScheduleSummaryView.from_value(schedule_summary)
    return False if view is None else view.is_planned


def graph_schedule_step_descriptions(schedule_summary: Any) -> list[str]:
    view = GraphScheduleSummaryView.from_value(schedule_summary)
    if view is None:
        return []
    return view.step_descriptions()


def ordered_graph_schedule_steps(schedule_summary: Any) -> list[dict[str, Any]]:
    view = GraphScheduleSummaryView.from_value(schedule_summary)
    if view is None:
        return []
    return view.ordered_steps


def _normalize_step(step: Any) -> dict[str, Any] | None:
    if not isinstance(step, Mapping):
        return None
    agent_id = step.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return None
    try:
        invocation_seq = int(step.get("invocation_seq") or 0)
    except (TypeError, ValueError):
        return None
    if invocation_seq < 0:
        return None
    return {**dict(step), "agent_id": agent_id, "invocation_seq": invocation_seq}


__all__ = [
    "GraphScheduleSummaryView",
    "enable_graph_schedule_summary_execution",
    "graph_schedule_is_planned",
    "graph_schedule_step_descriptions",
    "ordered_graph_schedule_steps",
    "project_graph_execution_schedule",
    "project_graph_schedule_failure",
    "project_graph_schedule_state",
    "project_graph_schedule_step",
]
