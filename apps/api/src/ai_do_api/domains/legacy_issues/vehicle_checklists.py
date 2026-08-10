from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from fastapi import status
from sqlalchemy import Text, cast, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User, Workspace, utcnow_naive
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    LEGACY_ISSUE_MODULE_KEYS,
    DatasetFieldDefinition,
    LegacyIssueDatasetDefinition,
    canonicalize_dataset_values,
    display_dataset_value,
    field_labels,
    get_dataset_definition_with_all_module_fields,
    list_dataset_records,
    merge_dataset_values,
    normalize_legacy_issue_module_key,
)
from ai_do_api.domains.legacy_issues.history import (
    LegacyIssueHistoryChange,
    add_record_history_entries,
    collect_value_changes,
    list_record_history,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueRecordHistory,
    LegacyIssueVehicleChecklistRecord,
    LegacyIssueVehicleChecklistRevision,
    LegacyIssueVehicleModel,
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleStage,
)
from ai_do_api.domains.legacy_issues.revisioning import (
    REVISION_STATUS_PUBLISHED,
    ensure_initial_published_revision,
    get_latest_published_revision,
    get_revision,
    legacy_issue_dataset_revision_key,
)
from ai_do_api.domains.legacy_issues.partitioning import ensure_revision_partition


VEHICLE_CHECKLIST_STATUS_DRAFT = "draft"
VEHICLE_CHECKLIST_STATUS_COMPLETED = "completed"
VEHICLE_CHECKLIST_CHECK_FIELD_KEYS = frozenset({"check_plan", "applied", "reflection_result"})
VEHICLE_CHECKLIST_RECORD_KIND = "legacy_issue_vehicle_checklist"
VEHICLE_MODEL_RECORD_KIND = "legacy_issue_vehicle_model"
DEFAULT_INITIAL_VEHICLE_STAGE_NAME = "기본"


@dataclass
class VehicleChecklistSummary:
    latest_draft: "VehicleChecklistSummaryEntry | None" = None
    latest_completed: "VehicleChecklistSummaryEntry | None" = None


@dataclass(frozen=True)
class VehicleChecklistSummaryEntry:
    revision_id: str
    source_master_revision_no: int | None
    updated_at: Any


@dataclass(frozen=True)
class VehicleChecklistHistoryRecordContext:
    record_id: str
    record_label: str | None
    source_module_key: str | None
    source_master_revision_no: int | None


@dataclass(frozen=True)
class VehicleChecklistHistory:
    revision: LegacyIssueVehicleChecklistRevision
    items: list[LegacyIssueRecordHistory]
    record_contexts: dict[str, VehicleChecklistHistoryRecordContext]


def normalize_vehicle_code(value: str) -> str:
    normalized = " ".join((value or "").strip().split())
    if not normalized or len(normalized) > 80:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_model_invalid",
        )
    return normalized


def normalize_vehicle_code_key(value: str) -> str:
    return normalize_vehicle_code(value).casefold()


def normalize_optional_vehicle_text(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split())
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_model_invalid",
        )
    return normalized


def normalize_vehicle_stage_name(value: str) -> str:
    normalized = " ".join((value or "").strip().split())
    if not normalized or len(normalized) > 80:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_stage_invalid",
        )
    return normalized


def list_vehicle_models(
    db: Session,
    *,
    workspace: Workspace,
    include_inactive: bool = False,
    query: str | None = None,
) -> list[LegacyIssueVehicleModel]:
    statement = select(LegacyIssueVehicleModel).where(
        LegacyIssueVehicleModel.workspace_id == workspace.id
    )
    if not include_inactive:
        statement = statement.where(LegacyIssueVehicleModel.active.is_(True))
    normalized_query = (query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                LegacyIssueVehicleModel.vehicle_code.ilike(pattern),
                LegacyIssueVehicleModel.vehicle_name.ilike(pattern),
                LegacyIssueVehicleModel.notes.ilike(pattern),
            )
        )
    return list(
        db.scalars(
            statement.order_by(
                LegacyIssueVehicleModel.active.desc(),
                LegacyIssueVehicleModel.vehicle_code_normalized.asc(),
            )
        )
    )


def vehicle_stages_by_vehicle_model_ids(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_ids: list[str],
) -> dict[str, list[LegacyIssueVehicleStage]]:
    normalized_ids = list(dict.fromkeys(item for item in vehicle_model_ids if item))
    grouped = {vehicle_model_id: [] for vehicle_model_id in normalized_ids}
    if not normalized_ids:
        return grouped
    rows = list(
        db.scalars(
            select(LegacyIssueVehicleStage)
            .where(
                LegacyIssueVehicleStage.workspace_id == workspace.id,
                LegacyIssueVehicleStage.vehicle_model_id.in_(normalized_ids),
            )
            .order_by(
                LegacyIssueVehicleStage.vehicle_model_id.asc(),
                LegacyIssueVehicleStage.sequence_no.asc(),
            )
        )
    )
    for row in rows:
        grouped.setdefault(row.vehicle_model_id, []).append(row)
    return grouped


