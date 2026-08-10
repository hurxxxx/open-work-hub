from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import OrgUnit, User, Workspace
from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisCountingUnit,
    AnalysisDataSource,
    AnalysisMode,
    AnalysisPlanV1,
    DimensionSpecV1,
    FilterConditionV1,
    FilterGroupV1,
    FilterOperator,
    MetricOperator,
    MetricSpecV1,
    QueryFamilyId,
    QueryRequestV1,
)
from ai_do_api.domains.legacy_issues.analysis_sql import (
    CHECKLIST_ANALYSIS_FIELDS,
    build_visible_records_relation,
    execute_analysis_plan,
    execute_analysis_query,
    resolve_analysis_scope,
)
from ai_do_api.domains.legacy_issues.analysis_v2.scope import (
    resolve_runtime_sql_scope,
)
from ai_do_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    COMMON_MASTER_FIELDS,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueRecord,
    LegacyIssueVehicleModel,
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleModuleChecklistRecord,
    LegacyIssueVehicleStage,
)
from ai_do_api.domains.legacy_issues.revisioning import (
    legacy_issue_dataset_revision_key,
)
from ai_do_api.domains.retrieval.models import RetrievalPartition


ANALYSIS_FIELDS = (*COMMON_MASTER_FIELDS, *CHECKLIST_ANALYSIS_FIELDS)


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
            LegacyIssueVehicleModel.__table__,
            LegacyIssueVehicleStage.__table__,
            LegacyIssueVehicleModuleChecklist.__table__,
            LegacyIssueVehicleModuleChecklistRecord.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


