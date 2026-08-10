import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from ai_do_api.core.db import Base, get_session_factory
from ai_do_api.core.i18n import translate_message
from ai_do_api.domains.auth.models import OrgUnit, User, Workspace, utcnow_naive
from ai_do_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    create_dataset_record,
    get_dataset_definition_for_view,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueAttachment,
    LegacyIssueDataRevision,
    LegacyIssueModuleField,
    LegacyIssueRecord,
    LegacyIssueRecordHistory,
    LegacyIssueSystemFieldSetting,
    LegacyIssueVehicleModel,
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleModuleChecklistAttachment,
    LegacyIssueVehicleModuleChecklistAttachmentCleanup,
    LegacyIssueVehicleModuleChecklistRecord,
    LegacyIssueVehicleStage,
)
from ai_do_api.domains.legacy_issues.revisioning import (
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    legacy_issue_dataset_revision_key,
)
from ai_do_api.domains.legacy_issues.vehicle_checklists import (
    create_vehicle_model,
    create_vehicle_stage,
)
from ai_do_api.domains.retrieval.models import RetrievalPartition
from ai_do_api.domains.legacy_issues import (
    vehicle_module_checklists as vehicle_module_checklist_service,
)
from ai_do_api.domains.legacy_issues.vehicle_module_checklists import (
    VEHICLE_MODULE_CHECKLIST_RECORD_KIND,
    complete_vehicle_module_checklist,
    create_vehicle_module_checklist,
    delete_vehicle_module_checklist,
    get_vehicle_module_checklist,
    import_previous_stage_vehicle_module_checklist,
    list_prior_stage_completed_vehicle_module_checklists,
    list_published_module_master_revisions,
    list_vehicle_module_checklist_history,
    list_vehicle_module_checklist_records,
    list_vehicle_module_checklists,
    list_vehicle_module_summaries,
    reopen_vehicle_module_checklist,
    update_vehicle_module_checklist_records,
)
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
            LegacyIssueRecord.__table__,
            LegacyIssueAttachment.__table__,
            LegacyIssueRecordHistory.__table__,
            LegacyIssueModuleField.__table__,
            LegacyIssueSystemFieldSetting.__table__,
            LegacyIssueVehicleModel.__table__,
            LegacyIssueVehicleStage.__table__,
            LegacyIssueVehicleModuleChecklist.__table__,
            LegacyIssueVehicleModuleChecklistRecord.__table__,
            LegacyIssueVehicleModuleChecklistAttachment.__table__,
            LegacyIssueVehicleModuleChecklistAttachmentCleanup.__table__,
        ],
    )
    return Session(engine)


def _workspace_and_user(
    db: Session,
    *,
    workspace_id: str = "workspace-1",
    user_id: str = "user-1",
) -> tuple[Workspace, User]:
    workspace = Workspace(
        id=workspace_id,
        key=workspace_id,
        name=workspace_id,
    )
    user = User(
        id=user_id,
        login_id=user_id,
        email=f"{user_id}@example.com",
        full_name=user_id,
        password_hash="hash",
        status="active",
    )
    db.add_all([workspace, user])
    db.flush()
    return workspace, user


def _module_revision(
    db: Session,
    *,
    workspace: Workspace,
    module_key: str,
    revision_no: int,
    status: str = REVISION_STATUS_PUBLISHED,
) -> LegacyIssueDataRevision:
    now = utcnow_naive()
    revision = LegacyIssueDataRevision(
        id=f"{workspace.id}-{module_key}-rev-{revision_no}-{status}",
        workspace_id=workspace.id,
        dataset_key=legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            module_key,
        ),
        revision_no=revision_no if status == REVISION_STATUS_PUBLISHED else None,
        status=status,
        created_at=now,
        updated_at=now,
        published_at=now if status == REVISION_STATUS_PUBLISHED else None,
    )
    db.add(revision)
    db.flush()
    return revision


