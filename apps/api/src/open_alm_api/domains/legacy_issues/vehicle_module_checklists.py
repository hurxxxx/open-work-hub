from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

from fastapi import status
from sqlalchemy import Text, cast, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.models import User, Workspace, utcnow_naive
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    MASTER_STATUS_FIELD_KEY,
    LegacyIssueDatasetDefinition,
    canonicalize_dataset_values,
    display_dataset_value,
    field_labels,
    get_dataset_definition_for_view,
    list_dataset_records,
    merge_dataset_values,
    normalize_legacy_issue_module_key,
)
from open_alm_api.domains.legacy_issues.history import (
    LegacyIssueHistoryChange,
    add_record_history_entries,
    collect_value_changes,
    list_record_history,
)
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueRecordHistory,
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleModuleChecklistRecord,
    LegacyIssueVehicleStage,
)
from open_alm_api.domains.legacy_issues.revisioning import (
    REVISION_STATUS_PUBLISHED,
    ensure_initial_published_revision,
    get_latest_published_revision,
    get_revision,
    legacy_issue_dataset_revision_key,
)
from open_alm_api.domains.legacy_issues.vehicle_checklists import (
    VEHICLE_CHECKLIST_CHECK_FIELD_KEYS,
    VEHICLE_CHECKLIST_STATUS_COMPLETED,
    VEHICLE_CHECKLIST_STATUS_DRAFT,
    dataset_definition_from_snapshot,
    dataset_definition_snapshot,
    get_vehicle_model,
    get_vehicle_stage,
)
from open_alm_api.domains.legacy_issues.vehicle_module_checklist_attachments import (
    VehicleModuleChecklistAttachmentCleanupRef,
    delete_vehicle_module_checklist_attachment_rows,
)


# LegacyIssueRecordHistory.record_kind is varchar(32), so keep the new kind
# distinct from the aggregate checklist kind while staying within that contract.
VEHICLE_MODULE_CHECKLIST_RECORD_KIND = "legacy_issue_module_checklist"
VEHICLE_MODULE_CHECKLIST_INCLUDED_MASTER_STATUS = "등재"


@dataclass(frozen=True)
class VehicleModuleChecklistSummary:
    module_key: str
    latest_master_revision: LegacyIssueDataRevision | None
    latest_checklist: LegacyIssueVehicleModuleChecklist | None
    checklist_count: int


@dataclass(frozen=True)
class VehicleModuleChecklistHistoryRecordContext:
    record_id: str
    record_label: str | None
    source_module_key: str
    source_master_revision_no: int | None


@dataclass(frozen=True)
class VehicleModuleChecklistHistory:
    checklist: LegacyIssueVehicleModuleChecklist
    items: list[LegacyIssueRecordHistory]
    record_contexts: dict[str, VehicleModuleChecklistHistoryRecordContext]


@dataclass(frozen=True)
class VehicleModuleChecklistImportCandidate:
    checklist: LegacyIssueVehicleModuleChecklist
    stage: LegacyIssueVehicleStage
    completed_by_name: str | None
    completed_by_email: str | None


def list_vehicle_module_summaries(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
    stage_id: str | None = None,
    module_keys: frozenset[str],
) -> list[VehicleModuleChecklistSummary]:
    vehicle_stage = get_vehicle_stage(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model_id,
        stage_id=stage_id,
    )
    summaries: list[VehicleModuleChecklistSummary] = []
    for module_key in sorted(module_keys):
        latest_master_revision = get_latest_published_revision(
            db,
            workspace=workspace,
            dataset_key=_module_revision_dataset_key(module_key),
        )
        checklist_statement = select(LegacyIssueVehicleModuleChecklist).where(
            LegacyIssueVehicleModuleChecklist.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklist.vehicle_model_id == vehicle_model_id,
            LegacyIssueVehicleModuleChecklist.vehicle_stage_id == vehicle_stage.id,
            LegacyIssueVehicleModuleChecklist.module_key == module_key,
        )
        latest_checklist = db.scalar(
            checklist_statement.order_by(
                LegacyIssueVehicleModuleChecklist.source_master_revision_no.desc().nullslast(),
                LegacyIssueVehicleModuleChecklist.created_at.desc(),
            )
        )
        checklist_count = int(
            db.scalar(select(func.count()).select_from(checklist_statement.subquery())) or 0
        )
        summaries.append(
            VehicleModuleChecklistSummary(
                module_key=module_key,
                latest_master_revision=latest_master_revision,
                latest_checklist=latest_checklist,
                checklist_count=checklist_count,
            )
        )
    return summaries


