from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from ai_do_api.core.llm_errors import LlmRuntimeError
from ai_do_api.domains.ai_graph.contracts import AiGraphNodeResult
from ai_do_api.domains.ai_graph.gateway_adapter import AiGatewayGraphAdapter
from ai_do_api.domains.ai_graph.runtime import (
    AiGraphNodeAdapter,
    AiGraphRuntimeContext,
)
from ai_do_api.domains.legacy_issues.analysis_graph.contracts import (
    AnalysisDataBundle,
    AnalysisInterpretation,
    GroundingReview,
    LegacyIssueAnalysisIncompleteError,
    require_complete_analysis_data,
)
from ai_do_api.domains.legacy_issues.analysis_graph.llm import (
    GraphStructuredOutputError,
    invoke_graph_json,
    invoke_graph_text,
)
from ai_do_api.domains.legacy_issues.analysis_graph.prompts import (
    answer_messages,
    correction_messages,
    draft_messages,
    finalizer_messages,
    interpretation_messages,
    report_outline_messages,
    review_messages,
    specialist_messages,
)
from ai_do_api.domains.legacy_issues.analysis_graph.report_guard import (
    build_source_markdown_fallback,
    sanitize_report_markdown,
    validate_report_markdown,
)
from ai_do_api.domains.legacy_issues.analysis_v2.recipes import (
    default_recipe_catalog,
)
from ai_do_api.domains.legacy_issues.task_kinds import (
    LEGACY_ISSUE_ANSWER_DRAFT_WORKLOAD_ID,
    LEGACY_ISSUE_CHECKLIST_ANALYST_WORKLOAD_ID,
    LEGACY_ISSUE_EVIDENCE_ANALYST_WORKLOAD_ID,
    LEGACY_ISSUE_GROUNDING_REVIEW_WORKLOAD_ID,
    LEGACY_ISSUE_QUANTITATIVE_ANALYST_WORKLOAD_ID,
    LEGACY_ISSUE_REPORT_CORRECTION_WORKLOAD_ID,
    LEGACY_ISSUE_REPORT_DRAFT_WORKLOAD_ID,
    LEGACY_ISSUE_REPORT_FINALIZE_WORKLOAD_ID,
    LEGACY_ISSUE_REPORT_TEMPLATE_WORKLOAD_ID,
    LEGACY_ISSUE_REQUEST_INTERPRET_WORKLOAD_ID,
)


class AnalysisDataProvider(Protocol):
    def analyze(
        self,
        *,
        context: AiGraphRuntimeContext,
        question: str,
        recent_messages: list[dict[str, str]],
        interpretation: AnalysisInterpretation,
    ) -> AnalysisDataBundle: ...


