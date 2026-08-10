from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import (
    AuditLog,
    OrgUnit,
    User,
    Workspace,
    WorkspaceUserBinding,
)
from open_alm_api.domains.legacy_issues import ai_search
from open_alm_api.domains.legacy_issues import router as legacy_issue_router
from open_alm_api.domains.legacy_issues.app_catalog import LEGACY_ISSUES_WORKSPACE_APP
from open_alm_api.domains.legacy_issues.dataset_records import (
    CLAIM_REGION_OPTIONS,
    COUNTERMEASURE_TYPE_OPTIONS,
    COMMON_MASTER_DATASET_KEY,
    DATASET_DEFINITIONS,
    DATASET_REQUIRED_FIELD_MISSING_CODE,
    DatasetFieldDefinition,
    INTRODUCED_REVISION_FIELD_KEY,
    LEGACY_ISSUE_EVIDENCE_FIELD_KEY,
    LEGACY_ISSUE_MODULE_KEYS,
    LegacyIssueDatasetDefinition,
    MASTER_STATUS_OPTIONS,
    OEM_DISCLOSURE_STATUS_OPTIONS,
    OX_SELECT_OPTIONS,
    REFLECTED_REVISION_FIELD_KEY,
    apply_record_projection,
    build_record_projection,
    canonicalize_dataset_values,
    clean_dataset_values,
    compare_dataset_revisions,
    create_dataset_record,
    display_dataset_value,
    field_labels,
    get_dataset_definition_for_view,
    get_dataset_definition_with_all_module_fields,
    import_dataset_records,
    list_system_field_setting_views,
    list_dataset_records,
    merge_dataset_values,
    module_key_from_legacy_department_label,
    normalize_legacy_issue_module_key,
    searchable_dataset_value_text,
    suggested_mapping,
    stamp_introduced_revision_numbers,
    update_dataset_record,
    upsert_system_field_setting,
    validate_required_values,
)
from open_alm_api.domains.legacy_issues.module_access import (
    LEGACY_ISSUE_COMPRESSOR_MODULE_KEYS,
    enabled_legacy_issue_module_keys,
    require_compressor_module_enabled,
)
from open_alm_api.domains.legacy_issues.module_direct_editors import (
    can_user_direct_edit_module,
    grant_module_direct_editor,
    list_module_direct_editors,
    revoke_module_direct_editor,
)
from open_alm_api.domains.legacy_issues.router import (
    LegacyIssueRecordBatchCreateItem,
    LegacyIssueRecordBatchSaveRequest,
    LegacyIssueRecordBatchUpdateItem,
)
from open_alm_api.domains.legacy_issues.column_orders import (
    COLUMN_ORDER_ATTACHMENT_KEY,
    get_column_order,
    sanitize_column_order,
    sanitize_hidden_column_keys,
    upsert_column_order,
)
from open_alm_api.domains.legacy_issues.history import normalize_history_value
from open_alm_api.domains.legacy_issues.module_fields import create_module_field
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueAiChunk,
    LegacyIssueAttachment,
    LegacyIssueColumnOrder,
    LegacyIssueDataRevision,
    LegacyIssueDataRevisionEvent,
    LegacyIssueModuleField,
    LegacyIssueModuleAccessRule,
    LegacyIssueRecord,
    LegacyIssueRecordHistory,
    LegacyIssueRevisionOverviewHistory,
    LegacyIssueSystemFieldSetting,
)
from open_alm_api.domains.legacy_issues.revisioning import (
    cancel_draft_revision,
    complete_revision_review,
    create_draft_revision,
    create_revision_overview_history,
    delete_revision_overview_history,
    hide_revision_from_overview_history,
    legacy_issue_dataset_revision_key,
    list_revision_overview_history,
    publish_draft_revision,
    release_draft_revision_editing,
    require_draft_revision_editor,
    require_record_revision_editor,
    update_revision_approval_assignees,
    update_revision_overview_history,
)
from open_alm_api.domains.retrieval.models import RetrievalPartition
from open_alm_api.domains.legacy_issues.tabular_import import EXPORT_RECORD_ID_HEADER


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            OrgUnit.__table__,
            Workspace.__table__,
            WorkspaceUserBinding.__table__,
            User.__table__,
            RetrievalPartition.__table__,
            LegacyIssueDataRevision.__table__,
            LegacyIssueDataRevisionEvent.__table__,
            LegacyIssueRevisionOverviewHistory.__table__,
            LegacyIssueRecord.__table__,
            LegacyIssueRecordHistory.__table__,
            LegacyIssueAiChunk.__table__,
            LegacyIssueAttachment.__table__,
            LegacyIssueModuleAccessRule.__table__,
            LegacyIssueModuleField.__table__,
            LegacyIssueSystemFieldSetting.__table__,
            LegacyIssueColumnOrder.__table__,
            AuditLog.__table__,
        ],
    )
    return Session(engine)


def _test_user(user_id: str, email: str) -> User:
    return User(
        id=user_id,
        login_id=user_id,
        email=email,
        full_name=user_id,
        password_hash="hash",
        status="active",
    )


def _binding(workspace: Workspace, user: User) -> WorkspaceUserBinding:
    return WorkspaceUserBinding(
        id=f"binding-{workspace.id}-{user.id}",
        workspace_id=workspace.id,
        user_id=user.id,
        role="member",
    )


def test_list_revision_overview_history_is_scoped_and_source_ordered() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        other_workspace = Workspace(id="workspace-2", key="other-workspace", name="Other Workspace")
        dataset_key = "legacy_issue.common-master.aircon"
        db.add_all(
            [
                workspace,
                other_workspace,
                LegacyIssueRevisionOverviewHistory(
                    id="history-2",
                    workspace_id=workspace.id,
                    dataset_key=dataset_key,
                    revision_no=14,
                    revision_label="14",
                    summary="older",
                    revised_on=date(2025, 2, 7),
                    source_filename="표지_에어컨.xlsx",
                    source_sha256="a" * 64,
                    source_sheet="샤시(ACON)",
                    source_row=7,
                    sort_order=1,
                ),
                LegacyIssueRevisionOverviewHistory(
                    id="history-1",
                    workspace_id=workspace.id,
                    dataset_key=dataset_key,
                    revision_no=15,
                    revision_label="15",
                    summary="latest",
                    revised_on=date(2025, 12, 10),
                    source_filename="표지_에어컨.xlsx",
                    source_sha256="a" * 64,
                    source_sheet="샤시(ACON)",
                    source_row=6,
                    sort_order=0,
                ),
                LegacyIssueRevisionOverviewHistory(
                    id="history-other",
                    workspace_id=other_workspace.id,
                    dataset_key=dataset_key,
                    revision_no=15,
                    revision_label="15",
                    source_filename="표지_에어컨.xlsx",
                    source_sha256="a" * 64,
                    source_sheet="샤시(ACON)",
                    source_row=6,
                    sort_order=0,
                ),
            ]
        )
        db.commit()

        rows = list_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
        )

        assert [row.id for row in rows] == ["history-1", "history-2"]


def test_platform_admin_can_update_revision_overview_history_with_audit(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = _test_user("platform-admin", "admin@example.com")
        dataset_key = "legacy_issue.common-master.aircon"
        revision = LegacyIssueDataRevision(
            id="revision-15",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=15,
            status="published",
            created_at=datetime(2025, 12, 10),
            updated_at=datetime(2025, 12, 10),
            published_at=datetime(2025, 12, 10),
        )
        history = LegacyIssueRevisionOverviewHistory(
            id="history-15",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=15,
            revision_label="15",
            summary="before",
            source_filename="표지_에어컨.xlsx",
            source_sha256="a" * 64,
            source_sheet="샤시(ACON)",
            source_row=2,
            sort_order=0,
        )
        db.add_all([workspace, user, _binding(workspace, user), revision, history])
        db.commit()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *_args, **_kwargs: True,
        )

        updated = update_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=history.id,
            user=user,
            revision_no=16,
            summary="after",
            revised_on=date(2026, 1, 2),
            vehicle_models="전차종",
            author_user_id=user.id,
            reviewer_user_id=None,
            approver_user_id=None,
            author_name="조작된 이름",
            reviewer_name="검토자",
            approver_name="승인자",
        )

        assert updated.revision_no == 16
        assert updated.revision_label == "16"
        assert updated.summary == "after"
        assert updated.author_user_id == user.id
        assert updated.author_name == "platform-admin"
        assert updated.reviewer_user_id is None
        assert updated.reviewer_name == "검토자"
        event = db.scalar(
            select(LegacyIssueDataRevisionEvent).where(
                LegacyIssueDataRevisionEvent.action == "overview_history_updated"
            )
        )
        assert event is not None
        assert event.actor_user_id == user.id
        assert event.details["previous"]["summary"] == "before"
        assert event.details["updated"]["summary"] == "after"


def test_overview_history_preserves_existing_employee_snapshot_on_later_edits(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("platform-admin", "admin@example.com")
        former_employee = _test_user("former-employee", "former@example.com")
        dataset_key = "legacy_issue.common-master.aircon"
        revision = LegacyIssueDataRevision(
            id="revision-15",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=15,
            status="published",
            created_at=datetime(2025, 12, 10),
            updated_at=datetime(2025, 12, 10),
            published_at=datetime(2025, 12, 10),
        )
        history = LegacyIssueRevisionOverviewHistory(
            id="history-15",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=15,
            revision_label="15",
            summary="before",
            author_user_id=former_employee.id,
            author_name="당시 이름",
            source_filename="표지_에어컨.xlsx",
            source_sha256="a" * 64,
            source_sheet="샤시(ACON)",
            source_row=2,
            sort_order=0,
        )
        former_employee.full_name = "현재 이름"
        former_employee.status = "inactive"
        db.add_all([workspace, admin, former_employee, revision, history])
        db.commit()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *_args, **_kwargs: True,
        )

        updated = update_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=history.id,
            user=admin,
            revision_no=15,
            summary="summary only changed",
            revised_on=None,
            vehicle_models=None,
            author_user_id=former_employee.id,
            reviewer_user_id=None,
            approver_user_id=None,
            author_name="클라이언트가 보낸 현재 이름",
            reviewer_name=None,
            approver_name=None,
        )

        assert updated.author_user_id == former_employee.id
        assert updated.author_name == "당시 이름"


def test_overview_history_direct_name_clears_existing_employee_link(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("platform-admin", "admin@example.com")
        employee = _test_user("employee", "employee@example.com")
        dataset_key = "legacy_issue.common-master.aircon"
        revision = LegacyIssueDataRevision(
            id="revision-15",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=15,
            status="published",
            created_at=datetime(2025, 12, 10),
            updated_at=datetime(2025, 12, 10),
            published_at=datetime(2025, 12, 10),
        )
        history = LegacyIssueRevisionOverviewHistory(
            id="history-15",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=15,
            revision_label="15",
            author_user_id=employee.id,
            author_name="직원 이름 스냅샷",
            source_filename="표지_에어컨.xlsx",
            source_sha256="a" * 64,
            source_sheet="샤시(ACON)",
            source_row=2,
            sort_order=0,
        )
        db.add_all([workspace, admin, employee, revision, history])
        db.commit()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *_args, **_kwargs: True,
        )

        updated = update_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=history.id,
            user=admin,
            revision_no=15,
            summary=None,
            revised_on=None,
            vehicle_models=None,
            author_user_id=None,
            reviewer_user_id=None,
            approver_user_id=None,
            author_name="퇴직자 직접 입력",
            reviewer_name=None,
            approver_name=None,
        )

        assert updated.author_user_id is None
        assert updated.author_name == "퇴직자 직접 입력"


def test_non_platform_admin_cannot_update_revision_overview_history(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = _test_user("member", "member@example.com")
        db.add_all([workspace, user])
        db.commit()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *_args, **_kwargs: False,
        )

        try:
            update_revision_overview_history(
                db,
                workspace=workspace,
                dataset_key="legacy_issue.common-master.aircon",
                history_id="history-15",
                user=user,
                revision_no=15,
                summary="blocked",
                revised_on=None,
                vehicle_models=None,
                author_user_id=None,
                reviewer_user_id=None,
                approver_user_id=None,
                author_name=None,
                reviewer_name=None,
                approver_name=None,
            )
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError("Expected platform-admin-only update to be rejected")