def list_published_module_master_revisions(
    db: Session,
    *,
    workspace: Workspace,
    module_key: str,
    module_keys: frozenset[str] | None = None,
) -> list[LegacyIssueDataRevision]:
    normalized_module_key = _normalize_enabled_module_key(module_key, module_keys=module_keys)
    return list(
        db.scalars(
            select(LegacyIssueDataRevision)
            .where(
                LegacyIssueDataRevision.workspace_id == workspace.id,
                LegacyIssueDataRevision.dataset_key
                == _module_revision_dataset_key(normalized_module_key),
                LegacyIssueDataRevision.status == REVISION_STATUS_PUBLISHED,
            )
            .order_by(
                LegacyIssueDataRevision.revision_no.desc().nullslast(),
                LegacyIssueDataRevision.created_at.desc(),
            )
        )
    )


def list_vehicle_module_checklists(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
    stage_id: str | None = None,
    module_key: str,
    module_keys: frozenset[str] | None = None,
) -> list[LegacyIssueVehicleModuleChecklist]:
    vehicle_stage = get_vehicle_stage(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model_id,
        stage_id=stage_id,
    )
    normalized_module_key = _normalize_enabled_module_key(module_key, module_keys=module_keys)
    return list(
        db.scalars(
            select(LegacyIssueVehicleModuleChecklist)
            .where(
                LegacyIssueVehicleModuleChecklist.workspace_id == workspace.id,
                LegacyIssueVehicleModuleChecklist.vehicle_model_id == vehicle_model_id,
                LegacyIssueVehicleModuleChecklist.vehicle_stage_id == vehicle_stage.id,
                LegacyIssueVehicleModuleChecklist.module_key == normalized_module_key,
            )
            .order_by(
                LegacyIssueVehicleModuleChecklist.source_master_revision_no.desc().nullslast(),
                LegacyIssueVehicleModuleChecklist.created_at.desc(),
            )
        )
    )