def list_vehicle_stages(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
) -> list[LegacyIssueVehicleStage]:
    get_vehicle_model(db, workspace=workspace, vehicle_model_id=vehicle_model_id)
    return vehicle_stages_by_vehicle_model_ids(
        db,
        workspace=workspace,
        vehicle_model_ids=[vehicle_model_id],
    )[vehicle_model_id]


def get_vehicle_stage(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
    stage_id: str | None = None,
) -> LegacyIssueVehicleStage:
    statement = select(LegacyIssueVehicleStage).where(
        LegacyIssueVehicleStage.workspace_id == workspace.id,
        LegacyIssueVehicleStage.vehicle_model_id == vehicle_model_id,
    )
    if stage_id is not None:
        statement = statement.where(LegacyIssueVehicleStage.id == stage_id)
    else:
        statement = statement.order_by(
            LegacyIssueVehicleStage.sequence_no.desc(),
            LegacyIssueVehicleStage.created_at.desc(),
        )
    row = db.scalar(statement)
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.vehicle_stage_not_found",
        )
    return row


def create_vehicle_stage(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    vehicle_model_id: str,
    name: str,
    allow_inactive: bool = False,
) -> LegacyIssueVehicleStage:
    vehicle_model = get_vehicle_model(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model_id,
        for_update=True,
    )
    if not vehicle_model.active and not allow_inactive:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_stage_vehicle_inactive",
        )
    normalized_name = normalize_vehicle_stage_name(name)
    previous_stage = db.scalar(
        select(LegacyIssueVehicleStage)
        .where(
            LegacyIssueVehicleStage.workspace_id == workspace.id,
            LegacyIssueVehicleStage.vehicle_model_id == vehicle_model.id,
        )
        .order_by(
            LegacyIssueVehicleStage.sequence_no.desc(),
            LegacyIssueVehicleStage.created_at.desc(),
        )
    )
    now = utcnow_naive()
    row = LegacyIssueVehicleStage(
        id=new_id(),
        workspace_id=workspace.id,
        vehicle_model_id=vehicle_model.id,
        name=normalized_name,
        name_normalized=normalized_name.casefold(),
        sequence_no=(previous_stage.sequence_no + 1 if previous_stage is not None else 1),
        previous_stage_id=previous_stage.id if previous_stage is not None else None,
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as error:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_stage_duplicate",
        ) from error
    return row


def update_vehicle_stage(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
    stage_id: str,
    name: str,
) -> LegacyIssueVehicleStage:
    row = db.scalar(
        select(LegacyIssueVehicleStage)
        .where(
            LegacyIssueVehicleStage.id == stage_id,
            LegacyIssueVehicleStage.workspace_id == workspace.id,
            LegacyIssueVehicleStage.vehicle_model_id == vehicle_model_id,
        )
        .with_for_update()
    )
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.vehicle_stage_not_found",
        )
    normalized_name = normalize_vehicle_stage_name(name)
    try:
        with db.begin_nested():
            row.name = normalized_name
            row.name_normalized = normalized_name.casefold()
            row.updated_at = utcnow_naive()
            db.add(row)
            db.flush()
    except IntegrityError as error:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_stage_duplicate",
        ) from error
    return row


def vehicle_checklist_summaries(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_ids: list[str],
) -> dict[str, VehicleChecklistSummary]:
    normalized_ids = list(dict.fromkeys(item for item in vehicle_model_ids if item))
    if not normalized_ids:
        return {}
    rows = list(
        db.scalars(
            select(LegacyIssueVehicleChecklistRevision).where(
                LegacyIssueVehicleChecklistRevision.workspace_id == workspace.id,
                LegacyIssueVehicleChecklistRevision.vehicle_model_id.in_(normalized_ids),
            )
        )
    )
    summaries: dict[str, VehicleChecklistSummary] = {
        vehicle_model_id: VehicleChecklistSummary() for vehicle_model_id in normalized_ids
    }
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.vehicle_model_id,
            row.source_master_revision_no if row.source_master_revision_no is not None else -1,
            row.updated_at,
        ),
        reverse=True,
    )
    for row in sorted_rows:
        summary = summaries.setdefault(row.vehicle_model_id, VehicleChecklistSummary())
        entry = VehicleChecklistSummaryEntry(
            revision_id=row.id,
            source_master_revision_no=row.source_master_revision_no,
            updated_at=row.updated_at,
        )
        if row.status == VEHICLE_CHECKLIST_STATUS_DRAFT and summary.latest_draft is None:
            summary.latest_draft = entry
        if row.status == VEHICLE_CHECKLIST_STATUS_COMPLETED and summary.latest_completed is None:
            summary.latest_completed = entry
    return summaries