def _master_record(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    revision: LegacyIssueDataRevision,
    module_key: str,
    issue_no: str,
    master_status: str | None = "등재",
) -> LegacyIssueRecord:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        workspace=workspace,
        view_key=module_key,
    )
    values = {
        "legacy_issue_number": issue_no,
        "symptom": f"{module_key} 현상",
        "cause": "원인",
        "countermeasure": "대책",
        "check_plan": "마스터 점검",
        "applied": "O",
        "reflection_result": "마스터 결과",
    }
    if master_status is not None:
        values["evidence_legacy_issue"] = master_status
    return create_dataset_record(
        db,
        definition,
        workspace=workspace,
        user=user,
        revision=revision,
        module_key=module_key,
        values=values,
    )


def _vehicle(db: Session, workspace: Workspace, user: User) -> LegacyIssueVehicleModel:
    return create_vehicle_model(
        db,
        workspace=workspace,
        user=user,
        vehicle_code="TEST-CAR",
    )


def test_module_checklist_copies_selected_module_revision_values_and_is_idempotent() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        aircon_rev = _module_revision(
            db,
            workspace=workspace,
            module_key="aircon",
            revision_no=3,
        )
        interior_rev = _module_revision(
            db,
            workspace=workspace,
            module_key="interior",
            revision_no=7,
        )
        aircon_record = _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=aircon_rev,
            module_key="aircon",
            issue_no="AIR-001",
        )
        _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=aircon_rev,
            module_key="aircon",
            issue_no="AIR-REVIEW",
            master_status="심사대기",
        )
        _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=aircon_rev,
            module_key="aircon",
            issue_no="AIR-NOT-LISTED",
            master_status="미등재",
        )
        _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=aircon_rev,
            module_key="aircon",
            issue_no="AIR-NO-STATUS",
            master_status=None,
        )
        _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=interior_rev,
            module_key="interior",
            issue_no="INT-001",
        )
        aircon_rev.grid_layout = {
            "version": 1,
            "column_order": ["symptom", "cause", "primary_attachment"],
            "column_widths": {"symptom": 420, "primary_attachment": 260},
            "hidden_column_keys": ["cause"],
        }
        db.add(aircon_rev)
        db.flush()
        vehicle = _vehicle(db, workspace, user)

        checklist = create_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            module_key="aircon",
            source_master_revision_id=aircon_rev.id,
            module_keys=frozenset({"aircon", "interior"}),
        )
        same_checklist = create_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            module_key="aircon",
            source_master_revision_id=aircon_rev.id,
            module_keys=frozenset({"aircon", "interior"}),
        )

        assert same_checklist.id == checklist.id
        assert checklist.module_key == "aircon"
        assert checklist.source_master_revision_no == 3
        assert checklist.row_count == 1
        assert not hasattr(checklist, "revision_no")
        assert checklist.definition_snapshot["module_key"] == "aircon"
        assert checklist.grid_layout is None
        rows = list(
            db.scalars(
                select(LegacyIssueVehicleModuleChecklistRecord).where(
                    LegacyIssueVehicleModuleChecklistRecord.checklist_id == checklist.id
                )
            )
        )
        assert len(rows) == 1
        assert rows[0].source_record_id == aircon_record.id
        assert rows[0].field_values["legacy_issue_number"] == "AIR-001"
        assert rows[0].field_values["check_plan"] == "마스터 점검"
        assert rows[0].field_values["applied"] == "O"
        assert rows[0].field_values["reflection_result"] == "마스터 결과"
        assert db.scalar(select(func.count()).select_from(LegacyIssueVehicleModuleChecklist)) == 1
        summaries = list_vehicle_module_summaries(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
            module_keys=frozenset({"aircon", "interior"}),
        )
        aircon_summary = next(item for item in summaries if item.module_key == "aircon")
        assert aircon_summary.latest_master_revision is aircon_rev
        assert aircon_summary.latest_checklist is checklist
        assert aircon_summary.checklist_count == 1


