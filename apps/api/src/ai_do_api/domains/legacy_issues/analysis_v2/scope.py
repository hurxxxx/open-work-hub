from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ai_do_api.domains.legacy_issues.analysis_v2.execution import AnalysisSqlScope
from ai_do_api.domains.legacy_issues.dataset_records import COMMON_MASTER_DATASET_KEY
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueVehicleModel,
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleStage,
)
from ai_do_api.domains.legacy_issues.module_access import LEGACY_ISSUE_MODULE_KEYS
from ai_do_api.domains.legacy_issues.revisioning import (
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    legacy_issue_dataset_revision_key,
)


class AnalysisScopeResolutionError(ValueError):
    pass


def resolve_runtime_sql_scope(
    db: Session,
    *,
    workspace_id: str,
    module_keys: Iterable[str],
    partition_ids: Iterable[str],
) -> AnalysisSqlScope:
    """Resolve the current revision/checklist snapshot for one authorized run."""

    normalized_modules = tuple(
        sorted({str(value).strip() for value in module_keys if str(value).strip()})
    )
    unknown_modules = set(normalized_modules).difference(LEGACY_ISSUE_MODULE_KEYS)
    if unknown_modules:
        raise AnalysisScopeResolutionError(
            f"unknown or disabled legacy issue modules: {sorted(unknown_modules)}"
        )
    normalized_partitions = tuple(
        sorted({str(value).strip() for value in partition_ids if str(value).strip()})
    )
    revision_keys = {
        module_key: legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            module_key,
        )
        for module_key in normalized_modules
    }
    revisions = list(
        db.scalars(
            select(LegacyIssueDataRevision).where(
                LegacyIssueDataRevision.workspace_id == workspace_id,
                LegacyIssueDataRevision.dataset_key.in_(tuple(revision_keys.values())),
                LegacyIssueDataRevision.status.in_(
                    (REVISION_STATUS_DRAFT, REVISION_STATUS_PUBLISHED)
                ),
                or_(
                    LegacyIssueDataRevision.retrieval_partition_id.is_(None),
                    LegacyIssueDataRevision.retrieval_partition_id.in_(normalized_partitions),
                ),
            )
        )
    )
    candidates_by_dataset: dict[str, list[LegacyIssueDataRevision]] = {}
    for revision in revisions:
        candidates_by_dataset.setdefault(revision.dataset_key, []).append(revision)
    revision_ids = tuple(
        selected.id
        for module_key in normalized_modules
        if (selected := _latest_revision(candidates_by_dataset.get(revision_keys[module_key], ())))
        is not None
    )

    latest_stage_sequences = (
        select(
            LegacyIssueVehicleStage.vehicle_model_id.label("vehicle_model_id"),
            func.max(LegacyIssueVehicleStage.sequence_no).label("sequence_no"),
        )
        .where(LegacyIssueVehicleStage.workspace_id == workspace_id)
        .group_by(LegacyIssueVehicleStage.vehicle_model_id)
        .subquery()
    )
    checklists = list(
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
    for checklist in checklists:
        identity = (checklist.vehicle_model_id, checklist.module_key)
        current = latest_checklists.get(identity)
        if current is None or _checklist_sort_key(checklist) > _checklist_sort_key(current):
            latest_checklists[identity] = checklist

    return AnalysisSqlScope(
        workspace_id=workspace_id,
        partition_ids=normalized_partitions,
        module_keys=normalized_modules,
        revision_ids=revision_ids,
        checklist_ids=tuple(
            checklist.id for _identity, checklist in sorted(latest_checklists.items())
        ),
    )


def _latest_revision(
    revisions: Iterable[LegacyIssueDataRevision],
) -> LegacyIssueDataRevision | None:
    return max(revisions, key=_revision_sort_key, default=None)


def _revision_sort_key(
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


__all__ = [
    "AnalysisScopeResolutionError",
    "resolve_runtime_sql_scope",
]