def vehicle_generated_checklist_counts(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_ids: list[str],
) -> dict[str, int]:
    normalized_ids = list(dict.fromkeys(item for item in vehicle_model_ids if item))
    if not normalized_ids:
        return {}

    generated_checklists = (
        select(LegacyIssueVehicleChecklistRevision.vehicle_model_id.label("vehicle_model_id"))
        .where(
            LegacyIssueVehicleChecklistRevision.workspace_id == workspace.id,
            LegacyIssueVehicleChecklistRevision.vehicle_model_id.in_(normalized_ids),
        )
        .union_all(
            select(
                LegacyIssueVehicleModuleChecklist.vehicle_model_id.label("vehicle_model_id")
            ).where(
                LegacyIssueVehicleModuleChecklist.workspace_id == workspace.id,
                LegacyIssueVehicleModuleChecklist.vehicle_model_id.in_(normalized_ids),
            )
        )
        .subquery()
    )
    counts = {vehicle_model_id: 0 for vehicle_model_id in normalized_ids}
    for vehicle_model_id, total in db.execute(
        select(
            generated_checklists.c.vehicle_model_id,
            func.count().label("total"),
        ).group_by(generated_checklists.c.vehicle_model_id)
    ):
        counts[vehicle_model_id] = int(total)
    return counts


def get_vehicle_model(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
    for_update: bool = False,
) -> LegacyIssueVehicleModel:
    statement = select(LegacyIssueVehicleModel).where(
        LegacyIssueVehicleModel.id == vehicle_model_id,
        LegacyIssueVehicleModel.workspace_id == workspace.id,
    )
    if for_update:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.vehicle_model_not_found",
        )
    return row


def create_vehicle_model(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    vehicle_code: str,
    vehicle_name: str | None = None,
    notes: str | None = None,
    initial_stage_name: str = DEFAULT_INITIAL_VEHICLE_STAGE_NAME,
) -> LegacyIssueVehicleModel:
    normalized_code = normalize_vehicle_code(vehicle_code)
    row = LegacyIssueVehicleModel(
        id=new_id(),
        workspace_id=workspace.id,
        vehicle_code=normalized_code,
        vehicle_code_normalized=normalized_code.casefold(),
        vehicle_name=normalize_optional_vehicle_text(vehicle_name, max_length=160),
        notes=normalize_optional_vehicle_text(notes, max_length=1000),
        active=True,
        created_by_id=user.id,
        created_at=utcnow_naive(),
        updated_at=utcnow_naive(),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as error:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_model_duplicate",
        ) from error
    create_vehicle_stage(
        db,
        workspace=workspace,
        user=user,
        vehicle_model_id=row.id,
        name=initial_stage_name,
        allow_inactive=True,
    )
    return row


def update_vehicle_model(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
    vehicle_code: str | None = None,
    vehicle_name: str | None = None,
    vehicle_name_set: bool = False,
    notes: str | None = None,
    notes_set: bool = False,
    active: bool | None = None,
) -> LegacyIssueVehicleModel:
    row = get_vehicle_model(db, workspace=workspace, vehicle_model_id=vehicle_model_id)
    if vehicle_code is not None:
        normalized_code = normalize_vehicle_code(vehicle_code)
        row.vehicle_code = normalized_code
        row.vehicle_code_normalized = normalized_code.casefold()
    if vehicle_name_set:
        row.vehicle_name = normalize_optional_vehicle_text(vehicle_name, max_length=160)
    if notes_set:
        row.notes = normalize_optional_vehicle_text(notes, max_length=1000)
    if active is not None:
        row.active = bool(active)
    row.updated_at = utcnow_naive()
    db.add(row)
    try:
        db.flush()
    except IntegrityError as error:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_model_duplicate",
        ) from error
    return row


def deactivate_vehicle_model(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
) -> LegacyIssueVehicleModel:
    return update_vehicle_model(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model_id,
        active=False,
    )


def permanently_delete_vehicle_model(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    vehicle_model_id: str,
) -> None:
    row = get_vehicle_model(
        db,
        workspace=workspace,
        vehicle_model_id=vehicle_model_id,
        for_update=True,
    )
    generated_checklist_count = vehicle_generated_checklist_counts(
        db,
        workspace=workspace,
        vehicle_model_ids=[row.id],
    )[row.id]
    if generated_checklist_count:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_model_has_checklists",
        )

    add_record_history_entries(
        db,
        workspace=workspace,
        user=user,
        record_kind=VEHICLE_MODEL_RECORD_KIND,
        record_id=row.id,
        action="delete",
        changes=[
            LegacyIssueHistoryChange(
                field_key="vehicle_model",
                field_label="vehicle_model",
                old_value=row.vehicle_code,
                new_value=None,
            )
        ],
        details={
            "vehicle_model": {
                "id": row.id,
                "vehicle_code": row.vehicle_code,
                "vehicle_name": row.vehicle_name,
                "notes": row.notes,
                "active": row.active,
                "created_by_id": row.created_by_id,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            },
            "generated_checklist_count": generated_checklist_count,
        },
    )
    db.delete(row)
    db.flush()