def create_vehicle_module_checklist(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    vehicle_model_id: str,
    stage_id: str | None = None,
    module_key: str,
    source_master_revision_id: str | None = None,
    module_keys: frozenset[str] | None = None,
) -> LegacyIssueVehicleModuleChecklist:
    vehicle_model = get_vehicle_model(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model_id,
    )
    if not vehicle_model.active:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_model_invalid",
        )
    vehicle_stage = get_vehicle_stage(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model.id,
        stage_id=stage_id,
    )
    normalized_module_key = _normalize_enabled_module_key(module_key, module_keys=module_keys)
    source_revision = _resolve_module_source_revision(
        db,
        workspace=workspace,
        module_key=normalized_module_key,
        source_master_revision_id=source_master_revision_id,
    )
    existing = _find_vehicle_module_checklist(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model.id,
        stage_id=vehicle_stage.id,
        module_key=normalized_module_key,
        source_master_revision_id=source_revision.id,
    )
    if existing is not None:
        return existing

    definition = get_dataset_definition_for_view(
        db,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        workspace=workspace,
        view_key=normalized_module_key,
    )
    source_rows, _total = list_dataset_records(
        db,
        definition,
        workspace=workspace,
        revision=source_revision,
        module_key=normalized_module_key,
        limit=None,
    )
    source_rows = [
        source_row
        for source_row in source_rows
        if canonicalize_dataset_values(source_row.field_values or {}).get(MASTER_STATUS_FIELD_KEY)
        == VEHICLE_MODULE_CHECKLIST_INCLUDED_MASTER_STATUS
    ]
    snapshot = dataset_definition_snapshot(definition)
    snapshot["module_key"] = normalized_module_key
    snapshot["source_master_revision_id"] = source_revision.id
    now = utcnow_naive()
    checklist = LegacyIssueVehicleModuleChecklist(
        id=new_id(),
        workspace_id=workspace.id,
        vehicle_model_id=vehicle_model.id,
        vehicle_stage_id=vehicle_stage.id,
        module_key=normalized_module_key,
        status=VEHICLE_CHECKLIST_STATUS_DRAFT,
        source_dataset_key=COMMON_MASTER_DATASET_KEY,
        source_master_revision_id=source_revision.id,
        source_master_revision_no=source_revision.revision_no,
        definition_snapshot=snapshot,
        row_count=len(source_rows),
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(checklist)
            db.flush()
    except IntegrityError:
        existing = _find_vehicle_module_checklist(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle_model.id,
            stage_id=vehicle_stage.id,
            module_key=normalized_module_key,
            source_master_revision_id=source_revision.id,
        )
        if existing is not None:
            return existing
        raise

    for sort_order, source_row in enumerate(source_rows, start=1):
        db.add(
            LegacyIssueVehicleModuleChecklistRecord(
                id=new_id(),
                workspace_id=workspace.id,
                checklist_id=checklist.id,
                source_record_id=source_row.id,
                source_stable_record_id=source_row.stable_record_id,
                sort_order=sort_order,
                field_values=_initial_checklist_values(source_row.field_values or {}),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    return checklist


def list_prior_stage_completed_vehicle_module_checklists(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
    stage_id: str | None,
    module_key: str,
    module_keys: frozenset[str] | None = None,
) -> list[VehicleModuleChecklistImportCandidate]:
    stage = get_vehicle_stage(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model_id,
        stage_id=stage_id,
    )
    normalized_module_key = _normalize_enabled_module_key(
        module_key,
        module_keys=module_keys,
    )
    rows = db.execute(
        select(LegacyIssueVehicleModuleChecklist, LegacyIssueVehicleStage)
        .join(
            LegacyIssueVehicleStage,
            LegacyIssueVehicleStage.id
            == LegacyIssueVehicleModuleChecklist.vehicle_stage_id,
        )
        .where(
            LegacyIssueVehicleModuleChecklist.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklist.vehicle_model_id == vehicle_model_id,
            LegacyIssueVehicleModuleChecklist.module_key == normalized_module_key,
            LegacyIssueVehicleModuleChecklist.status
            == VEHICLE_CHECKLIST_STATUS_COMPLETED,
            LegacyIssueVehicleStage.workspace_id == workspace.id,
            LegacyIssueVehicleStage.vehicle_model_id == vehicle_model_id,
            LegacyIssueVehicleStage.sequence_no < stage.sequence_no,
        )
        .order_by(
            LegacyIssueVehicleStage.sequence_no.desc(),
            LegacyIssueVehicleModuleChecklist.completed_at.desc().nullslast(),
            LegacyIssueVehicleModuleChecklist.source_master_revision_no.desc().nullslast(),
            LegacyIssueVehicleModuleChecklist.updated_at.desc(),
            LegacyIssueVehicleModuleChecklist.created_at.desc(),
        )
    ).all()
    completed_by_ids = {
        checklist.completed_by_id
        for checklist, _candidate_stage in rows
        if checklist.completed_by_id is not None
    }
    completed_by_users = (
        {
            user.id: user
            for user in db.scalars(select(User).where(User.id.in_(completed_by_ids)))
        }
        if completed_by_ids
        else {}
    )
    candidates: list[VehicleModuleChecklistImportCandidate] = []
    for checklist, candidate_stage in rows:
        completed_by = completed_by_users.get(checklist.completed_by_id)
        candidates.append(
            VehicleModuleChecklistImportCandidate(
                checklist=checklist,
                stage=candidate_stage,
                completed_by_name=(
                    completed_by.display_name or completed_by.full_name
                    if completed_by is not None
                    else None
                ),
                completed_by_email=(
                    completed_by.email if completed_by is not None else None
                ),
            )
        )
    return candidates


def import_previous_stage_vehicle_module_checklist(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    vehicle_model_id: str,
    stage_id: str,
    module_key: str,
    source_checklist_id: str,
    module_keys: frozenset[str] | None = None,
) -> LegacyIssueVehicleModuleChecklist:
    vehicle_model = get_vehicle_model(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model_id,
        for_update=True,
    )
    if not vehicle_model.active:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_model_invalid",
        )
    stage = get_vehicle_stage(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model.id,
        stage_id=stage_id,
    )
    normalized_module_key = _normalize_enabled_module_key(
        module_key,
        module_keys=module_keys,
    )
    existing = db.scalar(
        select(LegacyIssueVehicleModuleChecklist.id).where(
            LegacyIssueVehicleModuleChecklist.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklist.vehicle_model_id == vehicle_model.id,
            LegacyIssueVehicleModuleChecklist.vehicle_stage_id == stage.id,
            LegacyIssueVehicleModuleChecklist.module_key == normalized_module_key,
        )
    )
    if existing is not None:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_module_checklist_stage_not_empty",
        )
    source = db.scalar(
        select(LegacyIssueVehicleModuleChecklist)
        .join(
            LegacyIssueVehicleStage,
            LegacyIssueVehicleStage.id
            == LegacyIssueVehicleModuleChecklist.vehicle_stage_id,
        )
        .where(
            LegacyIssueVehicleModuleChecklist.id == source_checklist_id,
            LegacyIssueVehicleModuleChecklist.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklist.vehicle_model_id == vehicle_model.id,
            LegacyIssueVehicleModuleChecklist.module_key == normalized_module_key,
            LegacyIssueVehicleModuleChecklist.status
            == VEHICLE_CHECKLIST_STATUS_COMPLETED,
            LegacyIssueVehicleStage.workspace_id == workspace.id,
            LegacyIssueVehicleStage.vehicle_model_id == vehicle_model.id,
            LegacyIssueVehicleStage.sequence_no < stage.sequence_no,
        )
        .with_for_update(of=LegacyIssueVehicleModuleChecklist)
    )
    if source is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.vehicle_module_checklist_previous_completed_not_found",
        )

    now = utcnow_naive()
    cloned = LegacyIssueVehicleModuleChecklist(
        id=new_id(),
        workspace_id=workspace.id,
        vehicle_model_id=vehicle_model.id,
        vehicle_stage_id=stage.id,
        module_key=source.module_key,
        status=VEHICLE_CHECKLIST_STATUS_DRAFT,
        source_dataset_key=source.source_dataset_key,
        source_master_revision_id=source.source_master_revision_id,
        source_master_revision_no=source.source_master_revision_no,
        definition_snapshot=deepcopy(source.definition_snapshot),
        grid_layout=deepcopy(source.grid_layout),
        row_count=source.row_count,
        created_by_id=user.id,
        completed_by_id=None,
        completed_at=None,
        seeded_from_checklist_id=source.id,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(cloned)
            db.flush()
    except IntegrityError as error:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_module_checklist_stage_not_empty",
        ) from error
    source_rows = list(
        db.scalars(
            select(LegacyIssueVehicleModuleChecklistRecord)
            .where(
                LegacyIssueVehicleModuleChecklistRecord.workspace_id == workspace.id,
                LegacyIssueVehicleModuleChecklistRecord.checklist_id == source.id,
            )
            .order_by(
                LegacyIssueVehicleModuleChecklistRecord.sort_order.asc(),
                LegacyIssueVehicleModuleChecklistRecord.created_at.asc(),
            )
        )
    )
    for source_row in source_rows:
        db.add(
            LegacyIssueVehicleModuleChecklistRecord(
                id=new_id(),
                workspace_id=workspace.id,
                checklist_id=cloned.id,
                source_record_id=source_row.source_record_id,
                source_stable_record_id=source_row.source_stable_record_id,
                sort_order=source_row.sort_order,
                field_values=deepcopy(source_row.field_values),
                updated_by_id=None,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    return cloned


def get_vehicle_module_checklist(
    db: Session,
    *,
    workspace: Workspace,
    checklist_id: str,
    module_keys: frozenset[str] | None = None,
    for_update: bool = False,
) -> LegacyIssueVehicleModuleChecklist:
    statement = select(LegacyIssueVehicleModuleChecklist).where(
        LegacyIssueVehicleModuleChecklist.id == checklist_id,
        LegacyIssueVehicleModuleChecklist.workspace_id == workspace.id,
    )
    if for_update:
        statement = statement.with_for_update()
    checklist = db.scalar(statement)
    if checklist is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.vehicle_module_checklist_not_found",
        )
    _normalize_enabled_module_key(checklist.module_key, module_keys=module_keys)
    return checklist


def list_vehicle_module_checklist_records(
    db: Session,
    *,
    workspace: Workspace,
    checklist_id: str,
    query: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    module_keys: frozenset[str] | None = None,
) -> tuple[
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueDatasetDefinition,
    list[LegacyIssueVehicleModuleChecklistRecord],
    int,
]:
    checklist = get_vehicle_module_checklist(
        db,
        workspace=workspace,
        checklist_id=checklist_id,
        module_keys=module_keys,
    )
    definition = _definition_from_snapshot(checklist.definition_snapshot)
    statement = select(LegacyIssueVehicleModuleChecklistRecord).where(
        LegacyIssueVehicleModuleChecklistRecord.workspace_id == workspace.id,
        LegacyIssueVehicleModuleChecklistRecord.checklist_id == checklist.id,
    )
    normalized_query = (query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                cast(LegacyIssueVehicleModuleChecklistRecord.field_values, Text).ilike(pattern),
                LegacyIssueVehicleModuleChecklistRecord.source_record_id.ilike(pattern),
                LegacyIssueVehicleModuleChecklistRecord.source_stable_record_id.ilike(pattern),
            )
        )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows_statement = statement.order_by(
        LegacyIssueVehicleModuleChecklistRecord.sort_order.asc(),
        LegacyIssueVehicleModuleChecklistRecord.created_at.asc(),
    ).offset(max(offset, 0))
    if limit is not None:
        rows_statement = rows_statement.limit(max(limit, 1))
    return checklist, definition, list(db.scalars(rows_statement)), total