def test_platform_admin_can_create_manual_revision_overview_history_with_audit(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("platform-admin", "admin@example.com")
        dataset_key = "legacy_issue.common-master.compressor-electric"
        revision = LegacyIssueDataRevision(
            id="revision-36",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=36,
            status="published",
            created_at=datetime(2026, 7, 14),
            updated_at=datetime(2026, 7, 14),
            published_at=datetime(2026, 7, 14),
        )
        imported = LegacyIssueRevisionOverviewHistory(
            id="history-36",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=36,
            revision_label="36",
            source_filename="compressor.xlsx",
            source_sha256="a" * 64,
            source_sheet="전동",
            source_row=2,
            sort_order=4,
        )
        db.add_all([workspace, admin, _binding(workspace, admin), revision, imported])
        db.commit()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *_args, **_kwargs: True,
        )

        created = create_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            user=admin,
            linked_revision_id=None,
            revision_no=37,
            summary="수기 개요 행",
            revised_on=date(2026, 7, 14),
            vehicle_models="전차종",
            author_user_id=admin.id,
            reviewer_user_id=None,
            approver_user_id=None,
            author_name=None,
            reviewer_name="검토자",
            approver_name="승인자",
        )

        assert created.origin == "manual"
        assert created.linked_revision_id is None
        assert created.source_filename is None
        assert created.source_sha256 is None
        assert created.source_sheet is None
        assert created.source_row is None
        assert created.sort_order == 3
        assert created.author_name == "platform-admin"
        event = db.scalar(
            select(LegacyIssueDataRevisionEvent).where(
                LegacyIssueDataRevisionEvent.action == "overview_history_created"
            )
        )
        assert event is not None
        assert event.details["history"]["id"] == created.id
        assert event.details["history"]["origin"] == "manual"
        with pytest.raises(HTTPException) as duplicate_error:
            create_revision_overview_history(
                db,
                workspace=workspace,
                dataset_key=dataset_key,
                user=admin,
                linked_revision_id=None,
                revision_no=37,
                summary="중복 번호",
                revised_on=None,
                vehicle_models=None,
                author_user_id=None,
                reviewer_user_id=None,
                approver_user_id=None,
                author_name=None,
                reviewer_name=None,
                approver_name=None,
            )
        assert duplicate_error.value.status_code == 409
        future_revision = LegacyIssueDataRevision(
            id="revision-37",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=37,
            status="published",
            created_at=datetime(2026, 7, 15),
            updated_at=datetime(2026, 7, 15),
            published_at=datetime(2026, 7, 15),
        )
        db.add(future_revision)
        db.commit()

        linked = update_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=created.id,
            user=admin,
            revision_no=37,
            summary="수기 행과 같은 번호의 게시본 발행",
            revised_on=date(2026, 7, 15),
            vehicle_models="전차종",
            author_user_id=admin.id,
            reviewer_user_id=None,
            approver_user_id=None,
            author_name=None,
            reviewer_name="검토자",
            approver_name="승인자",
        )

        assert linked.linked_revision_id == future_revision.id
        deleted = delete_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=created.id,
            user=admin,
        )
        assert deleted.deleted_at is not None
        assert deleted.linked_revision_id == future_revision.id


def test_overview_number_change_keeps_canonical_revision_number_immutable(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("platform-admin", "admin@example.com")
        dataset_key = "legacy_issue.common-master.compressor-electric"
        revision = LegacyIssueDataRevision(
            id="revision-36",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=36,
            status="published",
            created_at=datetime(2026, 7, 14),
            updated_at=datetime(2026, 7, 14),
            published_at=datetime(2026, 7, 14),
        )
        other_revision = LegacyIssueDataRevision(
            id="revision-37",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=37,
            status="published",
            created_at=datetime(2026, 7, 14, 1),
            updated_at=datetime(2026, 7, 14, 1),
            published_at=datetime(2026, 7, 14, 1),
        )
        db.add_all(
            [
                workspace,
                admin,
                _binding(workspace, admin),
                revision,
                other_revision,
            ]
        )
        db.commit()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *_args, **_kwargs: True,
        )
        with pytest.raises(HTTPException) as manual_conflict_error:
            create_revision_overview_history(
                db,
                workspace=workspace,
                dataset_key=dataset_key,
                user=admin,
                linked_revision_id=None,
                revision_no=36,
                summary="manual row conflicts with canonical revision",
                revised_on=None,
                vehicle_models=None,
                author_user_id=None,
                reviewer_user_id=None,
                approver_user_id=None,
                author_name=None,
                reviewer_name=None,
                approver_name=None,
            )
        assert manual_conflict_error.value.status_code == 409

        created = create_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            user=admin,
            linked_revision_id=revision.id,
            revision_no=36,
            summary="before",
            revised_on=None,
            vehicle_models=None,
            author_user_id=None,
            reviewer_user_id=None,
            approver_user_id=None,
            author_name=None,
            reviewer_name=None,
            approver_name=None,
        )

        with pytest.raises(HTTPException) as conflict_error:
            update_revision_overview_history(
                db,
                workspace=workspace,
                dataset_key=dataset_key,
                history_id=created.id,
                user=admin,
                revision_no=37,
                summary="conflicts with canonical revision",
                revised_on=None,
                vehicle_models=None,
                author_user_id=None,
                reviewer_user_id=None,
                approver_user_id=None,
                author_name=None,
                reviewer_name=None,
                approver_name=None,
            )
        assert conflict_error.value.status_code == 409

        updated = update_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=created.id,
            user=admin,
            revision_no=40,
            summary="display number changed",
            revised_on=None,
            vehicle_models=None,
            author_user_id=None,
            reviewer_user_id=None,
            approver_user_id=None,
            author_name=None,
            reviewer_name=None,
            approver_name=None,
        )

        db.refresh(revision)
        assert updated.revision_no == 40
        assert updated.linked_revision_id == revision.id
        assert revision.revision_no == 36
        assert revision.status == "published"
        db.refresh(other_revision)
        assert other_revision.revision_no == 37


def test_delete_overview_history_soft_hides_row_and_links_published_revision(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("platform-admin", "admin@example.com")
        dataset_key = "legacy_issue.common-master.compressor-mechanical"
        revision = LegacyIssueDataRevision(
            id="revision-1",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=1,
            status="published",
            created_at=datetime(2026, 7, 14),
            updated_at=datetime(2026, 7, 14),
            published_at=datetime(2026, 7, 14),
        )
        history = LegacyIssueRevisionOverviewHistory(
            id="history-1",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=1,
            revision_label="1",
            source_filename="compressor.xls",
            source_sha256="a" * 64,
            source_sheet="기계식",
            source_row=2,
            sort_order=0,
        )
        db.add_all([workspace, admin, _binding(workspace, admin), revision, history])
        db.commit()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *_args, **_kwargs: True,
        )

        deleted = delete_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=history.id,
            user=admin,
        )

        assert deleted.deleted_at is not None
        assert deleted.deleted_by_id == admin.id
        assert deleted.linked_revision_id == revision.id
        db.refresh(revision)
        assert revision.revision_no == 1
        assert revision.status == "published"
        event = db.scalar(
            select(LegacyIssueDataRevisionEvent).where(
                LegacyIssueDataRevisionEvent.action == "overview_history_deleted"
            )
        )
        assert event is not None
        assert event.details["previous"]["revision_no"] == 1
        assert event.details["deleted"]["deleted_by_id"] == admin.id


def test_hide_published_revision_from_overview_is_idempotent(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("platform-admin", "admin@example.com")
        dataset_key = "legacy_issue.common-master.compressor-mechanical"
        revision = LegacyIssueDataRevision(
            id="revision-1",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=1,
            status="published",
            created_at=datetime(2026, 7, 14),
            updated_at=datetime(2026, 7, 14),
            published_at=datetime(2026, 7, 14),
        )
        db.add_all([workspace, admin, _binding(workspace, admin), revision])
        db.commit()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *_args, **_kwargs: True,
        )

        first = hide_revision_from_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            revision_id=revision.id,
            user=admin,
        )
        second = hide_revision_from_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            revision_id=revision.id,
            user=admin,
        )

        assert second.id == first.id
        assert first.deleted_at is not None
        assert first.origin == "system"
        rows = list_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
        )
        assert [row.id for row in rows] == [first.id]
        events = list(
            db.scalars(
                select(LegacyIssueDataRevisionEvent).where(
                    LegacyIssueDataRevisionEvent.action == "overview_history_deleted"
                )
            )
        )
        assert len(events) == 1


def test_non_platform_admin_cannot_create_or_delete_overview_history(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = _test_user("member", "member@example.com")
        db.add_all([workspace, user])
        db.commit()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *_args, **_kwargs: False,
        )

        with pytest.raises(HTTPException) as create_error:
            create_revision_overview_history(
                db,
                workspace=workspace,
                dataset_key="legacy_issue.common-master.compressor-electric",
                user=user,
                linked_revision_id=None,
                revision_no=36,
                summary=None,
                revised_on=None,
                vehicle_models=None,
                author_user_id=None,
                reviewer_user_id=None,
                approver_user_id=None,
                author_name=None,
                reviewer_name=None,
                approver_name=None,
            )
        assert create_error.value.status_code == 403

        with pytest.raises(HTTPException) as delete_error:
            delete_revision_overview_history(
                db,
                workspace=workspace,
                dataset_key="legacy_issue.common-master.compressor-electric",
                history_id="history-36",
                user=user,
            )
        assert delete_error.value.status_code == 403

        with pytest.raises(HTTPException) as hide_error:
            hide_revision_from_overview_history(
                db,
                workspace=workspace,
                dataset_key="legacy_issue.common-master.compressor-electric",
                revision_id="revision-36",
                user=user,
            )
        assert hide_error.value.status_code == 403


def test_common_master_is_the_only_dataset_definition() -> None:
    assert tuple(DATASET_DEFINITIONS) == (COMMON_MASTER_DATASET_KEY,)
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]

    assert definition.header_rows == 2
    assert definition.group_labels_ko == {"check": "CHECK", "evidence": "점검 근거"}
    assert [field.key for field in definition.fields[:5]] == [
        INTRODUCED_REVISION_FIELD_KEY,
        "department",
        "registrant",
        "legacy_issue_number",
        "major_category",
    ]
    fields = {field.key: field for field in definition.fields}
    assert "row_no" not in fields
    assert fields[INTRODUCED_REVISION_FIELD_KEY].readonly is False
    assert fields[INTRODUCED_REVISION_FIELD_KEY].settings_readonly is True
    assert fields["registrant"].label_ko == "대책 작성자"
    assert fields["registrant"].label_en == "Countermeasure Author"
    assert fields["registrant"].aliases == ("등록자", "Registrant")
    assert "claim_region" not in fields
    assert fields["region_zone"].label_ko == "권역"
    assert fields["region_zone"].required is False
    assert fields["region_zone"].options == CLAIM_REGION_OPTIONS
    assert fields["countermeasure_type"].options == COUNTERMEASURE_TYPE_OPTIONS
    assert "oem_open" not in fields
    assert fields["oem_disclosure_status"].options == OEM_DISCLOSURE_STATUS_OPTIONS
    assert "OEM오픈" in fields["oem_disclosure_status"].aliases
    assert fields["evidence_legacy_issue"].label_ko == "마스터 상태"
    assert fields["evidence_legacy_issue"].field_type == "select"
    assert fields["evidence_legacy_issue"].options == MASTER_STATUS_OPTIONS
    assert fields["applied"].field_type == "select"
    assert fields["applied"].options == OX_SELECT_OPTIONS
    assert fields[LEGACY_ISSUE_EVIDENCE_FIELD_KEY].label_ko == "과거차 문제점"
    assert fields[LEGACY_ISSUE_EVIDENCE_FIELD_KEY].field_type == "select"
    assert fields[LEGACY_ISSUE_EVIDENCE_FIELD_KEY].options == OX_SELECT_OPTIONS
    assert fields["evidence_quality_spec"].field_type == "select"
    assert fields["evidence_quality_spec"].options == OX_SELECT_OPTIONS
    field_keys = [field.key for field in definition.fields]
    assert (
        field_keys.index("evidence_legacy_issue")
        < field_keys.index(LEGACY_ISSUE_EVIDENCE_FIELD_KEY)
        < field_keys.index("evidence_design_check_sheet")
    )


def test_common_master_maps_legacy_issue_evidence_header_to_ox_column() -> None:
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]

    assert suggested_mapping(
        definition,
        ["마스터 상태", "과거차문제점", "설계체크시트"],
    ) == {
        "evidence_legacy_issue": 0,
        LEGACY_ISSUE_EVIDENCE_FIELD_KEY: 1,
        "evidence_design_check_sheet": 2,
    }


def test_common_master_projection_populates_sql_columns_and_search_text() -> None:
    values = {
        "row_no": " 17 ",
        "department": "샤시(ACON)",
        "legacy_issue_number": "PV-2026-001",
        "major_category": "HVAC",
        "vehicle_model": "MX5",
        "symptom": "저단 소음",
        "cause": "고정부 유격",
        "countermeasure": "브라켓 보강",
        "check_plan": "양산 전 확인",
        "notes": "재발 방지",
    }
    projection = build_record_projection(values, raw_fields={"원본컬럼": "원본값"})

    assert projection["department"] == "샤시(ACON)"
    assert projection["legacy_issue_number"] == "PV-2026-001"
    assert projection["vehicle_model"] == "MX5"
    assert "현상: 저단 소음" in (projection["search_text"] or "")
    assert "원본컬럼: 원본값" in (projection["search_text"] or "")

    record = LegacyIssueRecord(
        id="record-1",
        workspace_id="workspace-1",
        dataset_key=COMMON_MASTER_DATASET_KEY,
        field_values=values,
        oem_open="legacy",
        raw_fields={},
    )
    apply_record_projection(record, {**values, "oem_open": "O"})

    assert record.department == "샤시(ACON)"
    assert record.oem_open is None
    assert record.oem_disclosure_status == "공개"
    assert record.symptom == "저단 소음"
    assert record.search_text is not None


def test_common_master_revision_is_user_writable() -> None:
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]

    clean_values = clean_dataset_values(
        definition,
        {
            INTRODUCED_REVISION_FIELD_KEY: "12",
            "claim_region": "북미",
            "symptom": "소음",
        },
    )
    next_values, changed_values = merge_dataset_values(
        definition,
        current_values={INTRODUCED_REVISION_FIELD_KEY: "11", "symptom": "소음"},
        incoming_values={INTRODUCED_REVISION_FIELD_KEY: "12", "symptom": "진동"},
    )

    assert clean_values[INTRODUCED_REVISION_FIELD_KEY] == "12"
    assert next_values[INTRODUCED_REVISION_FIELD_KEY] == "12"
    assert changed_values == {
        INTRODUCED_REVISION_FIELD_KEY: "12",
        "symptom": "진동",
    }


