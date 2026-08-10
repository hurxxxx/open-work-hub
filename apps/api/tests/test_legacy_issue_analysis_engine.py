from __future__ import annotations

import json
from types import MappingProxyType

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import OrgUnit, User, Workspace
from open_alm_api.domains.legacy_issues.analysis_catalog import (
    AnalysisCatalogError,
    EXPECTED_QUERY_FAMILY_COUNT,
    FamilyExecutionKind,
    QUERY_FAMILY_CATALOG,
    analysis_catalog_payload,
    build_analysis_field_catalog,
    validate_query_request,
)
from open_alm_api.domains.legacy_issues.analysis_contracts import (
    PUBLIC_CELL_MAX_CHARS,
    PUBLIC_QUERY_ROWS_MAX_BYTES,
    AnalysisColumnV1,
    AnalysisMode,
    AnalysisPlanV1,
    AnalysisResultV1,
    AnalysisScopeV1,
    DimensionSpecV1,
    FilterConditionV1,
    FilterGroupV1,
    FilterOperator,
    LegacyIssueAnalysisArtifactV1,
    MetricOperator,
    MetricSpecV1,
    QueryFamilyId,
    QueryRequestV1,
    TimeGrain,
)
from open_alm_api.domains.legacy_issues.analysis_sql import (
    build_visible_records_relation,
    execute_analysis_plan,
    resolve_analysis_scope,
)
from open_alm_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    COMMON_MASTER_FIELDS,
    DatasetFieldDefinition,
)
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueAttachment,
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from open_alm_api.domains.legacy_issues.revisioning import (
    legacy_issue_dataset_revision_key,
)
from open_alm_api.domains.retrieval.models import RetrievalPartition


MULTI_VALUE_FIELD = DatasetFieldDefinition(
    key="custom.tags",
    label_ko="태그",
    label_en="Tags",
    field_type="select",
    allow_multiple=True,
    source="module",
)
ANALYSIS_FIELDS = (*COMMON_MASTER_FIELDS, MULTI_VALUE_FIELD)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            OrgUnit.__table__,
            Workspace.__table__,
            User.__table__,
            RetrievalPartition.__table__,
            LegacyIssueDataRevision.__table__,
            LegacyIssueRecord.__table__,
            LegacyIssueAttachment.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