def update_vehicle_module_checklist_records(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    checklist_id: str,
    updates: dict[str, dict[str, Any | None]],
    module_keys: frozenset[str] | None = None,
) -> list[LegacyIssueVehicleModuleChecklistRecord]:
    checklist = get_vehicle_module_checklist(
        db,
        workspace=workspace,
        checklist_id=checklist_id,
        module_keys=module_keys,
        for_update=True,
    )
    if checklist.status != VEHICLE_CHECKLIST_STATUS_DRAFT:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_module_checklist_completed",
        )
    definition = _definition_from_snapshot(checklist.definition_snapshot)
    labels = field_labels(definition)
    changed_rows: list[LegacyIssueVehicleModuleChecklistRecord] = []
    for record_id, values in updates.items():
        clean_update = _validate_checklist_update_values(values)
        if not clean_update:
            continue
        record = _get_vehicle_module_checklist_record(
            db,
            workspace=workspace,
            checklist=checklist,
            record_id=record_id,
        )
        old_values = canonicalize_dataset_values(record.field_values)
        next_values, changed_values = merge_dataset_values(
            definition,
            db=db,
            workspace=workspace,
            current_values=old_values,
            incoming_values=clean_update,
        )
        if not changed_values:
            continue
        now = utcnow_naive()
        record.field_values = next_values
        record.updated_by_id = user.id
        record.updated_at = now
        checklist.updated_at = now
        db.add_all([record, checklist])
        changed_rows.append(record)
        add_record_history_entries(
            db,
            workspace=workspace,
            user=user,
            record_kind=VEHICLE_MODULE_CHECKLIST_RECORD_KIND,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            record_id=record.id,
            action="update",
            changes=collect_value_changes(
                old_values=old_values,
                new_values=changed_values,
                field_labels=labels,
            ),
            details=_history_details(checklist),
        )
    if changed_rows or db.is_modified(checklist):
        db.flush()
    if changed_rows:
        for record in changed_rows:
            db.refresh(record)
    return changed_rows


