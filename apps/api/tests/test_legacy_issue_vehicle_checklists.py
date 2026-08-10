from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from ai_do_api.core.db import Base, get_session_factory
from ai_do_api.core.i18n import translate_message
from ai_do_api.domains.auth.models import OrgUnit, User, Workspace, utcnow_naive
from ai_do_api.domains.legacy_issues import router as legacy_issue_router
from ai_do_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    create_dataset_record,
    get_dataset_definition_with_all_module_fields,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueAttachment,
    LegacyIssueColumnOrder,
    LegacyIssueDataRevision,
    LegacyIssueDataRevisionEvent,
    LegacyIssueModuleField,
    LegacyIssueRecord,
    LegacyIssueRecordHistory,
    LegacyIssueSystemFieldSetting,
    LegacyIssueVehicleChecklistRecord,
    LegacyIssueVehicleChecklistRevision,
    LegacyIssueVehicleModel,
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleStage,
)
from ai_do_api.domains.legacy_issues.revisioning import (
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    legacy_issue_dataset_revision_key,
)
from ai_do_api.domains.legacy_issues.vehicle_checklists import (
    VEHICLE_CHECKLIST_CHECK_FIELD_KEYS,
    VEHICLE_CHECKLIST_RECORD_KIND,
    VEHICLE_MODEL_RECORD_KIND,
    complete_vehicle_checklist_revision,
    create_vehicle_checklist_revision,
    create_vehicle_model,
    create_vehicle_stage,
    delete_vehicle_checklist_revision,
    list_published_master_revisions,
    list_vehicle_checklist_history,
    list_vehicle_checklist_revisions,
    list_vehicle_models,
    list_vehicle_stages,
    list_vehicle_checklist_records,
    permanently_delete_vehicle_model,
    reopen_vehicle_checklist_revision,
    update_vehicle_model,
    update_vehicle_stage,
    update_vehicle_checklist_records,
    vehicle_checklist_summaries,
    vehicle_generated_checklist_counts,
)
from ai_do_api.domains.retrieval.models import RetrievalPartition
from dev_accounts import auth_headers, create_workspace_user_session


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            OrgUnit.__table__,
            Workspace.__table__,
            User.__table__,
            RetrievalPartition.__table__,
            LegacyIssueDataRevision.__table__,
            LegacyIssueDataRevisionEvent.__table__,
            LegacyIssueRecord.__table__,
            LegacyIssueRecordHistory.__table__,
            LegacyIssueAttachment.__table__,
            LegacyIssueModuleField.__table__,
            LegacyIssueSystemFieldSetting.__table__,
            LegacyIssueColumnOrder.__table__,
            LegacyIssueVehicleModel.__table__,
            LegacyIssueVehicleStage.__table__,
            LegacyIssueVehicleChecklistRevision.__table__,
            LegacyIssueVehicleChecklistRecord.__table__,
            LegacyIssueVehicleModuleChecklist.__table__,
        ],
    )
    return Session(engine)


def _test_user(user_id: str = "user-1") -> User:
    return User(
        id=user_id,
        login_id=user_id,
        email=f"{user_id}@example.com",
        full_name=user_id,
        password_hash="hash",
        status="active",
    )


def _workspace_and_user(db: Session) -> tuple[Workspace, User]:
    workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
    user = _test_user()
    db.add_all([workspace, user])
    db.flush()
    return workspace, user


def _published_master_revision(
    db: Session,
    workspace: Workspace,
    *,
    revision_id: str = "master-rev-3",
    revision_no: int = 3,
) -> LegacyIssueDataRevision:
    now = utcnow_naive()
    revision = LegacyIssueDataRevision(
        id=revision_id,
        workspace_id=workspace.id,
        dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
        revision_no=revision_no,
        status=REVISION_STATUS_PUBLISHED,
        note=f"Rev. {revision_no}",
        created_at=now,
        updated_at=now,
        published_at=now,
    )
    db.add(revision)
    db.flush()
    return revision


def _draft_master_revision(
    db: Session,
    workspace: Workspace,
    *,
    revision_id: str = "master-draft",
) -> LegacyIssueDataRevision:
    now = utcnow_naive()
    revision = LegacyIssueDataRevision(
        id=revision_id,
        workspace_id=workspace.id,
        dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
        revision_no=None,
        status=REVISION_STATUS_DRAFT,
        note="Draft",
        created_at=now,
        updated_at=now,
    )
    db.add(revision)
    db.flush()
    return revision


def _create_master_record(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    revision: LegacyIssueDataRevision,
    module_key: str,
    issue_no: str,
    symptom: str,
) -> LegacyIssueRecord:
    definition = get_dataset_definition_with_all_module_fields(
        db,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        workspace=workspace,
    )
    return create_dataset_record(
        db,
        definition,
        workspace=workspace,
        user=user,
        revision=revision,
        module_key=module_key,
        values={
            "legacy_issue_number": issue_no,
            "vehicle_model": "OLD-CAR",
            "symptom": symptom,
            "cause": "원인",
            "countermeasure": "개선대책",
            "check_plan": "마스터 점검방안",
            "applied": "O",
            "reflection_result": "마스터 결과",
        },
    )


def _generated_aggregate_checklist(
    db: Session,
    *,
    workspace: Workspace,
    vehicle: LegacyIssueVehicleModel,
    revision: LegacyIssueDataRevision,
) -> LegacyIssueVehicleChecklistRevision:
    now = utcnow_naive()
    checklist = LegacyIssueVehicleChecklistRevision(
        id=f"aggregate-{vehicle.id}",
        workspace_id=workspace.id,
        vehicle_model_id=vehicle.id,
        revision_no=1,
        status="draft",
        source_dataset_key=COMMON_MASTER_DATASET_KEY,
        source_master_revision_id=revision.id,
        source_master_revision_no=revision.revision_no,
        definition_snapshot={},
        row_count=0,
        created_at=now,
        updated_at=now,
    )
    db.add(checklist)
    db.flush()
    return checklist