def test_common_master_region_is_optional_by_default() -> None:
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]

    validate_required_values(definition, {"symptom": "소음"})
    validate_required_values(definition, {"region_zone": "북미", "symptom": "소음"})


def test_common_master_date_fields_are_optional_and_canonical() -> None:
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]
    fields = {field.key: field for field in definition.fields}

    assert fields["occurrence_date"].field_type == "date"
    assert fields["received_date"].field_type == "date"
    assert fields["occurrence_date"].required is False
    assert fields["received_date"].required is False
    assert (
        clean_dataset_values(
            definition,
            {"occurrence_date": None, "received_date": None},
        )
        == {}
    )
    assert (
        clean_dataset_values(
            definition,
            {"occurrence_date": "  ", "received_date": "  "},
        )
        == {}
    )
    cleared_values, cleared_changes = merge_dataset_values(
        definition,
        current_values={
            "occurrence_date": "2026-07-19",
            "received_date": "2026-07-20",
            "symptom": "소음",
        },
        incoming_values={"occurrence_date": None, "received_date": None},
    )
    assert cleared_values == {"symptom": "소음"}
    assert cleared_changes == {"occurrence_date": None, "received_date": None}

    for raw_value in (
        "2026-07-24",
        "20260724",
        "2026.7.24",
        "2026/07/24",
        date(2026, 7, 24),
        datetime(2026, 7, 24, 15, 30),
        "2026-07-24T15:30:00+09:00",
    ):
        for field_key in ("occurrence_date", "received_date"):
            assert clean_dataset_values(
                definition,
                {field_key: raw_value},
            ) == {field_key: "2026-07-24"}

    for invalid_value in ("-", "07/24/2026", "24/07/2026", "2026-02-30", "07/2026"):
        for field_key in ("occurrence_date", "received_date"):
            with pytest.raises(HTTPException) as invalid:
                clean_dataset_values(
                    definition,
                    {field_key: invalid_value},
                )
            assert invalid.value.status_code == 400
            assert invalid.value.detail.code == "legacy_issues.module_field_value_invalid"


def test_system_field_setting_can_require_region_for_new_rows() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        db.add_all([workspace, user])
        db.flush()

        setting = upsert_system_field_setting(
            db,
            workspace=workspace,
            user=user,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            field_key="region_zone",
            required=True,
        )
        definition = get_dataset_definition_for_view(
            db,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            workspace=workspace,
        )

        assert setting.field.required is True
        system_fields = {
            item.field.key: item
            for item in list_system_field_setting_views(
                db,
                workspace=workspace,
                dataset_key=COMMON_MASTER_DATASET_KEY,
            )
        }
        assert system_fields["region_zone"].id == setting.id
        try:
            validate_required_values(definition, {"symptom": "소음"})
        except HTTPException as error:
            assert error.status_code == 400
            assert error.detail.code == DATASET_REQUIRED_FIELD_MISSING_CODE
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("validate_required_values should reject missing region")

        validate_required_values(definition, {"region_zone": "북미", "symptom": "소음"})


def test_reflected_revision_system_field_setting_remains_readonly() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        db.add_all([workspace, user])
        db.flush()

        definition_item = legacy_issue_router._serialize_dataset_definition(
            get_dataset_definition_for_view(
                db,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                workspace=workspace,
            )
        )
        revision_field = next(
            field for field in definition_item.fields if field.key == INTRODUCED_REVISION_FIELD_KEY
        )
        settings_view = next(
            item
            for item in list_system_field_setting_views(
                db,
                workspace=workspace,
                dataset_key=COMMON_MASTER_DATASET_KEY,
            )
            if item.field.key == INTRODUCED_REVISION_FIELD_KEY
        )

        assert revision_field.readonly is False
        assert legacy_issue_router._serialize_system_field_setting(settings_view).readonly is True

        with pytest.raises(HTTPException) as error:
            upsert_system_field_setting(
                db,
                workspace=workspace,
                user=user,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                field_key=INTRODUCED_REVISION_FIELD_KEY,
                field_type="text",
            )

        assert error.value.status_code == 400
        assert error.value.detail.code == "legacy_issues.module_field_invalid"


def test_system_field_setting_overrides_type_and_select_options() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        db.add_all([workspace, user])
        db.flush()

        upsert_system_field_setting(
            db,
            workspace=workspace,
            user=user,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            field_key="countermeasure_type",
            field_type="select",
            options=["양산", "개발"],
        )
        definition = get_dataset_definition_for_view(
            db,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            workspace=workspace,
        )
        fields = {field.key: field for field in definition.fields}

        assert fields["countermeasure_type"].field_type == "select"
        assert fields["countermeasure_type"].options == ("양산", "개발")
        assert clean_dataset_values(definition, {"countermeasure_type": "양산"}) == {
            "countermeasure_type": "양산"
        }
        try:
            clean_dataset_values(definition, {"countermeasure_type": "실제"})
        except HTTPException as error:
            assert error.status_code == 400
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("clean_dataset_values should reject removed select options")


def test_custom_fields_normalize_multi_select_user_and_org_unit_values() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        owner = User(
            id="user-owner",
            login_id="owner",
            email="owner@example.com",
            full_name="Owner Kim",
            display_name="오너",
            password_hash="hash",
        )
        reviewer = User(
            id="user-reviewer",
            login_id="reviewer",
            email="reviewer@example.com",
            full_name="Reviewer Lee",
            display_name="리뷰어",
            password_hash="hash",
        )
        headquarters = OrgUnit(
            id="org-headquarters",
            name="Headquarters",
            slug="headquarters",
            unit_type="group",
        )
        research = OrgUnit(
            id="org-research",
            name="Research",
            slug="research",
            parent_id=headquarters.id,
        )
        db.add_all([workspace, owner, reviewer, headquarters, research])
        db.flush()
        definition = LegacyIssueDatasetDefinition(
            key="test",
            table_model=LegacyIssueRecord,
            title_ko="테스트",
            title_en="Test",
            hierarchy_ko=("테스트",),
            hierarchy_en=("Test",),
            fields=(
                DatasetFieldDefinition(
                    key="markets",
                    label_ko="권역",
                    label_en="Markets",
                    field_type="select",
                    options=("북미", "유럽"),
                    allow_multiple=True,
                ),
                DatasetFieldDefinition(
                    key="owners",
                    label_ko="담당자",
                    label_en="Owners",
                    field_type="user",
                    allow_multiple=True,
                ),
                DatasetFieldDefinition(
                    key="review_department",
                    label_ko="검토 부서",
                    label_en="Review Department",
                    field_type="orgUnit",
                ),
            ),
        )

        clean_values = clean_dataset_values(
            definition,
            {
                "markets": "북미; 유럽; 북미",
                "owners": ["owner@example.com", {"id": reviewer.id}],
                "review_department": "Headquarters / Research",
            },
            db=db,
            workspace=workspace,
        )

        assert clean_values == {
            "markets": ["북미", "유럽"],
            "owners": [
                {
                    "kind": "user",
                    "id": owner.id,
                    "label": "오너",
                    "email": "owner@example.com",
                },
                {
                    "kind": "user",
                    "id": reviewer.id,
                    "label": "리뷰어",
                    "email": "reviewer@example.com",
                },
            ],
            "review_department": {
                "kind": "orgUnit",
                "id": research.id,
                "label": "Research",
                "path": "Headquarters / Research",
            },
        }


def test_reference_values_render_for_display_search_and_history() -> None:
    value = [
        {
            "kind": "user",
            "id": "user-1",
            "label": "홍길동",
            "email": "hong@example.com",
        },
        {
            "kind": "orgUnit",
            "id": "org-1",
            "label": "연구소",
            "path": "Headquarters / 연구소",
        },
    ]

    assert display_dataset_value(value) == "홍길동; 연구소"
    assert (
        searchable_dataset_value_text(value)
        == "홍길동 hong@example.com user-1; 연구소 Headquarters / 연구소 org-1"
    )
    assert normalize_history_value(value) == "홍길동; 연구소"


def test_create_dataset_record_allows_new_row_without_region_by_default() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-12",
            workspace_id=workspace.id,
            dataset_key="legacy-issues:common-master",
            status="draft",
        )
        db.add_all([workspace, user, revision])
        db.flush()

        record = create_dataset_record(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            user=user,
            revision=revision,
            values={"symptom": "소음"},
        )

        assert record.field_values["symptom"] == "소음"
        assert "region_zone" not in record.field_values


def test_create_dataset_record_sets_introduced_revision_for_new_rows() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        revision_dataset_key = legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY)
        draft_revision = LegacyIssueDataRevision(
            id="revision-13-draft",
            workspace_id=workspace.id,
            dataset_key=revision_dataset_key,
            status="draft",
        )
        db.add_all([workspace, user, draft_revision])
        db.flush()

        record = create_dataset_record(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            user=user,
            revision=draft_revision,
            values={"region_zone": "북미", "symptom": "소음"},
        )

        assert record.field_values[INTRODUCED_REVISION_FIELD_KEY] == "1"
        assert record.introduced_revision_no == 1


def test_create_and_update_dataset_record_preserve_edited_introduced_revision() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-13-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="draft",
        )
        db.add_all([workspace, user, revision])
        db.flush()

        record = create_dataset_record(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            user=user,
            revision=revision,
            values={
                INTRODUCED_REVISION_FIELD_KEY: "7",
                "symptom": "소음",
            },
        )

        assert record.field_values[INTRODUCED_REVISION_FIELD_KEY] == "7"
        assert record.introduced_revision_no == 7

        updated = update_dataset_record(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            user=user,
            revision=revision,
            record_id=record.id,
            values={INTRODUCED_REVISION_FIELD_KEY: "9"},
        )

        assert updated.field_values[INTRODUCED_REVISION_FIELD_KEY] == "9"
        assert updated.introduced_revision_no == 9


def test_publish_draft_revision_requires_review_and_approval() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        author = _test_user("author", "author@example.com")
        reviewer = _test_user("reviewer", "reviewer@example.com")
        approver = _test_user("approver", "approver@example.com")
        revision = LegacyIssueDataRevision(
            id="revision-draft-approval",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="draft",
            locked_by_id=author.id,
            created_by_id=author.id,
            reviewer_id=reviewer.id,
            approver_id=approver.id,
        )
        db.add_all(
            [
                workspace,
                author,
                reviewer,
                approver,
                _binding(workspace, author),
                _binding(workspace, reviewer),
                _binding(workspace, approver),
                revision,
            ]
        )
        db.flush()

        try:
            publish_draft_revision(
                db,
                workspace=workspace,
                dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
                user=author,
                revision_id=revision.id,
                note="ready",
            )
        except HTTPException as error:
            assert error.status_code == 409
            assert error.detail.code == "legacy_issues.revision_approval_required"
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("publish should require review and approval")

        completed_at = datetime(2026, 7, 6, 9, 0, 0)
        revision.reviewed_by_id = reviewer.id
        revision.reviewed_at = completed_at
        revision.approved_by_id = approver.id
        revision.approved_at = completed_at

        published = publish_draft_revision(
            db,
            workspace=workspace,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            user=author,
            revision_id=revision.id,
            note="ready",
        )

        assert published.status == "published"
        assert published.revision_no == 1
        assert published.published_by_id == author.id


def test_revision_assignee_change_resets_matching_completion() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        author = _test_user("author", "author@example.com")
        old_reviewer = _test_user("old-reviewer", "old-reviewer@example.com")
        new_reviewer = _test_user("new-reviewer", "new-reviewer@example.com")
        approver = _test_user("approver", "approver@example.com")
        completed_at = datetime(2026, 7, 6, 9, 0, 0)
        revision = LegacyIssueDataRevision(
            id="revision-draft-reset",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="draft",
            locked_by_id=author.id,
            created_by_id=author.id,
            reviewer_id=old_reviewer.id,
            reviewed_by_id=old_reviewer.id,
            reviewed_at=completed_at,
            approver_id=approver.id,
            approved_by_id=approver.id,
            approved_at=completed_at,
        )
        users = [author, old_reviewer, new_reviewer, approver]
        db.add_all([workspace, revision, *users, *[_binding(workspace, user) for user in users]])
        db.flush()

        updated = update_revision_approval_assignees(
            db,
            workspace=workspace,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            user=author,
            revision_id=revision.id,
            reviewer_id=new_reviewer.id,
            approver_id=approver.id,
        )

        assert updated.reviewer_id == new_reviewer.id
        assert updated.reviewed_by_id is None
        assert updated.reviewed_at is None
        assert updated.approver_id == approver.id
        assert updated.approved_by_id == approver.id
        assert updated.approved_at == completed_at