def complete_vehicle_module_checklist(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    checklist_id: str,
    module_keys: frozenset[str] | None = None,
) -> LegacyIssueVehicleModuleChecklist:
    checklist = get_vehicle_module_checklist(
        db,
        workspace=workspace,
        checklist_id=checklist_id,
        module_keys=module_keys,
        for_update=True,
    )
    if checklist.status == VEHICLE_CHECKLIST_STATUS_COMPLETED:
        return checklist
    old_status = checklist.status
    now = utcnow_naive()
    checklist.status = VEHICLE_CHECKLIST_STATUS_COMPLETED
    checklist.completed_by_id = user.id
    checklist.completed_at = now
    checklist.updated_at = now
    db.add(checklist)
    _add_status_history(
        db,
        workspace=workspace,
        user=user,
        checklist=checklist,
        action="complete",
        old_status=old_status,
        new_status=VEHICLE_CHECKLIST_STATUS_COMPLETED,
    )
    db.flush()
    return checklist


def reopen_vehicle_module_checklist(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    checklist_id: str,
    module_keys: frozenset[str] | None = None,
) -> LegacyIssueVehicleModuleChecklist:
    checklist = get_vehicle_module_checklist(
        db,
        workspace=workspace,
        checklist_id=checklist_id,
        module_keys=module_keys,
        for_update=True,
    )
    if checklist.status == VEHICLE_CHECKLIST_STATUS_DRAFT:
        return checklist
    old_status = checklist.status
    now = utcnow_naive()
    checklist.status = VEHICLE_CHECKLIST_STATUS_DRAFT
    checklist.completed_by_id = None
    checklist.completed_at = None
    checklist.updated_at = now
    db.add(checklist)
    _add_status_history(
        db,
        workspace=workspace,
        user=user,
        checklist=checklist,
        action="reopen",
        old_status=old_status,
        new_status=VEHICLE_CHECKLIST_STATUS_DRAFT,
    )
    db.flush()
    return checklist


