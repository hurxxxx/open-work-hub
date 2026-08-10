from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Any

from sqlalchemy import (
    Date,
    Numeric,
    Text,
    and_,
    case,
    cast,
    distinct,
    false,
    func,
    literal,
    not_,
    or_,
    select,
    tuple_,
)
from sqlalchemy.orm import Session

from ai_do_api.domains.legacy_issues.analysis_catalog import (
    AnalysisFieldCapabilities,
    FamilyExecutionKind,
    QueryFamilyDescriptor,
    build_analysis_field_catalog,
    validate_query_request,
)
from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisColumnV1,
    AnalysisCountingUnit,
    AnalysisCoverageV1,
    AnalysisDataSource,
    AnalysisMode,
    AnalysisPlanV1,
    AnalysisResultV1,
    AnalysisScopeV1,
    DimensionSpecV1,
    Exactness,
    FilterConditionV1,
    FilterGroupV1,
    FilterJunction,
    FilterOperator,
    LegacyIssueAnalysisArtifactV1,
    LegacyIssuePlannerDiagnosticsV1,
    MetricOperator,
    MetricSpecV1,
    QueryFamilyId,
    QueryRequestV1,
    SortDirection,
    TimeGrain,
    ValueMatchMode,
    WindowOperator,
    WindowSpecV1,
)
from ai_do_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    COMMON_MASTER_FIELDS,
    PROJECTED_RECORD_FIELD_KEYS,
    DatasetFieldDefinition,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueAttachment,
    LegacyIssueDataRevision,
    LegacyIssueRecord,
    LegacyIssueVehicleModel,
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleModuleChecklistRecord,
    LegacyIssueVehicleStage,
)
from ai_do_api.domains.legacy_issues.module_access import LEGACY_ISSUE_MODULE_KEYS
from ai_do_api.domains.legacy_issues.revisioning import (
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    legacy_issue_dataset_revision_key,
)
from ai_do_api.domains.retrieval.partitioning import resolve_read_scope


NULL_GROUP_LABEL = "미입력"
DETAIL_RESULT_LIMIT = 200
AGGREGATE_RESULT_LIMIT = 500
_SUPPORTED_DIALECTS = frozenset({"postgresql", "sqlite"})
CHECKLIST_ANALYSIS_FIELDS = (
    DatasetFieldDefinition(
        key="checklist_id",
        label_ko="차량 체크리스트 ID",
        label_en="Vehicle Checklist ID",
        aliases=("체크리스트", "체크리스트 번호"),
        readonly=True,
    ),
    DatasetFieldDefinition(
        key="checklist_vehicle_code",
        label_ko="체크리스트 차량 코드",
        label_en="Checklist Vehicle Code",
        aliases=("차량 코드", "대상 차량"),
        readonly=True,
    ),
    DatasetFieldDefinition(
        key="checklist_vehicle_name",
        label_ko="체크리스트 차량명",
        label_en="Checklist Vehicle Name",
        aliases=("차량명", "대상 차종"),
        readonly=True,
    ),
    DatasetFieldDefinition(
        key="checklist_status",
        label_ko="체크리스트 상태",
        label_en="Checklist Status",
        aliases=("완료 상태", "진행 상태"),
        field_type="select",
        options=("draft", "completed"),
        readonly=True,
    ),
    DatasetFieldDefinition(
        key="checklist_module",
        label_ko="체크리스트 모듈",
        label_en="Checklist Module",
        aliases=("대상 모듈",),
        readonly=True,
    ),
    DatasetFieldDefinition(
        key="checklist_source_revision_no",
        label_ko="체크리스트 원본 리비전",
        label_en="Checklist Source Revision",
        aliases=("원본 Rev", "마스터 Rev"),
        field_type="number",
        readonly=True,
    ),
    DatasetFieldDefinition(
        key="checklist_updated_date",
        label_ko="체크리스트 갱신일",
        label_en="Checklist Updated Date",
        aliases=("체크리스트 수정일",),
        field_type="date",
        readonly=True,
    ),
)
_CHECKLIST_PROJECTED_FIELD_KEYS = frozenset(field.key for field in CHECKLIST_ANALYSIS_FIELDS)
_RESERVED_LOGICAL_COLUMNS = frozenset(
    {
        "record_id",
        "stable_record_id",
        "module_key",
        "revision_id",
        "retrieval_partition_id",
    }
)
_RAW_PRESENT_COLUMN_PREFIX = "__analysis_raw_present__"


class AnalysisSqlError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CompiledAnalysisQuery:
    statement: Any
    descriptor: QueryFamilyDescriptor
    columns: tuple[AnalysisColumnV1, ...]
    referenced_field_keys: tuple[str, ...]
    result_limit: int


def resolve_analysis_scope(
    db: Session,
    *,
    workspace_id: str,
    enabled_module_keys: Iterable[str] | None,
    retrieval_partition_ids: Iterable[str] | None = None,
    data_sources: Iterable[AnalysisDataSource] | None = None,
) -> AnalysisScopeV1:
    """Snapshot only the requested data sources for every enabled module."""

    normalized_data_sources = tuple(
        dict.fromkeys(
            AnalysisDataSource(data_source)
            for data_source in (
                data_sources if data_sources is not None else (AnalysisDataSource.LEGACY_ISSUES,)
            )
        )
    ) or (AnalysisDataSource.LEGACY_ISSUES,)
    normalized_modules = tuple(
        sorted(
            {
                str(module_key).strip()
                for module_key in (
                    enabled_module_keys
                    if enabled_module_keys is not None
                    else LEGACY_ISSUE_MODULE_KEYS
                )
                if str(module_key).strip()
            }
        )
    )
    unknown_modules = set(normalized_modules).difference(LEGACY_ISSUE_MODULE_KEYS)
    if unknown_modules:
        raise AnalysisSqlError(
            f"unknown or disabled legacy issue modules: {sorted(unknown_modules)}"
        )
    if (
        retrieval_partition_ids is None
        and AnalysisDataSource.LEGACY_ISSUES in normalized_data_sources
    ):
        partition_ids = tuple(
            str(partition_id)
            for partition_id in resolve_read_scope(
                db,
                source_namespaces=["legacy_issues"],
                workspace_id=workspace_id,
                user_id=None,
            ).for_source("legacy_issues")
        )
    elif retrieval_partition_ids is not None:
        partition_ids = tuple(
            sorted(
                {
                    str(partition_id).strip()
                    for partition_id in retrieval_partition_ids
                    if str(partition_id).strip()
                }
            )
        )
    else:
        partition_ids = ()

    revision_keys = {
        module_key: legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            module_key,
        )
        for module_key in normalized_modules
    }
    if not revision_keys:
        return AnalysisScopeV1(
            workspace_id=workspace_id,
            data_sources=normalized_data_sources,
            module_keys=(),
            revision_ids=(),
            revision_by_module={},
            retrieval_partition_ids=partition_ids,
        )

    revisions: list[LegacyIssueDataRevision] = []
    if AnalysisDataSource.LEGACY_ISSUES in normalized_data_sources:
        partition_predicate = _partition_compatibility_predicate(
            LegacyIssueDataRevision.retrieval_partition_id,
            partition_ids,
        )
        revisions = list(
            db.scalars(
                select(LegacyIssueDataRevision).where(
                    LegacyIssueDataRevision.workspace_id == workspace_id,
                    LegacyIssueDataRevision.dataset_key.in_(tuple(revision_keys.values())),
                    LegacyIssueDataRevision.status.in_(
                        (REVISION_STATUS_DRAFT, REVISION_STATUS_PUBLISHED)
                    ),
                    partition_predicate,
                )
            )
        )
    candidates_by_key: dict[str, list[LegacyIssueDataRevision]] = {}
    for revision in revisions:
        candidates_by_key.setdefault(revision.dataset_key, []).append(revision)

    revision_by_module: dict[str, str] = {}
    for module_key, revision_key in revision_keys.items():
        candidates = candidates_by_key.get(revision_key, ())
        if not candidates:
            continue
        selected = max(candidates, key=_effective_revision_sort_key)
        revision_by_module[module_key] = selected.id
    checklist_rows: list[LegacyIssueVehicleModuleChecklist] = []
    if AnalysisDataSource.VEHICLE_CHECKLISTS in normalized_data_sources:
        latest_stage_sequences = (
            select(
                LegacyIssueVehicleStage.vehicle_model_id.label("vehicle_model_id"),
                func.max(LegacyIssueVehicleStage.sequence_no).label("sequence_no"),
            )
            .where(LegacyIssueVehicleStage.workspace_id == workspace_id)
            .group_by(LegacyIssueVehicleStage.vehicle_model_id)
            .subquery()
        )
        checklist_rows = list(
            db.scalars(
                select(LegacyIssueVehicleModuleChecklist)
                .join(
                    LegacyIssueVehicleModel,
                    and_(
                        LegacyIssueVehicleModel.id
                        == LegacyIssueVehicleModuleChecklist.vehicle_model_id,
                        LegacyIssueVehicleModel.workspace_id == workspace_id,
                        LegacyIssueVehicleModel.workspace_id
                        == LegacyIssueVehicleModuleChecklist.workspace_id,
                    ),
                )
                .join(
                    LegacyIssueVehicleStage,
                    and_(
                        LegacyIssueVehicleStage.id
                        == LegacyIssueVehicleModuleChecklist.vehicle_stage_id,
                        LegacyIssueVehicleStage.workspace_id == workspace_id,
                        LegacyIssueVehicleStage.workspace_id
                        == LegacyIssueVehicleModuleChecklist.workspace_id,
                    ),
                )
                .join(
                    latest_stage_sequences,
                    and_(
                        latest_stage_sequences.c.vehicle_model_id
                        == LegacyIssueVehicleStage.vehicle_model_id,
                        latest_stage_sequences.c.sequence_no == LegacyIssueVehicleStage.sequence_no,
                    ),
                )
                .where(
                    LegacyIssueVehicleModuleChecklist.workspace_id == workspace_id,
                    LegacyIssueVehicleModuleChecklist.module_key.in_(normalized_modules),
                    LegacyIssueVehicleModuleChecklist.status.in_(("draft", "completed")),
                )
            )
        )
    latest_checklists: dict[tuple[str, str], LegacyIssueVehicleModuleChecklist] = {}
    for checklist in checklist_rows:
        key = (checklist.vehicle_model_id, checklist.module_key)
        current = latest_checklists.get(key)
        if current is None or _checklist_sort_key(checklist) > _checklist_sort_key(current):
            latest_checklists[key] = checklist
    checklist_ids = tuple(
        checklist.id
        for _key, checklist in sorted(
            latest_checklists.items(),
            key=lambda item: (item[0][1], item[0][0]),
        )
    )
    return AnalysisScopeV1(
        workspace_id=workspace_id,
        data_sources=normalized_data_sources,
        module_keys=normalized_modules,
        revision_ids=tuple(
            revision_by_module[module_key]
            for module_key in normalized_modules
            if module_key in revision_by_module
        ),
        revision_by_module=revision_by_module,
        checklist_ids=checklist_ids,
        retrieval_partition_ids=partition_ids,
    )


