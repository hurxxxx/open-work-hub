from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from open_work_hub_api.domains.ai.runtime.agent_definitions import ResolvedAgentDefinitions
from open_work_hub_api.domains.ai.runtime.contracts import ExecutionGraph
from open_work_hub_api.domains.ai.runtime.registry_validation import (
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


@dataclass(frozen=True)
class ManagerGraphValidator:
    registry: RuntimeRegistry
    write_agent_ids: frozenset[str] = frozenset()
    source: ManagerGraphCandidateSource = "local_manager"

    @classmethod
    def for_resolved_agents(
        cls,
        resolved_agents: ResolvedAgentDefinitions,
        *,
        source: ManagerGraphCandidateSource = "local_manager",
    ) -> "ManagerGraphValidator":
        return cls(
            registry=resolved_agents.runtime_registry,
            write_agent_ids=resolved_agents.write_agent_ids,
            source=source,
        )

    def validate(
        self,
        candidate: ExecutionGraph | Mapping[str, Any],
    ) -> ManagerGraphValidationResult:
        graph_or_failure = _coerce_execution_graph_candidate(
            candidate,
            source=self.source,
        )
        if isinstance(graph_or_failure, ManagerGraphValidationResult):
            return graph_or_failure

        graph = graph_or_failure
        registry_failure = _validate_runtime_registry(
            graph,
            registry=self.registry,
            source=self.source,
        )
        if registry_failure is not None:
            return registry_failure

        write_risk_failure = _enforce_write_risk_floor(
            graph,
            source=self.source,
            write_agent_ids=self.write_agent_ids,
        )
        if write_risk_failure is not None:
            return write_risk_failure

        return ManagerGraphValidationResult(
            accepted=True,
            graph=graph,
            source=self.source,
        )


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
    return ManagerGraphValidator(
        registry=registry,
        write_agent_ids=write_agent_ids,
        source=source,
    ).validate(candidate)


def _coerce_execution_graph_candidate(
    candidate: ExecutionGraph | Mapping[str, Any],
    *,
    source: ManagerGraphCandidateSource,
) -> ExecutionGraph | ManagerGraphValidationResult:
    try:
        if isinstance(candidate, ExecutionGraph):
            return candidate
        return ExecutionGraph.model_validate(candidate)
    except ValidationError as error:
        return ManagerGraphValidationResult(
            accepted=False,
            graph=None,
            source=source,
            fallback_reason="schema_validation_failed",
            error=_validation_error_summary(error),
        )


def _validate_runtime_registry(
    graph: ExecutionGraph,
    *,
    registry: RuntimeRegistry,
    source: ManagerGraphCandidateSource,
) -> ManagerGraphValidationResult | None:
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
    return None


def _enforce_write_risk_floor(
    graph: ExecutionGraph,
    *,
    source: ManagerGraphCandidateSource,
    write_agent_ids: frozenset[str],
) -> ManagerGraphValidationResult | None:
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
    return None


def _validation_error_summary(error: ValidationError) -> str:
    first_error = error.errors()[0]
    location = ".".join(str(part) for part in first_error.get("loc", ()))
    message = str(first_error.get("msg") or "invalid execution graph")
    if not location:
        return message
    return f"{location}: {message}"
