from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from open_alm_api.domains.ai.runtime.contracts import RuntimeProfile
from open_alm_api.domains.ai.runtime.external_capability import (
    failed_external_execution_result,
)
from open_alm_api.domains.ai.runtime.external_adapters import (
    select_external_planner_execution_adapter,
    select_external_search_execution_adapter,
)
from open_alm_api.domains.ai.runtime.external_egress import ExternalEgressDecision
from open_alm_api.domains.ai.runtime.external_planner import (
    ExternalPlannerExecutionResult,
    ExternalPlannerRequest,
    build_external_planner_request,
    summarize_external_planner_execution,
    summarize_external_planner_request,
)
from open_alm_api.domains.ai.runtime.external_search import (
    ExternalSearchExecutionResult,
    ExternalSearchRequest,
    build_external_search_trace_identity,
    build_external_search_request,
    summarize_external_search_execution,
    summarize_external_search_request,
)
from open_alm_api.domains.ai.runtime.metrics import record_external_execution


@dataclass(frozen=True)
class ExternalCapabilityTraceSummaries:
    request_summary: dict[str, Any] | None
    execution_summary: dict[str, Any] | None


def external_planner_trace_summaries(
    *,
    runtime_profile: RuntimeProfile,
    graph_candidate_summary: dict[str, Any] | None,
    decisions: list[dict[str, Any]],
    execution_enabled: bool,
    settings: Any,
) -> ExternalCapabilityTraceSummaries:
    return _external_capability_trace_summaries(
        capability="planning",
        decisions=decisions,
        build_request=lambda decision: build_external_planner_request(
            egress_decision=decision,
            runtime_profile=runtime_profile,
            agent_ids=_graph_candidate_agent_ids(graph_candidate_summary),
        ),
        select_adapter=lambda: select_external_planner_execution_adapter(
            settings,
            execution_enabled=execution_enabled,
        ),
        summarize_request=summarize_external_planner_request,
        summarize_execution=summarize_external_planner_execution,
    )


def external_search_trace_summaries(
    *,
    decisions: list[dict[str, Any]],
    execution_enabled: bool,
    settings: Any,
) -> ExternalCapabilityTraceSummaries:
    return _external_capability_trace_summaries(
        capability="search",
        decisions=decisions,
        build_request=lambda decision: build_external_search_request(
            egress_decision=decision,
        ),
        select_adapter=lambda: select_external_search_execution_adapter(
            settings,
            execution_enabled=execution_enabled,
        ),
        summarize_request=summarize_external_search_request,
        summarize_execution=summarize_external_search_execution,
    )


def _external_capability_trace_summaries(
    *,
    capability: Literal["planning", "search"],
    decisions: list[dict[str, Any]],
    build_request: Callable[[ExternalEgressDecision], Any],
    select_adapter: Callable[[], Any],
    summarize_request: Callable[[Any], dict[str, Any]],
    summarize_execution: Callable[[Any], dict[str, Any]],
) -> ExternalCapabilityTraceSummaries:
    decision = _decision_for_capability(decisions, capability)
    if decision is None:
        return ExternalCapabilityTraceSummaries(None, None)
    request = build_request(ExternalEgressDecision.model_validate(decision))
    adapter = select_adapter()
    try:
        execution = adapter.execute(request)
    except Exception as error:
        execution = _failed_external_capability_execution(
            capability=capability,
            error=error,
            execution_provider=str(getattr(adapter, "execution_provider", "unknown") or "unknown"),
            request=request,
        )
    execution_summary = summarize_execution(execution)
    _record_external_execution_summary(
        capability=capability,
        execution_summary=execution_summary,
    )
    return ExternalCapabilityTraceSummaries(
        request_summary=summarize_request(request),
        execution_summary=execution_summary,
    )


def _decision_for_capability(
    decisions: list[dict[str, Any]],
    capability: Literal["planning", "search"],
) -> dict[str, Any] | None:
    return next(
        (decision for decision in decisions if decision.get("capability") == capability),
        None,
    )


def _graph_candidate_agent_ids(candidate_summary: dict[str, Any] | None) -> list[str]:
    if not isinstance(candidate_summary, dict):
        return []
    agent_ids = candidate_summary.get("invocation_agent_ids")
    if not isinstance(agent_ids, list):
        return []
    return [agent_id for agent_id in agent_ids if isinstance(agent_id, str) and agent_id]


def _failed_external_capability_execution(
    *,
    capability: Literal["planning", "search"],
    error: Exception,
    execution_provider: str,
    request: Any,
) -> ExternalPlannerExecutionResult | ExternalSearchExecutionResult:
    error_class = type(error).__name__
    if capability == "planning":
        planner_request = _as_planner_request(request)
        return failed_external_execution_result(
            ExternalPlannerExecutionResult,
            provider=planner_request.provider,
            error_class=error_class,
            extra_fields={"execution_provider": execution_provider},
        )
    search_request = _as_search_request(request)
    return failed_external_execution_result(
        ExternalSearchExecutionResult,
        provider=search_request.provider,
        error_class=error_class,
        extra_fields={
            "execution_provider": execution_provider,
            **_failed_external_search_trace_fields(
                request=search_request,
                execution_provider=execution_provider,
            ),
        },
    )


def _as_planner_request(request: Any) -> ExternalPlannerRequest:
    if isinstance(request, ExternalPlannerRequest):
        return request
    return ExternalPlannerRequest.model_validate(request)


def _as_search_request(request: Any) -> ExternalSearchRequest:
    if isinstance(request, ExternalSearchRequest):
        return request
    return ExternalSearchRequest.model_validate(request)


def _failed_external_search_trace_fields(
    *,
    request: ExternalSearchRequest,
    execution_provider: str,
) -> dict[str, str]:
    if not request.query:
        return {}
    trace_identity = build_external_search_trace_identity(
        query=request.query,
        provider=request.provider,
        execution_provider=execution_provider,
    )
    return {
        "cache_key": trace_identity.cache_key,
        "query_digest": trace_identity.query_digest,
    }


def _record_external_execution_summary(
    *,
    capability: Literal["planning", "search"],
    execution_summary: dict[str, Any],
) -> None:
    record_external_execution(
        capability=capability,
        adapter_id=_metric_summary_string(execution_summary.get("adapter_id")),
        execution_provider=_metric_summary_string(
            execution_summary.get("execution_provider")
        ),
        status=_metric_summary_string(execution_summary.get("status")),
        error_class=_metric_optional_summary_string(execution_summary.get("error_class")),
    )


def _metric_summary_string(value: Any) -> str:
    normalized = str(value or "unknown").strip()
    return normalized or "unknown"


def _metric_optional_summary_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "ExternalCapabilityTraceSummaries",
    "external_planner_trace_summaries",
    "external_search_trace_summaries",
]