def build_scoped_records_relation(scope: AnalysisScopeV1) -> Any:
    """Build the physical scope relation shared by catalog and generated execution."""

    module_revision_predicates = [
        and_(
            LegacyIssueRecord.module_key == module_key,
            LegacyIssueRecord.revision_id == revision_id,
        )
        for module_key, revision_id in scope.revision_by_module.items()
    ]
    effective_revision_predicate = (
        or_(*module_revision_predicates) if module_revision_predicates else false()
    )
    return (
        select(LegacyIssueRecord.__table__)
        .where(
            LegacyIssueRecord.workspace_id == scope.workspace_id,
            LegacyIssueRecord.dataset_key == scope.dataset_key,
            effective_revision_predicate,
            _partition_compatibility_predicate(
                LegacyIssueRecord.retrieval_partition_id,
                scope.retrieval_partition_ids,
            ),
        )
        .cte("_scoped_legacy_issue_records")
    )


def build_scoped_vehicle_checklist_records_relation(scope: AnalysisScopeV1) -> Any:
    """Build the latest per-vehicle/module checklist record relation."""

    return (
        select(
            LegacyIssueVehicleModuleChecklistRecord.id.label("id"),
            LegacyIssueVehicleModuleChecklistRecord.id.label("stable_record_id"),
            LegacyIssueVehicleModuleChecklist.module_key.label("module_key"),
            LegacyIssueVehicleModuleChecklist.id.label("revision_id"),
            LegacyIssueVehicleModuleChecklistRecord.field_values.label("field_values"),
            LegacyIssueVehicleModuleChecklist.id.label("checklist_id"),
            LegacyIssueVehicleModel.vehicle_code.label("checklist_vehicle_code"),
            func.coalesce(
                LegacyIssueVehicleModel.vehicle_name,
                LegacyIssueVehicleModel.vehicle_code,
            ).label("checklist_vehicle_name"),
            LegacyIssueVehicleModuleChecklist.status.label("checklist_status"),
            LegacyIssueVehicleModuleChecklist.module_key.label("checklist_module"),
            LegacyIssueVehicleModuleChecklist.source_master_revision_no.label(
                "checklist_source_revision_no"
            ),
            cast(
                func.date(LegacyIssueVehicleModuleChecklist.updated_at),
                Text,
            ).label("checklist_updated_date"),
        )
        .join(
            LegacyIssueVehicleModuleChecklist,
            and_(
                LegacyIssueVehicleModuleChecklist.id
                == LegacyIssueVehicleModuleChecklistRecord.checklist_id,
                LegacyIssueVehicleModuleChecklist.workspace_id == scope.workspace_id,
                LegacyIssueVehicleModuleChecklist.workspace_id
                == LegacyIssueVehicleModuleChecklistRecord.workspace_id,
            ),
        )
        .join(
            LegacyIssueVehicleModel,
            and_(
                LegacyIssueVehicleModel.id == LegacyIssueVehicleModuleChecklist.vehicle_model_id,
                LegacyIssueVehicleModel.workspace_id == scope.workspace_id,
                LegacyIssueVehicleModel.workspace_id
                == LegacyIssueVehicleModuleChecklist.workspace_id,
            ),
        )
        .where(
            LegacyIssueVehicleModuleChecklistRecord.workspace_id == scope.workspace_id,
            LegacyIssueVehicleModuleChecklistRecord.checklist_id.in_(scope.checklist_ids)
            if scope.checklist_ids
            else false(),
            LegacyIssueVehicleModuleChecklist.module_key.in_(scope.module_keys)
            if scope.module_keys
            else false(),
        )
        .cte("_scoped_vehicle_checklist_records")
    )


def build_visible_records_relation(
    scope: AnalysisScopeV1,
    *,
    field_definitions: Iterable[DatasetFieldDefinition] = COMMON_MASTER_FIELDS,
    dialect_name: str,
    field_keys: Iterable[str] | None = None,
    include_generated_helpers: bool = False,
    data_source: AnalysisDataSource = AnalysisDataSource.LEGACY_ISSUES,
) -> Any:
    """Expose a scoped, typed logical relation without physical table access.

    The returned CTE is deliberately named ``visible_records`` so a guarded
    generated-SQL runner can expose exactly this relation and nothing else.
    """

    _require_supported_dialect(dialect_name)
    fields = build_analysis_field_catalog(field_definitions)
    selected_field_keys = (
        tuple(fields)
        if field_keys is None
        else tuple(dict.fromkeys(str(field_key) for field_key in field_keys))
    )
    for field_key in selected_field_keys:
        if field_key in _RESERVED_LOGICAL_COLUMNS:
            raise AnalysisSqlError(f"analysis field collides with reserved column: {field_key}")
        if field_key not in fields:
            raise AnalysisSqlError(f"unknown or inactive analysis field: {field_key}")

    scoped = (
        build_scoped_vehicle_checklist_records_relation(scope)
        if data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
        else build_scoped_records_relation(scope)
    )
    columns = [
        scoped.c.id.label("record_id"),
        scoped.c.stable_record_id.label("stable_record_id"),
        scoped.c.module_key.label("module_key"),
        scoped.c.revision_id.label("revision_id"),
    ]
    for field_key in selected_field_keys:
        capabilities = fields[field_key]
        raw_value = _raw_field_expression(
            scoped,
            capabilities=capabilities,
            dialect_name=dialect_name,
        )
        columns.append(_is_present(raw_value).label(_raw_present_column_key(field_key)))
        columns.append(
            _typed_field_expression(
                scoped,
                capabilities=capabilities,
                dialect_name=dialect_name,
            ).label(field_key)
        )
    if include_generated_helpers:
        if dialect_name != "postgresql":
            raise AnalysisSqlError("generated analysis helpers require PostgreSQL")
        columns.extend(
            _safe_generated_date_expression(
                scoped,
                capabilities=fields[field_key],
            ).label(f"{field_key}__date")
            for field_key in selected_field_keys
            if fields[field_key].field.field_type == "date"
        )
    return select(*columns).select_from(scoped).cte("visible_records")


def compile_analysis_query(
    request: QueryRequestV1,
    *,
    scope: AnalysisScopeV1,
    field_definitions: Iterable[DatasetFieldDefinition] = COMMON_MASTER_FIELDS,
    dialect_name: str,
) -> CompiledAnalysisQuery:
    _require_supported_dialect(dialect_name)
    definitions = tuple(field_definitions)
    fields = build_analysis_field_catalog(definitions)
    descriptor = validate_query_request(request, fields=fields)
    if descriptor.execution_kind in {
        FamilyExecutionKind.METADATA,
        FamilyExecutionKind.SEMANTIC,
        FamilyExecutionKind.GENERATED,
        FamilyExecutionKind.COMPOSITE,
    }:
        raise AnalysisSqlError(f"{descriptor.ref} is not a structured SQL family")

    referenced_field_keys = _referenced_field_keys(request)
    visible_records = build_visible_records_relation(
        scope,
        field_definitions=definitions,
        dialect_name=dialect_name,
        field_keys=referenced_field_keys,
        data_source=request.data_source,
    )
    if descriptor.execution_kind == FamilyExecutionKind.DETAIL:
        statement, columns = _compile_detail_statement(
            request,
            descriptor=descriptor,
            visible_records=visible_records,
            fields=fields,
            dialect_name=dialect_name,
        )
        result_limit = min(request.limit, DETAIL_RESULT_LIMIT)
    else:
        statement, columns = _compile_aggregate_statement(
            request,
            descriptor=descriptor,
            visible_records=visible_records,
            fields=fields,
            dialect_name=dialect_name,
        )
        # Default aggregate limits are transport hints, not row semantics.
        # Explicit global rankings and a non-default limit with time ordering
        # are bounded requests (Top-N, latest-N, or earliest-N).
        result_limit = (
            min(request.limit, AGGREGATE_RESULT_LIMIT)
            if _uses_semantic_aggregate_limit(request)
            else AGGREGATE_RESULT_LIMIT
        )
    return CompiledAnalysisQuery(
        statement=statement.limit(result_limit + 1),
        descriptor=descriptor,
        columns=columns,
        referenced_field_keys=referenced_field_keys,
        result_limit=result_limit,
    )