def test_new_vehicle_stage_waits_for_explicit_previous_completed_import() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        revision_1 = _module_revision(
            db,
            workspace=workspace,
            module_key="aircon",
            revision_no=1,
        )
        revision_2 = _module_revision(
            db,
            workspace=workspace,
            module_key="aircon",
            revision_no=2,
        )
        _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=revision_1,
            module_key="aircon",
            issue_no="AIR-PREVIOUS",
        )
        _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=revision_2,
            module_key="aircon",
            issue_no="AIR-LATEST",
        )
        vehicle = create_vehicle_model(
            db,
            workspace=workspace,
            user=user,
            vehicle_code="STAGED-CAR",
            initial_stage_name="P0",
        )
        first_stage = vehicle.stages[0]
        previous = create_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            stage_id=first_stage.id,
            module_key="aircon",
            source_master_revision_id=revision_1.id,
        )
        previous.status = "completed"
        previous.completed_by_id = user.id
        previous.completed_at = utcnow_naive()
        latest = create_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            stage_id=first_stage.id,
            module_key="aircon",
            source_master_revision_id=revision_2.id,
        )
        latest.grid_layout = {"column_order": ["symptom", "check_plan"]}
        source_record = db.scalar(
            select(LegacyIssueVehicleModuleChecklistRecord).where(
                LegacyIssueVehicleModuleChecklistRecord.checklist_id == latest.id
            )
        )
        assert source_record is not None
        source_record.field_values = {
            **(source_record.field_values or {}),
            "check_plan": "P0 점검계획",
            "applied": "O",
            "reflection_result": "P0 반영",
        }
        latest.status = "completed"
        latest.completed_by_id = user.id
        latest.completed_at = utcnow_naive()
        db.flush()

        second_stage = create_vehicle_stage(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            name="P1",
        )

        assert second_stage.sequence_no == 2
        assert second_stage.previous_stage_id == first_stage.id
        cloned_checklists = list_vehicle_module_checklists(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
            stage_id=second_stage.id,
            module_key="aircon",
        )
        assert cloned_checklists == []
        import_candidates = list_prior_stage_completed_vehicle_module_checklists(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
            stage_id=second_stage.id,
            module_key="aircon",
            module_keys=frozenset({"aircon"}),
        )
        assert [candidate.checklist.id for candidate in import_candidates] == [
            latest.id,
            previous.id,
        ]
        assert {candidate.stage.id for candidate in import_candidates} == {
            first_stage.id
        }
        assert {candidate.stage.name for candidate in import_candidates} == {"P0"}
        assert import_candidates[0].completed_by_name == user.full_name

        cloned = import_previous_stage_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            stage_id=second_stage.id,
            module_key="aircon",
            source_checklist_id=latest.id,
            module_keys=frozenset({"aircon"}),
        )
        assert cloned.seeded_from_checklist_id == latest.id
        assert cloned.source_master_revision_id == revision_2.id
        assert cloned.status == "draft"
        assert cloned.completed_by_id is None
        assert cloned.completed_at is None
        assert cloned.grid_layout == latest.grid_layout
        cloned_record = db.scalar(
            select(LegacyIssueVehicleModuleChecklistRecord).where(
                LegacyIssueVehicleModuleChecklistRecord.checklist_id == cloned.id
            )
        )
        assert cloned_record is not None
        assert cloned_record.id != source_record.id
        assert cloned_record.source_record_id == source_record.source_record_id
        assert cloned_record.field_values == source_record.field_values

        first_stage_checklists = list_vehicle_module_checklists(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
            stage_id=first_stage.id,
            module_key="aircon",
        )
        assert len(first_stage_checklists) == 2
        assert (
            create_vehicle_module_checklist(
                db,
                workspace=workspace,
                user=user,
                vehicle_model_id=vehicle.id,
                stage_id=second_stage.id,
                module_key="aircon",
                source_master_revision_id=revision_2.id,
            ).id
            == cloned.id
        )
        cloned.status = "completed"
        cloned.completed_by_id = user.id
        cloned.completed_at = utcnow_naive()
        third_stage = create_vehicle_stage(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            name="P2",
        )
        all_prior_candidates = list_prior_stage_completed_vehicle_module_checklists(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
            stage_id=third_stage.id,
            module_key="aircon",
            module_keys=frozenset({"aircon"}),
        )
        assert [
            candidate.stage.name for candidate in all_prior_candidates
        ] == ["P1", "P0", "P0"]