def test_unlocked_draft_allows_assignee_assignment_after_save() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        author = _test_user("author", "author@example.com")
        reviewer = _test_user("reviewer", "reviewer@example.com")
        approver = _test_user("approver", "approver@example.com")
        revision = LegacyIssueDataRevision(
            id="revision-draft-unlocked",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="draft",
            locked_by_id=None,
            created_by_id=author.id,
        )
        users = [author, reviewer, approver]
        db.add_all([workspace, revision, *users, *[_binding(workspace, user) for user in users]])
        db.flush()

        updated = update_revision_approval_assignees(
            db,
            workspace=workspace,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            user=author,
            revision_id=revision.id,
            reviewer_id=reviewer.id,
            approver_id=approver.id,
        )

        assert updated.locked_by_id is None
        assert updated.reviewer_id == reviewer.id
        assert updated.approver_id == approver.id


def test_complete_revision_review_requires_assigned_reviewer() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        reviewer = _test_user("reviewer", "reviewer@example.com")
        other = _test_user("other", "other@example.com")
        revision = LegacyIssueDataRevision(
            id="revision-draft-review",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="draft",
            reviewer_id=reviewer.id,
        )
        db.add_all(
            [
                workspace,
                reviewer,
                other,
                _binding(workspace, reviewer),
                _binding(workspace, other),
                revision,
            ]
        )
        db.flush()

        try:
            complete_revision_review(
                db,
                workspace=workspace,
                dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
                user=other,
                revision_id=revision.id,
            )
        except HTTPException as error:
            assert error.status_code == 403
            assert error.detail.code == "legacy_issues.revision_review_assignee_required"
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("review completion should require assigned reviewer")

        updated = complete_revision_review(
            db,
            workspace=workspace,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            user=reviewer,
            revision_id=revision.id,
        )

        assert updated.reviewed_by_id == reviewer.id
        assert updated.reviewed_at is not None


def test_create_dataset_record_sets_module_key_without_department_default() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            status="draft",
        )
        db.add_all([workspace, user, revision])
        db.flush()

        record = create_dataset_record(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            user=user,
            revision=revision,
            values={"region_zone": "북미", "symptom": "소음"},
            module_key="electrical-control-sw",
        )

        assert record.module_key == "electrical-control-sw"
        assert record.department is None
        assert "department" not in record.field_values


def test_module_key_filters_records_independently_from_department() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        revision = LegacyIssueDataRevision(
            id="revision-current",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="published",
        )
        aircon = LegacyIssueRecord(
            id="record-aircon",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id="stable-aircon",
            module_key="aircon",
            department="품질보증팀",
            field_values={"department": "품질보증팀", "symptom": "소음"},
            raw_fields={},
        )
        interior = LegacyIssueRecord(
            id="record-interior",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id="stable-interior",
            module_key="interior",
            department="품질보증팀",
            field_values={"department": "품질보증팀", "symptom": "진동"},
            raw_fields={},
        )
        db.add_all([workspace, revision, aircon, interior])
        db.flush()

        rows, total = list_dataset_records(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            revision=revision,
            module_key="aircon",
            departments=["품질보증팀"],
        )

        assert total == 1
        assert [row.id for row in rows] == ["record-aircon"]


def test_compressor_module_keys_labels_and_injected_access_gate() -> None:
    assert LEGACY_ISSUE_COMPRESSOR_MODULE_KEYS == {
        "compressor-electric",
        "compressor-mechanical",
    }
    assert LEGACY_ISSUE_COMPRESSOR_MODULE_KEYS <= LEGACY_ISSUE_MODULE_KEYS
    assert normalize_legacy_issue_module_key("compressor-electric") == "compressor-electric"
    assert normalize_legacy_issue_module_key("compressor-mechanical") == "compressor-mechanical"
    assert module_key_from_legacy_department_label("컴프레서(전동)") == "compressor-electric"
    assert module_key_from_legacy_department_label("컴프레서(기계)") == "compressor-mechanical"
    assert "heat-exchanger" in LEGACY_ISSUE_MODULE_KEYS
    assert normalize_legacy_issue_module_key("heat-exchanger") == "heat-exchanger"
    assert module_key_from_legacy_department_label("열교환기") == "heat-exchanger"

    require_compressor_module_enabled("compressor-electric", compressor_enabled=True)
    require_compressor_module_enabled("aircon", compressor_enabled=False)
    assert enabled_legacy_issue_module_keys(compressor_enabled=True) == LEGACY_ISSUE_MODULE_KEYS
    assert enabled_legacy_issue_module_keys(compressor_enabled=False).isdisjoint(
        LEGACY_ISSUE_COMPRESSOR_MODULE_KEYS
    )
    try:
        require_compressor_module_enabled("compressor-mechanical", compressor_enabled=False)
    except HTTPException as error:
        assert error.status_code == 404
        assert error.detail.code == "legacy_issues.module_not_found"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("disabled compressor modules must not be accessible")


def test_heat_exchanger_workspace_navigation_registration() -> None:
    item = next(
        item
        for item in LEGACY_ISSUES_WORKSPACE_APP.nav_items
        if item.id == "legacy-issues-heat-exchanger"
    )

    assert item.title == "열교환기"
    assert item.category == "legacy-issues"
    assert item.icon_key == "fan"
    assert item.path_suffix == "/heat-exchanger"


def test_first_heat_exchanger_read_persists_revision_for_draft_start(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        editor = _test_user("editor", "editor@example.com")
        db.add_all([workspace, editor, _binding(workspace, editor)])
        db.commit()
        monkeypatch.setattr(
            legacy_issue_router,
            "can_direct_edit_published_revision",
            lambda *args, **kwargs: False,
        )
        response = legacy_issue_router.list_legacy_issue_dataset_records(
            dataset_key=COMMON_MASTER_DATASET_KEY,
            department=None,
            q=None,
            revision_id=None,
            view_key="heat-exchanger",
            limit=None,
            offset=0,
            db=db,
            current_user=editor,
            current_workspace=workspace,
        )
        initial_revision = response.revision.current

        db.rollback()
        persisted_revision = db.get(LegacyIssueDataRevision, initial_revision.id)
        assert persisted_revision is not None
        assert persisted_revision.revision_no == 1
        assert persisted_revision.status == "published"

        draft = legacy_issue_router.create_legacy_issue_dataset_draft_revision(
            dataset_key=COMMON_MASTER_DATASET_KEY,
            payload=None,
            base_revision_id=initial_revision.id,
            view_key="heat-exchanger",
            db=db,
            current_user=editor,
            current_workspace=workspace,
        )

        assert draft.base_revision_id == initial_revision.id
        assert draft.status == "draft"


def test_first_heat_exchanger_revision_list_persists_initial_revision() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        db.add(workspace)
        db.commit()

        response = legacy_issue_router.list_legacy_issue_dataset_revisions(
            dataset_key=COMMON_MASTER_DATASET_KEY,
            view_key="heat-exchanger",
            db=db,
            current_workspace=workspace,
        )

        assert len(response.items) == 1
        initial_revision = response.items[0]
        db.rollback()
        persisted_revision = db.get(LegacyIssueDataRevision, initial_revision.id)
        assert persisted_revision is not None
        assert persisted_revision.revision_no == 1
        assert persisted_revision.status == "published"


def test_router_compressor_revision_gate_uses_core_feature_flag(monkeypatch) -> None:
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]
    monkeypatch.setattr(legacy_issue_router, "_compressor_enabled", lambda: False)
    try:
        legacy_issue_router._module_revision_dataset_key(definition, "compressor-electric")
    except HTTPException as error:
        assert error.status_code == 404
        assert error.detail.code == "legacy_issues.module_not_found"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("disabled compressor revisions must not be addressable")

    monkeypatch.setattr(legacy_issue_router, "_compressor_enabled", lambda: True)
    assert legacy_issue_router._module_revision_dataset_key(
        definition, "compressor-electric"
    ) == legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY, "compressor-electric")


def test_stored_assistant_runs_hide_disabled_compressor_evidence(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        revision = LegacyIssueDataRevision(
            id="revision-1",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            revision_no=1,
            status="published",
        )
        aircon = LegacyIssueRecord(
            id="record-aircon",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id="stable-aircon",
            module_key="aircon",
            field_values={},
            raw_fields={},
        )
        compressor = LegacyIssueRecord(
            id="record-compressor",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id="stable-compressor",
            module_key="compressor-electric",
            field_values={},
            raw_fields={},
        )
        db.add_all([workspace, revision, aircon, compressor])
        db.flush()
        rows = [
            SimpleNamespace(id="run-aircon", evidence=[{"record_id": aircon.id}]),
            SimpleNamespace(id="run-compressor", evidence=[{"record_id": compressor.id}]),
            SimpleNamespace(id="run-empty", evidence=[]),
        ]
        monkeypatch.setattr(legacy_issue_router, "_compressor_enabled", lambda: False)

        visible = legacy_issue_router._filter_enabled_assistant_runs(
            db,
            workspace=workspace,
            rows=rows,
        )

        assert [row.id for row in visible] == ["run-aircon", "run-empty"]


def test_stored_assistant_runs_hide_disabled_analysis_scope_modules(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        db.add(workspace)
        db.flush()
        rows = [
            SimpleNamespace(
                id="run-aircon",
                evidence=[],
                analysis_result={
                    "version": 1,
                    "scope": {"module_keys": ["aircon"]},
                },
            ),
            SimpleNamespace(
                id="run-compressor",
                evidence=[],
                analysis_result={
                    "version": 1,
                    "scope": {"module_keys": ["aircon", "compressor-electric"]},
                },
            ),
            SimpleNamespace(id="run-legacy", evidence=[]),
            SimpleNamespace(id="run-null", evidence=[], analysis_result=None),
            SimpleNamespace(
                id="run-invalid",
                evidence=[],
                analysis_result={
                    "version": 1,
                    "scope": {"module_keys": "compressor-electric"},
                },
            ),
            SimpleNamespace(
                id="run-empty-scope",
                evidence=[],
                analysis_result={
                    "version": 1,
                    "scope": {"module_keys": []},
                },
            ),
        ]
        monkeypatch.setattr(legacy_issue_router, "_compressor_enabled", lambda: False)

        visible = legacy_issue_router._filter_enabled_assistant_runs(
            db,
            workspace=workspace,
            rows=rows,
        )

        assert [row.id for row in visible] == [
            "run-aircon",
            "run-legacy",
            "run-null",
        ]

        monkeypatch.setattr(legacy_issue_router, "_compressor_enabled", lambda: True)
        visible_with_compressor = legacy_issue_router._filter_enabled_assistant_runs(
            db,
            workspace=workspace,
            rows=rows,
        )

        assert [row.id for row in visible_with_compressor] == [
            "run-aircon",
            "run-compressor",
            "run-legacy",
            "run-null",
        ]


def test_compressor_revisions_filter_independently_and_join_aggregate_reads() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        electric_revision = LegacyIssueDataRevision(
            id="compressor-electric-revision-36",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "compressor-electric",
            ),
            revision_no=36,
            status="published",
        )
        mechanical_revision = LegacyIssueDataRevision(
            id="compressor-mechanical-revision-1",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "compressor-mechanical",
            ),
            revision_no=1,
            status="published",
        )
        electric_record = LegacyIssueRecord(
            id="compressor-electric-record",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=electric_revision.id,
            stable_record_id="compressor-electric-stable",
            module_key="compressor-electric",
            field_values={"symptom": "전동 컴프레서 소음"},
            raw_fields={},
        )
        mechanical_record = LegacyIssueRecord(
            id="compressor-mechanical-record",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=mechanical_revision.id,
            stable_record_id="compressor-mechanical-stable",
            module_key="compressor-mechanical",
            field_values={"symptom": "기계식 컴프레서 진동"},
            raw_fields={},
        )
        db.add_all(
            [
                workspace,
                electric_revision,
                mechanical_revision,
                electric_record,
                mechanical_record,
            ]
        )
        db.flush()

        electric_rows, electric_total = list_dataset_records(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            revision=electric_revision,
            module_key="compressor-electric",
        )
        aggregate_rows, aggregate_total = list_dataset_records(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            revisions=[electric_revision, mechanical_revision],
        )
        requested_rows, requested_total = list_dataset_records(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            revisions=[electric_revision, mechanical_revision],
            record_ids=[mechanical_record.id, "outside-scope"],
        )
        empty_rows, empty_total = list_dataset_records(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            revisions=[electric_revision, mechanical_revision],
            record_ids=[],
        )

        assert electric_revision.dataset_key != mechanical_revision.dataset_key
        assert electric_total == 1
        assert [row.id for row in electric_rows] == [electric_record.id]
        assert aggregate_total == 2
        assert {row.id for row in aggregate_rows} == {
            electric_record.id,
            mechanical_record.id,
        }
        assert requested_total == 1
        assert [row.id for row in requested_rows] == [mechanical_record.id]
        assert empty_rows == []
        assert empty_total == 0


def test_compressor_modules_participate_in_ai_projection_discovery(monkeypatch) -> None:
    workspace = SimpleNamespace(id="workspace-1")
    revisions = {
        legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY, module_key): SimpleNamespace(
            id=f"revision-{module_key}",
        )
        for module_key in LEGACY_ISSUE_COMPRESSOR_MODULE_KEYS
    }

    monkeypatch.setattr(
        ai_search,
        "_effective_revision_for_ai",
        lambda _db, *, workspace, dataset_key: revisions.get(dataset_key),
    )

    class _ProjectionState:
        @staticmethod
        def execute(_statement):
            return SimpleNamespace(one=lambda: (1, 1, 1, 0))

    discovered = ai_search.ensure_legacy_issue_ai_projection_for_effective_revisions(
        _ProjectionState(),
        workspace=workspace,
        dataset_keys=(COMMON_MASTER_DATASET_KEY,),
    )

    assert {revision.id for revision in discovered[COMMON_MASTER_DATASET_KEY]} == {
        "revision-compressor-electric",
        "revision-compressor-mechanical",
    }


