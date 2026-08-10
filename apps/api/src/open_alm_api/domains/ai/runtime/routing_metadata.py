from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_alm_api.domains.ai.runtime.routing import RuntimeRoutingDecision


RUNTIME_ROUTING_META_KEYS = (
    "runtime_profile",
    "runtime_routing_reason_codes",
    "graph_gate",
    "graph_fallback_reason",
    "graph_used",
    "graph_validation_status",
    "graph_validation_fallback_reason",
    "graph_registry_agent_count",
    "graph_write_agent_count",
    "graph_candidate_summary",
    "graph_schedule_summary",
    "external_egress_summary",
    "external_planner_summary",
    "external_search_summary",
    "external_planner_execution_summary",
    "external_search_execution_summary",
    "graph_execution_status",
    "graph_execution_fallback_reason",
    "graph_execution_fallback_policy",
    "graph_execution_adapter",
    "graph_node_execution_summary",
)
RUNTIME_EXTERNAL_TRACE_SUMMARY_KEYS = (
    "external_egress_summary",
    "external_planner_summary",
    "external_search_summary",
    "external_planner_execution_summary",
    "external_search_execution_summary",
)
RUNTIME_GRAPH_EXECUTION_TRACE_KEYS = (
    "graph_execution_status",
    "graph_execution_fallback_reason",
    "graph_execution_fallback_policy",
    "graph_execution_adapter",
    "graph_node_execution_summary",
)
RUNTIME_GRAPH_CANDIDATE_VALIDATION_TRACE_KEYS = (
    "runtime_profile",
    "graph_gate",
    "graph_fallback_reason",
    "graph_used",
    "graph_validation_status",
    "graph_validation_fallback_reason",
    "graph_registry_agent_count",
    "graph_write_agent_count",
)
RUNTIME_SHADOW_META_KEYS = tuple(
    key for key in RUNTIME_ROUTING_META_KEYS if key != "runtime_profile"
)
_RUNTIME_STREAM_META_KEY_BY_KWARG = {
    "runtime_profile": "runtime_profile",
    "runtime_routing_reason_codes": "runtime_routing_reason_codes",
    "runtime_graph_gate": "graph_gate",
    "runtime_graph_fallback_reason": "graph_fallback_reason",
    "runtime_graph_used": "graph_used",
    "runtime_graph_validation_status": "graph_validation_status",
    "runtime_graph_validation_fallback_reason": "graph_validation_fallback_reason",
    "runtime_graph_registry_agent_count": "graph_registry_agent_count",
    "runtime_graph_write_agent_count": "graph_write_agent_count",
    "runtime_graph_candidate_summary": "graph_candidate_summary",
    "runtime_graph_schedule_summary": "graph_schedule_summary",
    "runtime_external_egress_summary": "external_egress_summary",
    "runtime_external_planner_summary": "external_planner_summary",
    "runtime_external_search_summary": "external_search_summary",
    "runtime_external_planner_execution_summary": "external_planner_execution_summary",
    "runtime_external_search_execution_summary": "external_search_execution_summary",
    "runtime_graph_execution_status": "graph_execution_status",
    "runtime_graph_execution_fallback_reason": "graph_execution_fallback_reason",
    "runtime_graph_execution_fallback_policy": "graph_execution_fallback_policy",
    "runtime_graph_execution_adapter": "graph_execution_adapter",
}


def runtime_routing_done_meta(
    runtime_routing: RuntimeRoutingDecision,
) -> dict[str, Any]:
    return {
        "runtime_profile": runtime_routing.runtime_profile,
        "runtime_routing_reason_codes": list(runtime_routing.reason_codes),
        "graph_gate": runtime_routing.graph_gate,
        "graph_fallback_reason": runtime_routing.graph_fallback_reason,
        "graph_used": runtime_routing.graph_used,
        "graph_validation_status": runtime_routing.graph_validation_status,
        "graph_validation_fallback_reason": (
            runtime_routing.graph_validation_fallback_reason
        ),
        "graph_registry_agent_count": runtime_routing.graph_registry_agent_count,
        "graph_write_agent_count": runtime_routing.graph_write_agent_count,
        "graph_candidate_summary": runtime_routing.graph_candidate_summary,
        "graph_schedule_summary": runtime_routing.graph_schedule_summary,
        "external_egress_summary": runtime_routing.external_egress_summary,
        "external_planner_summary": runtime_routing.external_planner_summary,
        "external_search_summary": runtime_routing.external_search_summary,
        "external_planner_execution_summary": (
            runtime_routing.external_planner_execution_summary
        ),
        "external_search_execution_summary": (
            runtime_routing.external_search_execution_summary
        ),
        "graph_execution_status": runtime_routing.graph_execution_status,
        "graph_execution_fallback_reason": (
            runtime_routing.graph_execution_fallback_reason
        ),
        "graph_execution_fallback_policy": (
            runtime_routing.graph_execution_fallback_policy
        ),
        "graph_execution_adapter": runtime_routing.graph_execution_adapter,
        "graph_node_execution_summary": None,
    }