@pytest.fixture
def seeded_scope(db: Session) -> tuple[Workspace, RetrievalPartition]:
    workspace = Workspace(id="workspace-analysis", key="analysis", name="Analysis")
    other_workspace = Workspace(id="workspace-other", key="other", name="Other")
    db.add_all([workspace, other_workspace])
    db.flush()
    allowed_partition = RetrievalPartition(
        id="10000000-0000-0000-0000-000000000001",
        source_namespace="legacy_issues",
        managed_workspace_id=workspace.id,
        candidate_scope_kind="workspace",
        candidate_workspace_id=workspace.id,
        state="active",
        metadata_version=1,
        is_default_ingest=True,
    )
    excluded_partition = RetrievalPartition(
        id="10000000-0000-0000-0000-000000000002",
        source_namespace="legacy_issues",
        managed_workspace_id=other_workspace.id,
        candidate_scope_kind="workspace",
        candidate_workspace_id=other_workspace.id,
        state="active",
        metadata_version=1,
        is_default_ingest=True,
    )
    db.add_all([allowed_partition, excluded_partition])
    db.flush()

    aircon_key = legacy_issue_dataset_revision_key(
        COMMON_MASTER_DATASET_KEY,
        "aircon",
    )
    interior_key = legacy_issue_dataset_revision_key(
        COMMON_MASTER_DATASET_KEY,
        "interior",
    )
    published_old = LegacyIssueDataRevision(
        id="revision-aircon-published-old",
        workspace_id=workspace.id,
        retrieval_partition_id=allowed_partition.id,
        dataset_key=aircon_key,
        revision_no=1,
        status="published",
    )
    published_latest = LegacyIssueDataRevision(
        id="revision-aircon-published-latest",
        workspace_id=workspace.id,
        retrieval_partition_id=allowed_partition.id,
        dataset_key=aircon_key,
        revision_no=2,
        status="published",
    )
    draft = LegacyIssueDataRevision(
        id="revision-aircon-draft",
        workspace_id=workspace.id,
        retrieval_partition_id=allowed_partition.id,
        dataset_key=aircon_key,
        status="draft",
        base_revision_id=published_latest.id,
    )
    interior = LegacyIssueDataRevision(
        id="revision-interior-published",
        workspace_id=workspace.id,
        retrieval_partition_id=allowed_partition.id,
        dataset_key=interior_key,
        revision_no=1,
        status="published",
    )
    db.add_all([published_old, published_latest, draft, interior])
    db.flush()

    records = [
        LegacyIssueRecord(
            id="record-draft-json",
            workspace_id=workspace.id,
            retrieval_partition_id=allowed_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=draft.id,
            stable_record_id="stable-json",
            field_values={
                "vehicle_model": "JSON-A",
                "region_zone": "한국",
                "occurrence_date": "2025-01-10",
                "custom.tags": ["A"],
            },
            vehicle_model="COLUMN-WRONG",
            region_zone="COLUMN-WRONG",
            occurrence_date="2024-12-31",
        ),
        LegacyIssueRecord(
            id="record-draft-json-null",
            workspace_id=workspace.id,
            retrieval_partition_id=allowed_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=draft.id,
            stable_record_id="stable-json-null",
            field_values={
                "vehicle_model": None,
                "occurrence_date": "2025-02-31",
                "custom.tags": ["AA"],
            },
            vehicle_model="COLUMN-MUST-NOT-RETURN",
            region_zone="유럽",
            occurrence_date="2025-01-15",
        ),
        LegacyIssueRecord(
            id="record-draft-fallback",
            workspace_id=workspace.id,
            retrieval_partition_id=allowed_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=draft.id,
            stable_record_id="stable-fallback",
            field_values={"custom.tags": ["A", "AA"]},
            vehicle_model="COLUMN-FALLBACK",
            occurrence_date="2025-02-20",
        ),
        LegacyIssueRecord(
            id="record-interior",
            workspace_id=workspace.id,
            retrieval_partition_id=allowed_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="interior",
            revision_id=interior.id,
            stable_record_id="stable-interior",
            field_values={
                "vehicle_model": "INT-A",
                "region_zone": "한국",
                "occurrence_date": "2025-01-21",
                "custom.tags": [],
            },
        ),
        LegacyIssueRecord(
            id="record-published-ignored",
            workspace_id=workspace.id,
            retrieval_partition_id=allowed_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=published_latest.id,
            stable_record_id="stable-published",
            field_values={"vehicle_model": "PUBLISHED"},
        ),
        LegacyIssueRecord(
            id="record-partition-excluded",
            workspace_id=workspace.id,
            retrieval_partition_id=excluded_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=draft.id,
            stable_record_id="stable-excluded",
            field_values={"vehicle_model": "EXCLUDED"},
        ),
    ]
    db.add_all(records)
    db.commit()
    return workspace, allowed_partition