def test_ai_projection_discovery_uses_effective_revision_per_module(monkeypatch) -> None:
    workspace = SimpleNamespace(id="workspace-1")
    aircon_key = legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY, "aircon")
    interior_key = legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY, "interior")
    active_draft = SimpleNamespace(id="draft-aircon")
    latest_published = SimpleNamespace(id="published-interior")
    effective_lookups: list[str] = []

    def fake_effective_revision(_db, *, workspace, dataset_key):
        effective_lookups.append(dataset_key)
        return {
            aircon_key: active_draft,
            interior_key: latest_published,
        }.get(dataset_key)

    monkeypatch.setattr(
        ai_search,
        "_effective_revision_for_ai",
        fake_effective_revision,
    )

    class _CompleteProjectionState:
        @staticmethod
        def execute(_statement):
            return SimpleNamespace(one=lambda: (1, 1, 1, 0))

    discovered = ai_search.ensure_legacy_issue_ai_projection_for_effective_revisions(
        _CompleteProjectionState(),
        workspace=workspace,
        dataset_keys=(COMMON_MASTER_DATASET_KEY,),
        module_keys=frozenset({"aircon", "interior"}),
    )

    assert [revision.id for revision in discovered[COMMON_MASTER_DATASET_KEY]] == [
        "draft-aircon",
        "published-interior",
    ]
    assert effective_lookups == [aircon_key, aircon_key, interior_key, interior_key]


def test_assistant_evidence_hydrates_active_draft_and_historical_published() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        revision_key = legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            "aircon",
        )
        published = LegacyIssueDataRevision(
            id="published-revision",
            workspace_id=workspace.id,
            dataset_key=revision_key,
            revision_no=1,
            status="published",
        )
        latest_published = LegacyIssueDataRevision(
            id="latest-published-revision",
            workspace_id=workspace.id,
            dataset_key=revision_key,
            revision_no=2,
            status="published",
        )
        draft = LegacyIssueDataRevision(
            id="active-draft",
            workspace_id=workspace.id,
            dataset_key=revision_key,
            status="draft",
            base_revision_id=latest_published.id,
        )
        canceled = LegacyIssueDataRevision(
            id="canceled-draft",
            workspace_id=workspace.id,
            dataset_key=revision_key,
            status="canceled",
            base_revision_id=latest_published.id,
        )
        published_record = LegacyIssueRecord(
            id="published-record",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=published.id,
            stable_record_id="stable-published",
            field_values={"problem": "published evidence"},
        )
        draft_record = LegacyIssueRecord(
            id="draft-record",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=draft.id,
            stable_record_id="stable-draft",
            field_values={"problem": "draft evidence"},
        )
        canceled_record = LegacyIssueRecord(
            id="canceled-record",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=canceled.id,
            stable_record_id="stable-canceled",
            field_values={"problem": "canceled evidence"},
        )
        db.add_all(
            [
                workspace,
                published,
                latest_published,
                draft,
                canceled,
                published_record,
                draft_record,
                canceled_record,
            ]
        )
        db.flush()

        def hydrate(revision_id: str, record_id: str):
            return legacy_issue_router._hydrate_assistant_evidence_ref(
                db,
                workspace=workspace,
                ref=legacy_issue_router.LegacyIssueAssistantEvidenceRefItem(
                    id="E1",
                    dataset_key=COMMON_MASTER_DATASET_KEY,
                    revision_id=revision_id,
                    record_id=record_id,
                ),
            )

        published_evidence = hydrate(published.id, published_record.id)
        draft_evidence = hydrate(draft.id, draft_record.id)

        assert published_evidence is not None
        assert published_evidence.revision_no == 1
        assert draft_evidence is not None
        assert draft_evidence.revision_id == draft.id
        assert draft_evidence.revision_no is None
        assert hydrate(canceled.id, canceled_record.id) is None


def test_assistant_evidence_hydration_enforces_partition_and_module_scope() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        allowed_partition = RetrievalPartition(
            source_namespace="legacy_issues",
            managed_workspace_id=workspace.id,
            candidate_scope_kind="workspace",
            candidate_workspace_id=workspace.id,
            state="active",
            metadata_version=1,
            is_default_ingest=True,
        )
        excluded_partition = RetrievalPartition(
            source_namespace="legacy_issues",
            managed_workspace_id=workspace.id,
            candidate_scope_kind="workspace",
            candidate_workspace_id=workspace.id,
            state="transitioning",
            metadata_version=1,
            is_default_ingest=False,
        )
        db.add_all([workspace, allowed_partition, excluded_partition])
        db.flush()
        revision_key = legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            "aircon",
        )
        allowed_revision = LegacyIssueDataRevision(
            id="allowed-revision",
            workspace_id=workspace.id,
            retrieval_partition_id=allowed_partition.id,
            dataset_key=revision_key,
            revision_no=1,
            status="published",
        )
        excluded_revision = LegacyIssueDataRevision(
            id="excluded-revision",
            workspace_id=workspace.id,
            retrieval_partition_id=excluded_partition.id,
            dataset_key=revision_key,
            revision_no=2,
            status="published",
        )
        invalid_module_revision = LegacyIssueDataRevision(
            id="invalid-module-revision",
            workspace_id=workspace.id,
            retrieval_partition_id=allowed_partition.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "retired-module",
            ),
            revision_no=3,
            status="published",
        )
        allowed_record = LegacyIssueRecord(
            id="allowed-record",
            workspace_id=workspace.id,
            retrieval_partition_id=allowed_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=allowed_revision.id,
            stable_record_id="stable-allowed",
            field_values={"problem": "allowed"},
        )
        excluded_record = LegacyIssueRecord(
            id="excluded-record",
            workspace_id=workspace.id,
            retrieval_partition_id=excluded_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=allowed_revision.id,
            stable_record_id="stable-excluded",
            field_values={"problem": "excluded"},
        )
        excluded_revision_record = LegacyIssueRecord(
            id="excluded-revision-record",
            workspace_id=workspace.id,
            retrieval_partition_id=excluded_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=excluded_revision.id,
            stable_record_id="stable-excluded-revision",
            field_values={"problem": "excluded revision"},
        )
        invalid_module_record = LegacyIssueRecord(
            id="invalid-module-record",
            workspace_id=workspace.id,
            retrieval_partition_id=allowed_partition.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="retired-module",
            revision_id=invalid_module_revision.id,
            stable_record_id="stable-invalid-module",
            field_values={"problem": "invalid module"},
        )
        db.add_all(
            [
                allowed_revision,
                excluded_revision,
                invalid_module_revision,
                allowed_record,
                excluded_record,
                excluded_revision_record,
                invalid_module_record,
            ]
        )
        db.flush()

        def hydrate(revision_id: str, record_id: str):
            return legacy_issue_router._hydrate_assistant_evidence_ref(
                db,
                workspace=workspace,
                ref=legacy_issue_router.LegacyIssueAssistantEvidenceRefItem(
                    id="E1",
                    dataset_key=COMMON_MASTER_DATASET_KEY,
                    revision_id=revision_id,
                    record_id=record_id,
                ),
            )

        assert hydrate(allowed_revision.id, allowed_record.id) is not None
        assert hydrate(allowed_revision.id, excluded_record.id) is None
        assert hydrate(excluded_revision.id, excluded_revision_record.id) is None
        assert hydrate(invalid_module_revision.id, invalid_module_record.id) is None


def test_module_revision_notifications_link_to_registered_module_routes() -> None:
    workspace = Workspace(id="workspace-1", key="research", name="Research")
    revision = LegacyIssueDataRevision(id="revision-36")

    electric_url = legacy_issue_router._legacy_issue_revision_action_url(
        workspace=workspace,
        revision=revision,
        view_key="compressor-electric",
    )
    mechanical_url = legacy_issue_router._legacy_issue_revision_action_url(
        workspace=workspace,
        revision=revision,
        view_key="compressor-mechanical",
    )
    heat_exchanger_url = legacy_issue_router._legacy_issue_revision_action_url(
        workspace=workspace,
        revision=revision,
        view_key="heat-exchanger",
    )

    assert electric_url == (
        "/w/research/legacy-issues/compressor/electric?tab=overview&revision_id=revision-36"
    )
    assert mechanical_url == (
        "/w/research/legacy-issues/compressor/mechanical?tab=overview&revision_id=revision-36"
    )
    assert heat_exchanger_url == (
        "/w/research/legacy-issues/heat-exchanger?tab=overview&revision_id=revision-36"
    )


def test_module_import_rejects_record_ids_from_other_modules() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            status="draft",
            locked_by_id=user.id,
            created_by_id=user.id,
        )
        record = LegacyIssueRecord(
            id="record-aircon",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id="stable-aircon",
            module_key="aircon",
            field_values={"region_zone": "북미", "symptom": "old"},
            raw_fields={},
        )
        db.add_all([workspace, user, revision, record])
        db.flush()

        content = "\n".join(
            [
                "record_id,권역,현상",
                "stable-aircon,북미,new",
            ]
        ).encode()

        try:
            import_dataset_records(
                db,
                DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
                workspace=workspace,
                user=user,
                revision=revision,
                filename="records.csv",
                content=content,
                mapping={
                    EXPORT_RECORD_ID_HEADER: 0,
                    "region_zone": 1,
                    "symptom": 2,
                },
                module_key="interior",
            )
        except HTTPException as error:
            assert error.status_code == 400
            assert error.detail.code == "legacy_issues.dataset_import_pk_invalid"
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("cross-module import should reject the record id")

        db.refresh(record)
        assert record.module_key == "aircon"
        assert record.field_values["symptom"] == "old"


def test_platform_admin_can_edit_latest_published_module_without_new_revision(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("admin", "admin@example.com")
        revision = LegacyIssueDataRevision(
            id="aircon-revision-1",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            revision_no=1,
            status="published",
        )
        db.add_all([workspace, admin, revision])
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: True,
        )

        editable = require_record_revision_editor(
            db,
            workspace=workspace,
            dataset_key=revision.dataset_key,
            user=admin,
            revision_id=revision.id,
        )

        assert editable.id == revision.id
        assert editable.revision_no == 1


def test_platform_admin_can_save_owned_module_draft(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("admin", "admin@example.com")
        revision = LegacyIssueDataRevision(
            id="aircon-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            status="draft",
            locked_by_id=admin.id,
            created_by_id=admin.id,
        )
        db.add_all([workspace, admin, revision])
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: True,
        )

        editable = require_record_revision_editor(
            db,
            workspace=workspace,
            dataset_key=revision.dataset_key,
            user=admin,
            revision_id=revision.id,
        )

        assert editable.id == revision.id
        assert editable.status == "draft"


def test_member_cannot_edit_latest_published_module_without_draft(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        member = _test_user("member", "member@example.com")
        revision = LegacyIssueDataRevision(
            id="aircon-revision-1",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            revision_no=1,
            status="published",
        )
        db.add_all([workspace, member, revision])
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )

        with pytest.raises(HTTPException) as error:
            require_record_revision_editor(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                user=member,
                revision_id=revision.id,
            )

        assert error.value.status_code == 409
        assert error.value.detail.code == "legacy_issues.revision_draft_required"


def test_explicit_module_editor_can_edit_only_assigned_latest_published_module(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        member = _test_user("member", "member@example.com")
        aircon_revision = LegacyIssueDataRevision(
            id="aircon-revision-1",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            revision_no=1,
            status="published",
        )
        interior_revision = LegacyIssueDataRevision(
            id="interior-revision-1",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "interior",
            ),
            revision_no=1,
            status="published",
        )
        access_rule = LegacyIssueModuleAccessRule(
            id="access-aircon-member",
            workspace_id=workspace.id,
            module_key="aircon",
            subject_type="user",
            subject_id=member.id,
            role="editor",
            active=True,
            created_at=datetime(2026, 7, 23, 9, 1),
            updated_at=datetime(2026, 7, 23, 9, 1),
        )
        member_binding = _binding(workspace, member)
        member_binding.created_at = datetime(2026, 7, 23, 9, 0)
        db.add_all(
            [
                workspace,
                member,
                member_binding,
                aircon_revision,
                interior_revision,
                access_rule,
            ]
        )
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.module_direct_editors.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )

        editable = require_record_revision_editor(
            db,
            workspace=workspace,
            dataset_key=aircon_revision.dataset_key,
            module_key="aircon",
            user=member,
            revision_id=aircon_revision.id,
        )

        assert editable.id == aircon_revision.id
        with pytest.raises(HTTPException) as error:
            require_record_revision_editor(
                db,
                workspace=workspace,
                dataset_key=interior_revision.dataset_key,
                module_key="interior",
                user=member,
                revision_id=interior_revision.id,
            )
        assert error.value.status_code == 409
        assert error.value.detail.code == "legacy_issues.revision_draft_required"