def list_vehicle_checklist_revisions(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
) -> list[LegacyIssueVehicleChecklistRevision]:
    get_vehicle_model(db, workspace=workspace, vehicle_model_id=vehicle_model_id)
    return list(
        db.scalars(
            select(LegacyIssueVehicleChecklistRevision)
            .where(
                LegacyIssueVehicleChecklistRevision.workspace_id == workspace.id,
                LegacyIssueVehicleChecklistRevision.vehicle_model_id == vehicle_model_id,
            )
            .order_by(
                LegacyIssueVehicleChecklistRevision.source_master_revision_no.desc(),
                LegacyIssueVehicleChecklistRevision.created_at.desc(),
            )
        )
    )


def get_vehicle_checklist_revision(
    db: Session,
    *,
    workspace: Workspace,
    revision_id: str,
) -> LegacyIssueVehicleChecklistRevision:
    row = db.scalar(
        select(LegacyIssueVehicleChecklistRevision).where(
            LegacyIssueVehicleChecklistRevision.id == revision_id,
            LegacyIssueVehicleChecklistRevision.workspace_id == workspace.id,
        )
    )
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.vehicle_checklist_revision_not_found",
        )
    return row


def delete_vehicle_checklist_revision(
    db: Session,
    *,
    workspace: Workspace,
    revision_id: str,
) -> None:
    revision = db.scalar(
        select(LegacyIssueVehicleChecklistRevision)
        .where(
            LegacyIssueVehicleChecklistRevision.id == revision_id,
            LegacyIssueVehicleChecklistRevision.workspace_id == workspace.id,
        )
        .with_for_update()
    )
    if revision is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.vehicle_checklist_revision_not_found",
        )

    checklist_record_ids = select(LegacyIssueVehicleChecklistRecord.id).where(
        LegacyIssueVehicleChecklistRecord.workspace_id == workspace.id,
        LegacyIssueVehicleChecklistRecord.checklist_revision_id == revision.id,
    )
    db.execute(
        delete(LegacyIssueRecordHistory).where(
            LegacyIssueRecordHistory.workspace_id == workspace.id,
            LegacyIssueRecordHistory.record_kind == VEHICLE_CHECKLIST_RECORD_KIND,
            or_(
                LegacyIssueRecordHistory.record_id == revision.id,
                LegacyIssueRecordHistory.record_id.in_(checklist_record_ids),
            ),
        )
    )
    db.execute(
        delete(LegacyIssueVehicleChecklistRecord).where(
            LegacyIssueVehicleChecklistRecord.workspace_id == workspace.id,
            LegacyIssueVehicleChecklistRecord.checklist_revision_id == revision.id,
        )
    )
    db.execute(
        delete(LegacyIssueVehicleChecklistRevision).where(
            LegacyIssueVehicleChecklistRevision.id == revision.id,
            LegacyIssueVehicleChecklistRevision.workspace_id == workspace.id,
        )
    )
    db.flush()


def latest_master_revision(
    db: Session,
    *,
    workspace: Workspace,
) -> Any:
    dataset_revision_key = legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY)
    return ensure_initial_published_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_revision_key,
    )


def list_published_master_revisions(
    db: Session,
    *,
    workspace: Workspace,
) -> list[LegacyIssueDataRevision]:
    dataset_revision_key = legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY)
    ensure_initial_published_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_revision_key,
    )
    return list(
        db.scalars(
            select(LegacyIssueDataRevision)
            .where(
                LegacyIssueDataRevision.workspace_id == workspace.id,
                LegacyIssueDataRevision.dataset_key == dataset_revision_key,
                LegacyIssueDataRevision.status == REVISION_STATUS_PUBLISHED,
            )
            .order_by(
                LegacyIssueDataRevision.revision_no.desc().nullslast(),
                LegacyIssueDataRevision.created_at.desc(),
            )
        )
    )