def runtime_routing_stream_kwargs(
    runtime_routing: RuntimeRoutingDecision,
) -> dict[str, Any]:
    meta = runtime_routing_done_meta(runtime_routing)
    return {
        kwarg: _runtime_stream_kwarg_value(kwarg, meta[meta_key])
        for kwarg, meta_key in _RUNTIME_STREAM_META_KEY_BY_KWARG.items()
    }


def runtime_model_meta_from_kwargs(
    *,
    runtime_profile: str,
    runtime_routing_reason_codes: tuple[str, ...],
    runtime_graph_gate: str,
    runtime_graph_fallback_reason: str | None,
    runtime_graph_used: bool,
    runtime_graph_validation_status: str | None,
    runtime_graph_validation_fallback_reason: str | None,
    runtime_graph_registry_agent_count: int,
    runtime_graph_write_agent_count: int,
    runtime_graph_candidate_summary: dict[str, Any] | None,
    runtime_graph_schedule_summary: dict[str, Any] | None,
    runtime_external_egress_summary: dict[str, Any] | None,
    runtime_external_planner_summary: dict[str, Any] | None,
    runtime_external_search_summary: dict[str, Any] | None,
    runtime_external_planner_execution_summary: dict[str, Any] | None,
    runtime_external_search_execution_summary: dict[str, Any] | None,
    runtime_graph_execution_status: str,
    runtime_graph_execution_fallback_reason: str | None,
    runtime_graph_execution_fallback_policy: dict[str, Any] | None,
    runtime_graph_execution_adapter: str | None,
) -> dict[str, Any]:
    kwargs = locals()
    meta = {
        meta_key: _normalized_runtime_meta_value(meta_key, kwargs[kwarg])
        for kwarg, meta_key in _RUNTIME_STREAM_META_KEY_BY_KWARG.items()
    }
    meta["graph_node_execution_summary"] = None
    return meta


def runtime_done_meta_from_model_meta(
    model_meta: Mapping[str, Any],
) -> dict[str, Any]:
    return _runtime_meta_from_mapping(model_meta, include_defaults=True)


def runtime_persisted_meta_from_done_meta(
    done_meta: Mapping[str, Any],
) -> dict[str, Any]:
    return _runtime_meta_from_mapping(done_meta, include_defaults=False)


def runtime_shadow_meta_from_mapping(
    runtime_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return _runtime_meta_from_mapping_keys(
        runtime_metadata,
        keys=RUNTIME_SHADOW_META_KEYS,
        include_defaults=True,
    )


def runtime_graph_execution_trace_fields(
    runtime_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return _runtime_meta_from_mapping_keys(
        runtime_metadata,
        keys=RUNTIME_GRAPH_EXECUTION_TRACE_KEYS,
        include_defaults=True,
    )


def runtime_graph_candidate_validation_trace_fields(
    runtime_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return _runtime_meta_from_mapping_keys(
        runtime_metadata,
        keys=RUNTIME_GRAPH_CANDIDATE_VALIDATION_TRACE_KEYS,
        include_defaults=True,
    )


def runtime_present_external_trace_summaries(
    runtime_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        key: value
        for key in RUNTIME_EXTERNAL_TRACE_SUMMARY_KEYS
        if (value := runtime_metadata.get(key)) is not None
    }


def _runtime_meta_from_mapping(
    value: Mapping[str, Any],
    *,
    include_defaults: bool,
) -> dict[str, Any]:
    return _runtime_meta_from_mapping_keys(
        value,
        keys=RUNTIME_ROUTING_META_KEYS,
        include_defaults=include_defaults,
    )


def _runtime_meta_from_mapping_keys(
    value: Mapping[str, Any],
    *,
    keys: tuple[str, ...],
    include_defaults: bool,
) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for key in keys:
        if include_defaults or key in value:
            meta[key] = _normalized_runtime_meta_value(key, value.get(key))
    return meta


def _normalized_runtime_meta_value(key: str, value: Any) -> Any:
    if key == "runtime_routing_reason_codes":
        return list(value or [])
    if key == "graph_used":
        return bool(value)
    if key in {"graph_registry_agent_count", "graph_write_agent_count"}:
        return int(value or 0)
    return value


def _runtime_stream_kwarg_value(kwarg: str, value: Any) -> Any:
    if kwarg == "runtime_routing_reason_codes":
        return tuple(value or ())
    return value


__all__ = [
    "RUNTIME_EXTERNAL_TRACE_SUMMARY_KEYS",
    "RUNTIME_GRAPH_CANDIDATE_VALIDATION_TRACE_KEYS",
    "RUNTIME_GRAPH_EXECUTION_TRACE_KEYS",
    "RUNTIME_ROUTING_META_KEYS",
    "RUNTIME_SHADOW_META_KEYS",
    "runtime_done_meta_from_model_meta",
    "runtime_graph_candidate_validation_trace_fields",
    "runtime_graph_execution_trace_fields",
    "runtime_model_meta_from_kwargs",
    "runtime_persisted_meta_from_done_meta",
    "runtime_present_external_trace_summaries",
    "runtime_routing_done_meta",
    "runtime_routing_stream_kwargs",
    "runtime_shadow_meta_from_mapping",
]