def test_catalog_is_complete_versioned_and_immutable() -> None:
    assert isinstance(QUERY_FAMILY_CATALOG, MappingProxyType)
    assert len(QUERY_FAMILY_CATALOG) == EXPECTED_QUERY_FAMILY_COUNT == 62
    assert {key[0] for key in QUERY_FAMILY_CATALOG} == set(QueryFamilyId)
    assert {key[1] for key in QUERY_FAMILY_CATALOG} == {1}
    with pytest.raises(TypeError):
        QUERY_FAMILY_CATALOG[(QueryFamilyId.TOTAL_COUNT, 2)] = QUERY_FAMILY_CATALOG[
            (QueryFamilyId.TOTAL_COUNT, 1)
        ]

    payload = analysis_catalog_payload(fields=COMMON_MASTER_FIELDS)
    assert payload["version"] == 1
    assert len(payload["families"]) == 62
    vehicle = next(field for field in payload["fields"] if field["key"] == "vehicle_model")
    assert vehicle["type"] == "text"
    assert "contains" in vehicle["filters"]
    assert "contains_any" in vehicle["filters"]

    compact = analysis_catalog_payload(
        fields=COMMON_MASTER_FIELDS,
        detailed_family_ids=(QueryFamilyId.TOTAL_COUNT,),
        compact=True,
    )
    assert len(compact["family_index"]) == 62
    assert [family["id"] for family in compact["family_details"]] == [
        QueryFamilyId.TOTAL_COUNT.value
    ]
    assert compact["field_rules"]


def test_plan_contract_separates_catalog_and_delegated_modes() -> None:
    AnalysisPlanV1(mode=AnalysisMode.SEMANTIC, queries=())
    AnalysisPlanV1(mode=AnalysisMode.GENERATED, queries=())
    AnalysisPlanV1(
        mode=AnalysisMode.SEMANTIC,
        delegated_family_id=QueryFamilyId.SEMANTIC_SIMILAR,
    )
    AnalysisPlanV1(
        mode=AnalysisMode.GENERATED,
        delegated_family_id=QueryFamilyId.DURATION_SUMMARY,
    )
    with pytest.raises(ValidationError, match="generated family requires generated mode"):
        AnalysisPlanV1(
            mode=AnalysisMode.SEMANTIC,
            delegated_family_id=QueryFamilyId.DURATION_SUMMARY,
        )
    with pytest.raises(ValidationError, match="semantic family requires semantic mode"):
        AnalysisPlanV1(
            mode=AnalysisMode.GENERATED,
            delegated_family_id=QueryFamilyId.SEMANTIC_SIMILAR,
        )
    query = QueryRequestV1(
        query_id="total",
        family_id=QueryFamilyId.TOTAL_COUNT,
    )
    with pytest.raises(ValidationError, match="query_id values must be unique"):
        AnalysisPlanV1(
            mode=AnalysisMode.ANALYTICS,
            queries=(
                query,
                QueryRequestV1(
                    query_id="total",
                    family_id=QueryFamilyId.FILTERED_COUNT,
                ),
            ),
        )
    with pytest.raises(ValidationError):
        AnalysisPlanV1(mode=AnalysisMode.SEMANTIC, queries=(query,))
    with pytest.raises(ValidationError):
        AnalysisPlanV1(mode=AnalysisMode.ANALYTICS, queries=())
    with pytest.raises(ValidationError):
        AnalysisPlanV1(
            mode=AnalysisMode.HYBRID,
            queries=(
                QueryRequestV1(
                    query_id="semantic",
                    family_id=QueryFamilyId.SEMANTIC_SIMILAR,
                ),
            ),
        )
    duration = QueryRequestV1(
        query_id="duration",
        family_id=QueryFamilyId.DURATION_SUMMARY,
    )
    with pytest.raises(ValidationError):
        AnalysisPlanV1(mode=AnalysisMode.ANALYTICS, queries=(duration,))
    assert (
        QUERY_FAMILY_CATALOG[(QueryFamilyId.DURATION_SUMMARY, 1)].execution_kind
        == FamilyExecutionKind.GENERATED
    )
    composite = QueryRequestV1(
        query_id="briefing",
        family_id=QueryFamilyId.EXECUTIVE_BRIEFING,
    )
    with pytest.raises(ValidationError):
        AnalysisPlanV1(mode=AnalysisMode.ANALYTICS, queries=(composite,))