def create_vehicle_checklist_revision(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    vehicle_model_id: str,
    source_master_revision_id: str | None = None,
    module_keys: frozenset[str] | None = None,
) -> LegacyIssueVehicleChecklistRevision:
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
    source_revision = _resolve_source_master_revision(
        db,
        workspace=workspace,
        source_master_revision_id=source_master_revision_id,
    )
    definition = get_dataset_definition_with_all_module_fields(
        db,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        workspace=workspace,
    )
    legacy_source_rows, _legacy_total = list_dataset_records(
        db,
        definition,
        workspace=workspace,
        revision=source_revision,
        limit=None,
    )
    if legacy_source_rows:
        source_rows = [
            row
            for row in legacy_source_rows
            if module_keys is None or row.module_key is None or row.module_key in module_keys
        ]
        source_revision_map = {"legacy-common-master": source_revision.id}
    else:
        source_module_revisions = _latest_published_module_revisions(
            db,
            workspace=workspace,
            module_keys=module_keys,
        )
        source_revision_map = {
            module_key: revision.id for module_key, revision in source_module_revisions.items()
        }
        source_rows, _total = list_dataset_records(
            db,
            definition,
            workspace=workspace,
            revisions=list(source_module_revisions.values()),
            limit=None,
        )
    existing_revisions = db.scalars(
        select(LegacyIssueVehicleChecklistRevision).where(
            LegacyIssueVehicleChecklistRevision.workspace_id == workspace.id,
            LegacyIssueVehicleChecklistRevision.vehicle_model_id == vehicle_model.id,
        )
    )
    for existing in existing_revisions:
        if (existing.definition_snapshot or {}).get(
            "source_module_revisions"
        ) == source_revision_map:
            return existing

    checklist_source_revision = (
        source_revision
        if "legacy-common-master" in source_revision_map
        else _checklist_source_identity_revision(
            db,
            workspace=workspace,
            source_revision_map=source_revision_map,
        )
    )
    definition_snapshot = dataset_definition_snapshot(definition)
    definition_snapshot["source_module_revisions"] = source_revision_map
    now = utcnow_naive()
    checklist_revision = LegacyIssueVehicleChecklistRevision(
        id=new_id(),
        workspace_id=workspace.id,
        vehicle_model_id=vehicle_model.id,
        revision_no=_next_vehicle_checklist_revision_no(
            db,
            workspace=workspace,
            vehicle_model_id=vehicle_model.id,
        ),
        status=VEHICLE_CHECKLIST_STATUS_DRAFT,
        source_dataset_key=COMMON_MASTER_DATASET_KEY,
        source_master_revision_id=checklist_source_revision.id,
        source_master_revision_no=checklist_source_revision.revision_no,
        definition_snapshot=definition_snapshot,
        row_count=len(source_rows),
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(checklist_revision)
    db.flush()

    for sort_order, source_row in enumerate(source_rows, start=1):
        values = _initial_vehicle_checklist_values(source_row.field_values or {})
        db.add(
            LegacyIssueVehicleChecklistRecord(
                id=new_id(),
                workspace_id=workspace.id,
                checklist_revision_id=checklist_revision.id,
                source_record_id=source_row.id,
                source_stable_record_id=source_row.stable_record_id,
                source_module_key=source_row.module_key,
                sort_order=sort_order,
                field_values=values,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    return checklist_revision


def list_vehicle_checklist_records(
    db: Session,
    *,
    workspace: Workspace,
    revision_id: str,
    view_key: str | None = None,
    query: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    module_keys: frozenset[str] | None = None,
) -> tuple[
    LegacyIssueVehicleChecklistRevision,
    LegacyIssueDatasetDefinition,
    list[LegacyIssueVehicleChecklistRecord],
    int,
]:
    revision = get_vehicle_checklist_revision(
        db,
        workspace=workspace,
        revision_id=revision_id,
    )
    module_key = normalize_legacy_issue_module_key(view_key)
    definition = dataset_definition_from_snapshot(revision.definition_snapshot, view_key=view_key)
    statement = select(LegacyIssueVehicleChecklistRecord).where(
        LegacyIssueVehicleChecklistRecord.workspace_id == workspace.id,
        LegacyIssueVehicleChecklistRecord.checklist_revision_id == revision.id,
    )
    if module_key is not None:
        statement = statement.where(
            LegacyIssueVehicleChecklistRecord.source_module_key == module_key
        )
    elif module_keys is not None:
        statement = statement.where(
            or_(
                LegacyIssueVehicleChecklistRecord.source_module_key.is_(None),
                LegacyIssueVehicleChecklistRecord.source_module_key.in_(module_keys),
            )
        )
    normalized_query = (query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                cast(LegacyIssueVehicleChecklistRecord.field_values, Text).ilike(pattern),
                LegacyIssueVehicleChecklistRecord.source_record_id.ilike(pattern),
                LegacyIssueVehicleChecklistRecord.source_stable_record_id.ilike(pattern),
            )
        )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    row_statement = statement.order_by(
        LegacyIssueVehicleChecklistRecord.sort_order.asc(),
        LegacyIssueVehicleChecklistRecord.created_at.asc(),
    ).offset(max(offset, 0))
    if limit is not None:
        row_statement = row_statement.limit(max(limit, 1))
    rows = list(db.scalars(row_statement))
    return revision, definition, rows, total


def update_vehicle_checklist_records(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    revision_id: str,
    updates: dict[str, dict[str, Any | None]],
    module_keys: frozenset[str] | None = None,
) -> list[LegacyIssueVehicleChecklistRecord]:
    revision = get_vehicle_checklist_revision(
        db,
        workspace=workspace,
        revision_id=revision_id,
    )
    if revision.status != VEHICLE_CHECKLIST_STATUS_DRAFT:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_checklist_revision_completed",
        )
    definition = dataset_definition_from_snapshot(revision.definition_snapshot)
    labels = field_labels(definition)
    changed_rows: list[LegacyIssueVehicleChecklistRecord] = []
    for record_id, values in updates.items():
        clean_update = _validate_checklist_update_values(values)
        if not clean_update:
            continue
        record = _get_vehicle_checklist_record(
            db,
            workspace=workspace,
            revision=revision,
            record_id=record_id,
        )
        if (
            module_keys is not None
            and record.source_module_key is not None
            and record.source_module_key not in module_keys
        ):
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                code="legacy_issues.module_not_found",
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
        record.field_values = next_values
        record.updated_by_id = user.id
        record.updated_at = utcnow_naive()
        revision.updated_at = record.updated_at
        db.add(record)
        changed_rows.append(record)
        add_record_history_entries(
            db,
            workspace=workspace,
            user=user,
            record_kind=VEHICLE_CHECKLIST_RECORD_KIND,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            record_id=record.id,
            action="update",
            changes=collect_value_changes(
                old_values=old_values,
                new_values=changed_values,
                field_labels=labels,
            ),
            details=_vehicle_checklist_history_details(revision),
        )
    if changed_rows:
        db.add(revision)
        db.flush()
        for record in changed_rows:
            db.refresh(record)
    return changed_rows


def complete_vehicle_checklist_revision(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    revision_id: str,
) -> LegacyIssueVehicleChecklistRevision:
    revision = get_vehicle_checklist_revision(
        db,
        workspace=workspace,
        revision_id=revision_id,
    )
    if revision.status == VEHICLE_CHECKLIST_STATUS_COMPLETED:
        return revision
    old_status = revision.status
    now = utcnow_naive()
    revision.status = VEHICLE_CHECKLIST_STATUS_COMPLETED
    revision.completed_by_id = user.id
    revision.completed_at = now
    revision.updated_at = now
    db.add(revision)
    _add_vehicle_checklist_status_history(
        db,
        workspace=workspace,
        user=user,
        revision=revision,
        action="complete",
        old_status=old_status,
        new_status=VEHICLE_CHECKLIST_STATUS_COMPLETED,
    )
    db.flush()
    return revision


def reopen_vehicle_checklist_revision(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    revision_id: str,
) -> LegacyIssueVehicleChecklistRevision:
    revision = get_vehicle_checklist_revision(
        db,
        workspace=workspace,
        revision_id=revision_id,
    )
    if revision.status == VEHICLE_CHECKLIST_STATUS_DRAFT:
        return revision
    old_status = revision.status
    now = utcnow_naive()
    revision.status = VEHICLE_CHECKLIST_STATUS_DRAFT
    revision.completed_by_id = None
    revision.completed_at = None
    revision.updated_at = now
    db.add(revision)
    _add_vehicle_checklist_status_history(
        db,
        workspace=workspace,
        user=user,
        revision=revision,
        action="reopen",
        old_status=old_status,
        new_status=VEHICLE_CHECKLIST_STATUS_DRAFT,
    )
    db.flush()
    return revision


def list_vehicle_checklist_history(
    db: Session,
    *,
    workspace: Workspace,
    revision_id: str,
    module_keys: frozenset[str] | None = None,
) -> VehicleChecklistHistory:
    revision = get_vehicle_checklist_revision(
        db,
        workspace=workspace,
        revision_id=revision_id,
    )
    record_statement = select(LegacyIssueVehicleChecklistRecord).where(
        LegacyIssueVehicleChecklistRecord.workspace_id == workspace.id,
        LegacyIssueVehicleChecklistRecord.checklist_revision_id == revision.id,
    )
    if module_keys is not None:
        record_statement = record_statement.where(
            or_(
                LegacyIssueVehicleChecklistRecord.source_module_key.is_(None),
                LegacyIssueVehicleChecklistRecord.source_module_key.in_(module_keys),
            )
        )
    records = list(
        db.scalars(
            record_statement.order_by(
                LegacyIssueVehicleChecklistRecord.sort_order.asc(),
                LegacyIssueVehicleChecklistRecord.created_at.asc(),
            )
        )
    )
    record_contexts = {
        revision.id: VehicleChecklistHistoryRecordContext(
            record_id=revision.id,
            record_label=f"Master Rev. {revision.source_master_revision_no or '-'}",
            source_module_key=None,
            source_master_revision_no=revision.source_master_revision_no,
        )
    }
    for record in records:
        record_contexts[record.id] = VehicleChecklistHistoryRecordContext(
            record_id=record.id,
            record_label=_vehicle_checklist_record_label(record),
            source_module_key=record.source_module_key,
            source_master_revision_no=revision.source_master_revision_no,
        )
    history_rows = list_record_history(
        db,
        workspace=workspace,
        record_kind=VEHICLE_CHECKLIST_RECORD_KIND,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        record_ids=record_contexts.keys(),
    )
    return VehicleChecklistHistory(
        revision=revision,
        items=history_rows,
        record_contexts=record_contexts,
    )


def dataset_definition_snapshot(definition: LegacyIssueDatasetDefinition) -> dict[str, Any]:
    return {
        "key": definition.key,
        "title_ko": definition.title_ko,
        "title_en": definition.title_en,
        "hierarchy_ko": list(definition.hierarchy_ko),
        "hierarchy_en": list(definition.hierarchy_en),
        "header_rows": definition.header_rows,
        "group_labels_ko": dict(definition.group_labels_ko),
        "group_labels_en": dict(definition.group_labels_en),
        "fields": [
            {
                "key": field.key,
                "label_ko": field.label_ko,
                "label_en": field.label_en,
                "group_key": field.group_key,
                "aliases": list(field.aliases),
                "field_type": field.field_type,
                "options": list(field.options),
                "allow_multiple": field.allow_multiple,
                "required": field.required,
                "source": field.source,
                "module_key": field.module_key,
                "field_id": field.field_id,
                "active": field.active,
                "readonly": field.readonly,
            }
            for field in definition.fields
        ],
    }


def dataset_definition_from_snapshot(
    snapshot: dict[str, Any],
    *,
    view_key: str | None = None,
) -> LegacyIssueDatasetDefinition:
    module_key = normalize_legacy_issue_module_key(view_key)
    fields = tuple(
        _field_from_snapshot(item)
        for item in snapshot.get("fields", [])
        if _snapshot_field_visible_for_view(item, module_key=module_key)
    )
    return LegacyIssueDatasetDefinition(
        key=str(snapshot.get("key") or COMMON_MASTER_DATASET_KEY),
        table_model=LegacyIssueVehicleChecklistRecord,
        title_ko=str(snapshot.get("title_ko") or "과거차 전체"),
        title_en=str(snapshot.get("title_en") or "Past Vehicle Issue All"),
        hierarchy_ko=tuple(snapshot.get("hierarchy_ko") or ("전체",)),
        hierarchy_en=tuple(snapshot.get("hierarchy_en") or ("All",)),
        fields=fields,
        header_rows=int(snapshot.get("header_rows") or 1),
        group_labels_ko=dict(snapshot.get("group_labels_ko") or {}),
        group_labels_en=dict(snapshot.get("group_labels_en") or {}),
    )


def _field_from_snapshot(item: dict[str, Any]) -> DatasetFieldDefinition:
    return DatasetFieldDefinition(
        key=str(item.get("key") or ""),
        label_ko=str(item.get("label_ko") or item.get("key") or ""),
        label_en=str(item.get("label_en") or item.get("label_ko") or item.get("key") or ""),
        group_key=item.get("group_key"),
        aliases=tuple(item.get("aliases") or ()),
        field_type=str(item.get("field_type") or "text"),
        options=tuple(item.get("options") or ()),
        allow_multiple=bool(item.get("allow_multiple")),
        required=bool(item.get("required")),
        source=str(item.get("source") or "system"),
        module_key=item.get("module_key"),
        field_id=item.get("field_id"),
        active=bool(item.get("active", True)),
        readonly=bool(item.get("readonly")),
    )


def _snapshot_field_visible_for_view(
    item: dict[str, Any],
    *,
    module_key: str | None,
) -> bool:
    source = str(item.get("source") or "system")
    if source != "module":
        return True
    if module_key is None:
        return False
    return item.get("module_key") == module_key


def _resolve_source_master_revision(
    db: Session,
    *,
    workspace: Workspace,
    source_master_revision_id: str | None,
) -> Any:
    revision_dataset_key = legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY)
    if not source_master_revision_id:
        revision = get_latest_published_revision(
            db,
            workspace=workspace,
            dataset_key=revision_dataset_key,
        )
        if revision is not None:
            return revision
        return ensure_initial_published_revision(
            db,
            workspace=workspace,
            dataset_key=revision_dataset_key,
        )
    revision = get_revision(
        db,
        workspace=workspace,
        dataset_key=revision_dataset_key,
        revision_id=source_master_revision_id,
    )
    if revision.status != REVISION_STATUS_PUBLISHED:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_checklist_revision_invalid",
        )
    return revision


