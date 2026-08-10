from __future__ import annotations

from typing import Any

from ai_do_api.domains.ai.events import make_envelope
from ai_do_api.domains.ai.runtime.graph_schedule_summary import (
    GraphScheduleSummaryView,
    enable_graph_schedule_summary_execution,
    graph_schedule_is_planned,
    graph_schedule_step_descriptions,
    ordered_graph_schedule_steps,
    project_graph_execution_schedule,
    project_graph_schedule_failure,
    project_graph_schedule_state,
    project_graph_schedule_step,
)


def make_done_envelope_with_meta(
    done_event: Any,
    meta_updates: dict[str, Any],
) -> Any:
    meta = dict(done_event.data.meta.model_dump(mode="json") if done_event.data.meta else {})
    meta.update(meta_updates)
    return make_envelope(
        "done",
        done_event.seq,
        {
            "finish_reason": done_event.data.finish_reason,
            "audit_id": done_event.data.audit_id,
            "meta": meta,
        },
        timestamp_ms=done_event.timestamp_ms,
    )


__all__ = [
    "GraphScheduleSummaryView",
    "enable_graph_schedule_summary_execution",
    "graph_schedule_is_planned",
    "graph_schedule_step_descriptions",
    "make_done_envelope_with_meta",
    "ordered_graph_schedule_steps",
    "project_graph_execution_schedule",
    "project_graph_schedule_failure",
    "project_graph_schedule_state",
    "project_graph_schedule_step",
]