def _generated_module_checklist(
    db: Session,
    *,
    workspace: Workspace,
    vehicle: LegacyIssueVehicleModel,
    revision: LegacyIssueDataRevision,
    module_key: str = "aircon",
) -> LegacyIssueVehicleModuleChecklist:
    now = utcnow_naive()
    checklist = LegacyIssueVehicleModuleChecklist(
        id=f"module-{module_key}-{vehicle.id}",
        workspace_id=workspace.id,
        vehicle_model_id=vehicle.id,
        vehicle_stage_id=db.scalar(
            select(LegacyIssueVehicleStage.id).where(
                LegacyIssueVehicleStage.vehicle_model_id == vehicle.id
            )
        ),
        module_key=module_key,
        status="draft",
        source_dataset_key=COMMON_MASTER_DATASET_KEY,
        source_master_revision_id=revision.id,
        source_master_revision_no=revision.revision_no,
        definition_snapshot={},
        row_count=0,
        created_at=now,
        updated_at=now,
    )
    db.add(checklist)
    db.flush()
    return checklist


def test_list_published_master_revisions_returns_published_revisions_desc() -> None:
    with _session() as db:
        workspace, _user = _workspace_and_user(db)
        _published_master_revision(
            db,
            workspace,
            revision_id="master-rev-3",
            revision_no=3,
        )
        _published_master_revision(
            db,
            workspace,
            revision_id="master-rev-5",
            revision_no=5,
        )
        _draft_master_revision(db, workspace, revision_id="master-draft")

        revisions = list_published_master_revisions(db, workspace=workspace)

        assert [item.id for item in revisions] == ["master-rev-5", "master-rev-3"]


def test_vehicle_checklist_revision_copies_master_rows_and_clears_check_fields() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        master_revision = _published_master_revision(db, workspace)
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=master_revision,
            module_key="aircon",
            issue_no="PV-001",
            symptom="공조 소음",
        )
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=master_revision,
            module_key="interior",
            issue_no="PV-002",
            symptom="의장 이음",
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="MX5",
        )

        checklist_revision = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=master_revision.id,
        )

        rows = list(
            db.scalars(
                select(LegacyIssueVehicleChecklistRecord).where(
                    LegacyIssueVehicleChecklistRecord.checklist_revision_id == checklist_revision.id
                )
            )
        )
        assert checklist_revision.revision_no == 1
        assert checklist_revision.source_master_revision_id == master_revision.id
        assert checklist_revision.source_master_revision_no == 3
        assert checklist_revision.row_count == 2
        assert len(rows) == 2
        assert {row.source_module_key for row in rows} == {"aircon", "interior"}
        assert all(
            not (VEHICLE_CHECKLIST_CHECK_FIELD_KEYS & set(row.field_values or {})) for row in rows
        )
        aircon_row = next(row for row in rows if row.source_module_key == "aircon")
        assert aircon_row.field_values["symptom"] == "공조 소음"
        assert "check_plan" in {
            field["key"] for field in checklist_revision.definition_snapshot["fields"]
        }


def test_vehicle_checklist_includes_and_filters_compressor_module_rows() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        aggregate_marker = _published_master_revision(
            db,
            workspace,
            revision_id="aggregate-marker",
            revision_no=1,
        )
        now = utcnow_naive()
        electric_revision = LegacyIssueDataRevision(
            id="compressor-electric-revision-36",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "compressor-electric",
            ),
            revision_no=36,
            status=REVISION_STATUS_PUBLISHED,
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        mechanical_revision = LegacyIssueDataRevision(
            id="compressor-mechanical-revision-1",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "compressor-mechanical",
            ),
            revision_no=1,
            status=REVISION_STATUS_PUBLISHED,
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        db.add_all([electric_revision, mechanical_revision])
        db.flush()
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=electric_revision,
            module_key="compressor-electric",
            issue_no="COMP-E-001",
            symptom="전동 컴프레서 소음",
        )
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=mechanical_revision,
            module_key="compressor-mechanical",
            issue_no="COMP-M-001",
            symptom="기계식 컴프레서 진동",
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="COMP-CAR",
        )

        checklist_revision = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=aggregate_marker.id,
        )
        _revision, _definition, electric_rows, electric_total = list_vehicle_checklist_records(
            db,
            workspace=workspace,
            revision_id=checklist_revision.id,
            view_key="compressor-electric",
        )
        _revision, _definition, mechanical_rows, mechanical_total = list_vehicle_checklist_records(
            db,
            workspace=workspace,
            revision_id=checklist_revision.id,
            view_key="compressor-mechanical",
        )

        assert checklist_revision.row_count == 2
        assert electric_total == 1
        assert [row.source_module_key for row in electric_rows] == ["compressor-electric"]
        assert mechanical_total == 1
        assert [row.source_module_key for row in mechanical_rows] == ["compressor-mechanical"]


def test_vehicle_model_optional_name_and_notes_can_be_searched_and_cleared() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="MX5",
            vehicle_name="싼타페 후속",
            notes="양산 검토 대상",
        )

        matches_by_name = list_vehicle_models(db, workspace=workspace, query="싼타페")
        matches_by_notes = list_vehicle_models(db, workspace=workspace, query="양산")

        assert [item.id for item in matches_by_name] == [vehicle.id]
        assert [item.id for item in matches_by_notes] == [vehicle.id]

        updated = update_vehicle_model(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
            vehicle_name=None,
            vehicle_name_set=True,
            notes="",
            notes_set=True,
        )

        assert updated.vehicle_name is None
        assert updated.notes is None