def list_vehicle_module_checklist_history(
    db: Session,
    *,
    workspace: Workspace,
    checklist_id: str,
    module_keys: frozenset[str] | None = None,
) -> VehicleModuleChecklistHistory:
    checklist = get_vehicle_module_checklist(
        db,
        workspace=workspace,
        checklist_id=checklist_id,
        module_keys=module_keys,
    )
    records = list(
        db.scalars(
            select(LegacyIssueVehicleModuleChecklistRecord)
            .where(
                LegacyIssueVehicleModuleChecklistRecord.workspace_id == workspace.id,
                LegacyIssueVehicleModuleChecklistRecord.checklist_id == checklist.id,
            )
            .order_by(
                LegacyIssueVehicleModuleChecklistRecord.sort_order.asc(),
                LegacyIssueVehicleModuleChecklistRecord.created_at.asc(),
            )
        )
    )
    record_contexts = {
        checklist.id: VehicleModuleChecklistHistoryRecordContext(
            record_id=checklist.id,
            record_label=f"Master Rev. {checklist.source_master_revision_no or '-'}",
            source_module_key=checklist.module_key,
            source_master_revision_no=checklist.source_master_revision_no,
        )
    }
    for record in records:
        record_contexts[record.id] = VehicleModuleChecklistHistoryRecordContext(
            record_id=record.id,
            record_label=_record_label(record),
            source_module_key=checklist.module_key,
            source_master_revision_no=checklist.source_master_revision_no,
        )
    history_rows = list_record_history(
        db,
        workspace=workspace,
        record_kind=VEHICLE_MODULE_CHECKLIST_RECORD_KIND,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        record_ids=record_contexts.keys(),
    )
    return VehicleModuleChecklistHistory(
        checklist=checklist,
        items=history_rows,
        record_contexts=record_contexts,
    )


def delete_vehicle_module_checklist(
    db: Session,
    *,
    workspace: Workspace,
    checklist_id: str,
    module_keys: frozenset[str] | None = None,
) -> list[VehicleModuleChecklistAttachmentCleanupRef]:
    checklist = get_vehicle_module_checklist(
        db,
        workspace=workspace,
        checklist_id=checklist_id,
        module_keys=module_keys,
        for_update=True,
    )
    checklist_record_ids = select(LegacyIssueVehicleModuleChecklistRecord.id).where(
        LegacyIssueVehicleModuleChecklistRecord.workspace_id == workspace.id,
        LegacyIssueVehicleModuleChecklistRecord.checklist_id == checklist.id,
    )
    attachment_cleanups = delete_vehicle_module_checklist_attachment_rows(
        db,
        workspace=workspace,
        checklist=checklist,
    )
    db.execute(
        delete(LegacyIssueRecordHistory).where(
            LegacyIssueRecordHistory.workspace_id == workspace.id,
            LegacyIssueRecordHistory.record_kind == VEHICLE_MODULE_CHECKLIST_RECORD_KIND,
            or_(
                LegacyIssueRecordHistory.record_id == checklist.id,
                LegacyIssueRecordHistory.record_id.in_(checklist_record_ids),
            ),
        )
    )
    db.execute(
        delete(LegacyIssueVehicleModuleChecklistRecord).where(
            LegacyIssueVehicleModuleChecklistRecord.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklistRecord.checklist_id == checklist.id,
        )
    )
    db.execute(
        delete(LegacyIssueVehicleModuleChecklist).where(
            LegacyIssueVehicleModuleChecklist.id == checklist.id,
            LegacyIssueVehicleModuleChecklist.workspace_id == workspace.id,
        )
    )
    db.flush()
    return attachment_cleanups


def _module_revision_dataset_key(module_key: str) -> str:
    return legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY, module_key)


def _normalize_enabled_module_key(
    module_key: str,
    *,
    module_keys: frozenset[str] | None,
) -> str:
    normalized = normalize_legacy_issue_module_key(module_key)
    if normalized is None or (module_keys is not None and normalized not in module_keys):
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.module_not_found",
        )
    return normalized