@pytest.fixture
def seeded_checklists(db: Session) -> Workspace:
    workspace = Workspace(
        id="workspace-checklist-analysis",
        key="checklist-analysis",
        name="Checklist analysis",
    )
    other_workspace = Workspace(
        id="workspace-checklist-other",
        key="checklist-other",
        name="Checklist other",
    )
    db.add_all([workspace, other_workspace])
    db.flush()

    revisions = [
        _revision(
            workspace_id=workspace.id,
            revision_id="revision-aircon-1",
            module_key="aircon",
            revision_no=1,
        ),
        _revision(
            workspace_id=workspace.id,
            revision_id="revision-aircon-2",
            module_key="aircon",
            revision_no=2,
        ),
        _revision(
            workspace_id=workspace.id,
            revision_id="revision-interior-1",
            module_key="interior",
            revision_no=1,
        ),
        _revision(
            workspace_id=other_workspace.id,
            revision_id="revision-other-aircon-1",
            module_key="aircon",
            revision_no=1,
        ),
    ]
    db.add_all(revisions)
    db.flush()

    vehicles = [
        _vehicle(
            workspace_id=workspace.id,
            vehicle_id="vehicle-a",
            code="CAR-A",
            name="차량 A",
        ),
        _vehicle(
            workspace_id=workspace.id,
            vehicle_id="vehicle-b",
            code="CAR-B",
            name=None,
        ),
        _vehicle(
            workspace_id=other_workspace.id,
            vehicle_id="vehicle-other",
            code="OTHER",
            name="다른 워크스페이스",
        ),
    ]
    db.add_all(vehicles)
    db.flush()
    db.add_all(
        [
            LegacyIssueVehicleStage(
                id=f"stage-{vehicle.id}",
                workspace_id=vehicle.workspace_id,
                vehicle_model_id=vehicle.id,
                name="P0",
                name_normalized="p0",
                sequence_no=1,
                created_at=datetime(2025, 1, 1, 9, 0, 0),
                updated_at=datetime(2025, 1, 1, 9, 0, 0),
            )
            for vehicle in vehicles
        ]
    )
    db.flush()

    old_a = _checklist(
        checklist_id="checklist-a-old",
        workspace_id=workspace.id,
        vehicle_model_id="vehicle-a",
        module_key="aircon",
        revision_id="revision-aircon-1",
        revision_no=1,
        status="completed",
        updated_at=datetime(2025, 1, 10, 9, 0, 0),
    )
    latest_a = _checklist(
        checklist_id="checklist-a-latest",
        workspace_id=workspace.id,
        vehicle_model_id="vehicle-a",
        module_key="aircon",
        revision_id="revision-aircon-2",
        revision_no=2,
        status="completed",
        updated_at=datetime(2025, 2, 10, 9, 0, 0),
    )
    latest_b = _checklist(
        checklist_id="checklist-b-latest",
        workspace_id=workspace.id,
        vehicle_model_id="vehicle-b",
        module_key="aircon",
        revision_id="revision-aircon-2",
        revision_no=2,
        status="draft",
        updated_at=datetime(2025, 2, 11, 9, 0, 0),
    )
    interior = _checklist(
        checklist_id="checklist-a-interior",
        workspace_id=workspace.id,
        vehicle_model_id="vehicle-a",
        module_key="interior",
        revision_id="revision-interior-1",
        revision_no=1,
        status="completed",
        updated_at=datetime(2025, 2, 12, 9, 0, 0),
    )
    other = _checklist(
        checklist_id="checklist-other",
        workspace_id=other_workspace.id,
        vehicle_model_id="vehicle-other",
        module_key="aircon",
        revision_id="revision-other-aircon-1",
        revision_no=1,
        status="completed",
        updated_at=datetime(2025, 2, 13, 9, 0, 0),
    )
    db.add_all([old_a, latest_a, latest_b, interior, other])
    db.flush()

    db.add_all(
        [
            _checklist_record(
                record_id="checklist-record-old",
                workspace_id=workspace.id,
                checklist_id=old_a.id,
                source_record_id="source-old",
                symptom="OLD-ONLY",
                cause="이전 원인",
            ),
            _checklist_record(
                record_id="checklist-record-a-1",
                workspace_id=workspace.id,
                checklist_id=latest_a.id,
                source_record_id="source-a-1",
                symptom="소음",
                cause="체결",
            ),
            _checklist_record(
                record_id="checklist-record-a-2",
                workspace_id=workspace.id,
                checklist_id=latest_a.id,
                source_record_id="source-a-2",
                symptom="누수",
                cause="실링",
            ),
            _checklist_record(
                record_id="checklist-record-b-1",
                workspace_id=workspace.id,
                checklist_id=latest_b.id,
                source_record_id="source-b-1",
                symptom="소음",
                cause="베어링",
            ),
            _checklist_record(
                record_id="checklist-record-interior",
                workspace_id=workspace.id,
                checklist_id=interior.id,
                source_record_id="source-interior",
                symptom="내장",
                cause="내장 원인",
            ),
            _checklist_record(
                record_id="checklist-record-other",
                workspace_id=other_workspace.id,
                checklist_id=other.id,
                source_record_id="source-other",
                symptom="다른 워크스페이스",
                cause="다른 원인",
            ),
        ]
    )
    db.add(
        LegacyIssueRecord(
            id="legacy-record-only",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id="revision-aircon-2",
            stable_record_id="legacy-stable-only",
            field_values={"symptom": "소음", "cause": "마스터 원인"},
            symptom="소음",
            cause="마스터 원인",
        )
    )
    db.commit()
    return workspace


def test_query_request_selects_vehicle_checklists_without_changing_the_default() -> None:
    checklist_query = QueryRequestV1(
        query_id="checklist-count",
        family_id=QueryFamilyId.TOTAL_COUNT,
        data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
    )
    legacy_query = QueryRequestV1(
        query_id="legacy-count",
        family_id=QueryFamilyId.TOTAL_COUNT,
    )

    assert checklist_query.data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
    assert legacy_query.data_source == AnalysisDataSource.LEGACY_ISSUES