def test_module_checklist_revision_and_module_scoping() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        aircon_rev_1 = _module_revision(
            db,
            workspace=workspace,
            module_key="aircon",
            revision_no=1,
        )
        aircon_rev_2 = _module_revision(
            db,
            workspace=workspace,
            module_key="aircon",
            revision_no=2,
        )
        interior_rev = _module_revision(
            db,
            workspace=workspace,
            module_key="interior",
            revision_no=1,
        )
        draft = _module_revision(
            db,
            workspace=workspace,
            module_key="aircon",
            revision_no=99,
            status=REVISION_STATUS_DRAFT,
        )
        _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=aircon_rev_1,
            module_key="aircon",
            issue_no="AIR-R1",
        )
        _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=aircon_rev_2,
            module_key="aircon",
            issue_no="AIR-R2",
        )
        vehicle = _vehicle(db, workspace, user)

        revisions = list_published_module_master_revisions(
            db,
            workspace=workspace,
            module_key="aircon",
        )
        assert [item.id for item in revisions] == [aircon_rev_2.id, aircon_rev_1.id]

        latest = create_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            module_key="aircon",
        )
        older = create_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            module_key="aircon",
            source_master_revision_id=aircon_rev_1.id,
        )
        assert latest.source_master_revision_id == aircon_rev_2.id
        assert older.source_master_revision_id == aircon_rev_1.id
        assert [
            item.source_master_revision_no
            for item in list_vehicle_module_checklists(
                db,
                workspace=workspace,
                vehicle_model_id=vehicle.id,
                module_key="aircon",
            )
        ] == [2, 1]

        with pytest.raises(HTTPException) as cross_module:
            create_vehicle_module_checklist(
                db,
                workspace=workspace,
                user=user,
                vehicle_model_id=vehicle.id,
                module_key="aircon",
                source_master_revision_id=interior_rev.id,
            )
        assert cross_module.value.status_code == 404

        with pytest.raises(HTTPException) as draft_source:
            create_vehicle_module_checklist(
                db,
                workspace=workspace,
                user=user,
                vehicle_model_id=vehicle.id,
                module_key="aircon",
                source_master_revision_id=draft.id,
            )
        assert draft_source.value.status_code == 400
        assert (
            draft_source.value.detail.code
            == "legacy_issues.vehicle_module_checklist_revision_invalid"
        )


def test_module_summaries_do_not_create_missing_master_revisions() -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        vehicle = _vehicle(db, workspace, user)

        summaries = list_vehicle_module_summaries(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle.id,
            module_keys=frozenset({"aircon", "heat-exchanger", "interior"}),
        )

        assert [item.module_key for item in summaries] == [
            "aircon",
            "heat-exchanger",
            "interior",
        ]
        assert all(item.latest_master_revision is None for item in summaries)
        assert all(item.latest_checklist is None for item in summaries)
        assert all(item.checklist_count == 0 for item in summaries)
        assert db.scalar(select(func.count()).select_from(LegacyIssueDataRevision)) == 0