def test_platform_admin_can_grant_and_revoke_heat_exchanger_direct_editor(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("admin", "admin@example.com")
        member = _test_user("member", "member@example.com")
        db.add_all(
            [
                workspace,
                admin,
                member,
                _binding(workspace, admin),
                _binding(workspace, member),
            ]
        )
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.module_direct_editors.is_platform_admin_user",
            lambda user, *args, **kwargs: user.id == admin.id,
        )

        granted = grant_module_direct_editor(
            db,
            workspace=workspace,
            actor=admin,
            module_key="heat-exchanger",
            user_id=member.id,
        )
        granted_again = grant_module_direct_editor(
            db,
            workspace=workspace,
            actor=admin,
            module_key="heat-exchanger",
            user_id=member.id,
        )

        assert granted.id == granted_again.id
        assert granted.user_id == member.id
        assert [
            item.user_id
            for item in list_module_direct_editors(
                db,
                workspace=workspace,
                actor=admin,
                module_key="heat-exchanger",
            )
        ] == [member.id]
        assert can_user_direct_edit_module(
            db,
            workspace=workspace,
            user=member,
            module_key="heat-exchanger",
        )
        assert (
            db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "legacy_issues.module_direct_editor.grant"
                )
            )
            == 1
        )

        original_binding = db.scalar(
            select(WorkspaceUserBinding).where(
                WorkspaceUserBinding.workspace_id == workspace.id,
                WorkspaceUserBinding.user_id == member.id,
            )
        )
        assert original_binding is not None
        db.delete(original_binding)
        db.flush()
        db.add(
            WorkspaceUserBinding(
                id="binding-rejoined-member",
                workspace_id=workspace.id,
                user_id=member.id,
                role="member",
                created_at=granted.updated_at + timedelta(seconds=1),
            )
        )
        db.flush()
        assert not can_user_direct_edit_module(
            db,
            workspace=workspace,
            user=member,
            module_key="heat-exchanger",
        )
        [stale_grant] = list_module_direct_editors(
            db,
            workspace=workspace,
            actor=admin,
            module_key="heat-exchanger",
        )
        assert not stale_grant.active_member

        regranted = grant_module_direct_editor(
            db,
            workspace=workspace,
            actor=admin,
            module_key="heat-exchanger",
            user_id=member.id,
        )
        assert regranted.active_member
        assert can_user_direct_edit_module(
            db,
            workspace=workspace,
            user=member,
            module_key="heat-exchanger",
        )
        assert (
            db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "legacy_issues.module_direct_editor.grant"
                )
            )
            == 2
        )

        revoke_module_direct_editor(
            db,
            workspace=workspace,
            actor=admin,
            module_key="heat-exchanger",
            user_id=member.id,
        )
        revoke_module_direct_editor(
            db,
            workspace=workspace,
            actor=admin,
            module_key="heat-exchanger",
            user_id=member.id,
        )

        assert not can_user_direct_edit_module(
            db,
            workspace=workspace,
            user=member,
            module_key="heat-exchanger",
        )
        assert (
            db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "legacy_issues.module_direct_editor.revoke"
                )
            )
            == 1
        )


def test_direct_editor_grant_rejects_non_workspace_user(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("admin", "admin@example.com")
        outsider = _test_user("outsider", "outsider@example.com")
        db.add_all([workspace, admin, outsider, _binding(workspace, admin)])
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.module_direct_editors.is_platform_admin_user",
            lambda user, *args, **kwargs: user.id == admin.id,
        )

        with pytest.raises(HTTPException) as error:
            grant_module_direct_editor(
                db,
                workspace=workspace,
                actor=admin,
                module_key="aircon",
                user_id=outsider.id,
            )

        assert error.value.status_code == 404
        assert error.value.detail.code == "admin.workspace_member_not_found"


def test_workspace_admin_cannot_manage_module_direct_editors(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        workspace_admin = _test_user("workspace-admin", "admin@example.com")
        binding = _binding(workspace, workspace_admin)
        binding.role = "admin"
        revision = LegacyIssueDataRevision(
            id="aircon-published",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            revision_no=1,
            status="published",
        )
        db.add_all([workspace, workspace_admin, binding, revision])
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.module_direct_editors.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )

        with pytest.raises(HTTPException) as error:
            list_module_direct_editors(
                db,
                workspace=workspace,
                actor=workspace_admin,
            )

        assert error.value.status_code == 403
        assert error.value.detail.code == "admin.platform_admin_required"
        with pytest.raises(HTTPException) as edit_error:
            require_record_revision_editor(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                module_key="aircon",
                user=workspace_admin,
                revision_id=revision.id,
            )
        assert edit_error.value.status_code == 409
        assert edit_error.value.detail.code == "legacy_issues.revision_draft_required"


def test_platform_admin_cannot_edit_published_module_with_active_draft(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("admin", "admin@example.com")
        dataset_key = legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            "aircon",
        )
        published = LegacyIssueDataRevision(
            id="aircon-revision-1",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=1,
            status="published",
        )
        draft = LegacyIssueDataRevision(
            id="aircon-draft",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            status="draft",
            base_revision_id=published.id,
            locked_by_id=admin.id,
            created_by_id=admin.id,
        )
        db.add_all([workspace, admin, published, draft])
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: True,
        )

        with pytest.raises(HTTPException) as error:
            require_record_revision_editor(
                db,
                workspace=workspace,
                dataset_key=dataset_key,
                user=admin,
                revision_id=published.id,
            )

        assert error.value.status_code == 409
        assert error.value.detail.code == "legacy_issues.revision_current_required"


def test_platform_admin_cannot_edit_older_published_module(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = _test_user("admin", "admin@example.com")
        dataset_key = legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            "aircon",
        )
        older_revision = LegacyIssueDataRevision(
            id="aircon-revision-1",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=1,
            status="published",
        )
        latest_revision = LegacyIssueDataRevision(
            id="aircon-revision-2",
            workspace_id=workspace.id,
            dataset_key=dataset_key,
            revision_no=2,
            status="published",
        )
        db.add_all([workspace, admin, older_revision, latest_revision])
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: True,
        )

        with pytest.raises(HTTPException) as error:
            require_record_revision_editor(
                db,
                workspace=workspace,
                dataset_key=dataset_key,
                user=admin,
                revision_id=older_revision.id,
            )

        assert error.value.status_code == 409
        assert error.value.detail.code == "legacy_issues.revision_current_required"


def test_aggregate_record_mutation_is_rejected() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = _test_user("user", "user@example.com")
        db.add_all([workspace, user])
        db.flush()

        try:
            legacy_issue_router._require_module_record_editor(
                db,
                definition=DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
                workspace=workspace,
                user=user,
                view_key=None,
                revision_id=None,
            )
        except HTTPException as error:
            assert error.status_code == 409
            assert error.detail.code == "legacy_issues.aggregate_readonly"
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("aggregate mutations must be rejected")


def test_draft_revision_editor_requires_owner() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        owner = User(
            id="user-owner",
            login_id="owner",
            email="owner@example.com",
            full_name="Owner",
            password_hash="hash",
        )
        other = User(
            id="user-other",
            login_id="other",
            email="other@example.com",
            full_name="Other",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="draft",
            locked_by_id=owner.id,
            created_by_id=owner.id,
        )
        db.add_all([workspace, owner, other, revision])
        db.flush()

        assert (
            require_draft_revision_editor(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                user=owner,
                revision_id=revision.id,
            ).id
            == revision.id
        )

        try:
            require_draft_revision_editor(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                user=other,
                revision_id=revision.id,
            )
        except HTTPException as error:
            assert error.status_code == 403
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("non-owner should not edit a draft revision")


def test_platform_admin_can_force_cancel_another_users_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        owner = User(
            id="user-owner",
            login_id="owner",
            email="owner@example.com",
            full_name="Owner",
            password_hash="hash",
        )
        admin = User(
            id="user-admin",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        member = User(
            id="user-member",
            login_id="member",
            email="member@example.com",
            full_name="Member",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="draft",
            note="Keep the original draft note",
            locked_by_id=owner.id,
            created_by_id=owner.id,
        )
        record = LegacyIssueRecord(
            id="record-draft",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            field_values={"problem": "saved draft data"},
        )
        attachment = LegacyIssueAttachment(
            id="attachment-draft",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            record_id=record.id,
            filename="draft-evidence.txt",
            storage_key="legacy-issues/shared/draft-evidence.txt",
        )
        db.add_all([workspace, owner, admin, member, revision, record, attachment])
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda candidate, _db: candidate.id == admin.id,
        )
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.module_direct_editors.is_platform_admin_user",
            lambda candidate, _db: candidate.id == admin.id,
        )

        with pytest.raises(HTTPException) as member_error:
            cancel_draft_revision(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                module_key="aircon",
                user=member,
                revision_id=revision.id,
            )
        assert member_error.value.status_code == 403
        assert member_error.value.detail.code == "legacy_issues.revision_locked"

        with pytest.raises(HTTPException) as confirmation_error:
            cancel_draft_revision(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                module_key="aircon",
                user=admin,
                revision_id=revision.id,
            )
        assert confirmation_error.value.status_code == 409
        assert (
            confirmation_error.value.detail.code
            == "legacy_issues.revision_force_cancel_confirmation_required"
        )

        canceled = cancel_draft_revision(
            db,
            workspace=workspace,
            dataset_key=revision.dataset_key,
            module_key="aircon",
            user=admin,
            revision_id=revision.id,
            force=True,
        )
        db.flush()

        assert canceled.status == "canceled"
        assert canceled.note == "Keep the original draft note"
        assert canceled.locked_by_id is None
        assert canceled.canceled_by_id == admin.id
        assert db.get(LegacyIssueRecord, record.id).field_values == {"problem": "saved draft data"}
        assert (
            db.get(LegacyIssueAttachment, attachment.id).storage_key
            == "legacy-issues/shared/draft-evidence.txt"
        )
        event = db.scalar(
            select(LegacyIssueDataRevisionEvent).where(
                LegacyIssueDataRevisionEvent.revision_id == revision.id,
                LegacyIssueDataRevisionEvent.action == "force_cancel",
            )
        )
        assert event is not None
        assert event.actor_user_id == admin.id
        assert event.details == {
            "forced_by_authorized_editor": True,
            "authorization_source": "platform_admin",
            "module_key": "aircon",
            "previous_locked_by_id": owner.id,
            "previous_locked_by_name": owner.full_name,
            "created_by_id": owner.id,
        }
        audit_log = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == revision.id,
                AuditLog.action == "legacy_issues.revision.force_cancel",
            )
        )
        assert audit_log is not None
        assert audit_log.actor_user_id == admin.id
        assert audit_log.payload == {
            "workspace_id": workspace.id,
            "dataset_key": revision.dataset_key,
            "module_key": "aircon",
            "authorization_source": "platform_admin",
            "previous_locked_by_id": owner.id,
            "previous_locked_by_name": owner.full_name,
            "created_by_id": owner.id,
        }

        with pytest.raises(HTTPException) as repeated_error:
            cancel_draft_revision(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                module_key="aircon",
                user=admin,
                revision_id=revision.id,
                force=True,
            )
        assert repeated_error.value.status_code == 409
        assert (
            db.scalar(
                select(func.count())
                .select_from(LegacyIssueDataRevisionEvent)
                .where(LegacyIssueDataRevisionEvent.revision_id == revision.id)
            )
            == 1
        )


def test_module_direct_editor_can_only_force_cancel_draft_in_assigned_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        current_editor = _test_user("current-editor", "current@example.com")
        direct_editor = _test_user("direct-editor", "direct@example.com")
        direct_editor_binding = _binding(workspace, direct_editor)
        direct_editor_binding.created_at = datetime(2026, 7, 23, 9, 0)
        access_rule = LegacyIssueModuleAccessRule(
            id="access-aircon-direct-editor",
            workspace_id=workspace.id,
            module_key="aircon",
            subject_type="user",
            subject_id=direct_editor.id,
            role="editor",
            active=True,
            created_at=datetime(2026, 7, 23, 9, 1),
            updated_at=datetime(2026, 7, 23, 9, 1),
        )
        aircon_draft = LegacyIssueDataRevision(
            id="aircon-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            status="draft",
            locked_by_id=current_editor.id,
            created_by_id=current_editor.id,
        )
        interior_draft = LegacyIssueDataRevision(
            id="interior-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "interior",
            ),
            status="draft",
            locked_by_id=current_editor.id,
            created_by_id=current_editor.id,
        )
        db.add_all(
            [
                workspace,
                current_editor,
                direct_editor,
                direct_editor_binding,
                access_rule,
                aircon_draft,
                interior_draft,
            ]
        )
        db.flush()
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.module_direct_editors.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )

        with pytest.raises(HTTPException) as other_module_error:
            cancel_draft_revision(
                db,
                workspace=workspace,
                dataset_key=interior_draft.dataset_key,
                module_key="interior",
                user=direct_editor,
                revision_id=interior_draft.id,
                force=True,
            )
        assert other_module_error.value.status_code == 403
        assert interior_draft.status == "draft"

        with pytest.raises(HTTPException) as confirmation_error:
            cancel_draft_revision(
                db,
                workspace=workspace,
                dataset_key=aircon_draft.dataset_key,
                module_key="aircon",
                user=direct_editor,
                revision_id=aircon_draft.id,
            )
        assert confirmation_error.value.status_code == 409
        assert (
            confirmation_error.value.detail.code
            == "legacy_issues.revision_force_cancel_confirmation_required"
        )

        canceled = cancel_draft_revision(
            db,
            workspace=workspace,
            dataset_key=aircon_draft.dataset_key,
            module_key="aircon",
            user=direct_editor,
            revision_id=aircon_draft.id,
            force=True,
        )
        db.flush()

        assert canceled.status == "canceled"
        assert canceled.canceled_by_id == direct_editor.id
        event = db.scalar(
            select(LegacyIssueDataRevisionEvent).where(
                LegacyIssueDataRevisionEvent.revision_id == aircon_draft.id,
                LegacyIssueDataRevisionEvent.action == "force_cancel",
            )
        )
        assert event is not None
        assert event.details is not None
        assert event.details["authorization_source"] == "module_direct_editor"
        assert event.details["module_key"] == "aircon"
        audit_log = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == aircon_draft.id,
                AuditLog.action == "legacy_issues.revision.force_cancel",
            )
        )
        assert audit_log is not None
        assert audit_log.payload["authorization_source"] == "module_direct_editor"
        assert audit_log.payload["module_key"] == "aircon"