def test_vehicle_model_creation_always_creates_initial_stage() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="STAGED-AT-CREATE",
            initial_stage_name="P0",
        )

        stages = list_vehicle_stages(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
        )
        assert [(item.name, item.sequence_no) for item in stages] == [("P0", 1)]
        assert stages[0].previous_stage_id is None

        with pytest.raises(HTTPException) as duplicate:
            create_vehicle_stage(
                db,
                workspace=workspace,
                user=user,
                vehicle_model_id=vehicle.id,
                name=" p0 ",
            )
        assert duplicate.value.status_code == 409
        assert duplicate.value.detail.code == "legacy_issues.vehicle_stage_duplicate"

        vehicle.active = False
        db.flush()
        with pytest.raises(HTTPException) as inactive:
            create_vehicle_stage(
                db,
                workspace=workspace,
                user=user,
                vehicle_model_id=vehicle.id,
                name="P1",
            )
        assert inactive.value.status_code == 400
        assert inactive.value.detail.code == "legacy_issues.vehicle_stage_vehicle_inactive"


def test_vehicle_stage_name_can_change_without_changing_identity_or_order() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="RENAME-STAGE",
            initial_stage_name="P0",
        )
        first_stage = list_vehicle_stages(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
        )[0]
        second_stage = create_vehicle_stage(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            name="P1",
        )

        renamed = update_vehicle_stage(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
            stage_id=first_stage.id,
            name=" Proto ",
        )
        assert renamed.id == first_stage.id
        assert renamed.name == "Proto"
        assert renamed.name_normalized == "proto"
        assert renamed.sequence_no == 1
        assert renamed.previous_stage_id is None
        assert second_stage.previous_stage_id == first_stage.id

        with pytest.raises(HTTPException) as duplicate:
            update_vehicle_stage(
                db,
                workspace=workspace,
                vehicle_model_id=vehicle.id,
                stage_id=first_stage.id,
                name="p1",
            )
        assert duplicate.value.status_code == 409
        assert duplicate.value.detail.code == "legacy_issues.vehicle_stage_duplicate"


def test_vehicle_generated_checklist_counts_use_one_query() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        revision = _published_master_revision(db, workspace)
        first_vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="COUNT-1",
        )
        second_vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="COUNT-2",
        )
        _generated_aggregate_checklist(
            db,
            workspace=workspace,
            vehicle=first_vehicle,
            revision=revision,
        )
        _generated_module_checklist(
            db,
            workspace=workspace,
            vehicle=first_vehicle,
            revision=revision,
        )
        _generated_module_checklist(
            db,
            workspace=workspace,
            vehicle=second_vehicle,
            revision=revision,
        )
        first_vehicle_id = first_vehicle.id
        second_vehicle_id = second_vehicle.id
        executed_statements = 0

        def count_statement(*_args) -> None:
            nonlocal executed_statements
            executed_statements += 1

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", count_statement)
        try:
            counts = vehicle_generated_checklist_counts(
                db,
                workspace=workspace,
                vehicle_model_ids=[
                    first_vehicle_id,
                    second_vehicle_id,
                    "missing-vehicle",
                    first_vehicle_id,
                ],
            )
        finally:
            event.remove(engine, "before_cursor_execute", count_statement)

        assert executed_statements == 1
        assert counts == {
            first_vehicle_id: 2,
            second_vehicle_id: 1,
            "missing-vehicle": 0,
        }


@pytest.mark.parametrize("active", [True, False])
def test_permanently_delete_vehicle_model_records_snapshot_and_preserves_master_data(
    active: bool,
) -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        revision = _published_master_revision(db, workspace)
        master_record = _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=revision,
            module_key="aircon",
            issue_no=f"MASTER-DELETE-{active}",
            symptom="차종 삭제 후에도 유지",
        )
        master_attachment = LegacyIssueAttachment(
            id=f"master-delete-attachment-{active}",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id=master_record.stable_record_id,
            record_id=master_record.id,
            filename="master.pdf",
            content_type="application/pdf",
            size_bytes=10,
            storage_key=f"legacy-issues/master-delete-{active}.pdf",
            uploaded_by_id=user.id,
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code=f"DELETE-{active}",
            vehicle_name="삭제 대상 차종",
            notes="삭제 감사 스냅샷",
        )
        vehicle.active = active
        db.add(master_attachment)
        db.flush()
        vehicle_id = vehicle.id
        master_record_id = master_record.id
        master_attachment_id = master_attachment.id
        expected_created_at = vehicle.created_at.isoformat()
        expected_updated_at = vehicle.updated_at.isoformat()

        permanently_delete_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle_id,
        )

        assert db.get(LegacyIssueVehicleModel, vehicle_id) is None
        history = db.scalar(
            select(LegacyIssueRecordHistory).where(
                LegacyIssueRecordHistory.workspace_id == workspace.id,
                LegacyIssueRecordHistory.record_kind == VEHICLE_MODEL_RECORD_KIND,
                LegacyIssueRecordHistory.record_id == vehicle_id,
            )
        )
        assert history is not None
        assert history.action == "delete"
        assert history.actor_user_id == user.id
        assert history.old_value == f"DELETE-{active}"
        assert history.new_value is None
        assert history.details == {
            "vehicle_model": {
                "id": vehicle_id,
                "vehicle_code": f"DELETE-{active}",
                "vehicle_name": "삭제 대상 차종",
                "notes": "삭제 감사 스냅샷",
                "active": active,
                "created_by_id": user.id,
                "created_at": expected_created_at,
                "updated_at": expected_updated_at,
            },
            "generated_checklist_count": 0,
        }
        assert db.get(LegacyIssueDataRevision, revision.id) is not None
        assert db.get(LegacyIssueRecord, master_record_id) is not None
        assert db.get(LegacyIssueAttachment, master_attachment_id) is not None