def test_module_checklist_only_check_fields_are_editable_and_completion_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        revision = _module_revision(
            db,
            workspace=workspace,
            module_key="aircon",
            revision_no=4,
        )
        _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=revision,
            module_key="aircon",
            issue_no="AIR-CHECK",
        )
        vehicle = _vehicle(db, workspace, user)
        checklist = create_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            module_key="aircon",
        )
        _checklist, _definition, records, total = list_vehicle_module_checklist_records(
            db,
            workspace=workspace,
            checklist_id=checklist.id,
        )
        assert total == 1
        record = records[0]

        parent_lock_requests: list[bool] = []
        original_get_checklist = vehicle_module_checklist_service.get_vehicle_module_checklist

        def get_checklist_with_lock_tracking(*args, **kwargs):
            parent_lock_requests.append(bool(kwargs.get("for_update")))
            return original_get_checklist(*args, **kwargs)

        monkeypatch.setattr(
            vehicle_module_checklist_service,
            "get_vehicle_module_checklist",
            get_checklist_with_lock_tracking,
        )

        updated = update_vehicle_module_checklist_records(
            db,
            workspace=workspace,
            user=user,
            checklist_id=checklist.id,
            updates={
                record.id: {
                    "check_plan": "FMEA 확인",
                    "applied": "O",
                    "reflection_result": "반영 완료",
                }
            },
        )
        assert updated[0].field_values["check_plan"] == "FMEA 확인"
        assert parent_lock_requests == [True]

        with pytest.raises(HTTPException) as invalid_field:
            update_vehicle_module_checklist_records(
                db,
                workspace=workspace,
                user=user,
                checklist_id=checklist.id,
                updates={record.id: {"symptom": "수정 금지"}},
            )
        assert invalid_field.value.status_code == 400
        assert (
            invalid_field.value.detail.code
            == "legacy_issues.vehicle_module_checklist_field_invalid"
        )

        completed = complete_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            checklist_id=checklist.id,
        )
        assert completed.status == "completed"
        with pytest.raises(HTTPException) as locked:
            update_vehicle_module_checklist_records(
                db,
                workspace=workspace,
                user=user,
                checklist_id=checklist.id,
                updates={record.id: {"check_plan": "완료 후 수정"}},
            )
        assert locked.value.status_code == 409
        assert locked.value.detail.code == "legacy_issues.vehicle_module_checklist_completed"

        reopened = reopen_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            checklist_id=checklist.id,
        )
        assert reopened.status == "draft"
        history = list_vehicle_module_checklist_history(
            db,
            workspace=workspace,
            checklist_id=checklist.id,
        )
        assert {item.action for item in history.items} == {"update", "complete", "reopen"}
        assert history.record_contexts[record.id].record_label == "AIR-CHECK · aircon 현상"


@pytest.mark.parametrize("completed", [False, True])
def test_module_checklist_hard_delete_is_workspace_scoped_and_preserves_master(
    completed: bool,
) -> None:
    with _session() as db:
        workspace, user = _workspace_and_user(db)
        other_workspace, _other_user = _workspace_and_user(
            db,
            workspace_id="workspace-2",
            user_id="user-2",
        )
        revision = _module_revision(
            db,
            workspace=workspace,
            module_key="aircon",
            revision_no=5,
        )
        master_record = _master_record(
            db,
            workspace=workspace,
            user=user,
            revision=revision,
            module_key="aircon",
            issue_no="AIR-DELETE",
        )
        master_attachment = LegacyIssueAttachment(
            id="module-master-attachment",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id=master_record.stable_record_id,
            record_id=master_record.id,
            filename="master-evidence.pdf",
            content_type="application/pdf",
            size_bytes=128,
            storage_key="legacy-issues/test/master-evidence.pdf",
            uploaded_by_id=user.id,
        )
        db.add(master_attachment)
        vehicle = _vehicle(db, workspace, user)
        checklist = create_vehicle_module_checklist(
            db,
            workspace=workspace,
            user=user,
            vehicle_model_id=vehicle.id,
            module_key="aircon",
        )
        record = db.scalar(
            select(LegacyIssueVehicleModuleChecklistRecord).where(
                LegacyIssueVehicleModuleChecklistRecord.checklist_id == checklist.id
            )
        )
        assert record is not None
        checklist_id = checklist.id
        checklist_record_id = record.id
        vehicle_id = vehicle.id
        revision_id = revision.id
        master_record_id = master_record.id
        master_attachment_id = master_attachment.id
        if completed:
            complete_vehicle_module_checklist(
                db,
                workspace=workspace,
                user=user,
                checklist_id=checklist.id,
            )
        db.add(
            LegacyIssueRecordHistory(
                id="other-kind-history",
                workspace_id=workspace.id,
                record_kind="legacy_issue",
                dataset_key=COMMON_MASTER_DATASET_KEY,
                record_id=checklist_record_id,
                action="update",
                created_at=utcnow_naive(),
            )
        )
        db.commit()

        with pytest.raises(HTTPException) as cross_workspace:
            delete_vehicle_module_checklist(
                db,
                workspace=other_workspace,
                checklist_id=checklist_id,
            )
        assert cross_workspace.value.status_code == 404
        assert (
            cross_workspace.value.detail.code == "legacy_issues.vehicle_module_checklist_not_found"
        )

        delete_vehicle_module_checklist(
            db,
            workspace=workspace,
            checklist_id=checklist_id,
        )

        assert db.get(LegacyIssueVehicleModuleChecklist, checklist_id) is None
        assert db.get(LegacyIssueVehicleModuleChecklistRecord, checklist_record_id) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(LegacyIssueRecordHistory)
                .where(
                    LegacyIssueRecordHistory.workspace_id == workspace.id,
                    LegacyIssueRecordHistory.record_kind == VEHICLE_MODULE_CHECKLIST_RECORD_KIND,
                    LegacyIssueRecordHistory.record_id.in_([checklist_id, checklist_record_id]),
                )
            )
            == 0
        )
        assert db.get(LegacyIssueRecordHistory, "other-kind-history") is not None
        assert db.get(LegacyIssueVehicleModel, vehicle_id) is not None
        assert db.get(LegacyIssueDataRevision, revision_id) is not None
        assert db.get(LegacyIssueRecord, master_record_id) is not None
        assert db.get(LegacyIssueAttachment, master_attachment_id) is not None

        with pytest.raises(HTTPException) as repeated:
            get_vehicle_module_checklist(
                db,
                workspace=workspace,
                checklist_id=checklist_id,
            )
        assert repeated.value.status_code == 404