def test_scope_selects_only_latest_checklist_per_workspace_vehicle_and_enabled_module(
    db: Session,
    seeded_checklists: Workspace,
) -> None:
    scope = resolve_analysis_scope(
        db,
        workspace_id=seeded_checklists.id,
        enabled_module_keys={"aircon"},
        retrieval_partition_ids=(),
        data_sources=(
            AnalysisDataSource.LEGACY_ISSUES,
            AnalysisDataSource.VEHICLE_CHECKLISTS,
        ),
    )

    assert scope.checklist_ids == (
        "checklist-a-latest",
        "checklist-b-latest",
    )
    assert scope.data_sources == (
        AnalysisDataSource.LEGACY_ISSUES,
        AnalysisDataSource.VEHICLE_CHECKLISTS,
    )
    assert "checklist-a-old" not in scope.checklist_ids
    assert "checklist-a-interior" not in scope.checklist_ids
    assert "checklist-other" not in scope.checklist_ids


def test_scope_prefers_latest_vehicle_stage_over_older_stage_recency(
    db: Session,
    seeded_checklists: Workspace,
) -> None:
    later_stage = LegacyIssueVehicleStage(
        id="stage-vehicle-a-p1",
        workspace_id=seeded_checklists.id,
        vehicle_model_id="vehicle-a",
        name="P1",
        name_normalized="p1",
        sequence_no=2,
        previous_stage_id="stage-vehicle-a",
        created_at=datetime(2025, 3, 1, 9, 0, 0),
        updated_at=datetime(2025, 3, 1, 9, 0, 0),
    )
    later_stage_checklist = _checklist(
        checklist_id="checklist-a-p1",
        workspace_id=seeded_checklists.id,
        vehicle_model_id="vehicle-a",
        vehicle_stage_id=later_stage.id,
        module_key="aircon",
        revision_id="revision-aircon-1",
        revision_no=1,
        status="draft",
        updated_at=datetime(2025, 1, 5, 9, 0, 0),
    )
    db.add_all([later_stage, later_stage_checklist])
    db.commit()

    legacy_scope = resolve_analysis_scope(
        db,
        workspace_id=seeded_checklists.id,
        enabled_module_keys={"aircon"},
        retrieval_partition_ids=(),
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
    )
    runtime_scope = resolve_runtime_sql_scope(
        db,
        workspace_id=seeded_checklists.id,
        module_keys={"aircon"},
        partition_ids=(),
    )

    assert legacy_scope.checklist_ids == (
        "checklist-a-p1",
        "checklist-b-latest",
    )
    assert runtime_scope.checklist_ids == (
        "checklist-a-p1",
        "checklist-b-latest",
    )
    assert "checklist-a-latest" not in legacy_scope.checklist_ids
    assert "checklist-a-latest" not in runtime_scope.checklist_ids


def test_scope_rejects_cross_workspace_vehicle_reference(
    db: Session,
    seeded_checklists: Workspace,
) -> None:
    cross_workspace = _checklist(
        checklist_id="checklist-cross-workspace-vehicle",
        workspace_id=seeded_checklists.id,
        vehicle_model_id="vehicle-other",
        module_key="aircon",
        revision_id="revision-aircon-2",
        revision_no=2,
        status="draft",
        updated_at=datetime(2025, 3, 1, 9, 0, 0),
    )
    db.add(cross_workspace)
    db.flush()
    db.add(
        _checklist_record(
            record_id="checklist-record-cross-workspace-vehicle",
            workspace_id=seeded_checklists.id,
            checklist_id=cross_workspace.id,
            source_record_id="source-cross-workspace",
            symptom="노출되면 안 됨",
            cause="다른 워크스페이스 차량",
        )
    )
    db.commit()

    scope = resolve_analysis_scope(
        db,
        workspace_id=seeded_checklists.id,
        enabled_module_keys={"aircon"},
        retrieval_partition_ids=(),
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
    )

    assert cross_workspace.id not in scope.checklist_ids