def test_draft_editor_cancel_keeps_the_existing_non_forced_audit_event() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        editor = User(
            id="user-editor",
            login_id="editor",
            email="editor@example.com",
            full_name="Editor",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            status="draft",
            locked_by_id=editor.id,
            created_by_id=editor.id,
        )
        db.add_all([workspace, editor, revision])
        db.flush()

        canceled = cancel_draft_revision(
            db,
            workspace=workspace,
            dataset_key=revision.dataset_key,
            module_key="aircon",
            user=editor,
            revision_id=revision.id,
        )
        db.flush()

        assert canceled.status == "canceled"
        event = db.scalar(
            select(LegacyIssueDataRevisionEvent).where(
                LegacyIssueDataRevisionEvent.revision_id == revision.id
            )
        )
        assert event is not None
        assert event.action == "cancel"
        assert event.details is None
        assert (
            db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == revision.id)
            )
            == 0
        )


def test_draft_revision_editor_refreshes_stale_identity_before_owner_check() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        first_editor = _test_user("user-first", "first@example.com")
        next_editor = _test_user("user-next", "next@example.com")
        revision = LegacyIssueDataRevision(
            id="revision-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="draft",
            locked_by_id=first_editor.id,
            created_by_id=first_editor.id,
        )
        db.add_all([workspace, first_editor, next_editor, revision])
        db.flush()

        db.execute(
            update(LegacyIssueDataRevision)
            .where(LegacyIssueDataRevision.id == revision.id)
            .values(locked_by_id=next_editor.id)
            .execution_options(synchronize_session=False)
        )
        assert revision.locked_by_id == first_editor.id

        with pytest.raises(HTTPException) as stale_editor_error:
            require_draft_revision_editor(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                user=first_editor,
                revision_id=revision.id,
            )

        assert stale_editor_error.value.status_code == 403
        assert revision.locked_by_id == next_editor.id


def test_saved_draft_can_be_acquired_by_another_editor() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        first_editor = _test_user("user-first", "first@example.com")
        next_editor = _test_user("user-next", "next@example.com")
        revision = LegacyIssueDataRevision(
            id="revision-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            status="draft",
            locked_by_id=first_editor.id,
            created_by_id=first_editor.id,
        )
        db.add_all([workspace, first_editor, next_editor, revision])
        db.flush()

        released = release_draft_revision_editing(
            db,
            workspace=workspace,
            dataset_key=revision.dataset_key,
            user=first_editor,
            revision_id=revision.id,
        )

        assert released.locked_by_id is None
        assert released.created_by_id == first_editor.id
        with pytest.raises(HTTPException) as unlocked_error:
            require_draft_revision_editor(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                user=first_editor,
                revision_id=revision.id,
            )
        assert unlocked_error.value.status_code == 403

        acquired, created = create_draft_revision(
            db,
            workspace=workspace,
            dataset_key=revision.dataset_key,
            user=next_editor,
        )

        assert created is False
        assert acquired.id == revision.id
        assert acquired.locked_by_id == next_editor.id
        assert acquired.created_by_id == first_editor.id
        with pytest.raises(HTTPException) as stale_editor_error:
            require_draft_revision_editor(
                db,
                workspace=workspace,
                dataset_key=revision.dataset_key,
                user=first_editor,
                revision_id=revision.id,
            )
        assert stale_editor_error.value.status_code == 403
        assert [
            event.action
            for event in db.scalars(
                select(LegacyIssueDataRevisionEvent).where(
                    LegacyIssueDataRevisionEvent.revision_id == revision.id,
                )
            )
        ] == ["draft_save", "draft_edit_start"]


def test_new_draft_does_not_inherit_base_revision_grid_layout() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = _test_user("user-editor", "editor@example.com")
        base_revision = LegacyIssueDataRevision(
            id="revision-published",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            revision_no=4,
            status="published",
            grid_layout={
                "version": 1,
                "column_order": ["symptom", "cause"],
                "column_widths": {"symptom": 420},
                "hidden_column_keys": ["cause"],
            },
            created_by_id=user.id,
            published_by_id=user.id,
        )
        db.add_all([workspace, user, base_revision])
        db.flush()

        draft, created = create_draft_revision(
            db,
            workspace=workspace,
            dataset_key=base_revision.dataset_key,
            user=user,
            base_revision_id=base_revision.id,
        )

        assert created is True
        assert draft.base_revision_id == base_revision.id
        assert draft.grid_layout is None


def test_update_dataset_record_allows_existing_row_without_region() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-12",
            workspace_id=workspace.id,
            dataset_key="legacy-issues:common-master",
            status="draft",
            base_revision_id="revision-11",
        )
        record = LegacyIssueRecord(
            id="record-current-1",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id="stable-existing",
            field_values={"symptom": "old"},
            raw_fields={},
        )
        db.add_all([workspace, user, revision, record])
        db.flush()

        updated = update_dataset_record(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            user=user,
            revision=revision,
            record_id=record.id,
            values={"symptom": "new"},
        )

        assert updated.field_values == {"symptom": "new"}


def test_draft_record_update_is_visible_when_revision_is_reloaded() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            status="draft",
            locked_by_id=user.id,
            created_by_id=user.id,
        )
        record = LegacyIssueRecord(
            id="record-current-1",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id="stable-existing",
            field_values={"region_zone": "북미", "symptom": "old"},
            raw_fields={},
        )
        db.add_all([workspace, user, revision, record])
        db.flush()

        update_dataset_record(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            user=user,
            revision=revision,
            record_id=record.id,
            values={"symptom": "new"},
        )
        db.commit()

        rows, total = list_dataset_records(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            revision=revision,
        )

        assert total == 1
        assert rows[0].field_values["symptom"] == "new"


def test_legacy_claim_region_values_are_canonicalized_to_region() -> None:
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]

    assert canonicalize_dataset_values({"claim_region": "북미", "symptom": "소음"}) == {
        "region_zone": "북미",
        "symptom": "소음",
    }
    assert clean_dataset_values(definition, {"claim_region": "유럽", "symptom": "소음"}) == {
        "region_zone": "유럽",
        "symptom": "소음",
    }


def test_legacy_oem_open_values_are_canonicalized_to_disclosure_status() -> None:
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]

    assert canonicalize_dataset_values({"oem_open": "O", "symptom": "소음"}) == {
        "oem_disclosure_status": "공개",
        "symptom": "소음",
    }
    assert canonicalize_dataset_values({"oem_open": "공개", "oem_disclosure_status": "비공개"}) == {
        "oem_disclosure_status": "비공개",
    }
    assert clean_dataset_values(definition, {"oem_open": "X", "symptom": "소음"}) == {
        "oem_disclosure_status": "비공개",
        "symptom": "소음",
    }


def test_legacy_reflected_revision_is_canonicalized_and_projection_is_cleared() -> None:
    values = canonicalize_dataset_values(
        {
            INTRODUCED_REVISION_FIELD_KEY: "1",
            REFLECTED_REVISION_FIELD_KEY: "12",
            "symptom": "소음",
        }
    )

    assert values == {
        INTRODUCED_REVISION_FIELD_KEY: "12",
        "symptom": "소음",
    }

    record = LegacyIssueRecord(
        id="record-1",
        workspace_id="workspace-1",
        dataset_key=COMMON_MASTER_DATASET_KEY,
        field_values=values,
        raw_fields={},
        introduced_revision_no=1,
        reflected_revision="12",
    )
    apply_record_projection(record, values)

    assert record.introduced_revision_no == 12
    assert record.reflected_revision is None


def test_legacy_master_status_values_are_canonicalized_to_select_options() -> None:
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]

    assert canonicalize_dataset_values({"evidence_legacy_issue": "○"}) == {
        "evidence_legacy_issue": "등재",
    }
    assert canonicalize_dataset_values({"evidence_legacy_issue": "X"}) == {
        "evidence_legacy_issue": "미등재",
    }
    assert clean_dataset_values(definition, {"evidence_legacy_issue": "심사대기"}) == {
        "evidence_legacy_issue": "심사대기",
    }


def test_ox_values_are_canonicalized_to_select_options() -> None:
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]

    assert canonicalize_dataset_values(
        {
            "applied": "●",
            LEGACY_ISSUE_EVIDENCE_FIELD_KEY: "○",
            "evidence_quality_spec": "X",
        }
    ) == {
        "applied": "O",
        LEGACY_ISSUE_EVIDENCE_FIELD_KEY: "O",
        "evidence_quality_spec": "X",
    }
    assert clean_dataset_values(
        definition,
        {
            "applied": "적용",
            LEGACY_ISSUE_EVIDENCE_FIELD_KEY: "미등재",
            "evidence_quality_spec": "",
        },
    ) == {
        "applied": "O",
        LEGACY_ISSUE_EVIDENCE_FIELD_KEY: "X",
    }


def test_stamp_introduced_revision_numbers_marks_only_new_revision_rows() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        revision = LegacyIssueDataRevision(
            id="revision-12",
            workspace_id=workspace.id,
            dataset_key="legacy-issues:common-master",
            revision_no=12,
            status="published",
            base_revision_id="revision-11",
        )
        existing_base = LegacyIssueRecord(
            id="record-base-1",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id="revision-11",
            stable_record_id="stable-existing",
            field_values={"region_zone": "북미", "symptom": "base"},
            raw_fields={},
        )
        existing_current = LegacyIssueRecord(
            id="record-current-1",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id="stable-existing",
            field_values={"region_zone": "북미", "symptom": "existing"},
            raw_fields={},
        )
        new_current = LegacyIssueRecord(
            id="record-current-2",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=revision.id,
            stable_record_id="stable-new",
            field_values={"region_zone": "유럽", "symptom": "new"},
            raw_fields={},
        )
        db.add_all([workspace, existing_base, existing_current, new_current])
        db.flush()

        stamped = stamp_introduced_revision_numbers(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            revision=revision,
        )

        assert stamped == 1
        assert existing_current.field_values == {
            "region_zone": "북미",
            "symptom": "existing",
        }
        assert new_current.field_values[INTRODUCED_REVISION_FIELD_KEY] == "12"
        assert new_current.introduced_revision_no == 12


def test_column_order_is_sanitized_and_persisted_per_view() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        db.add_all([workspace, user])
        db.flush()

        available_keys = [
            COLUMN_ORDER_ATTACHMENT_KEY,
            "row_no",
            INTRODUCED_REVISION_FIELD_KEY,
            "department",
            "registrant",
        ]

        assert sanitize_column_order(
            ["department", "unknown", "row_no", "department"],
            available_keys=available_keys,
        ) == [
            "department",
            "registrant",
            COLUMN_ORDER_ATTACHMENT_KEY,
            "row_no",
            INTRODUCED_REVISION_FIELD_KEY,
        ]
        assert sanitize_hidden_column_keys(
            ["registrant", "unknown", "registrant"],
            available_keys=available_keys,
        ) == ["registrant"]
        assert (
            sanitize_hidden_column_keys(
                available_keys,
                available_keys=available_keys,
            )
            == available_keys[1:]
        )

        saved = upsert_column_order(
            db,
            workspace=workspace,
            user=user,
            view_key=COMMON_MASTER_DATASET_KEY,
            column_order=["department", "row_no"],
            hidden_column_keys=["registrant", "unknown", "registrant"],
            available_keys=available_keys,
        )
        loaded = get_column_order(
            db,
            workspace=workspace,
            view_key=COMMON_MASTER_DATASET_KEY,
            available_keys=available_keys,
        )

        assert saved.column_order == loaded.column_order
        assert saved.hidden_column_keys == ["registrant"]
        assert loaded.hidden_column_keys == ["registrant"]
        assert loaded.column_order == [
            "department",
            "registrant",
            COLUMN_ORDER_ATTACHMENT_KEY,
            "row_no",
            INTRODUCED_REVISION_FIELD_KEY,
        ]

        order_only_update = upsert_column_order(
            db,
            workspace=workspace,
            user=user,
            view_key=COMMON_MASTER_DATASET_KEY,
            column_order=["row_no", "department"],
            available_keys=available_keys,
        )

        assert order_only_update.hidden_column_keys == ["registrant"]