def _uses_semantic_aggregate_limit(request: QueryRequestV1) -> bool:
    if request.family_id == QueryFamilyId.TOP_BOTTOM_N:
        return True
    time_aliases = {
        dimension.alias or dimension.field_key
        for dimension in request.dimensions
        if dimension.time_grain is not None
    }
    return bool(
        "limit" in request.model_fields_set and request.sort and request.sort[0].key in time_aliases
    )


def execute_analysis_query(
    db: Session,
    request: QueryRequestV1,
    *,
    scope: AnalysisScopeV1,
    field_definitions: Iterable[DatasetFieldDefinition] = COMMON_MASTER_FIELDS,
    title: str | None = None,
) -> AnalysisResultV1:
    definitions = tuple(field_definitions)
    fields = build_analysis_field_catalog(definitions)
    descriptor = validate_query_request(request, fields=fields)
    query_source_count = _source_count(
        db,
        scope,
        data_source=request.data_source,
    )
    query_scope = scope.model_copy(
        update={
            "data_sources": (request.data_source,),
            "source_count": query_source_count,
            "source_counts": {request.data_source: query_source_count},
        }
    )
    if descriptor.execution_kind == FamilyExecutionKind.METADATA:
        if request.data_source != AnalysisDataSource.LEGACY_ISSUES:
            raise AnalysisSqlError(
                "metadata query families currently require legacy_issues data_source"
            )
        rows, columns, truncated = _execute_metadata_query(
            db,
            request,
            descriptor=descriptor,
            fields=fields,
            scope=query_scope,
        )
        referenced_field_keys = _referenced_field_keys(request)
        filtered_population_count = query_source_count
        population_count = query_source_count
    else:
        compiled = compile_analysis_query(
            request,
            scope=query_scope,
            field_definitions=definitions,
            dialect_name=db.get_bind().dialect.name,
        )
        raw_rows = list(db.execute(compiled.statement).mappings())
        truncated = len(raw_rows) > compiled.result_limit
        rows = tuple(
            {key: _normalize_result_value(value) for key, value in row.items()}
            for row in raw_rows[: compiled.result_limit]
        )
        if _uses_default_chronological_order(request):
            rows = tuple(
                sorted(
                    rows,
                    key=lambda row: _chronological_result_key(request, row),
                )
            )
        columns = compiled.columns
        referenced_field_keys = compiled.referenced_field_keys
        include_dimension_constraints = descriptor.execution_kind in {
            FamilyExecutionKind.AGGREGATE,
            FamilyExecutionKind.HYBRID,
        } and any(
            dimension.time_grain is not None
            or dimension.numeric_bucket_size is not None
            or fields[dimension.field_key].field.field_type in {"number", "date"}
            for dimension in request.dimensions
        )
        filtered_population_count = _query_population_count(
            db,
            request=request,
            scope=query_scope,
            fields=fields,
            field_definitions=definitions,
            include_dimension_constraints=False,
        )
        population_count = (
            _query_population_count(
                db,
                request=request,
                scope=query_scope,
                fields=fields,
                field_definitions=definitions,
                include_dimension_constraints=True,
            )
            if include_dimension_constraints
            else filtered_population_count
        )

    coverage = _compute_coverage(
        db,
        scope=query_scope,
        fields=fields,
        field_keys=referenced_field_keys,
        data_source=request.data_source,
        request=(request if descriptor.execution_kind != FamilyExecutionKind.METADATA else None),
        field_definitions=definitions,
        include_dimension_constraints=False,
    )
    warnings: list[str] = []
    if request.data_source == AnalysisDataSource.LEGACY_ISSUES and not query_scope.revision_ids:
        warnings.append("활성 과거차 리비전이 없어 결과가 비어 있습니다.")
    if (
        request.data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
        and not query_scope.checklist_ids
    ):
        warnings.append("활성 차량 체크리스트가 없어 결과가 비어 있습니다.")
    invalid_fields = [item.label for item in coverage if item.invalid_count]
    if invalid_fields:
        warnings.append(
            "필드 형식과 맞지 않는 값은 집계에서 제외했습니다: " + ", ".join(invalid_fields)
        )
    totals: dict[str, Any] = {
        "source_count": query_scope.source_count,
        "base_population_count": query_scope.source_count,
        "filtered_population_count": filtered_population_count,
        "population_count": population_count,
    }
    if not request.dimensions and rows:
        for metric in request.metrics:
            if metric.alias in rows[0] and metric.alias not in totals:
                totals[metric.alias] = rows[0].get(metric.alias)
    return AnalysisResultV1(
        query_id=request.query_id,
        title=title or _default_query_title(request, descriptor=descriptor, fields=fields),
        family_id=request.family_id,
        family_version=request.family_version,
        exactness=Exactness.EXACT,
        output_shape=descriptor.output_shape,
        scope=query_scope,
        population_unit=_population_unit(request.data_source),
        counting_unit=_counting_unit(request),
        columns=columns,
        rows=rows,
        totals=totals,
        coverage=coverage,
        warnings=tuple(warnings),
        truncated=truncated,
    )


def _uses_default_chronological_order(request: QueryRequestV1) -> bool:
    return not request.sort and any(
        dimension.time_grain is not None for dimension in request.dimensions
    )


def _chronological_result_key(
    request: QueryRequestV1,
    row: Mapping[str, Any],
) -> tuple[str, ...]:
    dimensions = (
        *(dimension for dimension in request.dimensions if dimension.time_grain is None),
        *(dimension for dimension in request.dimensions if dimension.time_grain is not None),
    )
    return tuple(
        str(row.get(dimension.alias or dimension.field_key) or "") for dimension in dimensions
    )


def _population_unit(data_source: AnalysisDataSource) -> AnalysisCountingUnit:
    return (
        AnalysisCountingUnit.CHECKLIST_ITEMS
        if data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
        else AnalysisCountingUnit.LEGACY_RECORDS
    )


def _counting_unit(request: QueryRequestV1) -> AnalysisCountingUnit | None:
    units: set[AnalysisCountingUnit] = set()
    for metric in request.metrics:
        if metric.operator in {
            MetricOperator.ISSUE_COUNT,
            MetricOperator.PRESENT_COUNT,
            MetricOperator.MISSING_COUNT,
        }:
            units.add(_population_unit(request.data_source))
        elif (
            request.data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
            and metric.operator == MetricOperator.DISTINCT_COUNT
            and metric.field_key == "checklist_id"
        ):
            units.add(AnalysisCountingUnit.CHECKLISTS)
        else:
            return None
    return next(iter(units)) if len(units) == 1 else None


def _default_query_title(
    request: QueryRequestV1,
    *,
    descriptor: QueryFamilyDescriptor,
    fields: Mapping[str, AnalysisFieldCapabilities],
) -> str:
    dimension_labels = [
        fields[dimension.field_key].field.label_ko for dimension in request.dimensions
    ]
    if not dimension_labels:
        return descriptor.purpose
    return f"{' × '.join(dimension_labels)} · {descriptor.purpose}"


def execute_analysis_plan(
    db: Session,
    plan: AnalysisPlanV1,
    *,
    workspace_id: str,
    enabled_module_keys: Iterable[str] | None,
    field_definitions: Iterable[DatasetFieldDefinition] = COMMON_MASTER_FIELDS,
    retrieval_partition_ids: Iterable[str] | None = None,
    title: str = "과거차 문제점 분석",
    query_titles: Mapping[str, str] | None = None,
    planner_diagnostics: LegacyIssuePlannerDiagnosticsV1 | None = None,
) -> LegacyIssueAnalysisArtifactV1:
    definitions = tuple(field_definitions)
    data_sources = tuple(dict.fromkeys(request.data_source for request in plan.queries))
    scope = resolve_analysis_scope(
        db,
        workspace_id=workspace_id,
        enabled_module_keys=enabled_module_keys,
        retrieval_partition_ids=retrieval_partition_ids,
        data_sources=data_sources or (AnalysisDataSource.LEGACY_ISSUES,),
    )
    source_counts = {
        data_source: _source_count(db, scope, data_source=data_source)
        for data_source in data_sources
    }
    source_count = sum(source_counts.values())
    filter_payloads: tuple[dict[str, Any], ...] = ()
    if len(plan.queries) == 1:
        request = plan.queries[0]
        payloads: list[dict[str, Any]] = []
        if request.filters is not None:
            payloads.extend(
                condition.model_dump(mode="json")
                for condition in _flatten_filter_conditions(request.filters)
            )
        if request.record_set is not None:
            payloads.append(
                {
                    "record_set": request.record_set.model_dump(mode="json"),
                }
            )
        filter_payloads = tuple(payloads)
    date_fields = {
        dimension.field_key
        for request in plan.queries
        for dimension in request.dimensions
        if dimension.time_grain is not None
    }
    scope = scope.model_copy(
        update={
            "source_count": source_count,
            "source_counts": source_counts,
            "data_sources": data_sources or (AnalysisDataSource.LEGACY_ISSUES,),
            "filters": filter_payloads,
            "date_field": next(iter(date_fields)) if len(date_fields) == 1 else None,
        }
    )
    titles = query_titles or {}
    results = tuple(
        execute_analysis_query(
            db,
            request,
            scope=scope,
            field_definitions=definitions,
            title=titles.get(request.query_id),
        )
        for request in plan.queries
    )
    warnings: list[str] = []
    if plan.mode in {AnalysisMode.SEMANTIC, AnalysisMode.GENERATED} and not results:
        warnings.append("구조화 쿼리가 없는 분석 모드이며 후속 실행기가 결과를 보완해야 합니다.")
    return LegacyIssueAnalysisArtifactV1(
        mode=plan.mode,
        title=title,
        scope=scope,
        results=results,
        warnings=tuple(warnings),
        planner_diagnostics=planner_diagnostics,
    )