def test_typed_checklist_count_distribution_and_detail_use_snapshot_and_synthetic_fields(
    db: Session,
    seeded_checklists: Workspace,
) -> None:
    scope = resolve_analysis_scope(
        db,
        workspace_id=seeded_checklists.id,
        enabled_module_keys={"aircon"},
        retrieval_partition_ids=(),
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
    )
    completed_count = QueryRequestV1(
        query_id="completed-count",
        family_id=QueryFamilyId.FILTERED_COUNT,
        data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
        filters=FilterGroupV1(
            conditions=(
                FilterConditionV1(
                    field_key="checklist_status",
                    operator=FilterOperator.EQ,
                    value="completed",
                ),
            ),
        ),
    )
    symptom_distribution = QueryRequestV1(
        query_id="symptom-distribution",
        family_id=QueryFamilyId.SINGLE_DISTRIBUTION,
        data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
        dimensions=(DimensionSpecV1(field_key="symptom"),),
    )
    checklist_status_distribution = QueryRequestV1(
        query_id="checklist-status-distribution",
        family_id=QueryFamilyId.SINGLE_DISTRIBUTION,
        data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
        metrics=(
            MetricSpecV1(
                operator=MetricOperator.DISTINCT_COUNT,
                field_key="checklist_id",
                alias="checklist_count",
            ),
        ),
        dimensions=(DimensionSpecV1(field_key="checklist_status"),),
    )
    detail = QueryRequestV1(
        query_id="checklist-detail",
        family_id=QueryFamilyId.DETAIL_LIST,
        data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
        detail_fields=(
            "symptom",
            "cause",
            "checklist_id",
            "checklist_vehicle_code",
            "checklist_vehicle_name",
            "checklist_status",
            "checklist_module",
            "checklist_source_revision_no",
            "checklist_updated_date",
        ),
        limit=10,
    )

    count_result = execute_analysis_query(
        db,
        completed_count,
        scope=scope,
        field_definitions=ANALYSIS_FIELDS,
    )
    distribution_result = execute_analysis_query(
        db,
        symptom_distribution,
        scope=scope,
        field_definitions=ANALYSIS_FIELDS,
    )
    checklist_status_result = execute_analysis_query(
        db,
        checklist_status_distribution,
        scope=scope,
        field_definitions=ANALYSIS_FIELDS,
    )
    detail_result = execute_analysis_query(
        db,
        detail,
        scope=scope,
        field_definitions=ANALYSIS_FIELDS,
    )

    assert count_result.rows == ({"issue_count": 2},)
    assert count_result.scope.source_count == 3
    assert count_result.scope.data_sources == (AnalysisDataSource.VEHICLE_CHECKLISTS,)
    assert {row["symptom"]: row["issue_count"] for row in distribution_result.rows} == {
        "소음": 2,
        "누수": 1,
    }
    assert {
        row["checklist_status"]: row["checklist_count"] for row in checklist_status_result.rows
    } == {
        "completed": 1,
        "draft": 1,
    }
    assert len(detail_result.rows) == 3
    assert {row["checklist_id"] for row in detail_result.rows} == {
        "checklist-a-latest",
        "checklist-b-latest",
    }
    assert {row["symptom"] for row in detail_result.rows} == {"소음", "누수"}
    assert {row["checklist_vehicle_code"] for row in detail_result.rows} == {"CAR-A", "CAR-B"}
    assert {row["checklist_vehicle_name"] for row in detail_result.rows} == {"차량 A", "CAR-B"}
    assert {row["checklist_status"] for row in detail_result.rows} == {
        "completed",
        "draft",
    }
    assert {row["checklist_module"] for row in detail_result.rows} == {"aircon"}
    assert {row["checklist_source_revision_no"] for row in detail_result.rows} == {2}
    assert {row["checklist_updated_date"] for row in detail_result.rows} == {
        "2025-02-10",
        "2025-02-11",
    }


def test_checklist_overall_and_module_breakdown_share_item_population(
    db: Session,
    seeded_checklists: Workspace,
) -> None:
    artifact = execute_analysis_plan(
        db,
        AnalysisPlanV1(
            mode=AnalysisMode.ANALYTICS,
            queries=(
                QueryRequestV1(
                    query_id="overall",
                    family_id=QueryFamilyId.TOTAL_COUNT,
                    data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
                ),
                QueryRequestV1(
                    query_id="by-module",
                    family_id=QueryFamilyId.SINGLE_DISTRIBUTION,
                    data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
                    dimensions=(DimensionSpecV1(field_key="checklist_module"),),
                ),
            ),
        ),
        workspace_id=seeded_checklists.id,
        enabled_module_keys={"aircon", "interior"},
        field_definitions=ANALYSIS_FIELDS,
        retrieval_partition_ids=(),
    )

    assert artifact.results[0].rows == ({"issue_count": 4},)
    assert {row["checklist_module"]: row["issue_count"] for row in artifact.results[1].rows} == {
        "aircon": 3,
        "interior": 1,
    }
    assert all(
        result.scope.data_sources == (AnalysisDataSource.VEHICLE_CHECKLISTS,)
        and result.scope.source_count == 4
        and result.totals["population_count"] == 4
        for result in artifact.results
    )


