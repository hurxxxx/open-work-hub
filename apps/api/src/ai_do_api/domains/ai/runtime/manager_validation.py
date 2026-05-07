from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from ai_do_api.domains.ai.runtime.contracts import ExecutionGraph
from ai_do_api.domains.ai.runtime.registry_validation import (
    RuntimeRegistry,
    RuntimeRegistryValidationError,
    validate_execution_graph,
)


EXECUTION_GRAPH_SCHEMA_NAME = "ExecutionGraph"
ManagerGraphCandidateSource = Literal["local_manager", "external_planning"]
ManagerGraphFallbackReason = Literal[
    "schema_validation_failed",
    "runtime_registry_validation_failed",
    "risk_floor_violation",
]


@dataclass(frozen=True)
class ManagerGraphValidationResult:
    accepted: bool
    graph: ExecutionGraph | None
    source: ManagerGraphCandidateSource = "local_manager"
    fallback_reason: ManagerGraphFallbackReason | None = None
    error: str | None = None


def build_execution_graph_json_schema() -> dict[str, Any]:
    """Return a copy so provider-specific schema adapters cannot mutate the contract."""

    return deepcopy(ExecutionGraph.model_json_schema())


def build_execution_graph_response_schema() -> dict[str, Any]:
    return {
        "name": EXECUTION_GRAPH_SCHEMA_NAME,
        "strict": True,
        "schema": build_execution_graph_json_schema(),
    }


def validate_manager_graph_candidate(
    candidate: ExecutionGraph | Mapping[str, Any],
    *,
    registry: RuntimeRegistry,
    source: ManagerGraphCandidateSource = "local_manager",
    write_agent_ids: frozenset[str] = frozenset(),
) -> ManagerGraphValidationResult:
    try:
        graph = (
            candidate
            if isinstance(candidate, ExecutionGraph)
            else ExecutionGraph.model_validate(candidate)
        )
    except ValidationError as error:
        return ManagerGraphValidationResult(
            accepted=False,
            graph=None,
            source=source,
            fallback_reason="schema_validation_failed",
            error=_validation_error_summary(error),
        )

    try:
        validate_execution_graph(graph, registry=registry)
    except RuntimeRegistryValidationError as error:
        return ManagerGraphValidationResult(
            accepted=False,
            graph=None,
            source=source,
            fallback_reason="runtime_registry_validation_failed",
            error=str(error),
        )

    write_invocations = sorted(
        invocation.agent_id
        for invocation in graph.invocations
        if invocation.agent_id in write_agent_ids
    )
    if write_invocations and graph.risk != "high":
        return ManagerGraphValidationResult(
            accepted=False,
            graph=None,
            source=source,
            fallback_reason="risk_floor_violation",
            error=f"write-capable agent(s) require high risk graph: {write_invocations}",
        )

    return ManagerGraphValidationResult(accepted=True, graph=graph, source=source)


def _validation_error_summary(error: ValidationError) -> str:
    first_error = error.errors()[0]
    location = ".".join(str(part) for part in first_error.get("loc", ()))
    message = str(first_error.get("msg") or "invalid execution graph")
    if not location:
        return message
    return f"{location}: {message}"