@pytest.mark.parametrize("checklist_kind", ["aggregate", "module"])
def test_permanently_delete_vehicle_model_rejects_generated_checklists(
    checklist_kind: str,
) -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        revision = _published_master_revision(db, workspace)
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code=f"BLOCK-{checklist_kind}",
        )
        if checklist_kind == "aggregate":
            _generated_aggregate_checklist(
                db,
                workspace=workspace,
                vehicle=vehicle,
                revision=revision,
            )
        else:
            _generated_module_checklist(
                db,
                workspace=workspace,
                vehicle=vehicle,
                revision=revision,
            )
        vehicle_id = vehicle.id

        with pytest.raises(HTTPException) as blocked:
            permanently_delete_vehicle_model(
                db,
                workspace=workspace,
                user=user,
                vehicle_model_id=vehicle_id,
            )

        assert blocked.value.status_code == 409
        assert blocked.value.detail.code == "legacy_issues.vehicle_model_has_checklists"
        assert db.get(LegacyIssueVehicleModel, vehicle_id) is not None
        assert (
            db.scalar(
                select(func.count())
                .select_from(LegacyIssueRecordHistory)
                .where(LegacyIssueRecordHistory.record_kind == VEHICLE_MODEL_RECORD_KIND)
            )
            == 0
        )


def test_permanently_delete_vehicle_model_rolls_back_vehicle_and_history_together() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="ROLLBACK-DELETE",
        )
        vehicle_id = vehicle.id
        db.commit()

        permanently_delete_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle_id,
        )
        assert db.get(LegacyIssueVehicleModel, vehicle_id) is None

        db.rollback()

        assert db.get(LegacyIssueVehicleModel, vehicle_id) is not None
        assert (
            db.scalar(
                select(func.count())
                .select_from(LegacyIssueRecordHistory)
                .where(
                    LegacyIssueRecordHistory.record_kind == VEHICLE_MODEL_RECORD_KIND,
                    LegacyIssueRecordHistory.record_id == vehicle_id,
                )
            )
            == 0
        )


def test_vehicle_checklist_is_unique_per_vehicle_and_master_revision() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        first_master_revision = _published_master_revision(db, workspace)
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=first_master_revision,
            module_key="aircon",
            issue_no="PV-001",
            symptom="공조 소음",
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="MX5",
        )

        first_checklist = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=first_master_revision.id,
        )
        summaries = vehicle_checklist_summaries(
            db,
            workspace=workspace,
            vehicle_model_ids=[vehicle.id],
        )
        assert summaries[vehicle.id].latest_draft is not None
        assert summaries[vehicle.id].latest_draft.revision_id == first_checklist.id
        assert summaries[vehicle.id].latest_draft.source_master_revision_no == 3
        assert summaries[vehicle.id].latest_completed is None

        duplicate_request = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=first_master_revision.id,
        )

        assert duplicate_request.id == first_checklist.id
        assert (
            len(
                list_vehicle_checklist_revisions(
                    db, workspace=workspace, vehicle_model_id=vehicle.id
                )
            )
            == 1
        )

        complete_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            revision_id=first_checklist.id,
        )
        completed_summaries = vehicle_checklist_summaries(
            db,
            workspace=workspace,
            vehicle_model_ids=[vehicle.id],
        )
        assert completed_summaries[vehicle.id].latest_draft is None
        assert completed_summaries[vehicle.id].latest_completed is not None
        assert completed_summaries[vehicle.id].latest_completed.revision_id == first_checklist.id

        next_master_revision = _published_master_revision(
            db,
            workspace,
            revision_id="master-rev-4",
            revision_no=4,
        )
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=next_master_revision,
            module_key="aircon",
            issue_no="PV-002",
            symptom="신규 마스터 현상",
        )
        next_checklist = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=next_master_revision.id,
        )

        checklists = list_vehicle_checklist_revisions(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
        )
        next_summaries = vehicle_checklist_summaries(
            db,
            workspace=workspace,
            vehicle_model_ids=[vehicle.id],
        )
        assert next_checklist.id != first_checklist.id
        assert [item.source_master_revision_no for item in checklists] == [4, 3]
        assert next_summaries[vehicle.id].latest_draft is not None
        assert next_summaries[vehicle.id].latest_draft.revision_id == next_checklist.id
        assert next_summaries[vehicle.id].latest_completed is not None
        assert next_summaries[vehicle.id].latest_completed.revision_id == first_checklist.id


def test_vehicle_checklist_records_filter_by_module_and_do_not_follow_master_changes() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        master_revision = _published_master_revision(db, workspace)
        source_record = _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=master_revision,
            module_key="aircon",
            issue_no="PV-001",
            symptom="원본 현상",
        )
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=master_revision,
            module_key="interior",
            issue_no="PV-002",
            symptom="의장 현상",
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="MX5",
        )
        checklist_revision = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=master_revision.id,
        )

        source_record.field_values = {
            **(source_record.field_values or {}),
            "symptom": "변경된 마스터 현상",
        }
        db.add(source_record)
        db.flush()

        _revision, _definition, rows, total = list_vehicle_checklist_records(
            db,
            workspace=workspace,
            revision_id=checklist_revision.id,
            view_key="aircon",
        )

        assert total == 1
        assert len(rows) == 1
        assert rows[0].source_module_key == "aircon"
        assert rows[0].field_values["symptom"] == "원본 현상"