def _compile_aggregate_statement(
    request: QueryRequestV1,
    *,
    descriptor: QueryFamilyDescriptor,
    visible_records: Any,
    fields: Mapping[str, AnalysisFieldCapabilities],
    dialect_name: str,
) -> tuple[Any, tuple[AnalysisColumnV1, ...]]:
    dimension_expressions: list[Any] = []
    columns: list[AnalysisColumnV1] = []
    alias_to_dimension: dict[str, Any] = {}
    for dimension in request.dimensions:
        capabilities = fields[dimension.field_key]
        raw_value = visible_records.c[dimension.field_key]
        expression = _dimension_expression(
            raw_value,
            dimension=dimension,
            capabilities=capabilities,
            dialect_name=dialect_name,
        )
        alias = dimension.alias or dimension.field_key
        dimension_expressions.append(expression.label(alias))
        alias_to_dimension[alias] = expression
        columns.append(
            AnalysisColumnV1(
                key=alias,
                label=capabilities.field.label_ko,
                kind="dimension",
                value_type="date" if dimension.time_grain else "text",
                field_key=dimension.field_key,
            )
        )
    predicates = _request_population_predicates(
        request,
        visible_records=visible_records,
        fields=fields,
        dialect_name=dialect_name,
        include_dimension_constraints=True,
    )

    metric_expressions: list[Any] = []
    for metric in request.metrics:
        metric_expressions.append(
            _metric_expression(
                metric,
                visible_records=visible_records,
                fields=fields,
                dialect_name=dialect_name,
            ).label(metric.alias)
        )
        columns.append(_metric_column(metric, fields=fields))
    for comparison in request.comparisons:
        comparison_predicate = _compile_filter_group(
            comparison.filters,
            visible_records=visible_records,
            fields=fields,
            dialect_name=dialect_name,
        )
        for metric in request.metrics:
            alias = f"{comparison.key}__{metric.alias}"
            metric_expressions.append(
                _metric_expression(
                    metric,
                    visible_records=visible_records,
                    fields=fields,
                    dialect_name=dialect_name,
                    row_condition=comparison_predicate,
                ).label(alias)
            )
            metric_column = _metric_column(metric, fields=fields)
            columns.append(
                metric_column.model_copy(
                    update={
                        "key": alias,
                        "label": f"{comparison.label} · {metric_column.label}",
                    }
                )
            )

    aggregate = select(*dimension_expressions, *metric_expressions).select_from(visible_records)
    if predicates:
        aggregate = aggregate.where(and_(*predicates))
    if dimension_expressions:
        aggregate = aggregate.group_by(
            *(expression.element for expression in dimension_expressions)
        )
    aggregate_rows = aggregate.subquery("analysis_aggregate")

    output_expressions = [aggregate_rows.c[column.key] for column in columns]
    output_by_alias = {
        column.key: expression for column, expression in zip(columns, output_expressions)
    }
    dimension_aliases = set(alias_to_dimension)
    time_dimension_aliases = {
        dimension.alias or dimension.field_key
        for dimension in request.dimensions
        if dimension.time_grain is not None
    }
    requested_windows = list(request.windows)
    if request.family_id == QueryFamilyId.SHARE and not any(
        window.operator == WindowOperator.PERCENT_OF_TOTAL for window in requested_windows
    ):
        requested_windows.append(
            WindowSpecV1(
                operator=WindowOperator.PERCENT_OF_TOTAL,
                metric_alias=request.metrics[0].alias,
                alias="share",
            )
        )
    if request.family_id == QueryFamilyId.TOP_N_WITHIN_PARENT:
        requested_windows.append(
            WindowSpecV1(
                operator=WindowOperator.DENSE_RANK,
                metric_alias=request.metrics[0].alias,
                alias="within_parent_rank",
                partition_by=tuple(
                    dimension.alias or dimension.field_key for dimension in request.dimensions[:-1]
                ),
            )
        )
    for window in requested_windows:
        expression = _window_expression(
            window,
            aggregate_rows=aggregate_rows,
            dimension_aliases=dimension_aliases,
            time_dimension_aliases=time_dimension_aliases,
        ).label(window.alias)
        output_expressions.append(expression)
        output_by_alias[window.alias] = expression
        columns.append(
            AnalysisColumnV1(
                key=window.alias,
                label=window.alias,
                kind="window",
                value_type=(
                    "percent"
                    if window.operator
                    in {WindowOperator.PERCENT_OF_TOTAL, WindowOperator.RATE_CHANGE}
                    else "number"
                ),
            )
        )
    if request.family_id == QueryFamilyId.PARETO:
        metric = aggregate_rows.c[request.metrics[0].alias]
        total = func.sum(metric).over()
        share = (100.0 * metric / func.nullif(total, 0)).label("share")
        cumulative_share = (
            100.0
            * func.sum(metric).over(order_by=metric.desc(), rows=(None, 0))
            / func.nullif(total, 0)
        ).label("cumulative_share")
        output_expressions.extend((share, cumulative_share))
        output_by_alias.update(
            {
                "share": share,
                "cumulative_share": cumulative_share,
            }
        )
        columns.extend(
            (
                AnalysisColumnV1(
                    key="share",
                    label="구성비",
                    kind="window",
                    value_type="percent",
                ),
                AnalysisColumnV1(
                    key="cumulative_share",
                    label="누적 기여율",
                    kind="window",
                    value_type="percent",
                ),
            )
        )
    if request.family_id in {
        QueryFamilyId.FIELD_COVERAGE_CARDINALITY,
        QueryFamilyId.MISSING_POPULATED_RATE,
        QueryFamilyId.COMPLETENESS,
    }:
        _append_population_rates(
            request,
            aggregate_rows=aggregate_rows,
            output_expressions=output_expressions,
            output_by_alias=output_by_alias,
            columns=columns,
        )

    statement = select(*output_expressions).select_from(aggregate_rows)
    if request.sort:
        order_by = []
        for sort in request.sort:
            expression = output_by_alias[sort.key]
            order_by.append(
                expression.asc() if sort.direction == SortDirection.ASC else expression.desc()
            )
        statement = statement.order_by(*order_by)
    elif time_dimension_aliases:
        non_time_aliases = [
            dimension.alias or dimension.field_key
            for dimension in request.dimensions
            if dimension.time_grain is None
        ]
        ordered_time_aliases = [
            dimension.alias or dimension.field_key
            for dimension in request.dimensions
            if dimension.time_grain is not None
        ]
        statement = statement.order_by(
            *(aggregate_rows.c[alias].desc() for alias in ordered_time_aliases),
            *(aggregate_rows.c[alias].asc() for alias in non_time_aliases),
        )
    elif request.dimensions:
        primary_metric = aggregate_rows.c[request.metrics[0].alias]
        statement = statement.order_by(
            primary_metric.desc(),
            *(
                aggregate_rows.c[column.key].asc()
                for column in columns
                if column.kind == "dimension"
            ),
        )
    if request.family_id == QueryFamilyId.TOP_N_WITHIN_PARENT:
        ranked = statement.subquery("analysis_ranked")
        parent_aliases = [
            dimension.alias or dimension.field_key for dimension in request.dimensions[:-1]
        ]
        statement = (
            select(*(ranked.c[column.key] for column in columns))
            .where(ranked.c.within_parent_rank <= request.limit)
            .order_by(
                ranked.c.within_parent_rank.asc(),
                *(ranked.c[alias].asc() for alias in parent_aliases),
            )
        )
    return statement, tuple(columns)


def _append_population_rates(
    request: QueryRequestV1,
    *,
    aggregate_rows: Any,
    output_expressions: list[Any],
    output_by_alias: dict[str, Any],
    columns: list[AnalysisColumnV1],
) -> None:
    present_alias = next(
        metric.alias
        for metric in request.metrics
        if metric.operator == MetricOperator.PRESENT_COUNT
    )
    missing_alias = next(
        metric.alias
        for metric in request.metrics
        if metric.operator == MetricOperator.MISSING_COUNT
    )
    if {"present_rate", "missing_rate"}.intersection(output_by_alias):
        raise AnalysisSqlError("coverage rate aliases are reserved")
    present = aggregate_rows.c[present_alias]
    missing = aggregate_rows.c[missing_alias]
    population = func.nullif(present + missing, 0)
    present_rate = (100.0 * present / population).label("present_rate")
    missing_rate = (100.0 * missing / population).label("missing_rate")
    output_expressions.extend((present_rate, missing_rate))
    output_by_alias.update(
        {
            "present_rate": present_rate,
            "missing_rate": missing_rate,
        }
    )
    columns.extend(
        (
            AnalysisColumnV1(
                key="present_rate",
                label="입력률",
                kind="window",
                value_type="percent",
            ),
            AnalysisColumnV1(
                key="missing_rate",
                label="미입력률",
                kind="window",
                value_type="percent",
            ),
        )
    )