def test_catalog_validation_rejects_incompatible_metric() -> None:
    fields = build_analysis_field_catalog(COMMON_MASTER_FIELDS)
    request = QueryRequestV1(
        query_id="bad-average",
        family_id=QueryFamilyId.NUMERIC_SUMMARY,
        metrics=(
            MetricSpecV1(
                operator=MetricOperator.AVG,
                field_key="vehicle_model",
                alias="average",
            ),
        ),
    )
    with pytest.raises(AnalysisCatalogError, match="incompatible"):
        validate_query_request(request, fields=fields)


def test_scope_is_draft_first_and_logical_values_are_authoritative(
    db: Session,
    seeded_scope: tuple[Workspace, RetrievalPartition],
) -> None:
    workspace, partition = seeded_scope
    scope = resolve_analysis_scope(
        db,
        workspace_id=workspace.id,
        enabled_module_keys={"aircon", "interior"},
        retrieval_partition_ids=(partition.id,),
    )
    assert scope.revision_by_module == {
        "aircon": "revision-aircon-draft",
        "interior": "revision-interior-published",
    }

    visible = build_visible_records_relation(
        scope,
        field_definitions=COMMON_MASTER_FIELDS,
        dialect_name="sqlite",
        field_keys=("vehicle_model",),
    )
    rows = {
        row.record_id: row.vehicle_model
        for row in db.execute(select(visible.c.record_id, visible.c.vehicle_model))
    }
    assert rows == {
        "record-draft-json": "JSON-A",
        "record-draft-json-null": None,
        "record-draft-fallback": "COLUMN-FALLBACK",
        "record-interior": "INT-A",
    }


def test_total_distribution_and_public_artifact_contract(
    db: Session,
    seeded_scope: tuple[Workspace, RetrievalPartition],
) -> None:
    workspace, partition = seeded_scope
    total = QueryRequestV1(
        query_id="total",
        family_id=QueryFamilyId.TOTAL_COUNT,
        limit=10,
    )
    distribution = QueryRequestV1(
        query_id="regions",
        family_id=QueryFamilyId.SHARE,
        dimensions=(DimensionSpecV1(field_key="region_zone"),),
        limit=10,
    )
    artifact = execute_analysis_plan(
        db,
        AnalysisPlanV1(
            mode=AnalysisMode.ANALYTICS,
            queries=(total, distribution),
        ),
        workspace_id=workspace.id,
        enabled_module_keys={"aircon", "interior"},
        retrieval_partition_ids=(partition.id,),
    )
    assert artifact.scope.source_count == 4
    assert artifact.results[0].rows == ({"issue_count": 4},)
    region_rows = {
        row["region_zone"]: (row["issue_count"], row["share"]) for row in artifact.results[1].rows
    }
    assert region_rows["한국"] == pytest.approx((2, 50.0))
    assert region_rows["유럽"] == pytest.approx((1, 25.0))
    assert region_rows["미입력"] == pytest.approx((1, 25.0))

    payload = artifact.to_payload()
    assert payload["version"] == 1
    assert payload["mode"] == "analytics"
    assert payload["exactness"] == "exact"
    assert payload["scope"]["source_count"] == 4
    assert [query["shape"] for query in payload["queries"]] == ["scalar", "bar"]
    assert payload["queries"][0]["columns"][0] == {
        "key": "issue_count",
        "label": "전체 건수",
        "type": "number",
        "role": "metric",
    }


def test_time_series_ignores_invalid_typed_values_and_reports_coverage(
    db: Session,
    seeded_scope: tuple[Workspace, RetrievalPartition],
) -> None:
    workspace, partition = seeded_scope
    request = QueryRequestV1(
        query_id="monthly",
        family_id=QueryFamilyId.TIME_SERIES,
        dimensions=(
            DimensionSpecV1(
                field_key="occurrence_date",
                time_grain=TimeGrain.MONTH,
            ),
        ),
        limit=10,
    )
    artifact = execute_analysis_plan(
        db,
        AnalysisPlanV1(mode=AnalysisMode.ANALYTICS, queries=(request,)),
        workspace_id=workspace.id,
        enabled_module_keys={"aircon", "interior"},
        retrieval_partition_ids=(partition.id,),
    )
    assert {row["occurrence_date"]: row["issue_count"] for row in artifact.results[0].rows} == {
        "2025-01": 2,
        "2025-02": 1,
    }
    coverage = artifact.results[0].coverage[0]
    assert coverage.field_key == "occurrence_date"
    assert coverage.present_count == 3
    assert coverage.missing_count == 0
    assert coverage.invalid_count == 1
    assert "필드 형식과 맞지 않는 값" in artifact.results[0].warnings[0]


