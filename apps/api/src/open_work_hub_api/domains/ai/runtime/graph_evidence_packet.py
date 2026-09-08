from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from open_work_hub_api.domains.ai.runtime.contracts import (
    EvidenceCoverage,
    EvidenceItem,
    EvidencePacket,
    QueryPlan,
)
from open_work_hub_api.domains.ai.runtime.external_search import (
    ExternalSearchExecutionSummaryView,
)
from open_work_hub_api.domains.ai.runtime.graph_projection_values import (
    graph_candidate_string,
    graph_latest_user_text,
    trim_graph_text,
)
from open_work_hub_api.domains.ai.runtime.summary_fields import summary_string

if TYPE_CHECKING:
    from open_work_hub_api.domains.ai.runtime.graph_node_output import GraphNodeOutput


GRAPH_VERIFIER_AGENT_ID = "verifier.grounding"
GRAPH_WRITER_AGENT_ID = "writer.template"

GraphVerifierFailurePolicy = Literal[
    "not_required",
    "passed",
    "not_run_continue_with_gap_disclaimer",
    "failed_continue_with_gap_disclaimer",
]


@dataclass(frozen=True)
class _GraphEvidencePacketProjection:
    intent: str | None
    output_kind: str | None
    source_agent_ids: tuple[str, ...]
    query_plan: QueryPlan
    items: tuple[EvidenceItem, ...]
    intents_covered: tuple[str, ...]
    intents_missed: tuple[str, ...]
    verifier_status: str | None
    ready_for_grounded_write: bool
    failed_node_count: int
    tool_result_count: int
    gaps: tuple[str, ...]

    @classmethod
    def from_runtime_inputs(
        cls,
        *,
        messages: list[dict[str, Any]],
        node_outputs: list[GraphNodeOutput],
        candidate_summary: dict[str, Any] | None,
        external_planner_execution_summary: dict[str, Any] | None,
        external_search_execution_summary: dict[str, Any] | None,
    ) -> _GraphEvidencePacketProjection:
        failed_outputs = tuple(output for output in node_outputs if output.status == "failed")
        completed_outputs = tuple(
            output
            for output in node_outputs
            if output.status == "completed" and (output.text or output.tool_results)
        )
        provider_source_agent_ids = tuple(
            _external_provider_source_agent_ids(
                external_planner_execution_summary=external_planner_execution_summary,
                external_search_execution_summary=external_search_execution_summary,
            )
        )
        node_source_agent_ids = tuple(output.agent_id for output in node_outputs)
        source_agent_ids = node_source_agent_ids + provider_source_agent_ids
        node_items = tuple(_evidence_items_from_node_outputs(list(completed_outputs)))
        provider_items = tuple(
            _external_provider_evidence_items(
                external_search_execution_summary=external_search_execution_summary,
            )
        )
        items = (*node_items, *provider_items)
        verifier_status = _verifier_status(node_outputs)
        requires_verifier = candidate_requires_graph_verifier(candidate_summary)
        return cls(
            intent=graph_candidate_string(candidate_summary, "intent"),
            output_kind=graph_candidate_string(candidate_summary, "output_kind"),
            source_agent_ids=source_agent_ids,
            query_plan=_build_evidence_query_plan(
                messages=messages,
                items=items,
                external_search_execution_summary=external_search_execution_summary,
            ),
            items=items,
            intents_covered=tuple(output.agent_id for output in completed_outputs),
            intents_missed=tuple(output.agent_id for output in failed_outputs),
            verifier_status=verifier_status,
            ready_for_grounded_write=bool(node_items)
            and (
                verifier_status == "completed" if requires_verifier else verifier_status != "failed"
            ),
            failed_node_count=len(failed_outputs),
            tool_result_count=sum(len(output.tool_results) for output in completed_outputs),
            gaps=tuple(_evidence_gaps(node_outputs, verifier_status=verifier_status)),
        )

    def to_packet(self) -> EvidencePacket:
        return EvidencePacket(
            intent=self.intent,
            output_kind=self.output_kind,
            source_agent_ids=list(self.source_agent_ids),
            query_plan=self.query_plan,
            items=list(self.items),
            coverage=EvidenceCoverage(
                intents_covered=list(self.intents_covered),
                intents_missed=list(self.intents_missed),
            ),
            quality={
                "verifier_status": self.verifier_status,
                "ready_for_grounded_write": self.ready_for_grounded_write,
                "failed_node_count": self.failed_node_count,
                "tool_result_count": self.tool_result_count,
            },
            gaps=list(self.gaps),
        )