def _compile_detail_statement(
    request: QueryRequestV1,
    *,
    descriptor: QueryFamilyDescriptor,
    visible_records: Any,
    fields: Mapping[str, AnalysisFieldCapabilities],
    dialect_name: str,
) -> tuple[Any, tuple[AnalysisColumnV1, ...]]:
    del descriptor
    selected_field_keys = tuple(
        dict.fromkeys(
            (
                *(dimension.field_key for dimension in request.dimensions),
                *request.detail_fields,
            )
        )
    )
    expressions = [visible_records.c.record_id.label("record_id")]
    columns = [
        AnalysisColumnV1(
            key="record_id",
            label="레코드 ID",
            kind="record",
            value_type="text",
        )
    ]
    expression_by_alias: dict[str, Any] = {"record_id": visible_records.c.record_id}
    dimensions_by_field = {dimension.field_key: dimension for dimension in request.dimensions}
    for field_key in selected_field_keys:
        capabilities = fields[field_key]
        dimension = dimensions_by_field.get(field_key)
        if dimension is not None:
            expression = _dimension_expression(
                visible_records.c[field_key],
                dimension=dimension,
                capabilities=capabilities,
                dialect_name=dialect_name,
            )
            alias = dimension.alias or field_key
            kind = "dimension"
            value_type = "date" if dimension.time_grain else "text"
        else:
            expression = visible_records.c[field_key]
            alias = field_key
            kind = "record"
            value_type = _public_value_type(capabilities.field.field_type)
        expressions.append(expression.label(alias))
        expression_by_alias[alias] = expression
        columns.append(
            AnalysisColumnV1(
                key=alias,
                label=capabilities.field.label_ko,
                kind=kind,
                value_type=value_type,
                field_key=field_key,
            )
        )
    statement = select(*expressions).select_from(visible_records)
    if request.record_set is not None:
        statement = statement.where(
            _compile_record_set_predicate(
                request,
                visible_records=visible_records,
                fields=fields,
                dialect_name=dialect_name,
            )
        )
    if request.filters is not None:
        statement = statement.where(
            _compile_filter_group(
                request.filters,
                visible_records=visible_records,
                fields=fields,
                dialect_name=dialect_name,
            )
        )
    if request.sort:
        order_by = []
        for sort in request.sort:
            try:
                expression = expression_by_alias[sort.key]
            except KeyError as error:
                raise AnalysisSqlError(f"detail sort key is not selected: {sort.key}") from error
            order_by.append(
                expression.asc() if sort.direction == SortDirection.ASC else expression.desc()
            )
        statement = statement.order_by(*order_by)
    else:
        statement = statement.order_by(visible_records.c.record_id.asc())
    return statement, tuple(columns)


def _metric_expression(
    metric: MetricSpecV1,
    *,
    visible_records: Any,
    fields: Mapping[str, AnalysisFieldCapabilities],
    dialect_name: str,
    row_condition: Any | None = None,
) -> Any:
    identity = func.coalesce(
        visible_records.c.stable_record_id,
        visible_records.c.record_id,
    )
    conditioned_identity = (
        case((row_condition, identity), else_=None) if row_condition is not None else identity
    )
    if metric.operator == MetricOperator.ISSUE_COUNT:
        return func.count(distinct(conditioned_identity))

    if metric.operator == MetricOperator.CONDITIONAL_RATE:
        metric_condition = _compile_filter_group(
            metric.condition,
            visible_records=visible_records,
            fields=fields,
            dialect_name=dialect_name,
        )
        if row_condition is not None:
            metric_condition = and_(row_condition, metric_condition)
        numerator = func.count(distinct(case((metric_condition, identity), else_=None)))
        denominator = func.count(distinct(conditioned_identity))
        return 100.0 * numerator / func.nullif(denominator, 0)

    if metric.field_key is None:
        raise AnalysisSqlError(f"{metric.operator.value} requires field_key")
    value = visible_records.c[metric.field_key]
    nonempty = _is_present(value)
    if row_condition is not None:
        nonempty = and_(row_condition, nonempty)
    if metric.operator == MetricOperator.DISTINCT_COUNT:
        return func.count(distinct(case((nonempty, value), else_=None)))
    if metric.operator == MetricOperator.PRESENT_COUNT:
        return func.count(distinct(case((nonempty, identity), else_=None)))
    if metric.operator == MetricOperator.MISSING_COUNT:
        missing = not_(visible_records.c[_raw_present_column_key(metric.field_key)])
        if row_condition is not None:
            missing = and_(row_condition, missing)
        return func.count(distinct(case((missing, identity), else_=None)))

    aggregate_value = (
        case((row_condition, value), else_=None) if row_condition is not None else value
    )
    if metric.operator == MetricOperator.SUM:
        return func.sum(aggregate_value)
    if metric.operator == MetricOperator.AVG:
        return func.avg(aggregate_value)
    if metric.operator == MetricOperator.MIN:
        return func.min(aggregate_value)
    if metric.operator == MetricOperator.MAX:
        return func.max(aggregate_value)
    if metric.operator in {MetricOperator.MEDIAN, MetricOperator.PERCENTILE}:
        if dialect_name != "postgresql":
            raise AnalysisSqlError(f"{metric.operator.value} requires PostgreSQL")
        percentile = (
            0.5 if metric.operator == MetricOperator.MEDIAN else float(metric.percentile or 0.5)
        )
        return func.percentile_cont(percentile).within_group(aggregate_value)
    raise AnalysisSqlError(f"unsupported metric: {metric.operator.value}")


def _metric_column(
    metric: MetricSpecV1,
    *,
    fields: Mapping[str, AnalysisFieldCapabilities],
) -> AnalysisColumnV1:
    field_label = fields[metric.field_key].field.label_ko if metric.field_key else None
    metric_labels = {
        MetricOperator.ISSUE_COUNT: "전체 건수",
        MetricOperator.DISTINCT_COUNT: "고유값 수",
        MetricOperator.PRESENT_COUNT: "입력 건수",
        MetricOperator.MISSING_COUNT: "미입력 건수",
        MetricOperator.SUM: "합계",
        MetricOperator.AVG: "평균",
        MetricOperator.MIN: "최솟값",
        MetricOperator.MAX: "최댓값",
        MetricOperator.MEDIAN: "중앙값",
        MetricOperator.PERCENTILE: "백분위",
        MetricOperator.CONDITIONAL_RATE: "조건 비율",
    }
    label = metric_labels[metric.operator]
    if field_label:
        label = f"{field_label} {label}"
    return AnalysisColumnV1(
        key=metric.alias,
        label=label,
        kind="metric",
        value_type=("percent" if metric.operator == MetricOperator.CONDITIONAL_RATE else "number"),
        field_key=metric.field_key,
    )


def _window_expression(
    window: Any,
    *,
    aggregate_rows: Any,
    dimension_aliases: set[str],
    time_dimension_aliases: set[str],
) -> Any:
    metric = aggregate_rows.c[window.metric_alias]
    time_window_operators = {
        WindowOperator.LAG,
        WindowOperator.ABSOLUTE_CHANGE,
        WindowOperator.RATE_CHANGE,
        WindowOperator.MOVING_AVERAGE,
        WindowOperator.MOVING_SUM,
        WindowOperator.CUMULATIVE_SUM,
    }
    partition_aliases = window.partition_by
    if (
        not partition_aliases
        and time_dimension_aliases
        and window.operator in time_window_operators
    ):
        partition_aliases = tuple(sorted(dimension_aliases - time_dimension_aliases))
    partition_by = [aggregate_rows.c[alias] for alias in partition_aliases]
    order_aliases = (
        window.order_by or tuple(sorted(time_dimension_aliases)) or tuple(sorted(dimension_aliases))
    )
    order_by = [
        aggregate_rows.c[alias].asc()
        if alias in dimension_aliases
        else aggregate_rows.c[alias].desc()
        for alias in order_aliases
    ]
    if window.operator == WindowOperator.PERCENT_OF_TOTAL:
        return (
            100.0
            * metric
            / func.nullif(
                func.sum(metric).over(partition_by=partition_by),
                0,
            )
        )
    if window.operator == WindowOperator.RANK:
        return func.rank().over(partition_by=partition_by, order_by=metric.desc())
    if window.operator == WindowOperator.DENSE_RANK:
        return func.dense_rank().over(
            partition_by=partition_by,
            order_by=metric.desc(),
        )
    if window.operator == WindowOperator.CUMULATIVE_SUM:
        return func.sum(metric).over(
            partition_by=partition_by,
            order_by=order_by,
            rows=(None, 0),
        )
    if window.operator == WindowOperator.MOVING_AVERAGE:
        return func.avg(metric).over(
            partition_by=partition_by,
            order_by=order_by,
            rows=(-int(window.preceding or 1) + 1, 0),
        )
    if window.operator == WindowOperator.MOVING_SUM:
        return func.sum(metric).over(
            partition_by=partition_by,
            order_by=order_by,
            rows=(-int(window.preceding or 1) + 1, 0),
        )
    lagged = func.lag(metric, int(window.lag_offset or 1)).over(
        partition_by=partition_by,
        order_by=order_by,
    )
    if window.operator == WindowOperator.LAG:
        return lagged
    if window.operator == WindowOperator.ABSOLUTE_CHANGE:
        return metric - lagged
    if window.operator == WindowOperator.RATE_CHANGE:
        return 100.0 * (metric - lagged) / func.nullif(lagged, 0)
    raise AnalysisSqlError(f"unsupported window: {window.operator.value}")


def _dimension_expression(
    value: Any,
    *,
    dimension: DimensionSpecV1,
    capabilities: AnalysisFieldCapabilities,
    dialect_name: str,
) -> Any:
    if dimension.time_grain is not None:
        bucket = _time_bucket_expression(
            value,
            grain=dimension.time_grain,
            dialect_name=dialect_name,
        )
        return func.coalesce(bucket, literal(NULL_GROUP_LABEL))
    if dimension.numeric_bucket_size is not None:
        size = Decimal(str(dimension.numeric_bucket_size))
        bucket = func.floor(value / size) * size
        return func.coalesce(cast(bucket, Text), literal(NULL_GROUP_LABEL))
    del capabilities
    return func.coalesce(
        func.nullif(func.trim(cast(value, Text)), ""),
        literal(NULL_GROUP_LABEL),
    )