def _resolve_module_source_revision(
    db: Session,
    *,
    workspace: Workspace,
    module_key: str,
    source_master_revision_id: str | None,
) -> LegacyIssueDataRevision:
    dataset_key = _module_revision_dataset_key(module_key)
    if source_master_revision_id is None:
        revision = get_latest_published_revision(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
        )
        if revision is not None:
            return revision
        return ensure_initial_published_revision(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
        )
    revision = get_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_id=source_master_revision_id,
    )
    if revision.status != REVISION_STATUS_PUBLISHED:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_module_checklist_revision_invalid",
        )
    return revision


def _find_vehicle_module_checklist(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
    stage_id: str,
    module_key: str,
    source_master_revision_id: str,
) -> LegacyIssueVehicleModuleChecklist | None:
    return db.scalar(
        select(LegacyIssueVehicleModuleChecklist).where(
            LegacyIssueVehicleModuleChecklist.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklist.vehicle_model_id == vehicle_model_id,
            LegacyIssueVehicleModuleChecklist.vehicle_stage_id == stage_id,
            LegacyIssueVehicleModuleChecklist.module_key == module_key,
            LegacyIssueVehicleModuleChecklist.source_master_revision_id
            == source_master_revision_id,
        )
    )


def _definition_from_snapshot(snapshot: dict[str, Any]) -> LegacyIssueDatasetDefinition:
    return replace(
        dataset_definition_from_snapshot(snapshot, view_key=str(snapshot.get("module_key") or "")),
        table_model=LegacyIssueVehicleModuleChecklistRecord,
    )


def _initial_checklist_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in canonicalize_dataset_values(values).items()
        if display_dataset_value(value)
    }


def _validate_checklist_update_values(
    values: dict[str, Any | None],
) -> dict[str, Any | None]:
    invalid_keys = set(values) - VEHICLE_CHECKLIST_CHECK_FIELD_KEYS
    if invalid_keys:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_module_checklist_field_invalid",
            detail=", ".join(sorted(invalid_keys)),
        )
    return {
        key: value for key, value in values.items() if key in VEHICLE_CHECKLIST_CHECK_FIELD_KEYS
    }


def _get_vehicle_module_checklist_record(
    db: Session,
    *,
    workspace: Workspace,
    checklist: LegacyIssueVehicleModuleChecklist,
    record_id: str,
) -> LegacyIssueVehicleModuleChecklistRecord:
    record = db.scalar(
        select(LegacyIssueVehicleModuleChecklistRecord).where(
            LegacyIssueVehicleModuleChecklistRecord.id == record_id,
            LegacyIssueVehicleModuleChecklistRecord.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklistRecord.checklist_id == checklist.id,
        )
    )
    if record is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.dataset_record_not_found",
        )
    return record


def _add_status_history(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    checklist: LegacyIssueVehicleModuleChecklist,
    action: str,
    old_status: str,
    new_status: str,
) -> None:
    add_record_history_entries(
        db,
        workspace=workspace,
        user=user,
        record_kind=VEHICLE_MODULE_CHECKLIST_RECORD_KIND,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        record_id=checklist.id,
        action=action,
        changes=[
            LegacyIssueHistoryChange(
                field_key="status",
                field_label="status",
                old_value=old_status,
                new_value=new_status,
            )
        ],
        details=_history_details(checklist),
    )


def _history_details(checklist: LegacyIssueVehicleModuleChecklist) -> dict[str, Any]:
    return {
        "vehicle_module_checklist_id": checklist.id,
        "vehicle_model_id": checklist.vehicle_model_id,
        "vehicle_stage_id": checklist.vehicle_stage_id,
        "module_key": checklist.module_key,
        "source_master_revision_id": checklist.source_master_revision_id,
        "source_master_revision_no": checklist.source_master_revision_no,
    }


def _record_label(record: LegacyIssueVehicleModuleChecklistRecord) -> str:
    values = canonicalize_dataset_values(record.field_values)
    primary = display_dataset_value(values.get("legacy_issue_number"))
    secondary = (
        display_dataset_value(values.get("symptom"))
        or display_dataset_value(values.get("problem"))
        or display_dataset_value(values.get("cause"))
        or display_dataset_value(values.get("countermeasure"))
    )
    if primary and secondary:
        return f"{primary} · {secondary}"
    return primary or secondary or record.source_stable_record_id or record.source_record_id