def test_metadata_families_report_revision_attachment_and_invalid_coverage(
    db: Session,
    seeded_scope: tuple[Workspace, RetrievalPartition],
) -> None:
    workspace, partition = seeded_scope
    db.add_all(
        [
            LegacyIssueAttachment(
                id="attachment-indexed",
                workspace_id=workspace.id,
                retrieval_partition_id=partition.id,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                revision_id="revision-aircon-draft",
                record_id="record-draft-json",
                stable_record_id="stable-draft-json",
                filename="indexed.pdf",
                storage_key="tests/indexed.pdf",
                index_status="indexed",
            ),
            LegacyIssueAttachment(
                id="attachment-pending",
                workspace_id=workspace.id,
                retrieval_partition_id=partition.id,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                revision_id="revision-aircon-draft",
                record_id="record-draft-json",
                stable_record_id="stable-draft-json",
                filename="pending.pdf",
                storage_key="tests/pending.pdf",
                index_status="pending",
            ),
        ]
    )
    db.commit()
    invalid = QueryRequestV1(
        query_id="invalid-dates",
        family_id=QueryFamilyId.INVALID_VALUES,
        dimensions=(DimensionSpecV1(field_key="occurrence_date"),),
    )
    evidence = QueryRequestV1(
        query_id="attachment-coverage",
        family_id=QueryFamilyId.EVIDENCE_COVERAGE,
    )
    freshness = QueryRequestV1(
        query_id="revision-freshness",
        family_id=QueryFamilyId.ACTIVE_REVISION_FRESHNESS,
    )
    date_coverage = QueryRequestV1(
        query_id="date-coverage",
        family_id=QueryFamilyId.MISSING_POPULATED_RATE,
        metrics=(
            MetricSpecV1(
                operator=MetricOperator.PRESENT_COUNT,
                field_key="occurrence_date",
                alias="present_count",
            ),
            MetricSpecV1(
                operator=MetricOperator.MISSING_COUNT,
                field_key="occurrence_date",
                alias="missing_count",
            ),
        ),
    )

    artifact = execute_analysis_plan(
        db,
        AnalysisPlanV1(
            mode=AnalysisMode.METADATA,
            queries=(invalid, evidence, freshness, date_coverage),
        ),
        workspace_id=workspace.id,
        enabled_module_keys={"aircon", "interior"},
        retrieval_partition_ids=(partition.id,),
    )

    invalid_row = artifact.results[0].rows[0]
    assert invalid_row["field_key"] == "occurrence_date"
    assert invalid_row["invalid_count"] == 1
    attachment_row = artifact.results[1].rows[0]
    assert attachment_row["record_count"] == 4
    assert attachment_row["records_with_attachment"] == 1
    assert attachment_row["attachment_count"] == 2
    assert attachment_row["indexed_attachment_count"] == 1
    freshness_rows = {row["module_key"]: row for row in artifact.results[2].rows}
    assert freshness_rows["aircon"]["revision_id"] == "revision-aircon-draft"
    assert freshness_rows["aircon"]["status"] == "draft"
    assert artifact.results[3].rows == (
        {
            "present_count": 3,
            "missing_count": 0,
            "present_rate": 100.0,
            "missing_rate": 0.0,
        },
    )


