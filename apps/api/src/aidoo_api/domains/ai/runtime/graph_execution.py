from __future__ import annotations

from dataclasses import replace
from typing import Literal

from aidoo_api.domains.ai.runtime.routing import RuntimeRoutingDecision


GraphExecutionStatus = Literal[
    "not_applicable",
    "disabled",
    "adapter_unavailable",
]


def attach_graph_execution_adapter_decision(
    decision: RuntimeRoutingDecision,
    *,
    graph_execution_enabled: bool,
) -> RuntimeRoutingDecision:
    if decision.graph_gate != "eligible" or decision.graph_validation_status != "accepted":
        return replace(
            decision,
            graph_execution_status="not_applicable",
            graph_execution_fallback_reason=None,
            graph_execution_adapter=None,
        )
    schedule_summary = decision.graph_schedule_summary
    if not isinstance(schedule_summary, dict) or schedule_summary.get("state") != "planned":
        return replace(
            decision,
            graph_execution_status="not_applicable",
            graph_execution_fallback_reason="graph_schedule_unavailable",
            graph_execution_adapter=None,
        )
    if not graph_execution_enabled:
        return replace(
            decision,
            graph_execution_status="disabled",
            graph_execution_fallback_reason="graph_execution_disabled",
            graph_execution_adapter=None,
        )
    return replace(
        decision,
        graph_execution_status="adapter_unavailable",
        graph_execution_fallback_reason="graph_runtime_not_implemented",
        graph_execution_adapter=None,
    )


__all__ = ["GraphExecutionStatus", "attach_graph_execution_adapter_decision"]