def test_vehicle_checklist_updates_only_check_fields_and_completed_revision_is_locked() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        master_revision = _published_master_revision(db, workspace)
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=master_revision,
            module_key="aircon",
            issue_no="PV-001",
            symptom="공조 소음",
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="MX5",
        )
        checklist_revision = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=master_revision.id,
        )
        record = db.scalar(
            select(LegacyIssueVehicleChecklistRecord).where(
                LegacyIssueVehicleChecklistRecord.checklist_revision_id == checklist_revision.id
            )
        )
        assert record is not None

        updated_rows = update_vehicle_checklist_records(
            db,
            workspace=workspace,
            user=user,
            revision_id=checklist_revision.id,
            updates={
                record.id: {
                    "check_plan": "설계 FMEA 확인",
                    "applied": "O",
                    "reflection_result": "설계 반영",
                }
            },
        )

        assert len(updated_rows) == 1
        assert updated_rows[0].field_values["check_plan"] == "설계 FMEA 확인"
        assert updated_rows[0].field_values["applied"] == "O"
        assert updated_rows[0].field_values["reflection_result"] == "설계 반영"

        with pytest.raises(HTTPException) as invalid_update:
            update_vehicle_checklist_records(
                db,
                workspace=workspace,
                user=user,
                revision_id=checklist_revision.id,
                updates={record.id: {"symptom": "차종에서 마스터 항목 수정"}},
            )
        assert invalid_update.value.status_code == 400
        assert invalid_update.value.detail.code == "legacy_issues.vehicle_checklist_field_invalid"

        complete_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            revision_id=checklist_revision.id,
        )

        with pytest.raises(HTTPException) as locked_update:
            update_vehicle_checklist_records(
                db,
                workspace=workspace,
                user=user,
                revision_id=checklist_revision.id,
                updates={record.id: {"check_plan": "완료 후 수정"}},
            )
        assert locked_update.value.status_code == 409
        assert (
            locked_update.value.detail.code == "legacy_issues.vehicle_checklist_revision_completed"
        )

        reopened = reopen_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            revision_id=checklist_revision.id,
        )
        assert reopened.status == "draft"
        assert reopened.completed_by_id is None
        assert reopened.completed_at is None

        reopened_update_rows = update_vehicle_checklist_records(
            db,
            workspace=workspace,
            user=user,
            revision_id=checklist_revision.id,
            updates={record.id: {"check_plan": "완료 후 재수정"}},
        )
        assert len(reopened_update_rows) == 1
        assert reopened_update_rows[0].field_values["check_plan"] == "완료 후 재수정"

        complete_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            revision_id=checklist_revision.id,
        )
        history = list_vehicle_checklist_history(
            db,
            workspace=workspace,
            revision_id=checklist_revision.id,
        )
        actions = [item.action for item in history.items]
        assert actions.count("update") >= 2
        assert "complete" in actions
        assert "reopen" in actions
        assert history.record_contexts[record.id].record_label == "PV-001 · 공조 소음"


def test_vehicle_checklist_history_filters_disabled_module_records() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        master_revision = _published_master_revision(db, workspace)
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=master_revision,
            module_key="aircon",
            issue_no="PV-001",
            symptom="공조 소음",
        )
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=master_revision,
            module_key="compressor-electric",
            issue_no="COMP-E-001",
            symptom="전동 컴프레서 소음",
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="MX5",
        )
        checklist_revision = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=master_revision.id,
        )
        records = list(
            db.scalars(
                select(LegacyIssueVehicleChecklistRecord).where(
                    LegacyIssueVehicleChecklistRecord.checklist_revision_id == checklist_revision.id
                )
            )
        )
        update_vehicle_checklist_records(
            db,
            workspace=workspace,
            user=user,
            revision_id=checklist_revision.id,
            updates={row.id: {"check_plan": f"{row.source_module_key} 확인"} for row in records},
        )

        history = list_vehicle_checklist_history(
            db,
            workspace=workspace,
            revision_id=checklist_revision.id,
            module_keys=frozenset({"aircon"}),
        )

        aircon_record = next(row for row in records if row.source_module_key == "aircon")
        compressor_record = next(
            row for row in records if row.source_module_key == "compressor-electric"
        )
        assert aircon_record.id in history.record_contexts
        assert compressor_record.id not in history.record_contexts
        assert {row.record_id for row in history.items} <= {
            checklist_revision.id,
            aircon_record.id,
        }


def test_vehicle_checklist_source_identity_changes_with_module_revisions() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        aggregate_marker = _published_master_revision(
            db,
            workspace,
            revision_id="aggregate-marker",
            revision_no=1,
        )
        now = utcnow_naive()
        aircon_revision_1 = LegacyIssueDataRevision(
            id="aircon-rev-1",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            revision_no=1,
            status=REVISION_STATUS_PUBLISHED,
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        db.add(aircon_revision_1)
        db.flush()
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=aircon_revision_1,
            module_key="aircon",
            issue_no="PV-001",
            symptom="공조 소음",
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="MX5",
        )
        first = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=aggregate_marker.id,
        )

        aircon_revision_2 = LegacyIssueDataRevision(
            id="aircon-rev-2",
            workspace_id=workspace.id,
            dataset_key=aircon_revision_1.dataset_key,
            revision_no=2,
            status=REVISION_STATUS_PUBLISHED,
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        db.add(aircon_revision_2)
        db.flush()
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=aircon_revision_2,
            module_key="aircon",
            issue_no="PV-002",
            symptom="신규 공조 소음",
        )
        second = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=aggregate_marker.id,
        )

        assert second.id != first.id
        assert second.source_master_revision_id != first.source_master_revision_id
        assert (
            len(
                list_vehicle_checklist_revisions(
                    db,
                    workspace=workspace,
                    vehicle_model_id=vehicle.id,
                )
            )
            == 2
        )