def _time_bucket_expression(
    value: Any,
    *,
    grain: TimeGrain,
    dialect_name: str,
) -> Any:
    if grain == TimeGrain.DAY:
        return value
    if grain == TimeGrain.MONTH:
        return func.substr(value, 1, 7)
    if grain == TimeGrain.YEAR:
        return func.substr(value, 1, 4)
    if grain == TimeGrain.QUARTER:
        year = cast(func.substr(value, 1, 4), Text)
        month = func.substr(value, 6, 2)
        quarter = case(
            (month.in_(("01", "02", "03")), "-Q1"),
            (month.in_(("04", "05", "06")), "-Q2"),
            (month.in_(("07", "08", "09")), "-Q3"),
            (month.in_(("10", "11", "12")), "-Q4"),
            else_=None,
        )
        return year + quarter
    if grain == TimeGrain.WEEK:
        if dialect_name == "sqlite":
            return func.strftime("%Y-W%W", value)
        return func.to_char(
            func.to_date(value, "YYYY-MM-DD"),
            'IYYY-"W"IW',
        )
    raise AnalysisSqlError(f"unsupported time grain: {grain.value}")


def _request_population_predicates(
    request: QueryRequestV1,
    *,
    visible_records: Any,
    fields: Mapping[str, AnalysisFieldCapabilities],
    dialect_name: str,
    include_dimension_constraints: bool,
) -> list[Any]:
    """Return the exact row population predicates shared by execution metadata.

    Query filters and cohort re-entry always define the population. Aggregate
    time/numeric buckets additionally exclude values that cannot be typed, which
    mirrors the aggregate compiler and the documented invalid-value policy.
    """

    predicates: list[Any] = []
    if include_dimension_constraints:
        for dimension in request.dimensions:
            capabilities = fields[dimension.field_key]
            value = visible_records.c[dimension.field_key]
            if dimension.time_grain is not None or dimension.numeric_bucket_size is not None:
                predicates.append(value.is_not(None))
            elif capabilities.field.field_type in {"number", "date"}:
                predicates.append(
                    or_(
                        not_(visible_records.c[_raw_present_column_key(dimension.field_key)]),
                        value.is_not(None),
                    )
                )
    if request.filters is not None:
        predicates.append(
            _compile_filter_group(
                request.filters,
                visible_records=visible_records,
                fields=fields,
                dialect_name=dialect_name,
            )
        )
    if request.record_set is not None:
        predicates.append(
            _compile_record_set_predicate(
                request,
                visible_records=visible_records,
                fields=fields,
                dialect_name=dialect_name,
            )
        )
    return predicates


def _compile_filter_group(
    group: FilterGroupV1 | None,
    *,
    visible_records: Any,
    fields: Mapping[str, AnalysisFieldCapabilities],
    dialect_name: str,
) -> Any:
    if group is None:
        return literal(True)
    expressions = [
        _compile_filter_condition(
            condition,
            visible_records=visible_records,
            fields=fields,
            dialect_name=dialect_name,
        )
        for condition in group.conditions
    ]
    expressions.extend(
        _compile_filter_group(
            child,
            visible_records=visible_records,
            fields=fields,
            dialect_name=dialect_name,
        )
        for child in group.groups
    )
    if group.junction == FilterJunction.NOT:
        return not_(expressions[0])
    if group.junction == FilterJunction.ANY:
        return or_(*expressions)
    return and_(*expressions)


def _compile_record_set_predicate(
    request: QueryRequestV1,
    *,
    visible_records: Any,
    fields: Mapping[str, AnalysisFieldCapabilities],
    dialect_name: str,
) -> Any:
    record_set = request.record_set
    if record_set is None:
        return literal(True)

    seed_records = visible_records.alias("cohort_seed_records")
    seed_predicate = _compile_filter_group(
        record_set.seed_filters,
        visible_records=seed_records,
        fields=fields,
        dialect_name=dialect_name,
    )
    outer_keys: list[Any] = []
    seed_keys: list[Any] = []
    for field_key in record_set.key_fields:
        outer_value = visible_records.c[field_key]
        seed_value = seed_records.c[field_key]
        if record_set.key_match_mode == ValueMatchMode.NORMALIZED:
            outer_value = _normalized_text_expression(
                outer_value,
                dialect_name=dialect_name,
            )
            seed_value = _normalized_text_expression(
                seed_value,
                dialect_name=dialect_name,
            )
        outer_keys.append(outer_value)
        seed_keys.append(seed_value)

    cohort_keys = (
        select(*seed_keys)
        .select_from(seed_records)
        .where(seed_predicate, *(key.is_not(None) for key in seed_keys))
        .distinct()
    )
    if len(outer_keys) == 1:
        membership = outer_keys[0].in_(cohort_keys)
    else:
        membership = tuple_(*outer_keys).in_(cohort_keys)
    predicates = [
        *(key.is_not(None) for key in outer_keys),
        membership,
    ]
    if record_set.exclude_seed_matches:
        target_seed_predicate = _compile_filter_group(
            record_set.seed_filters,
            visible_records=visible_records,
            fields=fields,
            dialect_name=dialect_name,
        )
        predicates.append(not_(func.coalesce(target_seed_predicate, false())))
    return and_(*predicates)


def _compile_filter_condition(
    condition: FilterConditionV1,
    *,
    visible_records: Any,
    fields: Mapping[str, AnalysisFieldCapabilities],
    dialect_name: str,
) -> Any:
    capabilities = fields[condition.field_key]
    value = visible_records.c[condition.field_key]
    operator = condition.operator
    normalized_matching = condition.match_mode == ValueMatchMode.NORMALIZED
    if normalized_matching:
        value = _normalized_text_expression(value, dialect_name=dialect_name)

    def operand(item: Any) -> Any:
        if normalized_matching:
            return _normalize_text_operand(item)
        return _coerce_operand(item, capabilities)

    if operator == FilterOperator.IS_NULL:
        return not_(visible_records.c[_raw_present_column_key(condition.field_key)])
    if operator == FilterOperator.IS_NOT_NULL:
        return _is_present(value)
    if operator == FilterOperator.EQ:
        return value == operand(condition.value)
    if operator == FilterOperator.NE:
        return value != operand(condition.value)
    if operator in {FilterOperator.IN, FilterOperator.NOT_IN}:
        values = tuple(operand(item) for item in condition.values)
        expression = value.in_(values)
        return not_(expression) if operator == FilterOperator.NOT_IN else expression
    if operator == FilterOperator.CONTAINS:
        return cast(value, Text).ilike(
            _like_pattern(operand(condition.value), prefix=True, suffix=True),
            escape="\\",
        )
    if operator == FilterOperator.STARTS_WITH:
        return cast(value, Text).ilike(
            _like_pattern(operand(condition.value), prefix=False, suffix=True),
            escape="\\",
        )
    if operator == FilterOperator.GT:
        return value > operand(condition.value)
    if operator == FilterOperator.GTE:
        return value >= operand(condition.value)
    if operator == FilterOperator.LT:
        return value < operand(condition.value)
    if operator == FilterOperator.LTE:
        return value <= operand(condition.value)
    if operator == FilterOperator.BETWEEN:
        lower, upper = (operand(item) for item in condition.values)
        return value.between(lower, upper)
    if operator in {FilterOperator.CONTAINS_ANY, FilterOperator.CONTAINS_ALL}:
        if capabilities.field.allow_multiple:
            expressions = [
                _multi_value_contains(
                    value,
                    item=item,
                    dialect_name=dialect_name,
                )
                for item in condition.values
            ]
        else:
            expressions = [
                cast(value, Text).ilike(
                    _like_pattern(operand(item), prefix=True, suffix=True),
                    escape="\\",
                )
                for item in condition.values
            ]
        return or_(*expressions) if operator == FilterOperator.CONTAINS_ANY else and_(*expressions)
    raise AnalysisSqlError(f"unsupported filter operator: {operator.value}")


def _normalized_text_expression(value: Any, *, dialect_name: str) -> Any:
    _require_supported_dialect(dialect_name)
    text_value = cast(value, Text)
    if dialect_name == "postgresql":
        compact = func.regexp_replace(text_value, r"\s+", "", "g")
    else:
        compact = func.replace(
            func.replace(
                func.replace(
                    func.replace(text_value, " ", ""),
                    "\t",
                    "",
                ),
                "\n",
                "",
            ),
            "\r",
            "",
        )
    return func.nullif(func.lower(compact), "")


def _normalize_text_operand(value: Any) -> str:
    return "".join(str(value).split()).lower()


def _multi_value_contains(
    value: Any,
    *,
    item: Any,
    dialect_name: str,
) -> Any:
    _require_supported_dialect(dialect_name)
    normalized = func.trim(cast(value, Text))
    json_token = json.dumps(str(item), ensure_ascii=False)
    return and_(
        normalized.like("[%"),
        normalized.like("%]"),
        normalized.like(
            _like_pattern(json_token, prefix=True, suffix=True),
            escape="\\",
        ),
    )


def _raw_field_expression(
    scoped_records: Any,
    *,
    capabilities: AnalysisFieldCapabilities,
    dialect_name: str,
) -> Any:
    field_key = capabilities.field.key
    json_value = scoped_records.c.field_values[field_key].as_string()
    projected_field_keys = frozenset(PROJECTED_RECORD_FIELD_KEYS) | _CHECKLIST_PROJECTED_FIELD_KEYS
    if field_key not in projected_field_keys or field_key not in scoped_records.c:
        return cast(json_value, Text)
    projected_value = cast(scoped_records.c[field_key], Text)
    if dialect_name == "postgresql":
        json_key_exists = scoped_records.c.field_values.op("?")(field_key)
    elif dialect_name == "sqlite":
        json_key_exists = func.json_type(
            scoped_records.c.field_values,
            f'$."{field_key}"',
        ).is_not(None)
    else:
        raise AnalysisSqlError(f"unsupported analysis SQL dialect: {dialect_name}")
    return case(
        (json_key_exists, cast(json_value, Text)),
        else_=projected_value,
    )


