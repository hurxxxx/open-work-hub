from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.settings import get_settings
from ai_do_api.domains.ai.gateway import LlmWorkloadContext
from ai_do_api.domains.ai_artifacts.models import AiIndexGeneration
from ai_do_api.domains.ai_graph.runtime import AiGraphRuntimeContext
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.legacy_issues.analysis_graph.contracts import (
    AnalysisDataBundle,
    AnalysisEvidence,
    AnalysisInterpretation,
    AnalysisQueryResult,
    AnalysisSourceRevision,
)
from ai_do_api.domains.legacy_issues.analysis_v2.agent import (
    AnalysisAgentResult,
    AiDoChatModel,
    build_sql_agent,
    run_analysis_tools,
)
from ai_do_api.domains.legacy_issues.analysis_v2.composition import (
    AnalysisCompositionDependencies,
    AnalysisRetrieverKind,
    AnalysisRuntimeResolver,
    build_analysis_toolset,
    default_inference_gateway_embedding_client,
    default_pgvector_config,
)
from ai_do_api.domains.legacy_issues.analysis_v2.contracts import (
    QueryResult,
    RetrievalHit,
)
from ai_do_api.domains.legacy_issues.analysis_v2.execution import (
    AnalysisSqlScope,
)
from ai_do_api.domains.legacy_issues.analysis_v2.tools import AnalysisToolset
from ai_do_api.domains.legacy_issues.analysis_v2.scope import (
    resolve_runtime_sql_scope,
)
from ai_do_api.domains.legacy_issues.analysis_v2.vector_index import (
    FinalAclHydrator,
    GenerationQueryScope,
    VectorCandidate,
)
from ai_do_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from ai_do_api.domains.legacy_issues.module_access import (
    enabled_legacy_issue_module_keys,
)
from ai_do_api.domains.legacy_issues.revisioning import (
    legacy_issue_dataset_revision_key,
)
from ai_do_api.domains.legacy_issues.settings import get_legacy_issue_settings
from ai_do_api.domains.retrieval.partitioning import (
    RetrievalReadScope,
    flatten_read_scope,
)
from ai_do_api.domains.source_access import SourceAclPolicy


_ANALYSIS_METADATA_NAMESPACE = "legacy_issue_analysis_metadata"
_EVIDENCE_NAMESPACE = "legacy_issues"
_VECTOR_BACKEND = "llamaindex-pgvector"
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:\s*년)?(?!\d)")
_TOP_N_RE = re.compile(r"(?:상위|하위)\s*(\d{1,3})")
_RELATIVE_PERIOD_TERMS = (
    "최근",
    "지난",
    "올해",
    "금년",
    "작년",
    "전년",
    "분기",
    "개월",
    "주간",
    "월간",
    "연간",
)
_RECOVERABLE_PLANNER_REJECTION_CODES = frozenset(
    {
        "analysis_v2.invalid_literal_filter",
        "analysis_v2.invalid_module_filter",
    }
)
_RECOVERABLE_AGENT_STATUSES = frozenset({"max_steps", "model_error"})
_DIMENSION_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("region_zone", ("권역", "지역")),
    ("vehicle_model", ("차종", "차량모델", "차량 모델")),
    ("issue_type", ("문제유형", "문제 유형", "이슈유형", "이슈 유형")),
    ("severity_grade", ("중요도", "심각도")),
    ("module_key", ("모듈", "부품군")),
    ("department", ("부서", "담당부문", "담당 부문")),
    ("major_category", ("대분류", "대 분류")),
    ("middle_category", ("중분류", "중 분류")),
    ("occurrence_stage", ("발생단계", "발생 단계")),
    ("occurrence_type", ("발생유형", "발생 유형")),
    ("cause_type", ("원인유형", "원인 유형")),
    ("supplier", ("협력사", "공급사", "업체")),
    ("part_number", ("부품번호", "부품 번호", "품번")),
    ("process_name", ("공정",)),
    ("applied", ("적용여부", "적용 여부")),
)
_FILTER_PARAMETER_BY_DIMENSION = {
    "region_zone": "regions",
    "vehicle_model": "vehicle_models",
    "module_key": "module_keys",
}