def materialize_graph_evidence_packet(
    *,
    messages: list[dict[str, Any]],
    node_outputs: list[GraphNodeOutput],
    candidate_summary: dict[str, Any] | None,
    external_planner_execution_summary: dict[str, Any] | None = None,
    external_search_execution_summary: dict[str, Any] | None = None,
) -> EvidencePacket:
    return _GraphEvidencePacketProjection.from_runtime_inputs(
        messages=messages,
        node_outputs=node_outputs,
        candidate_summary=candidate_summary,
        external_planner_execution_summary=external_planner_execution_summary,
        external_search_execution_summary=external_search_execution_summary,
    ).to_packet()


def summarize_graph_evidence_packet(packet: EvidencePacket) -> dict[str, Any]:
    return {
        "packet_version": packet.packet_version,
        "intent": packet.intent,
        "output_kind": packet.output_kind,
        "source_agent_count": len(packet.source_agent_ids),
        "source_kinds": list(packet.query_plan.source_kinds),
        "evidence_item_count": len(packet.items),
        "gap_count": len(packet.gaps),
        "verifier_status": packet.quality.verifier_status,
        "ready_for_grounded_write": packet.quality.ready_for_grounded_write,
        "failed_node_count": packet.quality.failed_node_count,
        "tool_result_count": packet.quality.tool_result_count,
    }