def test_multi_value_filters_match_json_members_not_substrings(
    db: Session,
    seeded_scope: tuple[Workspace, RetrievalPartition],
) -> None:
    workspace, partition = seeded_scope
    request = QueryRequestV1(
        query_id="tag-a",
        family_id=QueryFamilyId.FILTERED_COUNT,
        filters=FilterGroupV1(
            conditions=(
                FilterConditionV1(
                    field_key="custom.tags",
                    operator=FilterOperator.CONTAINS_ANY,
                    values=("A",),
                ),
            ),
        ),
    )
    artifact = execute_analysis_plan(
        db,
        AnalysisPlanV1(mode=AnalysisMode.ANALYTICS, queries=(request,)),
        workspace_id=workspace.id,
        enabled_module_keys={"aircon", "interior"},
        field_definitions=ANALYSIS_FIELDS,
        retrieval_partition_ids=(partition.id,),
    )

    assert artifact.results[0].rows == ({"issue_count": 2},)


def test_generated_relation_is_scoped_and_uses_bound_parameters() -> None:
    resolve_scope = {
        "workspace_id": "workspace-secret",
        "module_keys": ("aircon",),
        "revision_ids": ("revision-secret",),
        "revision_by_module": {"aircon": "revision-secret"},
        "retrieval_partition_ids": ("partition-secret",),
    }
    relation = build_visible_records_relation(
        AnalysisScopeV1(**resolve_scope),
        field_definitions=COMMON_MASTER_FIELDS,
        dialect_name="postgresql",
        field_keys=("vehicle_model", "occurrence_date"),
    )
    compiled = select(relation).compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "visible_records" in sql
    assert "_scoped_legacy_issue_records" in sql
    assert "legacy_issue_records" in sql
    assert "workspace-secret" not in sql
    assert "revision-secret" not in sql
    assert "workspace-secret" in compiled.params.values()
    assert "revision-secret" in compiled.params.values()

    complete_relation = build_visible_records_relation(
        AnalysisScopeV1(**resolve_scope),
        field_definitions=COMMON_MASTER_FIELDS,
        dialect_name="postgresql",
        include_generated_helpers=True,
    )
    assert "evidence_past_vehicle_issue" in complete_relation.c
    assert "occurrence_date__date" in complete_relation.c
    helper_sql = str(
        select(complete_relation.c.occurrence_date__date).compile(dialect=postgresql.dialect())
    )
    assert "pg_input_is_valid" in helper_sql


def test_public_artifact_bounds_cells_and_serialized_rows() -> None:
    scope = AnalysisScopeV1(
        workspace_id="workspace",
        module_keys=("aircon",),
        revision_ids=("revision",),
        revision_by_module={"aircon": "revision"},
        retrieval_partition_ids=(),
        source_count=40,
    )
    result = AnalysisResultV1(
        query_id="large",
        title="Large",
        family_id=QueryFamilyId.DETAIL_LIST,
        output_shape="detail",
        scope=scope,
        columns=(
            AnalysisColumnV1(
                key="notes",
                label="비고",
                kind="record",
                value_type="text",
                field_key="notes",
            ),
        ),
        rows=tuple({"notes": "가" * 20_000} for _ in range(40)),
    )
    payload = LegacyIssueAnalysisArtifactV1(
        mode=AnalysisMode.ANALYTICS,
        title="Large",
        scope=scope,
        results=(result,),
    ).to_payload()
    query = payload["queries"][0]

    assert query["truncated"] is True
    assert len(query["rows"]) < 40
    assert len(query["rows"][0]["notes"]) == PUBLIC_CELL_MAX_CHARS
    assert (
        len(json.dumps(query["rows"], ensure_ascii=False).encode("utf-8"))
        <= PUBLIC_QUERY_ROWS_MAX_BYTES
    )
    assert "표시 한도를 초과한 셀 값을 잘랐습니다." in query["warnings"]
    assert "응답 크기 제한에 따라 일부 행만 표시합니다." in query["warnings"]