class LegacyIssueAnalysisRuntimeResolver(AnalysisRuntimeResolver):
    """Resolve all SQL/vector scopes from authenticated server state."""

    def resolve_source_namespaces(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run,
        kind: AnalysisRetrieverKind,
    ) -> tuple[str, ...]:
        del db, workspace, user, run, kind
        # Analysis metadata is replicated into each authorized legacy partition
        # so the same common read scope can protect both retrievers.
        return ("legacy_issues",)

    def resolve_sql_scope(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run,
        retrieval_scope: RetrievalReadScope,
    ) -> AnalysisSqlScope:
        del user, run
        return resolve_runtime_sql_scope(
            db,
            workspace_id=workspace.id,
            module_keys=enabled_legacy_issue_module_keys(
                compressor_enabled=get_settings().legacy_issue_compressor_enabled
            ),
            partition_ids=tuple(
                str(value) for value in flatten_read_scope(retrieval_scope)
            ),
        )

    def resolve_generation_scope(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run,
        kind: AnalysisRetrieverKind,
        retrieval_scope: RetrievalReadScope,
    ) -> GenerationQueryScope:
        namespace = (
            _ANALYSIS_METADATA_NAMESPACE
            if kind == "analysis_metadata"
            else _EVIDENCE_NAMESPACE
        )
        generation = db.scalar(
            select(AiIndexGeneration)
            .where(
                AiIndexGeneration.workspace_id == workspace.id,
                AiIndexGeneration.app_id == "legacy-issues",
                AiIndexGeneration.backend == _VECTOR_BACKEND,
                AiIndexGeneration.source_namespace == namespace,
                AiIndexGeneration.status == "active",
            )
            .order_by(AiIndexGeneration.cutover_at.desc(), AiIndexGeneration.created_at.desc())
            .limit(1)
        )
        if generation is None:
            raise LookupError(f"active analysis index generation missing: {namespace}")
        try:
            generation_number = int(generation.generation_key)
        except (TypeError, ValueError) as error:
            raise ValueError("analysis index generation_key must be an integer") from error

        sql_scope = self.resolve_sql_scope(
            db,
            workspace=workspace,
            user=user,
            run=run,
            retrieval_scope=retrieval_scope,
        )
        return GenerationQueryScope(
            workspace_id=workspace.id,
            partition_ids=tuple(
                str(value) for value in flatten_read_scope(retrieval_scope)
            ),
            module_keys=sql_scope.module_keys,
            revision_ids=sql_scope.revision_ids,
            source_kinds=(
                ("analysis_metadata",)
                if kind == "analysis_metadata"
                else ("legacy_issue_record",)
            ),
            generation=generation_number,
        )

    def resolve_final_acl_hydrator(
        self,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
        run,
        kind: AnalysisRetrieverKind,
        acl_policy: SourceAclPolicy,
        generation_scope: GenerationQueryScope,
    ) -> FinalAclHydrator:
        del user, run
        if kind == "analysis_metadata":
            return _metadata_hydrator

        def hydrate(
            candidates: tuple[VectorCandidate, ...],
            limit: int,
        ) -> tuple[RetrievalHit, ...]:
            candidate_ids = tuple(
                dict.fromkeys(item.metadata.source_id for item in candidates)
            )
            allowed = acl_policy.authorize_many_resources(
                ("legacy_issue_record", record_id) for record_id in candidate_ids
            )
            allowed_ids = {
                resource_id
                for resource_type, resource_id in allowed
                if resource_type == "legacy_issue_record"
            }
            rows = {
                row.id: row
                for row in db.scalars(
                    select(LegacyIssueRecord).where(
                        LegacyIssueRecord.id.in_(allowed_ids),
                        LegacyIssueRecord.workspace_id == workspace.id,
                        LegacyIssueRecord.retrieval_partition_id.in_(
                            generation_scope.partition_ids
                        ),
                        LegacyIssueRecord.module_key.in_(generation_scope.module_keys),
                        LegacyIssueRecord.revision_id.in_(generation_scope.revision_ids),
                    )
                )
            }
            revision_ids = {
                str(row.revision_id)
                for row in rows.values()
                if row.revision_id
            }
            revision_statuses = (
                dict(
                    db.execute(
                        select(
                            LegacyIssueDataRevision.id,
                            LegacyIssueDataRevision.status,
                        ).where(
                            LegacyIssueDataRevision.workspace_id == workspace.id,
                            LegacyIssueDataRevision.id.in_(revision_ids),
                        )
                    ).all()
                )
                if revision_ids
                else {}
            )
            hits: list[RetrievalHit] = []
            seen_record_ids: set[str] = set()
            for candidate in candidates:
                row = rows.get(candidate.metadata.source_id)
                if row is None or row.id in seen_record_ids:
                    continue
                seen_record_ids.add(row.id)
                title = " / ".join(
                    value
                    for value in (
                        row.legacy_issue_number,
                        row.vehicle_model,
                        row.symptom,
                    )
                    if value
                ) or row.id
                hits.append(
                    RetrievalHit(
                        hit_id=candidate.node_id,
                        text=(row.search_text or candidate.indexed_text)[:20_000],
                        score=candidate.score,
                        resource_type="legacy_issue_record",
                        resource_id=row.id,
                        partition_id=candidate.metadata.partition_id,
                        metadata={
                            "title": title,
                            "revision_id": row.revision_id,
                            "revision_status": revision_statuses.get(
                                str(row.revision_id)
                            ),
                            "module_key": row.module_key,
                            "stable_record_id": row.stable_record_id,
                            "vehicle_model": row.vehicle_model,
                        },
                    )
                )
                if len(hits) >= limit:
                    break
            return tuple(hits)

        return hydrate

    def resolve_embedding_client(self, db, *, workspace, user, run):
        del db, workspace, user, run
        return default_inference_gateway_embedding_client()

    def resolve_pgvector_config(self, db, *, workspace, user, run):
        del db, workspace, user, run
        return default_pgvector_config(
            embed_dim=get_legacy_issue_settings().ai_embedding_dimensions
        )