class AnalysisArtifactWriter(Protocol):
    def persist(
        self,
        *,
        context: AiGraphRuntimeContext,
        artifact_type: str,
        title: str,
        markdown: str,
        data: AnalysisDataBundle,
        input_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class LegacyIssueGraphDependencies:
    gateway: AiGatewayGraphAdapter
    data_provider: AnalysisDataProvider
    artifact_writer: AnalysisArtifactWriter


def build_legacy_issue_node_adapters(
    dependencies: LegacyIssueGraphDependencies,
) -> dict[str, AiGraphNodeAdapter]:
    gateway = dependencies.gateway

    async def interpret(
        state: Mapping[str, Any],
        context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        inputs = _inputs(state)
        question = _question(inputs)
        recent_messages = _recent_messages(inputs)
        interpretation = await invoke_graph_json(
            gateway,
            context,
            workload_id=LEGACY_ISSUE_REQUEST_INTERPRET_WORKLOAD_ID,
            messages=interpretation_messages(
                question=question,
                recent_messages=recent_messages,
            ),
            response_model=AnalysisInterpretation,
        )
        return AiGraphNodeResult(output=interpretation.model_dump(mode="json"))

    async def analyze_data(
        state: Mapping[str, Any],
        context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        inputs = _inputs(state)
        interpretation = AnalysisInterpretation.model_validate(
            _output(state, "interpret")
        )
        data = await asyncio.to_thread(
            dependencies.data_provider.analyze,
            context=context,
            question=_question(inputs),
            recent_messages=_recent_messages(inputs),
            interpretation=interpretation,
        )
        return AiGraphNodeResult(output=data.model_dump(mode="json"))

    async def choose_output(
        state: Mapping[str, Any],
        _context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        _require_complete_analysis(_data(state))
        interpretation = AnalysisInterpretation.model_validate(
            _output(state, "interpret")
        )
        route = "report" if interpretation.report_requested else "answer"
        return AiGraphNodeResult(
            output={"route": route},
            route=route,
        )

    async def answer_draft(
        state: Mapping[str, Any],
        context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        data = _data(state)
        _require_complete_analysis(data)
        question = _question(_inputs(state))
        if data.capability_limitations:
            return AiGraphNodeResult(
                output=_source_fallback(
                    data=data,
                    question=question,
                    title="과거차 문제점 분석",
                )
            )
        text = await invoke_graph_text(
            gateway,
            context,
            workload_id=LEGACY_ISSUE_ANSWER_DRAFT_WORKLOAD_ID,
            messages=answer_messages(
                question=question,
                source_payload=_source_payload(data),
            ),
            max_tokens=2_000,
        )
        validation = validate_report_markdown(
            f"# 답변\n\n{text}",
            question=question,
            query_results=[
                item.model_dump(mode="json") for item in data.query_results
            ],
            evidence=[item.model_dump(mode="json") for item in data.evidence],
            source_revisions=[
                item.model_dump(mode="json") for item in data.source_revisions
            ],
        )
        return AiGraphNodeResult(
            output=(
                text
                if validation.valid
                else _source_fallback(
                    data=data,
                    question=question,
                    title="과거차 문제점 분석",
                )
            )
        )

    async def report_template(
        state: Mapping[str, Any],
        context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        data = _data(state)
        outline = await invoke_graph_text(
            gateway,
            context,
            workload_id=LEGACY_ISSUE_REPORT_TEMPLATE_WORKLOAD_ID,
            messages=report_outline_messages(
                question=_question(_inputs(state)),
                interpretation=_output(state, "interpret"),
                source_manifest=_source_manifest(data),
            ),
            max_tokens=1_500,
        )
        return AiGraphNodeResult(output=outline)

    def specialist(
        *,
        node_id: str,
        role: str,
        workload_id: str,
        source_filter: Callable[[dict[str, Any]], bool],
    ) -> AiGraphNodeAdapter:
        async def run(
            state: Mapping[str, Any],
            context: AiGraphRuntimeContext,
        ) -> AiGraphNodeResult:
            sources = [
                item for item in _source_payload(_data(state)) if source_filter(item)
            ]
            if not sources:
                return AiGraphNodeResult(output="")
            notes = await invoke_graph_text(
                gateway,
                context,
                workload_id=workload_id,
                messages=specialist_messages(
                    role=role,
                    question=_question(_inputs(state)),
                    source_payload=sources,
                ),
                max_tokens=2_000,
            )
            return AiGraphNodeResult(output=notes)

        run.__name__ = node_id
        return run

    async def report_draft(
        state: Mapping[str, Any],
        context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        data = _data(state)
        notes = {
            "quantitative": _optional_text_output(state, "quantitative_analyst"),
            "evidence": _optional_text_output(state, "evidence_analyst"),
            "checklist": _optional_text_output(state, "checklist_analyst"),
        }
        draft = await invoke_graph_text(
            gateway,
            context,
            workload_id=LEGACY_ISSUE_REPORT_DRAFT_WORKLOAD_ID,
            messages=draft_messages(
                question=_question(_inputs(state)),
                outline=_text_output(state, "report_template"),
                specialist_notes=notes,
                source_payload=_source_payload(data),
            ),
            max_tokens=5_000,
        )
        return AiGraphNodeResult(output=draft)

    async def grounding_review(
        state: Mapping[str, Any],
        context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        try:
            review = await invoke_graph_json(
                gateway,
                context,
                workload_id=LEGACY_ISSUE_GROUNDING_REVIEW_WORKLOAD_ID,
                messages=review_messages(
                    question=_question(_inputs(state)),
                    draft=_text_output(state, "report_draft"),
                    source_payload=_source_payload(_data(state)),
                ),
                response_model=GroundingReview,
                max_tokens=2_500,
            )
        except (GraphStructuredOutputError, LlmRuntimeError) as error:
            if isinstance(error, LlmRuntimeError) and not _is_timeout_error(error):
                raise
            review = GroundingReview(
                grounded=False,
                correction_instructions=[
                    "The structured grounding review was inconclusive. "
                    "Retain only claims supported by captured sources."
                ],
            )
        return AiGraphNodeResult(output=review.model_dump(mode="json"))

    async def report_finalize(
        state: Mapping[str, Any],
        context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        data = _data(state)
        _require_complete_analysis(data)
        if data.capability_limitations:
            return AiGraphNodeResult(
                output=_source_fallback(
                    data=data,
                    title="과거차 문제점 분석 보고서",
                    question=_question(_inputs(state)),
                )
            )
        markdown = await invoke_graph_text(
            gateway,
            context,
            workload_id=LEGACY_ISSUE_REPORT_FINALIZE_WORKLOAD_ID,
            messages=finalizer_messages(
                question=_question(_inputs(state)),
                outline=_text_output(state, "report_template"),
                draft=_text_output(state, "report_draft"),
                review=_output(state, "grounding_review"),
                source_payload=_source_payload(_data(state)),
            ),
            max_tokens=5_000,
        )
        return AiGraphNodeResult(output=markdown)

    async def validate_report(
        state: Mapping[str, Any],
        _context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        validation = _validate(
            markdown=_text_output(state, "report_finalize"),
            state=state,
        )
        route = "accept" if validation["valid"] else "correct"
        return AiGraphNodeResult(output=validation, route=route)

    async def report_correction(
        state: Mapping[str, Any],
        context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        validation = _output(state, "validate_report")
        corrected = await invoke_graph_text(
            gateway,
            context,
            workload_id=LEGACY_ISSUE_REPORT_CORRECTION_WORKLOAD_ID,
            messages=correction_messages(
                question=_question(_inputs(state)),
                markdown=_text_output(state, "report_finalize"),
                validation_errors=list(validation.get("errors") or ()),
                source_payload=_source_payload(_data(state)),
            ),
            max_tokens=5_000,
        )
        return AiGraphNodeResult(output=corrected)

    async def validate_correction(
        state: Mapping[str, Any],
        _context: AiGraphRuntimeContext,
    ) -> AiGraphNodeResult:
        validation = _validate(
            markdown=_text_output(state, "report_correction"),
            state=state,
        )
        route = "accept" if validation["valid"] else "fallback"
        return AiGraphNodeResult(output=validation, route=route)

    def persist_node(
        *,
        artifact_type: str,
        markdown_node: str | None,
        fallback: bool = False,
    ) -> AiGraphNodeAdapter:
        async def persist(
            state: Mapping[str, Any],
            context: AiGraphRuntimeContext,
        ) -> AiGraphNodeResult:
            inputs = _inputs(state)
            data = _data(state)
            _require_complete_analysis(data)
            if fallback:
                correction = _optional_text_output(state, "report_correction")
                validation = _output(state, "validate_correction")
                sanitized = sanitize_report_markdown(
                    correction,
                    errors=list(validation.get("errors") or ()),
                )
                if sanitized and _validate(markdown=sanitized, state=state)["valid"]:
                    markdown = sanitized
                else:
                    markdown = build_source_markdown_fallback(
                        title="과거차 문제점 분석 보고서",
                        question=_question(inputs),
                        query_results=[
                            {
                                **item.model_dump(mode="json"),
                                **_recipe_metadata(item.recipe_id),
                            }
                            for item in data.query_results
                        ],
                        evidence=[
                            item.model_dump(mode="json") for item in data.evidence
                        ],
                        source_revisions=[
                            item.model_dump(mode="json")
                            for item in data.source_revisions
                        ],
                        capability_limitations=data.capability_limitations,
                    )
            else:
                assert markdown_node is not None
                markdown = _text_output(state, markdown_node)
            persisted = await asyncio.to_thread(
                dependencies.artifact_writer.persist,
                context=context,
                artifact_type=artifact_type,
                title=(
                    "과거차 문제점 분석 보고서"
                    if artifact_type == "report"
                    else "과거차 문제점 분석"
                ),
                markdown=markdown,
                data=data,
                input_payload=inputs,
            )
            return AiGraphNodeResult(output=persisted)

        return persist

    def query_source(item: dict[str, Any]) -> bool:
        return item.get("source_type") == "query"

    def evidence_source(item: dict[str, Any]) -> bool:
        return item.get("source_type") == "evidence"

    def checklist_source(item: dict[str, Any]) -> bool:
        return (
            item.get("source_type") == "evidence"
            and item.get("source_kind") == "vehicle_checklist"
        ) or (
            item.get("source_type") == "query"
            and (
                item.get("counting_unit")
                in {"checklists", "checklist_items", "mixed"}
                or "체크리스트" in str(item.get("source_label") or "")
            )
        )

    return {
        "interpret": interpret,
        "analyze_data": analyze_data,
        "choose_output": choose_output,
        "answer_draft": answer_draft,
        "persist_answer": persist_node(
            artifact_type="analysis",
            markdown_node="answer_draft",
        ),
        "report_template": report_template,
        "quantitative_analyst": specialist(
            node_id="quantitative_analyst",
            role="quantitative analyst",
            workload_id=LEGACY_ISSUE_QUANTITATIVE_ANALYST_WORKLOAD_ID,
            source_filter=query_source,
        ),
        "evidence_analyst": specialist(
            node_id="evidence_analyst",
            role="case evidence analyst",
            workload_id=LEGACY_ISSUE_EVIDENCE_ANALYST_WORKLOAD_ID,
            source_filter=evidence_source,
        ),
        "checklist_analyst": specialist(
            node_id="checklist_analyst",
            role="vehicle checklist analyst",
            workload_id=LEGACY_ISSUE_CHECKLIST_ANALYST_WORKLOAD_ID,
            source_filter=checklist_source,
        ),
        "report_draft": report_draft,
        "grounding_review": grounding_review,
        "report_finalize": report_finalize,
        "validate_report": validate_report,
        "persist_report": persist_node(
            artifact_type="report",
            markdown_node="report_finalize",
        ),
        "report_correction": report_correction,
        "validate_correction": validate_correction,
        "persist_corrected_report": persist_node(
            artifact_type="report",
            markdown_node="report_correction",
        ),
        "persist_source_fallback": persist_node(
            artifact_type="report",
            markdown_node=None,
            fallback=True,
        ),
    }


def _inputs(state: Mapping[str, Any]) -> dict[str, Any]:
    value = state.get("inputs")
    if not isinstance(value, Mapping):
        raise ValueError("analysis graph inputs are missing")
    return dict(value)


def _outputs(state: Mapping[str, Any]) -> Mapping[str, Any]:
    value = state.get("outputs")
    if not isinstance(value, Mapping):
        raise ValueError("analysis graph outputs are missing")
    return value


def _output(state: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    value = _outputs(state).get(node_id)
    if not isinstance(value, Mapping):
        raise ValueError(f"analysis graph output is missing: {node_id}")
    return dict(value)


def _text_output(state: Mapping[str, Any], node_id: str) -> str:
    value = _outputs(state).get(node_id)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"analysis graph text output is missing: {node_id}")
    return value.strip()


def _optional_text_output(state: Mapping[str, Any], node_id: str) -> str:
    value = _outputs(state).get(node_id)
    return value.strip() if isinstance(value, str) else ""


def _question(inputs: Mapping[str, Any]) -> str:
    value = inputs.get("question")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("analysis question is missing")
    return value.strip()


def _recent_messages(inputs: Mapping[str, Any]) -> list[dict[str, str]]:
    values = inputs.get("recent_messages")
    if not isinstance(values, list):
        return []
    messages: list[dict[str, str]] = []
    for value in values[-8:]:
        if not isinstance(value, Mapping):
            continue
        role = str(value.get("role") or "")
        content = value.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            messages.append({"role": role, "content": content[:4_000]})
    return messages


def _data(state: Mapping[str, Any]) -> AnalysisDataBundle:
    return AnalysisDataBundle.model_validate(_output(state, "analyze_data"))


def _require_complete_analysis(data: AnalysisDataBundle) -> None:
    require_complete_analysis_data(data)


def _source_payload(
    data: AnalysisDataBundle,
    *,
    max_chars: int = 60_000,
    max_query_rows: int = 50,
    max_evidence: int = 12,
) -> list[dict[str, Any]]:
    """Build a bounded LLM projection while artifacts retain full captured rows."""

    evidence_payload: list[dict[str, Any]] = []
    evidence_budget = min(20_000, max_chars // 3)
    for evidence in data.evidence[:max_evidence]:
        item = evidence.model_dump(
            mode="json",
            include={
                "evidence_id",
                "source_kind",
                "title",
                "excerpt",
            },
        )
        if len(item.get("excerpt") or "") > 2_000:
            item["excerpt"] = str(item["excerpt"])[:2_000]
        item["source_type"] = "evidence"
        revision_status = str(
            evidence.metadata.get("revision_status") or ""
        ).strip().casefold()
        if revision_status:
            item["source_status"] = revision_status
        item["qualitative_example"] = True
        item["population_metric"] = False
        item["citation_scope"] = (
            "This citation supports only facts contained in this one source card."
        )
        if not _append_with_budget(
            evidence_payload,
            item,
            max_chars=evidence_budget,
        ):
            break

    limitation_payload = [
        {
            "source_type": "capability_limitation",
            "message": limitation,
        }
        for limitation in data.capability_limitations
        if limitation.strip()
    ]
    payload: list[dict[str, Any]] = []
    query_source_status = _query_source_status(data)
    query_budget = max(
        max_chars - _serialized_size(evidence_payload),
        max_chars // 3,
    )
    for result in sorted(
        data.query_results,
        key=_query_projection_priority,
    ):
        recipe = _recipe_metadata(result.recipe_id)
        item = result.model_dump(
            mode="json",
            include={
                "recipe_id",
                "params",
                "recipe_arguments",
                "columns",
                "rows",
                "truncated",
                "status",
                "error_code",
            },
        )
        item.update(recipe)
        item.pop("recipe_id", None)
        row_limit = (
            min(max_query_rows, 8)
            if recipe["result_shape"] == "detail"
            else max_query_rows
        )
        string_limit = 300 if recipe["result_shape"] == "detail" else 500
        rows = [
            {
                key: (
                    value[:string_limit]
                    if isinstance(value, str) and len(value) > string_limit
                    else value
                )
                for key, value in row.items()
            }
            for row in item.get("rows", [])[:row_limit]
        ]
        item["rows"] = rows
        requested_limit = _requested_limit(result.recipe_arguments)
        projection_limited = result.row_count > len(rows)
        population_complete = bool(
            not result.truncated
            and not projection_limited
            and (
                requested_limit is None
                or result.row_count < requested_limit
            )
        )
        item["selection"] = {
            "requested_limit": requested_limit,
            "returned_row_count": result.row_count,
            "projection_limited": projection_limited,
            "population_complete": population_complete,
        }
        item["result_row_count_is_business_metric"] = False
        item["row_atomicity"] = "one row is one indivisible result record"
        item["source_type"] = "query"
        if query_source_status:
            item["source_status"] = query_source_status
        if not _append_with_budget(payload, item, max_chars=query_budget):
            continue
    return [*limitation_payload, *payload, *evidence_payload]


def _query_projection_priority(result: Any) -> tuple[int, str]:
    shape = _recipe_metadata(getattr(result, "recipe_id", None))["result_shape"]
    priority = {
        "scalar": 0,
        "comparison": 0,
        "timeseries": 1,
        "table": 1,
        "detail": 2,
        "unspecified": 2,
    }.get(str(shape), 2)
    return (priority, str(getattr(result, "recipe_id", "") or ""))


def _query_source_status(data: AnalysisDataBundle) -> str:
    statuses = {
        str(revision.status or "").strip().casefold()
        for revision in data.source_revisions
        if str(revision.status or "").strip()
    }
    if "draft" in statuses:
        return "draft"
    if statuses == {"published"}:
        return "published"
    return ""


def _recipe_metadata(recipe_id: str | None) -> dict[str, Any]:
    if not recipe_id:
        return {
            "source_label": "허용된 동적 정형 조회",
            "source_description": (
                "요청 범위에 대해 실행된 동적 조회이며 각 결과 컬럼의 의미만 사용한다."
            ),
            "counting_unit": "unspecified",
            "result_shape": "unspecified",
            "metric_definitions": [],
        }
    try:
        recipe = default_recipe_catalog().get(recipe_id, 1)
    except KeyError:
        return {
            "source_label": recipe_id,
            "source_description": "버전이 기록된 정형 조회 결과",
            "counting_unit": "unspecified",
            "result_shape": "unspecified",
            "metric_definitions": [],
        }
    return {
        "source_label": recipe.title,
        "source_description": recipe.description,
        "counting_unit": recipe.counting_unit,
        "result_shape": recipe.result_shape,
        "metric_definitions": [
            item.model_dump(mode="json") for item in recipe.metrics
        ],
    }


def _requested_limit(arguments: Mapping[str, Any]) -> int | None:
    for name in ("limit", "top_n"):
        value = arguments.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _append_with_budget(
    payload: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    max_chars: int,
) -> bool:
    candidate_size = _serialized_size([*payload, item])
    if candidate_size > max_chars:
        return False
    payload.append(item)
    return True


def _serialized_size(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    )


def _source_fallback(
    *,
    data: AnalysisDataBundle,
    title: str,
    question: str,
    degraded: bool = False,
) -> str:
    return build_source_markdown_fallback(
        title=title,
        question=question,
        query_results=(
            []
            if degraded
            else [
                {
                    **item.model_dump(mode="json"),
                    **_recipe_metadata(item.recipe_id),
                }
                for item in data.query_results
            ]
        ),
        evidence=[item.model_dump(mode="json") for item in data.evidence],
        source_revisions=[
            item.model_dump(mode="json") for item in data.source_revisions
        ],
        capability_limitations=data.capability_limitations,
        analysis_degraded=degraded,
    )


def _is_timeout_error(error: Exception) -> bool:
    message = str(error).casefold()
    return "timed out" in message or "timeout" in message


def _source_manifest(data: AnalysisDataBundle) -> list[dict[str, Any]]:
    return [
        {
            "source_type": item.get("source_type"),
            "source_id": item.get("query_id") or item.get("evidence_id"),
            "source_kind": item.get("source_kind"),
            "source_status": item.get("source_status"),
            "recipe_id": item.get("recipe_id"),
            "source_label": item.get("source_label"),
            "source_description": item.get("source_description"),
            "counting_unit": item.get("counting_unit"),
            "metric_definitions": item.get("metric_definitions"),
            "recipe_arguments": item.get("recipe_arguments"),
            "selection": item.get("selection"),
            "message": item.get("message"),
            "status": item.get("status"),
        }
        for item in _source_payload(data)
    ]


def _validate(
    *,
    markdown: str,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    data = _data(state)
    review = GroundingReview.model_validate(_output(state, "grounding_review"))
    result = validate_report_markdown(
        markdown,
        question=_question(_inputs(state)),
        query_results=[item.model_dump(mode="json") for item in data.query_results],
        evidence=[item.model_dump(mode="json") for item in data.evidence],
        source_revisions=[
            item.model_dump(mode="json") for item in data.source_revisions
        ],
        reviewed_unsupported_claims=review.unsupported_claims,
        reviewed_internal_commentary=review.internal_commentary,
    )
    return {"valid": result.valid, "errors": list(result.errors)}

__all__ = [
    "AnalysisArtifactWriter",
    "AnalysisDataProvider",
    "LegacyIssueAnalysisIncompleteError",
    "LegacyIssueGraphDependencies",
    "build_legacy_issue_node_adapters",
]