def render_evidence_packet(packet: EvidencePacket) -> str:
    return "EvidencePacket JSON:\n" + json.dumps(
        packet.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def graph_verifier_failure_policy(
    node_outputs: list[GraphNodeOutput],
    *,
    requires_verifier: bool,
) -> GraphVerifierFailurePolicy:
    if not requires_verifier:
        return "not_required"
    verifier_status = _verifier_status(node_outputs)
    if verifier_status == "completed":
        return "passed"
    if verifier_status == "failed":
        return "failed_continue_with_gap_disclaimer"
    return "not_run_continue_with_gap_disclaimer"


def candidate_requires_graph_verifier(
    candidate_summary: dict[str, Any] | None,
) -> bool:
    return bool(
        isinstance(candidate_summary, dict) and candidate_summary.get("requires_verifier") is True
    )


def _build_evidence_query_plan(
    *,
    messages: list[dict[str, Any]],
    items: tuple[EvidenceItem, ...],
    external_search_execution_summary: dict[str, Any] | None,
) -> QueryPlan:
    external_search = ExternalSearchExecutionSummaryView.from_summary(
        external_search_execution_summary
    )
    return QueryPlan(
        keywords=_extract_query_keywords(messages),
        source_kinds=sorted({item.source_kind for item in items}),
        sources_used=[item.ref for item in items[:12]],
        candidate_top_k=len(items),
        rerank_top_k=min(len(items), 8),
        final_evidence_token_budget=2048,
        external_search_used=external_search.used,
        external_search_provider=(external_search.provider if external_search.used else None),
        sanitized_query_ref=external_search.sanitized_query_ref,
    )


def _evidence_items_from_node_outputs(
    node_outputs: list[GraphNodeOutput],
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for output in node_outputs:
        source_kind = _source_kind_for_agent(output.agent_id)
        authority_class = _authority_class_for_source_kind(source_kind)
        trust_level = "trusted" if source_kind != "verifier" else "mixed"
        if output.text:
            items.append(
                EvidenceItem(
                    ref=f"graph-node:{output.agent_id}#note",
                    source_kind=source_kind,
                    excerpt=trim_graph_text(output.text, limit=1200),
                    provenance=output.agent_id,
                    trust_level=trust_level,
                    authority_class=authority_class,
                )
            )
        for index, result in enumerate(output.tool_results, start=1):
            items.append(
                EvidenceItem(
                    ref=f"graph-node:{output.agent_id}#tool-{index}",
                    source_kind=source_kind,
                    excerpt=trim_graph_text(result, limit=900),
                    provenance=output.agent_id,
                    trust_level=trust_level,
                    authority_class=authority_class,
                )
            )
    return items


def _external_provider_source_agent_ids(
    *,
    external_planner_execution_summary: dict[str, Any] | None,
    external_search_execution_summary: dict[str, Any] | None,
) -> list[str]:
    agent_ids: list[str] = []
    if _execution_status(external_planner_execution_summary) == "completed":
        adapter_id = summary_string(external_planner_execution_summary, "adapter_id")
        if adapter_id:
            agent_ids.append(adapter_id)
    external_search = ExternalSearchExecutionSummaryView.from_summary(
        external_search_execution_summary
    )
    if external_search.used and external_search.adapter_id:
        agent_ids.append(external_search.adapter_id)
    return agent_ids


def _external_provider_evidence_items(
    *,
    external_search_execution_summary: dict[str, Any] | None,
) -> list[EvidenceItem]:
    external_search = ExternalSearchExecutionSummaryView.from_summary(
        external_search_execution_summary
    )
    if not external_search.used:
        return []
    query_ref = external_search.sanitized_query_ref
    if not query_ref:
        return []
    provider = external_search.provider or "unknown"
    adapter_id = external_search.adapter_id or "external_search"
    execution_provider = external_search.execution_provider or "unknown"
    source_kinds = list(external_search.source_kinds)
    source_kind = external_search.source_kind
    result_refs = external_search.result_refs_or_fallback()
    items: list[EvidenceItem] = []
    for index, result_ref in enumerate(result_refs, start=1):
        excerpt = (
            "Mock external search normalized result metadata only; "
            f"sanitized_query_ref={query_ref}; "
            f"result_index={index}; "
            f"normalized_result_count={external_search.result_count}; "
            f"source_kinds={source_kinds or [source_kind]}."
        )
        items.append(
            EvidenceItem(
                ref=result_ref,
                source_kind=source_kind,
                excerpt=excerpt,
                provenance=f"{adapter_id}:{execution_provider}:{provider}",
                trust_level="untrusted",
                authority_class="public_web",
            )
        )
    return items


def _evidence_gaps(
    node_outputs: list[GraphNodeOutput],
    *,
    verifier_status: str | None,
) -> list[str]:
    gaps: list[str] = []
    for output in node_outputs:
        if output.status == "failed":
            error = trim_graph_text(
                output.error or "node failed without detail",
                limit=240,
            )
            gaps.append(f"{output.agent_id}: {error}")
        elif not output.text and not output.tool_results:
            gaps.append(f"{output.agent_id}: no evidence returned")
    if verifier_status == "failed":
        gaps.append("verifier.grounding: grounding verification failed")
    return _dedupe(gaps)


def _verifier_status(node_outputs: list[GraphNodeOutput]) -> str | None:
    for output in node_outputs:
        if output.agent_id == GRAPH_VERIFIER_AGENT_ID:
            return output.status
    return None


def _source_kind_for_agent(agent_id: str) -> str:
    if agent_id.startswith("domain."):
        return agent_id.removeprefix("domain.")
    if agent_id.startswith("search."):
        return "rag"
    if agent_id == GRAPH_VERIFIER_AGENT_ID:
        return "verifier"
    return "runtime"


def _authority_class_for_source_kind(source_kind: str) -> str:
    if source_kind in {"pms", "meeting", "docs", "planner", "rag"}:
        return "internal_system_of_record"
    if source_kind in {"external_web", "public_web_mock"}:
        return "public_web"
    return "unknown"


def _extract_query_keywords(messages: list[dict[str, Any]]) -> list[str]:
    text = graph_latest_user_text(messages)
    tokens = [
        token.strip(" \t\n\r.,!?;:()[]{}'\"`") for token in re.split(r"\s+", text) if token.strip()
    ]
    selected: list[str] = []
    for token in tokens:
        if len(token) < 2 or token in selected:
            continue
        selected.append(token[:40])
        if len(selected) >= 8:
            break
    return selected


def _execution_status(summary: dict[str, Any] | None) -> str | None:
    return summary_string(summary, "status")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        out.append(value)
        seen.add(value)
    return out


__all__ = [
    "GRAPH_VERIFIER_AGENT_ID",
    "GRAPH_WRITER_AGENT_ID",
    "GraphVerifierFailurePolicy",
    "candidate_requires_graph_verifier",
    "graph_verifier_failure_policy",
    "materialize_graph_evidence_packet",
    "render_evidence_packet",
    "summarize_graph_evidence_packet",
]