def _latest_published_module_revisions(
    db: Session,
    *,
    workspace: Workspace,
    module_keys: frozenset[str] | None = None,
) -> dict[str, LegacyIssueDataRevision]:
    revisions: dict[str, LegacyIssueDataRevision] = {}
    effective_module_keys = LEGACY_ISSUE_MODULE_KEYS if module_keys is None else module_keys
    for module_key in sorted(effective_module_keys):
        revision_key = legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            module_key,
        )
        revision = get_latest_published_revision(
            db,
            workspace=workspace,
            dataset_key=revision_key,
        )
        if revision is None:
            revision = ensure_initial_published_revision(
                db,
                workspace=workspace,
                dataset_key=revision_key,
            )
        revisions[module_key] = revision
    return revisions


def _checklist_source_identity_revision(
    db: Session,
    *,
    workspace: Workspace,
    source_revision_map: dict[str, str],
) -> LegacyIssueDataRevision:
    source_fingerprint = "|".join(
        f"{module_key}:{revision_id}"
        for module_key, revision_id in sorted(source_revision_map.items())
    )
    digest = hashlib.sha256(source_fingerprint.encode("utf-8")).hexdigest()[:32]
    dataset_key = f"legacy_issue.checklist-source.{digest}"
    existing = get_latest_published_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
    )
    if existing is not None:
        ensure_revision_partition(db, existing)
        return existing
    now = utcnow_naive()
    revision = LegacyIssueDataRevision(
        id=new_id(),
        workspace_id=workspace.id,
        dataset_key=dataset_key,
        revision_no=1,
        status=REVISION_STATUS_PUBLISHED,
        created_at=now,
        updated_at=now,
        published_at=now,
    )
    ensure_revision_partition(db, revision)
    db.add(revision)
    db.flush()
    return revision