def test_module_checklist_errors_are_localized() -> None:
    for code in (
        "legacy_issues.vehicle_module_checklist_not_found",
        "legacy_issues.vehicle_module_checklist_completed",
        "legacy_issues.vehicle_module_checklist_revision_invalid",
        "legacy_issues.vehicle_module_checklist_previous_completed_not_found",
        "legacy_issues.vehicle_module_checklist_stage_not_empty",
        "legacy_issues.vehicle_module_checklist_field_invalid",
        "legacy_issues.vehicle_module_checklist_attachment_too_large",
        "legacy_issues.vehicle_module_checklist_attachment_empty",
        "legacy_issues.vehicle_module_checklist_attachment_not_found",
        "legacy_issues.vehicle_module_checklist_attachment_upload_failed",
        "legacy_issues.vehicle_module_checklist_attachment_download_failed",
        "legacy_issues.vehicle_module_checklist_attachment_delete_failed",
    ):
        message = type("Message", (), {"code": code, "params": {}})()
        assert translate_message(message, "ko-KR") != code
        assert translate_message(message, "en-US") != code


def test_module_checklist_create_and_delete_http_enforce_workspace_membership(
    client: TestClient,
) -> None:
    member_session = create_workspace_user_session(
        client,
        workspace_key="module-checklist-member-workspace",
        workspace_name="Module Checklist Member Workspace",
        login_id="modulechecklistmember",
        email="module-checklist-member@ai-do.local",
        full_name="Module Checklist Member",
        role="member",
    )
    outsider_session = create_workspace_user_session(
        client,
        workspace_key="module-checklist-outsider-workspace",
        workspace_name="Module Checklist Outsider Workspace",
        login_id="modulechecklistoutsider",
        email="module-checklist-outsider@ai-do.local",
        full_name="Module Checklist Outsider",
        role="member",
    )
    master_revision_id = "http-module-master-revision-1"
    master_record_id = "http-module-master-record-1"
    vehicle_id = "http-module-vehicle-1"
    stage_id = "http-module-stage-1"
    next_stage_id = "http-module-stage-2"
    history_id = "http-module-checklist-history-1"

    with get_session_factory()() as db:
        workspace = db.scalar(
            select(Workspace).where(Workspace.key == "module-checklist-member-workspace")
        )
        assert workspace is not None
        member = db.get(User, member_session["user"]["id"])
        assert member is not None
        now = utcnow_naive()
        master_revision = LegacyIssueDataRevision(
            id=master_revision_id,
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
        vehicle = LegacyIssueVehicleModel(
            id=vehicle_id,
            workspace_id=workspace.id,
            vehicle_code="HTTP-MODULE-CAR",
            vehicle_code_normalized="http-module-car",
            active=True,
            created_by_id=member.id,
            created_at=now,
            updated_at=now,
        )
        stage = LegacyIssueVehicleStage(
            id=stage_id,
            workspace_id=workspace.id,
            vehicle_model_id=vehicle.id,
            name="P0",
            name_normalized="p0",
            sequence_no=1,
            created_by_id=member.id,
            created_at=now,
            updated_at=now,
        )
        next_stage = LegacyIssueVehicleStage(
            id=next_stage_id,
            workspace_id=workspace.id,
            vehicle_model_id=vehicle.id,
            name="P1",
            name_normalized="p1",
            sequence_no=2,
            previous_stage_id=stage.id,
            created_by_id=member.id,
            created_at=now,
            updated_at=now,
        )
        master_record = LegacyIssueRecord(
            id=master_record_id,
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=master_revision.id,
            stable_record_id="http-module-master-stable-record-1",
            field_values={
                "legacy_issue_number": "HTTP-AIR-001",
                "symptom": "HTTP module permission test",
                "check_plan": "마스터 작성 예시",
                "applied": "검토 필요",
                "reflection_result": "마스터 검토 예시",
                "evidence_legacy_issue": "등재",
            },
            created_by_id=member.id,
            created_at=now,
            updated_at=now,
        )
        db.add_all([master_revision, vehicle, stage, next_stage, master_record])
        db.commit()

    create_path = (
        "/api/v1/workspaces/module-checklist-member-workspace/legacy-issues/"
        f"vehicle-models/{vehicle_id}/checklist-modules/aircon/checklists"
    )
    create_payload = {
        "stage_id": stage_id,
        "source_master_revision_id": master_revision_id,
    }

    anonymous_create = client.post(create_path, json=create_payload)
    assert anonymous_create.status_code == 401, anonymous_create.text
    assert anonymous_create.json()["code"] == "auth.required"

    cross_workspace_create = client.post(
        create_path,
        json=create_payload,
        headers=auth_headers(outsider_session["token"]),
    )
    assert cross_workspace_create.status_code == 403, cross_workspace_create.text
    assert cross_workspace_create.json()["code"] == "workspace.membership_required"

    with get_session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(LegacyIssueVehicleModuleChecklist)) == 0

    member_create = client.post(
        create_path,
        json=create_payload,
        headers=auth_headers(member_session["token"]),
    )
    assert member_create.status_code == 201, member_create.text
    created_payload = member_create.json()
    assert created_payload["vehicle_model_id"] == vehicle_id
    assert created_payload["module_key"] == "aircon"
    assert created_payload["source_master_revision_no"] == 1
    assert created_payload["row_count"] == 1
    assert "revision_no" not in created_payload
    assert "grid_layout" not in created_payload
    checklist_id = created_payload["id"]

    with get_session_factory()() as db:
        completed_checklist = db.get(LegacyIssueVehicleModuleChecklist, checklist_id)
        assert completed_checklist is not None
        completed_checklist.status = "completed"
        completed_checklist.completed_by_id = member_session["user"]["id"]
        completed_checklist.completed_at = utcnow_naive()
        db.commit()

    next_stage_list = client.get(
        create_path,
        params={"stage_id": next_stage_id},
        headers=auth_headers(member_session["token"]),
    )
    assert next_stage_list.status_code == 200, next_stage_list.text
    assert next_stage_list.json()["items"] == []
    assert len(next_stage_list.json()["import_candidates"]) == 1
    import_candidate = next_stage_list.json()["import_candidates"][0]
    assert import_candidate["checklist"]["id"] == checklist_id
    assert import_candidate["stage"]["id"] == stage_id
    assert import_candidate["stage"]["name"] == "P0"
    assert import_candidate["completed_by_name"] == member_session["user"]["full_name"]

    import_path = f"{create_path}/import-previous-stage"
    import_response = client.post(
        import_path,
        json={
            "source_checklist_id": checklist_id,
            "stage_id": next_stage_id,
        },
        headers=auth_headers(member_session["token"]),
    )
    assert import_response.status_code == 201, import_response.text
    imported_payload = import_response.json()
    assert imported_payload["stage_id"] == next_stage_id
    assert imported_payload["status"] == "draft"
    assert imported_payload["seeded_from_checklist_id"] == checklist_id
    repeated_import = client.post(
        import_path,
        json={
            "source_checklist_id": checklist_id,
            "stage_id": next_stage_id,
        },
        headers=auth_headers(member_session["token"]),
    )
    assert repeated_import.status_code == 409, repeated_import.text
    assert (
        repeated_import.json()["code"]
        == "legacy_issues.vehicle_module_checklist_stage_not_empty"
    )

    records_response = client.get(
        (
            "/api/v1/workspaces/module-checklist-member-workspace/legacy-issues/"
            f"vehicle-module-checklists/{checklist_id}/records"
        ),
        headers=auth_headers(member_session["token"]),
    )
    assert records_response.status_code == 200, records_response.text
    assert "grid_layout" not in records_response.json()["checklist"]
    assert records_response.json()["items"][0]["values"] == {
        "legacy_issue_number": "HTTP-AIR-001",
        "symptom": "HTTP module permission test",
        "check_plan": "마스터 작성 예시",
        "applied": "검토 필요",
        "reflection_result": "마스터 검토 예시",
        "evidence_legacy_issue": "등재",
    }

    with get_session_factory()() as db:
        checklist_record = db.scalar(
            select(LegacyIssueVehicleModuleChecklistRecord).where(
                LegacyIssueVehicleModuleChecklistRecord.checklist_id == checklist_id
            )
        )
        assert checklist_record is not None
        checklist_record_id = checklist_record.id
        db.add(
            LegacyIssueRecordHistory(
                id=history_id,
                workspace_id=checklist_record.workspace_id,
                record_kind=VEHICLE_MODULE_CHECKLIST_RECORD_KIND,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                record_id=checklist_record.id,
                action="update",
                actor_user_id=member_session["user"]["id"],
                created_at=utcnow_naive(),
            )
        )
        db.commit()

    delete_path = (
        "/api/v1/workspaces/module-checklist-member-workspace/legacy-issues/"
        f"vehicle-module-checklists/{checklist_id}"
    )
    anonymous_response = client.delete(delete_path)
    assert anonymous_response.status_code == 401, anonymous_response.text
    assert anonymous_response.json()["code"] == "auth.required"

    cross_workspace_response = client.delete(
        delete_path,
        headers=auth_headers(outsider_session["token"]),
    )
    assert cross_workspace_response.status_code == 403, cross_workspace_response.text
    assert cross_workspace_response.json()["code"] == "workspace.membership_required"

    with get_session_factory()() as db:
        assert db.get(LegacyIssueVehicleModuleChecklist, checklist_id) is not None
        assert db.get(LegacyIssueVehicleModuleChecklistRecord, checklist_record_id) is not None
        assert db.get(LegacyIssueRecordHistory, history_id) is not None

    member_response = client.delete(
        delete_path,
        headers=auth_headers(member_session["token"]),
    )
    assert member_response.status_code == 204, member_response.text
    assert member_response.content == b""

    with get_session_factory()() as db:
        assert db.get(LegacyIssueVehicleModuleChecklist, checklist_id) is None
        assert db.get(LegacyIssueVehicleModuleChecklistRecord, checklist_record_id) is None
        assert db.get(LegacyIssueRecordHistory, history_id) is None
        assert db.get(LegacyIssueDataRevision, master_revision_id) is not None
        assert db.get(LegacyIssueRecord, master_record_id) is not None
        assert db.get(LegacyIssueVehicleModel, vehicle_id) is not None