def test_compare_dataset_revisions_includes_attachment_changes() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        left_revision = LegacyIssueDataRevision(
            id="revision-left",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            revision_no=1,
            status="published",
            created_by_id=user.id,
        )
        right_revision = LegacyIssueDataRevision(
            id="revision-right",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY),
            revision_no=2,
            status="published",
            created_by_id=user.id,
        )
        left_record = LegacyIssueRecord(
            id="record-left",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=left_revision.id,
            stable_record_id="stable-record-1",
            field_values={
                "legacy_issue_number": "PV-2026-001",
                "region_zone": "북미",
                "symptom": "noise",
            },
            raw_fields={},
        )
        right_record = LegacyIssueRecord(
            id="record-right",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=right_revision.id,
            stable_record_id="stable-record-1",
            field_values={
                "legacy_issue_number": "PV-2026-001",
                "region_zone": "북미",
                "symptom": "noise",
            },
            raw_fields={},
        )
        left_attachment = LegacyIssueAttachment(
            id="attachment-left",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=left_revision.id,
            stable_record_id=left_record.stable_record_id,
            record_id=left_record.id,
            filename="old-evidence.pdf",
            content_type="application/pdf",
            size_bytes=100,
            description="old file",
            storage_key="legacy-issues/test/old-evidence.pdf",
            is_primary=True,
            uploaded_by_id=user.id,
        )
        right_attachment = LegacyIssueAttachment(
            id="attachment-right",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            revision_id=right_revision.id,
            stable_record_id=right_record.stable_record_id,
            record_id=right_record.id,
            filename="new-evidence.pdf",
            content_type="application/pdf",
            size_bytes=200,
            description="new file",
            storage_key="legacy-issues/test/new-evidence.pdf",
            is_primary=True,
            uploaded_by_id=user.id,
        )
        db.add_all(
            [
                workspace,
                user,
                left_revision,
                right_revision,
                left_record,
                right_record,
                left_attachment,
                right_attachment,
            ]
        )
        db.flush()

        rows = compare_dataset_revisions(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            left_revision=left_revision,
            right_revision=right_revision,
        )

        row = next(item for item in rows if item.stable_record_id == "stable-record-1")
        attachment_cell = next(
            item for item in row.cells if item.field_key == COLUMN_ORDER_ATTACHMENT_KEY
        )

        assert row.status == "modified"
        assert attachment_cell.field_label == "첨부파일"
        assert attachment_cell.changed is True
        assert attachment_cell.left_value == "대표: old-evidence.pdf (100 bytes) - old file"
        assert attachment_cell.right_value == "대표: new-evidence.pdf (200 bytes) - new file"


def test_module_fields_extend_only_target_module_definition() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        db.add_all([workspace, user])
        db.flush()

        field = create_module_field(
            db,
            workspace=workspace,
            user=user,
            module_key="aircon",
            label_ko="시험결과",
            label_en="Test Result",
            field_type="select",
            options=["OK", "NG"],
            required=True,
        )

        base_definition = get_dataset_definition_for_view(
            db,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            workspace=workspace,
        )
        module_definition = get_dataset_definition_for_view(
            db,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            workspace=workspace,
            view_key="aircon",
        )
        all_fields_definition = get_dataset_definition_with_all_module_fields(
            db,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            workspace=workspace,
        )

        assert field.field_key not in {item.key for item in base_definition.fields}
        assert field.field_key in {item.key for item in module_definition.fields}
        assert field.field_key in {item.key for item in all_fields_definition.fields}

        base_field_keys = [item.key for item in base_definition.fields]
        assert base_field_keys[0] == INTRODUCED_REVISION_FIELD_KEY
        assert base_field_keys.count(INTRODUCED_REVISION_FIELD_KEY) == 1
        assert REFLECTED_REVISION_FIELD_KEY not in base_field_keys
        base_revision_field = base_definition.fields[0]
        assert base_revision_field.label_ko == "반영Rev"
        assert base_revision_field.label_en == "Reflected Rev."
        assert base_revision_field.readonly is False

        for module_key in LEGACY_ISSUE_MODULE_KEYS:
            current_definition = get_dataset_definition_for_view(
                db,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                workspace=workspace,
                view_key=module_key,
            )
            module_field_keys = [item.key for item in current_definition.fields]
            assert module_field_keys[0] == INTRODUCED_REVISION_FIELD_KEY
            assert module_field_keys.count(INTRODUCED_REVISION_FIELD_KEY) == 1
            assert REFLECTED_REVISION_FIELD_KEY not in module_field_keys
            reflected_revision_field = current_definition.fields[0]
            assert reflected_revision_field.label_ko == "반영Rev"
            assert reflected_revision_field.label_en == "Reflected Rev."
            assert reflected_revision_field.readonly is False

        all_field_keys = [item.key for item in all_fields_definition.fields]
        assert all_field_keys[0] == INTRODUCED_REVISION_FIELD_KEY
        assert REFLECTED_REVISION_FIELD_KEY not in all_field_keys

        clean_values = clean_dataset_values(
            module_definition,
            {
                "legacy_issue_number": "PV-2026-001",
                field.field_key: "OK",
            },
        )
        assert clean_values[field.field_key] == "OK"

        record = LegacyIssueRecord(
            id="record-1",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            field_values=clean_values,
            raw_fields={},
        )
        apply_record_projection(
            record,
            clean_values,
            value_labels=field_labels(module_definition),
        )

        assert record.search_text is not None
        assert "시험결과: OK" in record.search_text


def test_all_module_saved_column_orders_remove_original_reflected_revision() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = _test_user("user-1", "admin@example.com")
        db.add_all([workspace, user])
        for index, module_key in enumerate(sorted(LEGACY_ISSUE_MODULE_KEYS), start=1):
            db.add(
                LegacyIssueColumnOrder(
                    id=f"column-order-{index}",
                    workspace_id=workspace.id,
                    view_key=module_key,
                    column_order=[
                        INTRODUCED_REVISION_FIELD_KEY,
                        "department",
                        "registrant",
                        REFLECTED_REVISION_FIELD_KEY,
                    ],
                    updated_by_id=user.id,
                )
            )
        db.flush()

        for module_key in LEGACY_ISSUE_MODULE_KEYS:
            loaded = get_column_order(
                db,
                workspace=workspace,
                view_key=module_key,
                available_keys=[
                    INTRODUCED_REVISION_FIELD_KEY,
                    "department",
                    "registrant",
                ],
            )

            assert loaded.column_order == [
                INTRODUCED_REVISION_FIELD_KEY,
                "department",
                "registrant",
            ]


def test_batch_record_save_merges_update_cells_and_creates_rows(monkeypatch) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-draft",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            status="draft",
            locked_by_id=user.id,
            created_by_id=user.id,
            reviewer_id=user.id,
            approver_id=user.id,
            review_requested_by_id=user.id,
            review_requested_at=datetime(2026, 7, 6, 8, 0, 0),
            approval_requested_by_id=user.id,
            approval_requested_at=datetime(2026, 7, 6, 8, 0, 0),
            reviewed_by_id=user.id,
            reviewed_at=datetime(2026, 7, 6, 9, 0, 0),
            approved_by_id=user.id,
            approved_at=datetime(2026, 7, 6, 9, 0, 0),
            grid_layout={
                "version": 1,
                "column_order": ["cause", "symptom"],
                "column_widths": {"cause": 333},
                "hidden_column_keys": [],
            },
        )
        record = LegacyIssueRecord(
            id="record-current-1",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=revision.id,
            stable_record_id="stable-existing",
            field_values={"region_zone": "북미", "symptom": "old"},
            raw_fields={},
        )
        db.add_all([workspace, user, revision, record])
        db.flush()
        reindexed_record_ids: list[str] = []

        def fake_reindex(*args, **kwargs) -> None:
            reindexed_record_ids.append(kwargs["record"].id)

        monkeypatch.setattr(
            legacy_issue_router,
            "reindex_legacy_issue_record_ai_chunks",
            fake_reindex,
        )
        monkeypatch.setattr(
            legacy_issue_router,
            "list_dataset_attachments_for_records",
            lambda *args, **kwargs: {},
        )
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )

        response = legacy_issue_router.save_legacy_issue_dataset_records_batch(
            COMMON_MASTER_DATASET_KEY,
            LegacyIssueRecordBatchSaveRequest(
                updates=[
                    LegacyIssueRecordBatchUpdateItem(
                        record_id=record.id,
                        values={"symptom": "new"},
                    ),
                    LegacyIssueRecordBatchUpdateItem(
                        record_id=record.id,
                        values={"cause": "loose bracket"},
                    ),
                ],
                creates=[
                    LegacyIssueRecordBatchCreateItem(
                        client_row_id="pending-row-1",
                        values={"region_zone": "북미", "symptom": "created"},
                    )
                ],
            ),
            revision_id=revision.id,
            view_key="aircon",
            db=db,
            current_user=user,
            current_workspace=workspace,
        )

        db.refresh(record)

        assert response.updated == 1
        assert response.created == 1
        assert len(response.items) == 2
        assert len(response.created_records) == 1
        assert response.created_records[0].client_row_id == "pending-row-1"
        assert response.created_records[0].record.values["symptom"] == "created"
        assert record.field_values["symptom"] == "new"
        assert record.field_values["cause"] == "loose bracket"
        assert reindexed_record_ids.count(record.id) == 1
        db.refresh(revision)
        assert revision.grid_layout == {
            "version": 1,
            "column_order": ["cause", "symptom"],
            "column_widths": {"cause": 333},
            "hidden_column_keys": [],
        }
        assert revision.locked_by_id == user.id
        assert revision.review_requested_at is None
        assert revision.approval_requested_at is None
        assert revision.reviewed_at is None
        assert revision.approved_at is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(LegacyIssueDataRevisionEvent)
                .where(
                    LegacyIssueDataRevisionEvent.revision_id == revision.id,
                    LegacyIssueDataRevisionEvent.action == "approval_reset",
                )
            )
            == 1
        )

        released = legacy_issue_router.save_legacy_issue_dataset_records_batch(
            COMMON_MASTER_DATASET_KEY,
            LegacyIssueRecordBatchSaveRequest(
                release_editing=True,
                updates=[
                    LegacyIssueRecordBatchUpdateItem(
                        record_id=record.id,
                        values={"cause": "secured bracket"},
                    )
                ],
            ),
            revision_id=revision.id,
            view_key="aircon",
            db=db,
            current_user=user,
            current_workspace=workspace,
        )

        db.refresh(revision)
        assert released.created == 0
        assert released.updated == 1
        assert revision.locked_by_id is None


def test_batch_record_save_allows_direct_admin_create_on_published_revision(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        admin = User(
            id="user-1",
            login_id="admin",
            email="admin@example.com",
            full_name="Admin",
            password_hash="hash",
        )
        revision = LegacyIssueDataRevision(
            id="revision-published",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            revision_no=3,
            status="published",
        )
        db.add_all([workspace, admin, revision])
        db.flush()

        monkeypatch.setattr(
            legacy_issue_router,
            "reindex_legacy_issue_record_ai_chunks",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            legacy_issue_router,
            "list_dataset_attachments_for_records",
            lambda *args, **kwargs: {},
        )
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: True,
        )

        response = legacy_issue_router.save_legacy_issue_dataset_records_batch(
            COMMON_MASTER_DATASET_KEY,
            LegacyIssueRecordBatchSaveRequest(
                creates=[
                    LegacyIssueRecordBatchCreateItem(
                        client_row_id="pending-row-1",
                        values={"symptom": "created directly"},
                    )
                ],
            ),
            revision_id=revision.id,
            view_key="aircon",
            db=db,
            current_user=admin,
            current_workspace=workspace,
        )

        assert response.created == 1
        assert response.updated == 0
        assert len(response.created_records) == 1
        created = response.created_records[0].record
        assert created.values["symptom"] == "created directly"
        assert created.values[INTRODUCED_REVISION_FIELD_KEY] == "3"
        persisted = db.scalar(select(LegacyIssueRecord).where(LegacyIssueRecord.id == created.id))
        assert persisted is not None
        assert persisted.introduced_revision_no == 3


def test_delete_record_allows_direct_editor_on_published_revision(
    monkeypatch,
) -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        direct_editor = _test_user("direct-editor", "direct@example.com")
        binding = _binding(workspace, direct_editor)
        binding.created_at = datetime(2026, 7, 23, 9, 0)
        access_rule = LegacyIssueModuleAccessRule(
            id="access-aircon-direct-editor",
            workspace_id=workspace.id,
            module_key="aircon",
            subject_type="user",
            subject_id=direct_editor.id,
            role="editor",
            active=True,
            created_at=datetime(2026, 7, 23, 9, 1),
            updated_at=datetime(2026, 7, 23, 9, 1),
        )
        revision = LegacyIssueDataRevision(
            id="revision-published",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                "aircon",
            ),
            revision_no=3,
            status="published",
        )
        record = LegacyIssueRecord(
            id="record-published",
            workspace_id=workspace.id,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id=revision.id,
            stable_record_id="stable-published",
            field_values={"symptom": "delete directly"},
            raw_fields={},
        )
        db.add_all([workspace, direct_editor, binding, access_rule, revision, record])
        db.flush()
        monkeypatch.setattr(
            legacy_issue_router,
            "delete_legacy_issue_record_ai_chunks",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.revisioning.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )
        monkeypatch.setattr(
            "open_alm_api.domains.legacy_issues.module_direct_editors.is_platform_admin_user",
            lambda *args, **kwargs: False,
        )

        response = legacy_issue_router.delete_legacy_issue_dataset_record(
            COMMON_MASTER_DATASET_KEY,
            record.id,
            revision_id=revision.id,
            view_key="aircon",
            db=db,
            current_user=direct_editor,
            current_workspace=workspace,
        )

        assert response.status_code == 204
        assert db.get(LegacyIssueRecord, record.id) is None