def test_checklist_result_distinguishes_item_population_from_document_counting_unit(
    db: Session,
    seeded_checklists: Workspace,
) -> None:
    artifact = execute_analysis_plan(
        db,
        AnalysisPlanV1(
            mode=AnalysisMode.ANALYTICS,
            queries=(
                QueryRequestV1(
                    query_id="item-count",
                    family_id=QueryFamilyId.TOTAL_COUNT,
                    data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
                ),
                QueryRequestV1(
                    query_id="checklist-count",
                    family_id=QueryFamilyId.DISTINCT_COUNT,
                    data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
                    metrics=(
                        MetricSpecV1(
                            operator=MetricOperator.DISTINCT_COUNT,
                            field_key="checklist_id",
                            alias="checklist_count",
                        ),
                    ),
                ),
            ),
        ),
        workspace_id=seeded_checklists.id,
        enabled_module_keys={"aircon"},
        field_definitions=ANALYSIS_FIELDS,
        retrieval_partition_ids=(),
    )

    item_result, checklist_result = artifact.results
    assert item_result.rows == ({"issue_count": 3},)
    assert item_result.population_unit == AnalysisCountingUnit.CHECKLIST_ITEMS
    assert item_result.counting_unit == AnalysisCountingUnit.CHECKLIST_ITEMS
    assert checklist_result.rows == ({"checklist_count": 2},)
    assert checklist_result.population_unit == AnalysisCountingUnit.CHECKLIST_ITEMS
    assert checklist_result.counting_unit == AnalysisCountingUnit.CHECKLISTS
    assert checklist_result.totals["population_count"] == 3

    item_payload, checklist_payload = artifact.to_payload()["queries"]
    assert item_payload["population_unit"] == "checklist_items"
    assert item_payload["counting_unit"] == "checklist_items"
    assert checklist_payload["population_unit"] == "checklist_items"
    assert checklist_payload["counting_unit"] == "checklists"


def test_legacy_and_checklist_queries_do_not_union_or_double_count_sources(
    db: Session,
    seeded_checklists: Workspace,
) -> None:
    legacy_total = QueryRequestV1(
        query_id="legacy-total",
        family_id=QueryFamilyId.TOTAL_COUNT,
    )
    checklist_total = QueryRequestV1(
        query_id="checklist-total",
        family_id=QueryFamilyId.TOTAL_COUNT,
        data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
    )

    artifact = execute_analysis_plan(
        db,
        AnalysisPlanV1(
            mode=AnalysisMode.ANALYTICS,
            queries=(legacy_total, checklist_total),
        ),
        workspace_id=seeded_checklists.id,
        enabled_module_keys={"aircon"},
        field_definitions=ANALYSIS_FIELDS,
        retrieval_partition_ids=(),
    )

    assert artifact.results[0].rows == ({"issue_count": 1},)
    assert artifact.results[0].scope.source_count == 1
    assert artifact.results[1].rows == ({"issue_count": 3},)
    assert artifact.results[1].scope.source_count == 3
    assert artifact.scope.source_count == 4
    assert artifact.scope.source_counts == {
        AnalysisDataSource.LEGACY_ISSUES: 1,
        AnalysisDataSource.VEHICLE_CHECKLISTS: 3,
    }
    assert "source_count" not in artifact.to_payload()["scope"]
    assert artifact.scope.data_sources == (
        AnalysisDataSource.LEGACY_ISSUES,
        AnalysisDataSource.VEHICLE_CHECKLISTS,
    )