class LangChainLegacyIssueDataProvider:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        resolver: AnalysisRuntimeResolver | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._resolver = resolver or LegacyIssueAnalysisRuntimeResolver()

    def analyze(
        self,
        *,
        context: AiGraphRuntimeContext,
        question: str,
        recent_messages: list[dict[str, str]],
        interpretation: AnalysisInterpretation,
    ) -> AnalysisDataBundle:
        with self._session_factory() as db:
            workspace = db.get(Workspace, context.workspace_id)
            user = db.get(User, context.requested_by_user_id)
            if workspace is None or user is None:
                raise LookupError("analysis run principal no longer exists")
            toolset = build_analysis_toolset(
                db,
                workspace=workspace,
                user=user,
                run=context,
                dependencies=AnalysisCompositionDependencies(
                    resolver=self._resolver,
                ),
            )
            model = AiDoChatModel(
                db=db,
                context=LlmWorkloadContext(
                    source="worker.legacy_issues.sql_agent",
                    workspace_id=workspace.id,
                    actor_user_id=user.id,
                    principal_kind="user",
                    principal_id=user.id,
                    app_id="legacy-issues",
                ),
                agent_run_id=context.run_id,
                conversation_id=context.conversation_id,
            )
            agent = build_sql_agent(model=model, toolset=toolset)
            recipe_catalog = [
                {
                    "id": recipe.recipe_id,
                    "version": recipe.version,
                    "title": recipe.title,
                    "description": recipe.description,
                    "shape": recipe.result_shape,
                    "unit": recipe.counting_unit,
                    "parameters": [
                        {
                            key: value
                            for key, value in {
                                "name": parameter.name,
                                "type": parameter.value_type.value,
                                "description": (
                                    f"{parameter.description} "
                                    "(exact contiguous phrase, at most 4 terms)"
                                    if getattr(parameter.operator, "value", None)
                                    == "contains"
                                    else parameter.description
                                ),
                                "required": parameter.required,
                                "default": parameter.default,
                                "allowed": (
                                    list(parameter.allowed_values)
                                    or (
                                        list(toolset.allowed_module_keys)
                                        if parameter.name == "module_keys"
                                        else []
                                    )
                                ),
                                "minimum": parameter.minimum,
                                "maximum": parameter.maximum,
                            }.items()
                            if value not in (None, [], ())
                        }
                        for parameter in recipe.parameters
                    ],
                }
                for recipe in toolset.catalog.all()
            ]
            result = run_analysis_tools(
                agent,
                graph_run_id=context.run_id,
                messages=[
                    *recent_messages[-8:],
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "interpretation": interpretation.model_dump(
                                    mode="json"
                                ),
                                "available_recipes": recipe_catalog,
                                "instruction": (
                                    "Use the smallest sufficient set of versioned "
                                    "recipes and authorized semantic evidence. "
                                    "Use safe SQL only for a genuine catalog gap. "
                                    "Do not invent filters. Cover every explicitly "
                                    "requested dimension, period, and measure before "
                                    "stopping. Date endpoints are exact: never replace "
                                    "an unsupported requested date field with another "
                                    "available date field. Never invent a period; a "
                                    "request without a period has no date filter. "
                                    "Treat allowed module keys as a closed enum. A "
                                    "component, part, symptom, or synonym is not a "
                                    "module key. query_text is one literal contiguous "
                                    "substring: never pass the whole question or join "
                                    "alternative expressions into it; use semantic "
                                    "evidence for concepts and synonyms."
                                ),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
            )
            result = _supplement_required_sources(
                toolset=toolset,
                result=result,
                question=question,
                interpretation=interpretation,
            )
            capability_limitations = _requested_capability_limitations(question)
            bundle = _agent_result_to_bundle(
                result,
                interpretation=interpretation,
                capability_limitations=capability_limitations,
            )
            return bundle.model_copy(
                update={
                    "source_revisions": _source_revisions_for_scope(
                        db,
                        workspace_id=workspace.id,
                        revision_ids=toolset.authorized_revision_ids,
                        module_keys=toolset.allowed_module_keys,
                    ),
                    "source_snapshot_captured": True,
                }
            )


def _metadata_hydrator(
    candidates: tuple[VectorCandidate, ...],
    limit: int,
) -> tuple[RetrievalHit, ...]:
    return tuple(
        RetrievalHit(
            hit_id=item.node_id,
            text=item.indexed_text,
            score=item.score,
            resource_type="analysis_metadata",
            resource_id=item.metadata.source_id,
            partition_id=item.metadata.partition_id,
            metadata={
                "module_key": item.metadata.module_key,
                "revision_id": item.metadata.revision_id,
            },
        )
        for item in candidates[:limit]
    )


def _source_revisions_for_scope(
    db: Session,
    *,
    workspace_id: str,
    revision_ids: tuple[str, ...],
    module_keys: tuple[str, ...],
) -> list[AnalysisSourceRevision]:
    if not revision_ids:
        return []
    module_by_dataset_key = {
        legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY, module_key): (
            module_key
        )
        for module_key in module_keys
    }
    revisions = list(
        db.scalars(
            select(LegacyIssueDataRevision).where(
                LegacyIssueDataRevision.id.in_(revision_ids),
                LegacyIssueDataRevision.workspace_id == workspace_id,
            )
        )
    )
    revision_by_id = {revision.id: revision for revision in revisions}
    return [
        AnalysisSourceRevision(
            revision_id=revision.id,
            status=revision.status,
            module_key=module_by_dataset_key.get(revision.dataset_key),
        )
        for revision_id in revision_ids
        if (revision := revision_by_id.get(revision_id)) is not None
    ]