def _typed_field_expression(
    scoped_records: Any,
    *,
    capabilities: AnalysisFieldCapabilities,
    dialect_name: str,
) -> Any:
    raw_value = _raw_field_expression(
        scoped_records,
        capabilities=capabilities,
        dialect_name=dialect_name,
    )
    normalized = func.nullif(func.trim(raw_value), "")
    if capabilities.field.field_type == "number":
        valid = _regexp_predicate(
            normalized,
            r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$",
            dialect_name=dialect_name,
        )
        return case((valid, cast(normalized, Numeric)), else_=None)
    if capabilities.field.field_type == "date":
        iso_shaped = _regexp_predicate(
            normalized,
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
            dialect_name=dialect_name,
        )
        if dialect_name == "postgresql":
            calendar_valid = func.pg_input_is_valid(normalized, literal("date"))
        elif dialect_name == "sqlite":
            # SQLite < 3.45 only normalizes overflow dates when a modifier is applied.
            calendar_valid = func.date(normalized, literal("+0 days")) == normalized
        else:
            raise AnalysisSqlError(f"unsupported analysis SQL dialect: {dialect_name}")
        valid = and_(
            iso_shaped,
            normalized >= "0001-01-01",
            calendar_valid,
        )
        return case((valid, normalized), else_=None)
    return normalized


def _safe_generated_date_expression(
    scoped_records: Any,
    *,
    capabilities: AnalysisFieldCapabilities,
) -> Any:
    """Return a PostgreSQL DATE or NULL without raising on malformed source text."""

    raw_value = _raw_field_expression(
        scoped_records,
        capabilities=capabilities,
        dialect_name="postgresql",
    )
    normalized = func.nullif(func.trim(raw_value), "")
    iso_shaped = normalized.op("~")(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    valid_date = func.pg_input_is_valid(normalized, literal("date"))
    return case(
        (
            and_(
                iso_shaped,
                normalized >= "0001-01-01",
                valid_date,
            ),
            cast(normalized, Date),
        ),
        else_=None,
    )


def _regexp_predicate(value: Any, pattern: str, *, dialect_name: str) -> Any:
    if dialect_name == "postgresql":
        return value.op("~")(pattern)
    if dialect_name == "sqlite":
        return value.op("REGEXP")(pattern)
    raise AnalysisSqlError(f"unsupported analysis SQL dialect: {dialect_name}")


def _query_population_count(
    db: Session,
    *,
    request: QueryRequestV1,
    scope: AnalysisScopeV1,
    fields: Mapping[str, AnalysisFieldCapabilities],
    field_definitions: Iterable[DatasetFieldDefinition],
    include_dimension_constraints: bool,
) -> int:
    """Count the records in the exact post-filter query population."""

    dialect_name = db.get_bind().dialect.name
    visible_records = build_visible_records_relation(
        scope,
        field_definitions=field_definitions,
        dialect_name=dialect_name,
        field_keys=_referenced_field_keys(request),
        data_source=request.data_source,
    )
    identity = func.coalesce(
        visible_records.c.stable_record_id,
        visible_records.c.record_id,
    )
    statement = select(func.count(distinct(identity))).select_from(visible_records)
    predicates = _request_population_predicates(
        request,
        visible_records=visible_records,
        fields=fields,
        dialect_name=dialect_name,
        include_dimension_constraints=include_dimension_constraints,
    )
    if predicates:
        statement = statement.where(and_(*predicates))
    return int(db.scalar(statement) or 0)


def _compute_coverage(
    db: Session,
    *,
    scope: AnalysisScopeV1,
    fields: Mapping[str, AnalysisFieldCapabilities],
    field_keys: Sequence[str],
    data_source: AnalysisDataSource = AnalysisDataSource.LEGACY_ISSUES,
    request: QueryRequestV1 | None = None,
    field_definitions: Iterable[DatasetFieldDefinition] = COMMON_MASTER_FIELDS,
    include_dimension_constraints: bool = False,
) -> tuple[AnalysisCoverageV1, ...]:
    unique_keys = tuple(dict.fromkeys(field_keys))
    if not unique_keys:
        return ()
    dialect_name = db.get_bind().dialect.name
    if request is not None:
        scoped = build_visible_records_relation(
            scope,
            field_definitions=field_definitions,
            dialect_name=dialect_name,
            field_keys=unique_keys,
            data_source=data_source,
        )
        identity = func.coalesce(scoped.c.stable_record_id, scoped.c.record_id)
        predicates = _request_population_predicates(
            request,
            visible_records=scoped,
            fields=fields,
            dialect_name=dialect_name,
            include_dimension_constraints=include_dimension_constraints,
        )
    else:
        scoped = (
            build_scoped_vehicle_checklist_records_relation(scope)
            if data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
            else build_scoped_records_relation(scope)
        )
        identity = func.coalesce(scoped.c.stable_record_id, scoped.c.id)
        predicates = []
    expressions: list[Any] = []
    for index, field_key in enumerate(unique_keys):
        capabilities = fields[field_key]
        if request is not None:
            typed_value = scoped.c[field_key]
            raw_present = scoped.c[_raw_present_column_key(field_key)]
        else:
            raw_value = _raw_field_expression(
                scoped,
                capabilities=capabilities,
                dialect_name=dialect_name,
            )
            typed_value = _typed_field_expression(
                scoped,
                capabilities=capabilities,
                dialect_name=dialect_name,
            )
            raw_present = _is_present(raw_value)
        valid_present = and_(raw_present, typed_value.is_not(None))
        invalid = (
            and_(raw_present, typed_value.is_(None))
            if capabilities.field.field_type in {"number", "date"}
            else false()
        )
        expressions.extend(
            (
                func.count(distinct(case((valid_present, identity), else_=None))).label(
                    f"present_{index}"
                ),
                func.count(distinct(case((not_(raw_present), identity), else_=None))).label(
                    f"missing_{index}"
                ),
                func.count(distinct(case((invalid, identity), else_=None))).label(
                    f"invalid_{index}"
                ),
            )
        )
    statement = select(*expressions).select_from(scoped)
    if predicates:
        statement = statement.where(and_(*predicates))
    row = db.execute(statement).mappings().one()
    return tuple(
        AnalysisCoverageV1(
            field_key=field_key,
            label=fields[field_key].field.label_ko,
            present_count=int(row[f"present_{index}"] or 0),
            missing_count=int(row[f"missing_{index}"] or 0),
            invalid_count=int(row[f"invalid_{index}"] or 0),
        )
        for index, field_key in enumerate(unique_keys)
    )


def _execute_metadata_query(
    db: Session,
    request: QueryRequestV1,
    *,
    descriptor: QueryFamilyDescriptor,
    fields: Mapping[str, AnalysisFieldCapabilities],
    scope: AnalysisScopeV1,
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[AnalysisColumnV1, ...],
    bool,
]:
    del descriptor
    if request.family_id == QueryFamilyId.FIELD_CATALOG:
        all_rows = [
            {
                "field_key": capabilities.field.key,
                "label": capabilities.field.label_ko,
                "field_type": capabilities.field.field_type,
                "allow_multiple": ("true" if capabilities.field.allow_multiple else "false"),
            }
            for capabilities in fields.values()
        ]
        columns = (
            AnalysisColumnV1(
                key="field_key",
                label="필드 키",
                kind="dimension",
                value_type="text",
            ),
            AnalysisColumnV1(
                key="label",
                label="필드명",
                kind="dimension",
                value_type="text",
            ),
            AnalysisColumnV1(
                key="field_type",
                label="필드 유형",
                kind="dimension",
                value_type="text",
            ),
            AnalysisColumnV1(
                key="allow_multiple",
                label="다중값",
                kind="dimension",
                value_type="text",
            ),
        )
    elif request.family_id == QueryFamilyId.ACTIVE_REVISION_FRESHNESS:
        revisions = {
            revision.id: revision
            for revision in db.scalars(
                select(LegacyIssueDataRevision).where(
                    LegacyIssueDataRevision.workspace_id == scope.workspace_id,
                    LegacyIssueDataRevision.id.in_(scope.revision_ids),
                )
            )
        }
        all_rows = []
        for module_key in scope.module_keys:
            revision_id = scope.revision_by_module.get(module_key)
            revision = revisions.get(revision_id or "")
            all_rows.append(
                {
                    "module_key": module_key,
                    "revision_id": revision_id,
                    "status": revision.status if revision is not None else None,
                    "revision_no": revision.revision_no if revision is not None else None,
                    "created_at": _normalize_result_value(
                        revision.created_at if revision is not None else None
                    ),
                    "published_at": _normalize_result_value(
                        revision.published_at if revision is not None else None
                    ),
                    "updated_at": _normalize_result_value(
                        revision.updated_at if revision is not None else None
                    ),
                }
            )
        columns = (
            AnalysisColumnV1(
                key="module_key",
                label="모듈",
                kind="dimension",
                value_type="text",
            ),
            AnalysisColumnV1(
                key="revision_id",
                label="유효 리비전",
                kind="dimension",
                value_type="text",
            ),
            AnalysisColumnV1(
                key="status",
                label="상태",
                kind="dimension",
                value_type="text",
            ),
            AnalysisColumnV1(
                key="revision_no",
                label="리비전 번호",
                kind="metric",
                value_type="number",
            ),
            AnalysisColumnV1(
                key="created_at",
                label="생성 시각",
                kind="metric",
                value_type="date",
            ),
            AnalysisColumnV1(
                key="published_at",
                label="게시 시각",
                kind="metric",
                value_type="date",
            ),
            AnalysisColumnV1(
                key="updated_at",
                label="갱신 시각",
                kind="metric",
                value_type="date",
            ),
        )
    elif request.family_id == QueryFamilyId.EVIDENCE_COVERAGE:
        scoped = build_scoped_records_relation(scope)
        identity = func.coalesce(scoped.c.stable_record_id, scoped.c.id)
        joined = scoped.outerjoin(
            LegacyIssueAttachment,
            and_(
                LegacyIssueAttachment.record_id == scoped.c.id,
                LegacyIssueAttachment.workspace_id == scope.workspace_id,
                LegacyIssueAttachment.dataset_key == scope.dataset_key,
                LegacyIssueAttachment.revision_id == scoped.c.revision_id,
            ),
        )
        row = (
            db.execute(
                select(
                    func.count(distinct(identity)).label("record_count"),
                    func.count(
                        distinct(
                            case(
                                (LegacyIssueAttachment.id.is_not(None), identity),
                                else_=None,
                            )
                        )
                    ).label("records_with_attachment"),
                    func.count(distinct(LegacyIssueAttachment.id)).label("attachment_count"),
                    func.count(
                        distinct(
                            case(
                                (
                                    LegacyIssueAttachment.index_status == "indexed",
                                    LegacyIssueAttachment.id,
                                ),
                                else_=None,
                            )
                        )
                    ).label("indexed_attachment_count"),
                ).select_from(joined)
            )
            .mappings()
            .one()
        )
        record_count = int(row["record_count"] or 0)
        with_attachment = int(row["records_with_attachment"] or 0)
        attachment_count = int(row["attachment_count"] or 0)
        indexed_count = int(row["indexed_attachment_count"] or 0)
        all_rows = [
            {
                "record_count": record_count,
                "records_with_attachment": with_attachment,
                "records_without_attachment": max(record_count - with_attachment, 0),
                "attachment_record_rate": (
                    100.0 * with_attachment / record_count if record_count else None
                ),
                "attachment_count": attachment_count,
                "indexed_attachment_count": indexed_count,
                "attachment_index_rate": (
                    100.0 * indexed_count / attachment_count if attachment_count else None
                ),
            }
        ]
        columns = (
            AnalysisColumnV1(
                key="record_count",
                label="전체 레코드",
                kind="metric",
                value_type="number",
            ),
            AnalysisColumnV1(
                key="records_with_attachment",
                label="첨부 보유 레코드",
                kind="metric",
                value_type="number",
            ),
            AnalysisColumnV1(
                key="records_without_attachment",
                label="첨부 미보유 레코드",
                kind="metric",
                value_type="number",
            ),
            AnalysisColumnV1(
                key="attachment_record_rate",
                label="첨부 보유율",
                kind="metric",
                value_type="percent",
            ),
            AnalysisColumnV1(
                key="attachment_count",
                label="전체 첨부",
                kind="metric",
                value_type="number",
            ),
            AnalysisColumnV1(
                key="indexed_attachment_count",
                label="색인 완료 첨부",
                kind="metric",
                value_type="number",
            ),
            AnalysisColumnV1(
                key="attachment_index_rate",
                label="첨부 색인율",
                kind="metric",
                value_type="percent",
            ),
        )
    elif request.family_id == QueryFamilyId.INVALID_VALUES:
        coverage = _compute_coverage(
            db,
            scope=scope,
            fields=fields,
            field_keys=(dimension.field_key for dimension in request.dimensions),
        )
        all_rows = [
            {
                "field_key": item.field_key,
                "label": item.label,
                "valid_count": item.present_count,
                "missing_count": item.missing_count,
                "invalid_count": item.invalid_count,
            }
            for item in coverage
        ]
        columns = (
            AnalysisColumnV1(
                key="field_key",
                label="필드 키",
                kind="dimension",
                value_type="text",
            ),
            AnalysisColumnV1(
                key="label",
                label="필드명",
                kind="dimension",
                value_type="text",
            ),
            AnalysisColumnV1(
                key="valid_count",
                label="유효값",
                kind="metric",
                value_type="number",
            ),
            AnalysisColumnV1(
                key="missing_count",
                label="미입력",
                kind="metric",
                value_type="number",
            ),
            AnalysisColumnV1(
                key="invalid_count",
                label="형식 불일치",
                kind="metric",
                value_type="number",
            ),
        )
    else:
        all_rows = [
            {
                "module_key": module_key,
                "revision_id": scope.revision_by_module.get(module_key),
            }
            for module_key in scope.module_keys
        ]
        columns = (
            AnalysisColumnV1(
                key="module_key",
                label="모듈",
                kind="dimension",
                value_type="text",
            ),
            AnalysisColumnV1(
                key="revision_id",
                label="유효 리비전",
                kind="dimension",
                value_type="text",
            ),
        )
    limit = min(request.limit, AGGREGATE_RESULT_LIMIT)
    return tuple(all_rows[:limit]), columns, len(all_rows) > limit


def _source_count(
    db: Session,
    scope: AnalysisScopeV1,
    *,
    data_source: AnalysisDataSource = AnalysisDataSource.LEGACY_ISSUES,
) -> int:
    scoped = (
        build_scoped_vehicle_checklist_records_relation(scope)
        if data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
        else build_scoped_records_relation(scope)
    )
    identity = func.coalesce(scoped.c.stable_record_id, scoped.c.id)
    return int(db.scalar(select(func.count(distinct(identity))).select_from(scoped)) or 0)


def _referenced_field_keys(request: QueryRequestV1) -> tuple[str, ...]:
    keys: list[str] = []
    keys.extend(dimension.field_key for dimension in request.dimensions)
    keys.extend(metric.field_key for metric in request.metrics if metric.field_key is not None)
    keys.extend(request.detail_fields)
    keys.extend(_filter_field_keys(request.filters))
    if request.record_set is not None:
        keys.extend(request.record_set.key_fields)
        keys.extend(_filter_field_keys(request.record_set.seed_filters))
    for metric in request.metrics:
        keys.extend(_filter_field_keys(metric.condition))
    for comparison in request.comparisons:
        keys.extend(_filter_field_keys(comparison.filters))
    return tuple(dict.fromkeys(keys))


def _filter_field_keys(group: FilterGroupV1 | None) -> list[str]:
    if group is None:
        return []
    keys = [condition.field_key for condition in group.conditions]
    for child in group.groups:
        keys.extend(_filter_field_keys(child))
    return keys


def _flatten_filter_conditions(
    group: FilterGroupV1,
) -> tuple[FilterConditionV1, ...]:
    conditions = list(group.conditions)
    for child in group.groups:
        conditions.extend(_flatten_filter_conditions(child))
    return tuple(conditions)


def _coerce_operand(
    value: Any,
    capabilities: AnalysisFieldCapabilities,
) -> Any:
    if capabilities.field.field_type == "number":
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError) as error:
            raise AnalysisSqlError(
                f"invalid numeric filter for {capabilities.field.key}"
            ) from error
    if capabilities.field.field_type == "date":
        normalized = str(value)
        try:
            date.fromisoformat(normalized)
        except ValueError as error:
            raise AnalysisSqlError(f"invalid date filter for {capabilities.field.key}") from error
        return normalized
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _like_pattern(value: Any, *, prefix: bool, suffix: bool) -> str:
    normalized = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{'%' if prefix else ''}{normalized}{'%' if suffix else ''}"