@pytest.mark.parametrize("completed", [False, True])
def test_delete_vehicle_checklist_revision_purges_only_generated_data(
    completed: bool,
) -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        other_workspace = Workspace(
            id="workspace-2",
            key="other-workspace",
            name="Other Workspace",
        )
        db.add(other_workspace)
        master_revision = _published_master_revision(db, workspace)
        master_record = _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=master_revision,
            module_key="aircon",
            issue_no="PV-DELETE-001",
            symptom="삭제 경계 검증",
        )
        master_attachment = LegacyIssueAttachment(
            id="master-attachment-1",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=master_revision.id,
            stable_record_id=master_record.stable_record_id,
            record_id=master_record.id,
            filename="evidence.pdf",
            content_type="application/pdf",
            size_bytes=123,
            storage_key="legacy-issues/test/evidence.pdf",
            uploaded_by_id=user.id,
        )
        db.add(master_attachment)
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="DELETE-CAR",
        )
        checklist_revision = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=master_revision.id,
        )
        checklist_record = db.scalar(
            select(LegacyIssueVehicleChecklistRecord).where(
                LegacyIssueVehicleChecklistRecord.checklist_revision_id == checklist_revision.id
            )
        )
        assert checklist_record is not None
        checklist_revision_id = checklist_revision.id
        checklist_record_id = checklist_record.id
        vehicle_id = vehicle.id
        master_revision_id = master_revision.id
        master_record_id = master_record.id
        master_attachment_id = master_attachment.id
        if completed:
            complete_vehicle_checklist_revision(
                db,
                workspace=workspace,
                user=user,
                revision_id=checklist_revision_id,
            )

        now = utcnow_naive()
        db.add_all(
            [
                LegacyIssueRecordHistory(
                    id="checklist-parent-history",
                    workspace_id=workspace.id,
                    record_kind=VEHICLE_CHECKLIST_RECORD_KIND,
                    dataset_key=COMMON_MASTER_DATASET_KEY,
                    record_id=checklist_revision_id,
                    action="update",
                    actor_user_id=user.id,
                    created_at=now,
                ),
                LegacyIssueRecordHistory(
                    id="checklist-record-history",
                    workspace_id=workspace.id,
                    record_kind=VEHICLE_CHECKLIST_RECORD_KIND,
                    dataset_key=COMMON_MASTER_DATASET_KEY,
                    record_id=checklist_record_id,
                    action="update",
                    actor_user_id=user.id,
                    created_at=now,
                ),
                LegacyIssueRecordHistory(
                    id="same-id-other-kind-history",
                    workspace_id=workspace.id,
                    record_kind="legacy_issue_record",
                    dataset_key=COMMON_MASTER_DATASET_KEY,
                    record_id=checklist_record_id,
                    action="update",
                    actor_user_id=user.id,
                    created_at=now,
                ),
                LegacyIssueRecordHistory(
                    id="same-id-other-workspace-history",
                    workspace_id=other_workspace.id,
                    record_kind=VEHICLE_CHECKLIST_RECORD_KIND,
                    dataset_key=COMMON_MASTER_DATASET_KEY,
                    record_id=checklist_record_id,
                    action="update",
                    actor_user_id=user.id,
                    created_at=now,
                ),
            ]
        )
        db.commit()

        with pytest.raises(HTTPException) as cross_workspace_delete:
            delete_vehicle_checklist_revision(
                db,
                workspace=other_workspace,
                revision_id=checklist_revision_id,
            )
        assert cross_workspace_delete.value.status_code == 404
        assert (
            cross_workspace_delete.value.detail.code
            == "legacy_issues.vehicle_checklist_revision_not_found"
        )

        delete_vehicle_checklist_revision(
            db,
            workspace=workspace,
            revision_id=checklist_revision_id,
        )

        assert db.get(LegacyIssueVehicleChecklistRevision, checklist_revision_id) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(LegacyIssueVehicleChecklistRecord)
                .where(
                    LegacyIssueVehicleChecklistRecord.checklist_revision_id == checklist_revision_id
                )
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(LegacyIssueRecordHistory)
                .where(
                    LegacyIssueRecordHistory.workspace_id == workspace.id,
                    LegacyIssueRecordHistory.record_kind == VEHICLE_CHECKLIST_RECORD_KIND,
                    LegacyIssueRecordHistory.record_id.in_(
                        [checklist_revision_id, checklist_record_id]
                    ),
                )
            )
            == 0
        )
        assert db.get(LegacyIssueRecordHistory, "same-id-other-kind-history") is not None
        assert db.get(LegacyIssueRecordHistory, "same-id-other-workspace-history") is not None
        assert db.get(LegacyIssueVehicleModel, vehicle_id) is not None
        assert db.get(LegacyIssueDataRevision, master_revision_id) is not None
        assert db.get(LegacyIssueRecord, master_record_id) is not None
        assert db.get(LegacyIssueAttachment, master_attachment_id) is not None

        with pytest.raises(HTTPException) as repeated_delete:
            delete_vehicle_checklist_revision(
                db,
                workspace=workspace,
                revision_id=checklist_revision_id,
            )
        assert repeated_delete.value.status_code == 404


def test_delete_vehicle_checklist_revision_rolls_back_as_one_transaction() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        master_revision = _published_master_revision(db, workspace)
        _create_master_record(
            db,
            workspace=workspace,
            user=user,
            revision=master_revision,
            module_key="aircon",
            issue_no="PV-ROLLBACK-001",
            symptom="트랜잭션 검증",
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="ROLLBACK-CAR",
        )
        checklist_revision = create_vehicle_checklist_revision(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            source_master_revision_id=master_revision.id,
        )
        checklist_record = db.scalar(
            select(LegacyIssueVehicleChecklistRecord).where(
                LegacyIssueVehicleChecklistRecord.checklist_revision_id == checklist_revision.id
            )
        )
        assert checklist_record is not None
        checklist_revision_id = checklist_revision.id
        checklist_record_id = checklist_record.id
        db.add(
            LegacyIssueRecordHistory(
                id="rollback-history",
                workspace_id=workspace.id,
                record_kind=VEHICLE_CHECKLIST_RECORD_KIND,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                record_id=checklist_record_id,
                action="update",
                actor_user_id=user.id,
                created_at=utcnow_naive(),
            )
        )
        db.commit()

        delete_vehicle_checklist_revision(
            db,
            workspace=workspace,
            revision_id=checklist_revision_id,
        )
        assert db.get(LegacyIssueVehicleChecklistRevision, checklist_revision_id) is None
        assert db.get(LegacyIssueVehicleChecklistRecord, checklist_record_id) is None
        assert db.get(LegacyIssueRecordHistory, "rollback-history") is None

        db.rollback()

        assert db.get(LegacyIssueVehicleChecklistRevision, checklist_revision_id) is not None
        assert db.get(LegacyIssueVehicleChecklistRecord, checklist_record_id) is not None
        assert db.get(LegacyIssueRecordHistory, "rollback-history") is not None