def _next_vehicle_checklist_revision_no(
    db: Session,
    *,
    workspace: Workspace,
    vehicle_model_id: str,
) -> int:
    current = db.scalar(
        select(func.max(LegacyIssueVehicleChecklistRevision.revision_no)).where(
            LegacyIssueVehicleChecklistRevision.workspace_id == workspace.id,
            LegacyIssueVehicleChecklistRevision.vehicle_model_id == vehicle_model_id,
        )
    )
    return int(current or 0) + 1


def _initial_vehicle_checklist_values(values: dict[str, Any]) -> dict[str, Any]:
    clean_values = canonicalize_dataset_values(values)
    return {
        key: value
        for key, value in clean_values.items()
        if key not in VEHICLE_CHECKLIST_CHECK_FIELD_KEYS and display_dataset_value(value)
    }


def _validate_checklist_update_values(
    values: dict[str, Any | None],
) -> dict[str, Any | None]:
    invalid_keys = set(values) - VEHICLE_CHECKLIST_CHECK_FIELD_KEYS
    if invalid_keys:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="legacy_issues.vehicle_checklist_field_invalid",
            detail=", ".join(sorted(invalid_keys)),
        )
    return {
        key: value for key, value in values.items() if key in VEHICLE_CHECKLIST_CHECK_FIELD_KEYS
    }