def _is_present(value: Any) -> Any:
    return and_(
        value.is_not(None),
        func.trim(cast(value, Text)) != "",
    )


def _partition_compatibility_predicate(
    column: Any,
    partition_ids: Sequence[str],
) -> Any:
    """Preserve pre-partition NULL rows while requiring resolved IDs for bound rows."""

    return or_(column.is_(None), column.in_(tuple(partition_ids)))


def _raw_present_column_key(field_key: str) -> str:
    return f"{_RAW_PRESENT_COLUMN_PREFIX}{field_key}"


def _effective_revision_sort_key(
    revision: LegacyIssueDataRevision,
) -> tuple[bool, int, datetime, datetime]:
    minimum = datetime.min
    return (
        revision.status == REVISION_STATUS_DRAFT,
        revision.revision_no if revision.revision_no is not None else -1,
        revision.published_at or minimum,
        revision.created_at or minimum,
    )


def _checklist_sort_key(
    checklist: LegacyIssueVehicleModuleChecklist,
) -> tuple[int, datetime, datetime, str]:
    minimum = datetime.min
    return (
        checklist.source_master_revision_no
        if checklist.source_master_revision_no is not None
        else -1,
        checklist.updated_at or minimum,
        checklist.created_at or minimum,
        checklist.id,
    )


def _normalize_result_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _public_value_type(field_type: str) -> str:
    if field_type == "number":
        return "number"
    if field_type == "date":
        return "date"
    if field_type == "boolean":
        return "boolean"
    return "text"


def _require_supported_dialect(dialect_name: str) -> None:
    if dialect_name not in _SUPPORTED_DIALECTS:
        raise AnalysisSqlError(f"unsupported analysis SQL dialect: {dialect_name}")


__all__ = [
    "AGGREGATE_RESULT_LIMIT",
    "AnalysisSqlError",
    "CHECKLIST_ANALYSIS_FIELDS",
    "CompiledAnalysisQuery",
    "DETAIL_RESULT_LIMIT",
    "NULL_GROUP_LABEL",
    "build_scoped_records_relation",
    "build_scoped_vehicle_checklist_records_relation",
    "build_visible_records_relation",
    "compile_analysis_query",
    "execute_analysis_plan",
    "execute_analysis_query",
    "resolve_analysis_scope",
]