def _agent_result_to_bundle(
    result: AnalysisAgentResult,
    *,
    interpretation: AnalysisInterpretation,
    capability_limitations: Sequence[str] = (),
) -> AnalysisDataBundle:
    queries: list[AnalysisQueryResult] = []
    evidence: list[AnalysisEvidence] = []
    backend_ids: list[str] = []
    limitations: list[str] = []
    execution_warnings: list[str] = []
    seen_evidence: set[tuple[str, str]] = set()
    seen_queries: set[str] = set()
    for tool_result in result.tool_results:
        limitation_code = tool_result.get("limitation_code")
        if isinstance(limitation_code, str) and limitation_code.strip():
            limitations.append(limitation_code.strip())
        query_payload = tool_result.get("result")
        if isinstance(query_payload, Mapping):
            query = QueryResult.model_validate(query_payload)
            query_signature = json.dumps(
                [query.parameterized_sql, query.parameters],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            if query_signature in seen_queries:
                continue
            seen_queries.add(query_signature)
            queries.append(
                AnalysisQueryResult(
                    query_id=query.query_id,
                    recipe_id=query.recipe.recipe_id if query.recipe else None,
                    sql=query.parameterized_sql,
                    params=query.parameters,
                    recipe_arguments=query.recipe_arguments,
                    columns=[column.name for column in query.columns],
                    rows=[dict(row) for row in query.rows],
                    row_count=query.row_count,
                    truncated=query.truncated,
                    duration_ms=query.elapsed_ms,
                    status=query.status,
                    error_code=query.error_code,
                )
            )
            continue
        hits = tool_result.get("hits")
        backend_id = tool_result.get("backend_id")
        if not isinstance(hits, list) or not isinstance(backend_id, str):
            continue
        if backend_id not in backend_ids:
            backend_ids.append(backend_id)
        for raw_hit in hits:
            hit = RetrievalHit.model_validate(raw_hit)
            if hit.resource_type == "analysis_metadata":
                continue
            identity = (hit.resource_type, hit.resource_id)
            if identity in seen_evidence:
                continue
            seen_evidence.add(identity)
            evidence.append(
                AnalysisEvidence(
                    evidence_id=f"E{len(evidence) + 1}",
                    source_kind=(
                        "vehicle_checklist"
                        if hit.resource_type == "vehicle_checklist"
                        else "legacy_issue"
                    ),
                    title=str(hit.metadata.get("title") or hit.resource_id),
                    excerpt=hit.text[:4_000],
                    record_id=hit.resource_id,
                    revision_id=(
                        str(hit.metadata.get("revision_id"))
                        if hit.metadata.get("revision_id")
                        else None
                    ),
                    metadata={
                        **hit.metadata,
                        "score": hit.score,
                        "retrieval_hit_id": hit.hit_id,
                    },
                )
            )
    if result.status != "completed":
        agent_status = f"analysis_agent:{result.status}"
        if (
            result.status in _RECOVERABLE_AGENT_STATUSES
            and _has_required_grounded_sources(
                query_results=queries,
                evidence=evidence,
                interpretation=interpretation,
                capability_limitations=capability_limitations,
            )
        ):
            execution_warnings.append(agent_status)
        else:
            limitations.append(agent_status)
    if any(item.status == "failed" for item in queries):
        limitations.append("one_or_more_queries_failed")
    return AnalysisDataBundle(
        query_results=queries,
        evidence=evidence,
        retrieval_backend_ids=backend_ids,
        limitations=limitations,
        capability_limitations=list(dict.fromkeys(capability_limitations)),
        execution_warnings=execution_warnings,
    )


def _has_required_grounded_sources(
    *,
    query_results: Sequence[AnalysisQueryResult],
    evidence: Sequence[AnalysisEvidence],
    interpretation: AnalysisInterpretation,
    capability_limitations: Sequence[str],
) -> bool:
    """Allow bounded-agent recovery only when every requested source class exists."""

    if any(str(item).strip() for item in capability_limitations):
        return True
    successful_queries = [
        item
        for item in query_results
        if item.status == "succeeded" and bool(item.rows)
    ]
    if not successful_queries and not evidence:
        return False
    if interpretation.needs_statistics and not successful_queries:
        return False
    if interpretation.needs_semantic_evidence and not evidence:
        return False
    if interpretation.needs_checklists and not any(
        _is_checklist_query(item) for item in successful_queries
    ):
        return False
    if (
        interpretation.needs_business_data
        and not successful_queries
        and not evidence
    ):
        return False
    return True


def _is_checklist_query(result: AnalysisQueryResult) -> bool:
    recipe_id = str(result.recipe_id or "")
    return recipe_id.startswith("checklist_") or recipe_id == (
        "issue_checklist_coverage"
    )


def _supplement_required_sources(
    *,
    toolset: AnalysisToolset,
    result: AnalysisAgentResult,
    question: str,
    interpretation: AnalysisInterpretation,
) -> AnalysisAgentResult:
    """Enforce the minimum structured and semantic sources requested by intent."""

    retained_results = _retain_scope_compliant_results(
        result.tool_results,
        question=question,
    )
    rejected_structured_scope = _has_recoverable_planner_rejection(
        result.tool_results
    )
    supplements: list[dict[str, object]] = []
    if rejected_structured_scope and (
        interpretation.needs_statistics or interpretation.needs_checklists
    ):
        supplements.append(
            {"limitation_code": "structured_filter_scope_unresolved"}
        )
    if interpretation.needs_checklists and not rejected_structured_scope:
        retained_results = _retain_requested_coverage_order(
            retained_results,
            sort_direction=_coverage_sort_direction(question),
        )
        checklist_baseline = (
            ("checklist_total", {}),
            ("checklist_item_total", {}),
            ("checklist_status_summary", {}),
            (
                "checklist_item_breakdown",
                {"dimension": "checklist_status", "limit": 100},
            ),
            (
                "checklist_item_breakdown",
                {"dimension": "module_key", "limit": 100},
            ),
            (
                "issue_checklist_coverage",
                {
                    "dimension": "vehicle_model",
                    "limit": 100,
                    "sort_direction": _coverage_sort_direction(question),
                },
            ),
        )
        signatures = _query_signatures(retained_results)
        for recipe_id, parameters in checklist_baseline:
            if _recipe_signature(recipe_id, parameters) in signatures:
                continue
            try:
                supplements.append(
                    toolset.run_recipe(
                        recipe_id=recipe_id,
                        version=1,
                        parameters=parameters,
                    )
                )
            except Exception:
                continue
    if interpretation.needs_statistics:
        if not rejected_structured_scope:
            supplements.extend(
                _supplement_statistical_plan(
                    toolset=toolset,
                    tool_results=(*retained_results, *supplements),
                    question=question,
                )
            )
    supplements.extend(
        _supplement_hotspot_examples(
            toolset=toolset,
            tool_results=(*retained_results, *supplements),
            question=question,
        )
    )

    combined_results = (*retained_results, *supplements)
    if interpretation.needs_semantic_evidence and not _has_business_evidence(
        combined_results
    ):
        try:
            supplements.append(
                toolset.search_legacy_evidence(
                    question[:2_000],
                    limit=12,
                )
            )
        except Exception:
            supplements.append(
                {"limitation_code": "semantic_retrieval_failed"}
            )
    if not supplements and retained_results == result.tool_results:
        return result
    return result.model_copy(
        update={"tool_results": (*retained_results, *supplements)}
    )


def _supplement_statistical_plan(
    *,
    toolset: AnalysisToolset,
    tool_results,
    question: str,
) -> list[dict[str, object]]:
    """Fill generic dimension/period slots the bounded SQL agent did not cover."""

    dimensions = _requested_dimensions(question)
    scopes = _requested_period_scopes(question)
    if scopes is None:
        if _has_query_result(tool_results):
            return []
        scopes = ({},)

    discovery: dict[str, dict[str, object]] = {}
    filters: dict[str, object] = {}
    for dimension in dimensions:
        parameter_name = _FILTER_PARAMETER_BY_DIMENSION.get(dimension)
        if parameter_name is None:
            continue
        try:
            raw = toolset.run_recipe(
                recipe_id="issue_breakdown",
                version=1,
                parameters={"dimension": dimension, "limit": 200},
            )
        except Exception:
            continue
        discovery[dimension] = raw
        matched_values = _mentioned_dimension_values(
            raw,
            question=question,
        )
        if matched_values:
            filters[parameter_name] = matched_values

    supplements: list[dict[str, object]] = []
    signatures = _query_signatures(tool_results)

    def add(recipe_id: str, parameters: dict[str, object]) -> None:
        if len(supplements) >= 32:
            return
        signature = _recipe_signature(recipe_id, parameters)
        if signature in signatures:
            return
        try:
            raw = toolset.run_recipe(
                recipe_id=recipe_id,
                version=1,
                parameters=parameters,
            )
        except Exception:
            return
        supplements.append(raw)
        signatures.add(signature)

    for scope in scopes:
        scoped_filters = {**filters, **scope}
        add("issue_total", scoped_filters)
        for dimension in dimensions:
            parameters = {
                "dimension": dimension,
                "limit": 200,
                **scoped_filters,
            }
            unfiltered_discovery = discovery.get(dimension)
            if (
                not scoped_filters
                and unfiltered_discovery is not None
                and _recipe_signature("issue_breakdown", parameters) not in signatures
            ):
                supplements.append(unfiltered_discovery)
                signatures.add(_recipe_signature("issue_breakdown", parameters))
            else:
                add("issue_breakdown", parameters)
            add(
                "issue_ranked_summary",
                {
                    "dimension": dimension,
                    "top_n": _requested_top_n(question),
                    **scoped_filters,
                },
            )
        for row_dimension, column_dimension in combinations(dimensions, 2):
            add(
                "issue_matrix",
                {
                    "row_dimension": row_dimension,
                    "column_dimension": column_dimension,
                    "limit": 500,
                    **scoped_filters,
                },
            )
        representative = _representative_dimension(question, dimensions)
        cube_roles = (
            (
                row_dimension,
                column_dimension,
                representative,
            )
            for row_dimension, column_dimension in combinations(
                tuple(
                    dimension
                    for dimension in dimensions
                    if dimension != representative
                ),
                2,
            )
        ) if representative is not None else combinations(dimensions, 3)
        for row_dimension, column_dimension, detail_dimension in cube_roles:
            add(
                "issue_cube",
                {
                    "row_dimension": row_dimension,
                    "column_dimension": column_dimension,
                    "detail_dimension": detail_dimension,
                    "limit": 500,
                    **scoped_filters,
                },
            )

    if len(scopes) == 2:
        first, second = scopes
        add(
            "issue_period_comparison",
            {
                "period_a_from": first["date_from"],
                "period_a_to": first["date_to"],
                "period_b_from": second["date_from"],
                "period_b_to": second["date_to"],
                **filters,
            },
        )
    return supplements


def _representative_dimension(
    question: str,
    dimensions: tuple[str, ...],
) -> str | None:
    normalized = "".join(question.casefold().split())
    for dimension, terms in _DIMENSION_TERMS:
        if dimension not in dimensions:
            continue
        if any(
            f"대표{''.join(term.casefold().split())}" in normalized
            for term in terms
        ):
            return dimension
    return None


def _supplement_hotspot_examples(
    *,
    toolset: AnalysisToolset,
    tool_results,
    question: str,
) -> list[dict[str, object]]:
    normalized = "".join(question.casefold().split())
    if not any(term in normalized for term in ("사례", "대책", "원인")):
        return []
    signatures = _query_signatures(tool_results)
    supplements: list[dict[str, object]] = []
    max_groups = min(_requested_top_n(question), 10)
    for tool_result in tool_results:
        query = tool_result.get("result")
        if not isinstance(query, Mapping):
            continue
        recipe = query.get("recipe")
        recipe_id = (
            str(recipe.get("recipe_id") or "")
            if isinstance(recipe, Mapping)
            else ""
        )
        if recipe_id != "issue_supplier_part_hotspots":
            continue
        arguments = query.get("recipe_arguments")
        if not isinstance(arguments, Mapping):
            arguments = query.get("parameters")
        scope_arguments = (
            {
                key: arguments[key]
                for key in (
                    "date_from",
                    "date_to",
                    "vehicle_models",
                    "regions",
                    "module_keys",
                    "query_text",
                )
                if key in arguments
            }
            if isinstance(arguments, Mapping)
            else {}
        )
        for row in list(query.get("rows") or ())[:max_groups]:
            if not isinstance(row, Mapping):
                continue
            parameters: dict[str, object] = {**scope_arguments, "limit": 2}
            supplier = str(row.get("supplier") or "").strip()
            part_number = str(row.get("part_number") or "").strip()
            if bool(row.get("supplier_missing")) or not supplier:
                parameters["supplier_missing"] = True
            else:
                parameters["suppliers"] = [supplier]
            if bool(row.get("part_number_missing")) or not part_number:
                parameters["part_number_missing"] = True
            else:
                parameters["part_numbers"] = [part_number]
            signature = _recipe_signature("issue_details", parameters)
            if signature in signatures:
                continue
            try:
                supplements.append(
                    toolset.run_recipe(
                        recipe_id="issue_details",
                        version=1,
                        parameters=parameters,
                    )
                )
            except Exception:
                continue
            signatures.add(signature)
    return supplements


def _requested_capability_limitations(question: str) -> list[str]:
    normalized = "".join(question.casefold().split())
    final_countermeasure_terms = (
        "최종대책일",
        "최종대책완료일",
        "대책완료일",
        "최종조치일",
        "조치완료일",
    )
    duration_terms = ("소요기간", "대응기간", "며칠", "평균", "중앙값", "최장")
    if any(term in normalized for term in final_countermeasure_terms) and any(
        term in normalized for term in duration_terms
    ):
        return [
            "현재 분석 데이터에는 최종 대책일 또는 대책 완료일 컬럼이 없어 "
            "문제 발생일부터 최종 대책일까지의 소요기간, 평균·중앙값·최장값, "
            "장기 대응 건을 계산할 수 없습니다. 접수일 등 다른 날짜로 대체하지 "
            "않았습니다."
        ]
    return []


def _retain_scope_compliant_results(tool_results, *, question: str):
    normalized = "".join(question.casefold().split())
    has_explicit_period = bool(_YEAR_RE.search(question)) or any(
        term in normalized for term in _RELATIVE_PERIOD_TERMS
    )
    retained = []
    for tool_result in tool_results:
        query = tool_result.get("result")
        if not isinstance(query, Mapping):
            retained.append(tool_result)
            continue
        if (
            str(query.get("status") or "") == "failed"
            and str(query.get("error_code") or "")
            in _RECOVERABLE_PLANNER_REJECTION_CODES
        ):
            continue
        parameters = query.get("parameters")
        sql = str(query.get("parameterized_sql") or "")
        has_date_parameter = isinstance(parameters, Mapping) and any(
            key in parameters for key in ("date_from", "date_to")
        )
        has_date_literal = bool(re.search(r"(?:19|20)\d{2}-\d{2}-\d{2}", sql))
        if (
            has_explicit_period
            or (not has_date_parameter and not has_date_literal)
        ):
            retained.append(tool_result)
    return tuple(retained)


def _has_recoverable_planner_rejection(tool_results) -> bool:
    return any(
        isinstance(item.get("result"), Mapping)
        and str(item["result"].get("status") or "") == "failed"
        and str(item["result"].get("error_code") or "")
        in _RECOVERABLE_PLANNER_REJECTION_CODES
        for item in tool_results
    )


def _retain_requested_coverage_order(
    tool_results,
    *,
    sort_direction: str,
):
    retained = []
    expected_order = f"coverage_rate {sort_direction}".casefold()
    for tool_result in tool_results:
        query = tool_result.get("result")
        if not isinstance(query, Mapping):
            retained.append(tool_result)
            continue
        recipe = query.get("recipe")
        recipe_id = (
            str(recipe.get("recipe_id") or "")
            if isinstance(recipe, Mapping)
            else ""
        )
        if recipe_id != "issue_checklist_coverage":
            retained.append(tool_result)
            continue
        sql = str(query.get("parameterized_sql") or "").casefold()
        if expected_order in sql:
            retained.append(tool_result)
    return tuple(retained)


def _requested_dimensions(question: str) -> tuple[str, ...]:
    normalized = "".join(question.casefold().split())
    return tuple(
        dimension
        for dimension, terms in _DIMENSION_TERMS
        if any("".join(term.casefold().split()) in normalized for term in terms)
    )


def _requested_period_scopes(
    question: str,
) -> tuple[dict[str, str], ...] | None:
    years = tuple(dict.fromkeys(int(value) for value in _YEAR_RE.findall(question)))
    if not years:
        normalized = "".join(question.casefold().split())
        if any(term in normalized for term in _RELATIVE_PERIOD_TERMS):
            return None
        return ({},)
    if len(years) == 1:
        return (_year_scope(years[0]),)
    if len(years) == 2:
        normalized = "".join(question.casefold().split())
        if any(term in normalized for term in ("부터", "까지", "사이", "~")):
            start, end = min(years), max(years)
            return (
                {
                    "date_from": f"{start:04d}-01-01",
                    "date_to": f"{end:04d}-12-31",
                },
            )
        return tuple(_year_scope(year) for year in years)
    return None


def _year_scope(year: int) -> dict[str, str]:
    return {
        "date_from": f"{year:04d}-01-01",
        "date_to": f"{year:04d}-12-31",
    }


def _requested_top_n(question: str) -> int:
    match = _TOP_N_RE.search(question)
    if match is None:
        return 10
    return min(max(int(match.group(1)), 1), 100)


def _coverage_sort_direction(question: str) -> str:
    normalized = "".join(question.casefold().split())
    return (
        "ASC"
        if any(
            term in normalized
            for term in ("낮은", "낮게", "저반영", "미반영", "취약", "하위")
        )
        else "DESC"
    )


def _mentioned_dimension_values(
    tool_result: Mapping[str, object],
    *,
    question: str,
) -> list[str]:
    query = tool_result.get("result")
    if not isinstance(query, Mapping):
        return []
    normalized_question = question.casefold()
    candidates: list[tuple[str, tuple[tuple[int, int], ...]]] = []
    for row in query.get("rows") or ():
        if not isinstance(row, Mapping):
            continue
        value = str(row.get("dimension_value") or "").strip()
        if len(value) < 2:
            continue
        spans = tuple(
            match.span()
            for match in re.finditer(
                re.escape(value.casefold()),
                normalized_question,
            )
        )
        if spans:
            candidates.append((value, spans))
    selected: list[str] = []
    occupied: list[tuple[int, int]] = []
    for value, spans in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        uncovered = [
            span
            for span in spans
            if not any(start <= span[0] and span[1] <= end for start, end in occupied)
        ]
        if not uncovered:
            continue
        selected.append(value)
        occupied.extend(uncovered)
    return list(dict.fromkeys(selected))


def _query_signatures(tool_results) -> set[str]:
    signatures: set[str] = set()
    for tool_result in tool_results:
        query = tool_result.get("result")
        if not isinstance(query, Mapping):
            continue
        recipe = query.get("recipe")
        if not isinstance(recipe, Mapping):
            continue
        recipe_id = str(recipe.get("recipe_id") or "")
        parameters = query.get("recipe_arguments")
        if not isinstance(parameters, Mapping):
            parameters = query.get("parameters")
        if recipe_id and isinstance(parameters, Mapping):
            signatures.add(_recipe_signature(recipe_id, dict(parameters)))
    return signatures


def _recipe_signature(recipe_id: str, parameters: Mapping[str, object]) -> str:
    return json.dumps(
        [recipe_id, parameters],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _has_query_result(tool_results) -> bool:
    return any(
        isinstance(item.get("result"), Mapping)
        and str(item["result"].get("status") or "succeeded") == "succeeded"
        for item in tool_results
    )


def _has_business_evidence(tool_results) -> bool:
    for tool_result in tool_results:
        hits = tool_result.get("hits")
        if not isinstance(hits, list):
            continue
        if any(
            isinstance(hit, Mapping)
            and hit.get("resource_type") != "analysis_metadata"
            for hit in hits
        ):
            return True
    return False


__all__ = [
    "LangChainLegacyIssueDataProvider",
    "LegacyIssueAnalysisRuntimeResolver",
]