def test_generated_visible_records_preserves_checklist_data_source(
    db: Session,
    seeded_checklists: Workspace,
) -> None:
    scope = resolve_analysis_scope(
        db,
        workspace_id=seeded_checklists.id,
        enabled_module_keys={"aircon"},
        retrieval_partition_ids=(),
        data_sources=(AnalysisDataSource.VEHICLE_CHECKLISTS,),
    )
    visible_records = build_visible_records_relation(
        scope,
        field_definitions=ANALYSIS_FIELDS,
        dialect_name="postgresql",
        field_keys=(
            "symptom",
            "checklist_id",
            "checklist_vehicle_code",
            "checklist_updated_date",
        ),
        include_generated_helpers=True,
        data_source=AnalysisDataSource.VEHICLE_CHECKLISTS,
    )

    compiled = select(visible_records).compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "visible_records" in sql
    assert "legacy_issue_vehicle_module_checklist_records" in sql
    assert "legacy_issue_vehicle_module_checklists" in sql
    assert "legacy_issue_vehicle_models" in sql
    assert "legacy_issue_records" not in sql
    assert "checklist_id" in visible_records.c
    assert "checklist_vehicle_code" in visible_records.c
    assert "checklist_updated_date__date" in visible_records.c


def _revision(
    *,
    workspace_id: str,
    revision_id: str,
    module_key: str,
    revision_no: int,
) -> LegacyIssueDataRevision:
    return LegacyIssueDataRevision(
        id=revision_id,
        workspace_id=workspace_id,
        dataset_key=legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            module_key,
        ),
        revision_no=revision_no,
        status="published",
        created_at=datetime(2025, 1, revision_no, 9, 0, 0),
        updated_at=datetime(2025, 1, revision_no, 9, 0, 0),
        published_at=datetime(2025, 1, revision_no, 9, 0, 0),
    )


def _vehicle(
    *,
    workspace_id: str,
    vehicle_id: str,
    code: str,
    name: str | None,
) -> LegacyIssueVehicleModel:
    return LegacyIssueVehicleModel(
        id=vehicle_id,
        workspace_id=workspace_id,
        vehicle_code=code,
        vehicle_code_normalized=code.casefold(),
        vehicle_name=name,
        active=True,
        created_at=datetime(2025, 1, 1, 9, 0, 0),
        updated_at=datetime(2025, 1, 1, 9, 0, 0),
    )


def _checklist(
    *,
    checklist_id: str,
    workspace_id: str,
    vehicle_model_id: str,
    vehicle_stage_id: str | None = None,
    module_key: str,
    revision_id: str,
    revision_no: int,
    status: str,
    updated_at: datetime,
) -> LegacyIssueVehicleModuleChecklist:
    return LegacyIssueVehicleModuleChecklist(
        id=checklist_id,
        workspace_id=workspace_id,
        vehicle_model_id=vehicle_model_id,
        vehicle_stage_id=vehicle_stage_id or f"stage-{vehicle_model_id}",
        module_key=module_key,
        status=status,
        source_dataset_key=COMMON_MASTER_DATASET_KEY,
        source_master_revision_id=revision_id,
        source_master_revision_no=revision_no,
        definition_snapshot={},
        row_count=0,
        created_at=updated_at,
        updated_at=updated_at,
    )


def _checklist_record(
    *,
    record_id: str,
    workspace_id: str,
    checklist_id: str,
    source_record_id: str,
    symptom: str,
    cause: str,
) -> LegacyIssueVehicleModuleChecklistRecord:
    return LegacyIssueVehicleModuleChecklistRecord(
        id=record_id,
        workspace_id=workspace_id,
        checklist_id=checklist_id,
        source_record_id=source_record_id,
        source_stable_record_id=f"stable-{source_record_id}",
        sort_order=0,
        field_values={
            "symptom": symptom,
            "cause": cause,
            "countermeasure": "개선대책",
        },
        created_at=datetime(2025, 2, 1, 9, 0, 0),
        updated_at=datetime(2025, 2, 1, 9, 0, 0),
    )