def _get_vehicle_checklist_record(
    db: Session,
    *,
    workspace: Workspace,
    revision: LegacyIssueVehicleChecklistRevision,
    record_id: str,
) -> LegacyIssueVehicleChecklistRecord:
    row = db.scalar(
        select(LegacyIssueVehicleChecklistRecord).where(
            LegacyIssueVehicleChecklistRecord.id == record_id,
            LegacyIssueVehicleChecklistRecord.workspace_id == workspace.id,
            LegacyIssueVehicleChecklistRecord.checklist_revision_id == revision.id,
        )
    )
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.dataset_record_not_found",
        )
    return row


def _add_vehicle_checklist_status_history(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    revision: LegacyIssueVehicleChecklistRevision,
    action: str,
    old_status: str,
    new_status: str,
) -> None:
    add_record_history_entries(
        db,
        workspace=workspace,
        user=user,
        record_kind=VEHICLE_CHECKLIST_RECORD_KIND,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        record_id=revision.id,
        action=action,
        changes=[
            LegacyIssueHistoryChange(
                field_key="status",
                field_label="status",
                old_value=old_status,
                new_value=new_status,
            )
        ],
        details=_vehicle_checklist_history_details(revision),
    )


def _vehicle_checklist_history_details(
    revision: LegacyIssueVehicleChecklistRevision,
) -> dict[str, Any]:
    return {
        "vehicle_checklist_revision_id": revision.id,
        "vehicle_model_id": revision.vehicle_model_id,
        "source_master_revision_id": revision.source_master_revision_id,
        "source_master_revision_no": revision.source_master_revision_no,
    }


def _vehicle_checklist_record_label(record: LegacyIssueVehicleChecklistRecord) -> str:
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
    if primary:
        return primary
    if secondary:
        return secondary
    return record.source_stable_record_id or record.source_record_id


def checklist_has_newer_master_revision(
    revision: LegacyIssueVehicleChecklistRevision,
    latest_revision_no: int | None,
) -> bool:
    if latest_revision_no is None:
        return False
    if revision.source_master_revision_no is None:
        return revision.source_master_revision_id != ""
    return latest_revision_no > revision.source_master_revision_no