def test_aggregate_vehicle_checklist_write_endpoints_are_transition_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*_args, **_kwargs):
        pytest.fail("frozen aggregate endpoint must not call its write service")

    monkeypatch.setattr(
        legacy_issue_router,
        "create_vehicle_checklist_revision",
        fail_if_called,
    )
    monkeypatch.setattr(
        legacy_issue_router,
        "update_vehicle_checklist_records",
        fail_if_called,
    )
    monkeypatch.setattr(
        legacy_issue_router,
        "complete_vehicle_checklist_revision",
        fail_if_called,
    )
    monkeypatch.setattr(
        legacy_issue_router,
        "reopen_vehicle_checklist_revision",
        fail_if_called,
    )

    class FakeDb:
        commits = 0

        def commit(self) -> None:
            self.commits += 1

    db = FakeDb()
    user = SimpleNamespace(id="member-1")
    workspace = SimpleNamespace(id="workspace-1")
    actions = (
        lambda: legacy_issue_router.create_legacy_issue_vehicle_checklist_revision(
            "vehicle-1",
            SimpleNamespace(source_master_revision_id=None),
            db=db,
            current_user=user,
            current_workspace=workspace,
        ),
        lambda: legacy_issue_router.save_legacy_issue_vehicle_checklist_records_batch(
            "checklist-1",
            SimpleNamespace(updates=[]),
            db=db,
            current_user=user,
            current_workspace=workspace,
        ),
        lambda: legacy_issue_router.complete_legacy_issue_vehicle_checklist_revision(
            "checklist-1",
            db=db,
            current_user=user,
            current_workspace=workspace,
        ),
        lambda: legacy_issue_router.reopen_legacy_issue_vehicle_checklist_revision(
            "checklist-1",
            db=db,
            current_user=user,
            current_workspace=workspace,
        ),
    )

    for action in actions:
        with pytest.raises(HTTPException) as frozen:
            action()
        assert frozen.value.status_code == 409
        assert frozen.value.detail.code == "legacy_issues.vehicle_checklist_transition_read_only"
        assert translate_message(frozen.value.detail, "ko-KR") != frozen.value.detail.code
        assert translate_message(frozen.value.detail, "en-US") != frozen.value.detail.code
    assert db.commits == 0


def test_vehicle_checklist_delete_http_enforces_workspace_membership(
    client: TestClient,
) -> None:
    member_session = create_workspace_user_session(
        client,
        workspace_key="vehicle-checklist-member-workspace",
        workspace_name="Vehicle Checklist Member Workspace",
        login_id="vehiclechecklistmember",
        email="vehicle-checklist-member@ai-do.local",
        full_name="Vehicle Checklist Member",
        role="member",
    )
    outsider_session = create_workspace_user_session(
        client,
        workspace_key="vehicle-checklist-outsider-workspace",
        workspace_name="Vehicle Checklist Outsider Workspace",
        login_id="vehiclechecklistoutsider",
        email="vehicle-checklist-outsider@ai-do.local",
        full_name="Vehicle Checklist Outsider",
        role="member",
    )

    checklist_revision_id = "http-checklist-revision-1"
    checklist_record_id = "http-checklist-record-1"
    with get_session_factory()() as db:
        workspace = db.scalar(
            select(Workspace).where(Workspace.key == "vehicle-checklist-member-workspace")
        )
        assert workspace is not None
        member = db.get(User, member_session["user"]["id"])
        assert member is not None
        now = utcnow_naive()
        master_revision = LegacyIssueDataRevision(
            id="http-master-revision-1",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            revision_no=1,
            status=REVISION_STATUS_PUBLISHED,
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        vehicle = LegacyIssueVehicleModel(
            id="http-vehicle-model-1",
            workspace_id=workspace.id,
            vehicle_code="HTTP-CAR",
            vehicle_code_normalized="http-car",
            active=True,
            created_by_id=member.id,
            created_at=now,
            updated_at=now,
        )
        checklist_revision = LegacyIssueVehicleChecklistRevision(
            id=checklist_revision_id,
            workspace_id=workspace.id,
            vehicle_model_id=vehicle.id,
            revision_no=1,
            status="completed",
            source_dataset_key=COMMON_MASTER_DATASET_KEY,
            source_master_revision_id=master_revision.id,
            source_master_revision_no=master_revision.revision_no,
            definition_snapshot={},
            row_count=1,
            created_by_id=member.id,
            completed_by_id=member.id,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        checklist_record = LegacyIssueVehicleChecklistRecord(
            id=checklist_record_id,
            workspace_id=workspace.id,
            checklist_revision_id=checklist_revision.id,
            source_record_id="http-master-record-1",
            source_stable_record_id="http-master-stable-record-1",
            source_module_key="aircon",
            sort_order=1,
            field_values={"check_plan": "HTTP delete permission test"},
            updated_by_id=member.id,
            created_at=now,
            updated_at=now,
        )
        history = LegacyIssueRecordHistory(
            id="http-checklist-history-1",
            workspace_id=workspace.id,
            record_kind=VEHICLE_CHECKLIST_RECORD_KIND,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            record_id=checklist_record.id,
            action="update",
            actor_user_id=member.id,
            created_at=now,
        )
        db.add_all(
            [
                master_revision,
                vehicle,
                checklist_revision,
                checklist_record,
                history,
            ]
        )
        db.commit()

    path = (
        "/api/v1/workspaces/vehicle-checklist-member-workspace/legacy-issues/"
        f"vehicle-checklist-revisions/{checklist_revision_id}"
    )

    anonymous_response = client.delete(path)
    assert anonymous_response.status_code == 401, anonymous_response.text
    assert anonymous_response.json()["code"] == "auth.required"

    cross_workspace_response = client.delete(
        path,
        headers=auth_headers(outsider_session["token"]),
    )
    assert cross_workspace_response.status_code == 403, cross_workspace_response.text
    assert cross_workspace_response.json()["code"] == "workspace.membership_required"

    with get_session_factory()() as db:
        assert db.get(LegacyIssueVehicleChecklistRevision, checklist_revision_id) is not None
        assert db.get(LegacyIssueVehicleChecklistRecord, checklist_record_id) is not None
        assert db.get(LegacyIssueRecordHistory, "http-checklist-history-1") is not None

    member_response = client.delete(
        path,
        headers=auth_headers(member_session["token"]),
    )
    assert member_response.status_code == 204, member_response.text
    assert member_response.content == b""

    with get_session_factory()() as db:
        assert db.get(LegacyIssueVehicleChecklistRevision, checklist_revision_id) is None
        assert db.get(LegacyIssueVehicleChecklistRecord, checklist_record_id) is None
        assert db.get(LegacyIssueRecordHistory, "http-checklist-history-1") is None
        assert db.get(LegacyIssueDataRevision, "http-master-revision-1") is not None
        assert db.get(LegacyIssueVehicleModel, "http-vehicle-model-1") is not None


def test_vehicle_model_create_allows_members_but_delete_requires_admin(
    client: TestClient,
) -> None:
    member_session = create_workspace_user_session(
        client,
        workspace_key="vehicle-model-member-workspace",
        workspace_name="Vehicle Model Member Workspace",
        login_id="vehiclemodelmember",
        email="vehicle-model-member@ai-do.local",
        full_name="Vehicle Model Member",
        role="member",
    )
    base_path = "/api/v1/workspaces/vehicle-model-member-workspace/legacy-issues/vehicle-models"

    missing_stage_response = client.post(
        base_path,
        headers=auth_headers(member_session["token"]),
        json={"vehicle_code": "MISSING-STAGE"},
    )
    assert missing_stage_response.status_code == 422, missing_stage_response.text

    create_response = client.post(
        base_path,
        headers=auth_headers(member_session["token"]),
        json={
            "vehicle_code": "MEMBER-CAR",
            "vehicle_name": "Member-created model",
            "notes": "created without administrator access",
            "initial_stage_name": "P0",
        },
    )

    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["vehicle_code"] == "MEMBER-CAR"
    assert [(item["name"], item["sequence_no"]) for item in created["stages"]] == [("P0", 1)]
    with get_session_factory()() as db:
        created_row = db.get(LegacyIssueVehicleModel, created["id"])
        assert created_row is not None
        assert created_row.created_by_id == member_session["user"]["id"]

    member_stage_response = client.post(
        f"{base_path}/{created['id']}/stages",
        headers=auth_headers(member_session["token"]),
        json={"name": "P1"},
    )
    assert member_stage_response.status_code == 403, member_stage_response.text
    assert member_stage_response.json()["code"] == "legacy_issues.module_field_manage_required"

    admin_session = create_workspace_user_session(
        client,
        workspace_key="vehicle-model-member-workspace",
        login_id="vehiclemodelstageadmin",
        email="vehicle-model-stage-admin@ai-do.local",
        full_name="Vehicle Model Stage Admin",
        role="admin",
    )
    admin_stage_response = client.post(
        f"{base_path}/{created['id']}/stages",
        headers=auth_headers(admin_session["token"]),
        json={"name": "P1"},
    )
    assert admin_stage_response.status_code == 201, admin_stage_response.text
    added_stage = admin_stage_response.json()
    assert added_stage["name"] == "P1"
    assert added_stage["sequence_no"] == 2
    assert added_stage["previous_stage_id"] == created["stages"][0]["id"]

    rename_stage_response = client.patch(
        f"{base_path}/{created['id']}/stages/{added_stage['id']}",
        headers=auth_headers(admin_session["token"]),
        json={"name": "Pilot"},
    )
    assert rename_stage_response.status_code == 200, rename_stage_response.text
    renamed_stage = rename_stage_response.json()
    assert renamed_stage["id"] == added_stage["id"]
    assert renamed_stage["name"] == "Pilot"
    assert renamed_stage["sequence_no"] == 2
    assert renamed_stage["previous_stage_id"] == created["stages"][0]["id"]
    list_response = client.get(
        base_path,
        headers=auth_headers(admin_session["token"]),
        params={"include_inactive": True},
    )
    assert list_response.status_code == 200, list_response.text
    listed_vehicle = next(
        item for item in list_response.json()["items"] if item["id"] == created["id"]
    )
    assert [item["name"] for item in listed_vehicle["stages"]] == ["P0", "Pilot"]

    deactivate_response = client.patch(
        f"{base_path}/{created['id']}",
        headers=auth_headers(admin_session["token"]),
        json={"active": False},
    )
    assert deactivate_response.status_code == 200, deactivate_response.text
    inactive_stage_response = client.post(
        f"{base_path}/{created['id']}/stages",
        headers=auth_headers(admin_session["token"]),
        json={"name": "P2"},
    )
    assert inactive_stage_response.status_code == 400, inactive_stage_response.text
    assert inactive_stage_response.json()["code"] == "legacy_issues.vehicle_stage_vehicle_inactive"

    delete_response = client.delete(
        f"{base_path}/{created['id']}",
        headers=auth_headers(member_session["token"]),
    )
    assert delete_response.status_code == 403, delete_response.text
    assert delete_response.json()["code"] == "legacy_issues.module_field_manage_required"
