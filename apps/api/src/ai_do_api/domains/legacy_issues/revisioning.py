from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.access import is_platform_admin_user, record_audit_log
from ai_do_api.domains.auth.models import User, Workspace, WorkspaceUserBinding, utcnow_naive
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueDataRevisionEvent,
    LegacyIssueRevisionOverviewHistory,
)
from ai_do_api.domains.legacy_issues.module_access import LEGACY_ISSUE_MODULE_KEYS
from ai_do_api.domains.legacy_issues.module_direct_editors import (
    can_user_direct_edit_module,
)
from ai_do_api.domains.legacy_issues.partitioning import ensure_revision_partition


REVISION_STATUS_DRAFT = "draft"
REVISION_STATUS_PUBLISHED = "published"
REVISION_STATUS_CANCELED = "canceled"

DATASET_KEY_PREFIX = "legacy_issue."
REVISION_MEETING_DATASET_KEYS = frozenset(
    f"legacy_issue.common-master.{module_key}" for module_key in LEGACY_ISSUE_MODULE_KEYS
)


@dataclass(frozen=True)
class RevisionContext:
    current: LegacyIssueDataRevision
    latest_published: LegacyIssueDataRevision | None
    active_draft: LegacyIssueDataRevision | None


def legacy_issue_dataset_revision_key(
    dataset_key: str,
    module_key: str | None = None,
) -> str:
    base_key = f"{DATASET_KEY_PREFIX}{dataset_key}"
    normalized_module_key = (module_key or "").strip()
    return f"{base_key}.{normalized_module_key}" if normalized_module_key else base_key


def require_record_revision_editor(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    module_key: str | None = None,
    user: User,
    revision_id: str | None = None,
) -> LegacyIssueDataRevision:
    if revision_id is not None:
        requested_revision = get_revision(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            revision_id=revision_id,
        )
        if requested_revision.status == REVISION_STATUS_DRAFT:
            return require_draft_revision_editor(
                db,
                workspace=workspace,
                dataset_key=dataset_key,
                user=user,
                revision_id=revision_id,
            )
    if not is_platform_admin_user(user, db) and (
        module_key is None
        or not can_user_direct_edit_module(
            db,
            workspace=workspace,
            user=user,
            module_key=module_key,
        )
    ):
        return require_draft_revision_editor(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            user=user,
            revision_id=revision_id,
        )
    context = resolve_read_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_id=revision_id,
    )
    latest = context.latest_published
    if (
        latest is None
        or context.current.id != latest.id
        or context.current.status != REVISION_STATUS_PUBLISHED
        or context.active_draft is not None
    ):
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.revision_current_required",
        )
    return context.current


def can_direct_edit_published_revision(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    module_key: str,
    context: RevisionContext,
) -> bool:
    latest = context.latest_published
    return (
        can_user_direct_edit_module(
            db,
            workspace=workspace,
            user=user,
            module_key=module_key,
        )
        and latest is not None
        and context.current.id == latest.id
        and context.current.status == REVISION_STATUS_PUBLISHED
        and context.active_draft is None
    )


def list_revisions(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
) -> list[LegacyIssueDataRevision]:
    return list(
        db.scalars(
            select(LegacyIssueDataRevision)
            .options(
                selectinload(LegacyIssueDataRevision.locked_by),
                selectinload(LegacyIssueDataRevision.created_by),
                selectinload(LegacyIssueDataRevision.published_by),
                selectinload(LegacyIssueDataRevision.canceled_by),
                selectinload(LegacyIssueDataRevision.reviewer),
                selectinload(LegacyIssueDataRevision.approver),
                selectinload(LegacyIssueDataRevision.review_requested_by),
                selectinload(LegacyIssueDataRevision.approval_requested_by),
                selectinload(LegacyIssueDataRevision.reviewed_by),
                selectinload(LegacyIssueDataRevision.approved_by),
            )
            .where(
                LegacyIssueDataRevision.workspace_id == workspace.id,
                LegacyIssueDataRevision.dataset_key == dataset_key,
            )
            .order_by(
                LegacyIssueDataRevision.status == REVISION_STATUS_DRAFT,
                LegacyIssueDataRevision.revision_no.desc().nullslast(),
                LegacyIssueDataRevision.created_at.desc(),
            )
        )
    )


def list_revision_events(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    limit: int = 200,
) -> list[LegacyIssueDataRevisionEvent]:
    return list(
        db.scalars(
            select(LegacyIssueDataRevisionEvent)
            .options(selectinload(LegacyIssueDataRevisionEvent.actor))
            .where(
                LegacyIssueDataRevisionEvent.workspace_id == workspace.id,
                LegacyIssueDataRevisionEvent.dataset_key == dataset_key,
            )
            .order_by(LegacyIssueDataRevisionEvent.created_at.desc())
            .limit(max(limit, 1))
        )
    )


def list_revision_overview_history(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
) -> list[LegacyIssueRevisionOverviewHistory]:
    return list(
        db.scalars(
            select(LegacyIssueRevisionOverviewHistory)
            .where(
                LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
                LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
            )
            .order_by(
                LegacyIssueRevisionOverviewHistory.sort_order,
                LegacyIssueRevisionOverviewHistory.source_row,
                LegacyIssueRevisionOverviewHistory.created_at,
                LegacyIssueRevisionOverviewHistory.id,
            )
        )
    )


def create_revision_overview_history(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User,
    linked_revision_id: str | None,
    revision_no: int | None,
    summary: str | None,
    revised_on: date | None,
    vehicle_models: str | None,
    author_user_id: str | None,
    reviewer_user_id: str | None,
    approver_user_id: str | None,
    author_name: str | None,
    reviewer_name: str | None,
    approver_name: str | None,
) -> LegacyIssueRevisionOverviewHistory:
    _require_overview_history_admin(db, user=user)
    latest_revision = _require_overview_history_event_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
    )
    linked_revision = None
    if linked_revision_id is not None:
        linked_revision = _get_published_overview_revision(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            revision_id=linked_revision_id,
        )
        existing = db.scalar(
            select(LegacyIssueRevisionOverviewHistory).where(
                LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
                LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
                LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
                (
                    (LegacyIssueRevisionOverviewHistory.linked_revision_id == linked_revision.id)
                    | (
                        LegacyIssueRevisionOverviewHistory.linked_revision_id.is_(None)
                        & (
                            LegacyIssueRevisionOverviewHistory.revision_no
                            == linked_revision.revision_no
                        )
                    )
                ),
            )
        )
        if existing is not None:
            raise localized_http_exception(
                status_code=409,
                code="legacy_issues.revision_overview_history_exists",
            )
    _ensure_overview_revision_no_available(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_no=revision_no,
        linked_revision_id=linked_revision.id if linked_revision else None,
    )
    minimum_sort_order = db.scalar(
        select(func.min(LegacyIssueRevisionOverviewHistory.sort_order)).where(
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
        )
    )
    row = LegacyIssueRevisionOverviewHistory(
        id=new_id(),
        workspace_id=workspace.id,
        dataset_key=dataset_key,
        linked_revision_id=linked_revision.id if linked_revision else None,
        origin="system" if linked_revision else "manual",
        revision_no=revision_no,
        revision_label=str(revision_no) if revision_no is not None else "-",
        summary=summary,
        revised_on=revised_on,
        vehicle_models=vehicle_models,
        source_filename=None,
        source_sha256=None,
        source_sheet=None,
        source_row=None,
        sort_order=(minimum_sort_order - 1) if minimum_sort_order is not None else 0,
    )
    row.author_user_id, row.author_name = _resolve_overview_history_actor(
        db,
        workspace=workspace,
        existing_user_id=None,
        existing_name=None,
        submitted_user_id=author_user_id,
        submitted_name=author_name,
    )
    row.reviewer_user_id, row.reviewer_name = _resolve_overview_history_actor(
        db,
        workspace=workspace,
        existing_user_id=None,
        existing_name=None,
        submitted_user_id=reviewer_user_id,
        submitted_name=reviewer_name,
    )
    row.approver_user_id, row.approver_name = _resolve_overview_history_actor(
        db,
        workspace=workspace,
        existing_user_id=None,
        existing_name=None,
        submitted_user_id=approver_user_id,
        submitted_name=approver_name,
    )
    db.add(row)
    add_revision_event(
        db,
        workspace=workspace,
        revision=latest_revision,
        user=user,
        action="overview_history_created",
        note=summary,
        details={"history": _overview_history_snapshot(row)},
    )
    _flush_overview_history_mutation(db)
    return row


def update_revision_overview_history(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    history_id: str,
    user: User,
    revision_no: int | None,
    summary: str | None,
    revised_on: date | None,
    vehicle_models: str | None,
    author_user_id: str | None,
    reviewer_user_id: str | None,
    approver_user_id: str | None,
    author_name: str | None,
    reviewer_name: str | None,
    approver_name: str | None,
) -> LegacyIssueRevisionOverviewHistory:
    _require_overview_history_admin(db, user=user)
    row = db.scalar(
        select(LegacyIssueRevisionOverviewHistory)
        .where(
            LegacyIssueRevisionOverviewHistory.id == history_id,
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
        )
        .with_for_update()
    )
    if row is None or row.deleted_at is not None:
        raise localized_http_exception(
            status_code=404,
            code="legacy_issues.revision_not_found",
        )
    latest_revision = _require_overview_history_event_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
    )
    previous = _overview_history_snapshot(row)
    _link_overview_history_to_matching_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        row=row,
    )
    _ensure_overview_revision_no_available(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_no=revision_no,
        linked_revision_id=row.linked_revision_id,
        exclude_history_id=row.id,
    )
    row.revision_no = revision_no
    row.revision_label = str(revision_no) if revision_no is not None else "-"
    row.summary = summary
    row.revised_on = revised_on
    row.vehicle_models = vehicle_models
    row.author_user_id, row.author_name = _resolve_overview_history_actor(
        db,
        workspace=workspace,
        existing_user_id=row.author_user_id,
        existing_name=row.author_name,
        submitted_user_id=author_user_id,
        submitted_name=author_name,
    )
    row.reviewer_user_id, row.reviewer_name = _resolve_overview_history_actor(
        db,
        workspace=workspace,
        existing_user_id=row.reviewer_user_id,
        existing_name=row.reviewer_name,
        submitted_user_id=reviewer_user_id,
        submitted_name=reviewer_name,
    )
    row.approver_user_id, row.approver_name = _resolve_overview_history_actor(
        db,
        workspace=workspace,
        existing_user_id=row.approver_user_id,
        existing_name=row.approver_name,
        submitted_user_id=approver_user_id,
        submitted_name=approver_name,
    )
    row.updated_at = utcnow_naive()
    db.add(row)
    add_revision_event(
        db,
        workspace=workspace,
        revision=latest_revision,
        user=user,
        action="overview_history_updated",
        note=summary,
        details={
            "history_id": row.id,
            "previous": previous,
            "updated": _overview_history_snapshot(row),
            "source_filename": row.source_filename,
            "source_sha256": row.source_sha256,
            "source_sheet": row.source_sheet,
            "source_row": row.source_row,
        },
    )
    _flush_overview_history_mutation(db)
    return row


def delete_revision_overview_history(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    history_id: str,
    user: User,
) -> LegacyIssueRevisionOverviewHistory:
    _require_overview_history_admin(db, user=user)
    row = db.scalar(
        select(LegacyIssueRevisionOverviewHistory)
        .where(
            LegacyIssueRevisionOverviewHistory.id == history_id,
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
        )
        .with_for_update()
    )
    if row is None:
        raise localized_http_exception(
            status_code=404,
            code="legacy_issues.revision_not_found",
        )
    if row.deleted_at is not None:
        return row
    latest_revision = _require_overview_history_event_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
    )
    previous = _overview_history_snapshot(row)
    _link_overview_history_to_matching_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        row=row,
    )
    row.deleted_at = utcnow_naive()
    row.deleted_by_id = user.id
    row.updated_at = row.deleted_at
    db.add(row)
    add_revision_event(
        db,
        workspace=workspace,
        revision=latest_revision,
        user=user,
        action="overview_history_deleted",
        note=row.summary,
        details={
            "history_id": row.id,
            "previous": previous,
            "deleted": _overview_history_snapshot(row),
        },
    )
    db.flush()
    return row


def hide_revision_from_overview_history(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    revision_id: str,
    user: User,
) -> LegacyIssueRevisionOverviewHistory:
    _require_overview_history_admin(db, user=user)
    revision = _get_published_overview_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_id=revision_id,
    )
    existing = db.scalar(
        select(LegacyIssueRevisionOverviewHistory)
        .where(
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
            LegacyIssueRevisionOverviewHistory.linked_revision_id == revision.id,
            LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
        )
        .order_by(LegacyIssueRevisionOverviewHistory.created_at.desc())
    )
    if existing is not None:
        return delete_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=existing.id,
            user=user,
        )
    existing_deleted = db.scalar(
        select(LegacyIssueRevisionOverviewHistory)
        .where(
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
            LegacyIssueRevisionOverviewHistory.linked_revision_id == revision.id,
            LegacyIssueRevisionOverviewHistory.deleted_at.is_not(None),
        )
        .order_by(LegacyIssueRevisionOverviewHistory.created_at.desc())
    )
    if existing_deleted is not None:
        return existing_deleted
    matching_unlinked = db.scalar(
        select(LegacyIssueRevisionOverviewHistory)
        .where(
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
            LegacyIssueRevisionOverviewHistory.linked_revision_id.is_(None),
            LegacyIssueRevisionOverviewHistory.revision_no == revision.revision_no,
            LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
        )
        .order_by(
            LegacyIssueRevisionOverviewHistory.sort_order,
            LegacyIssueRevisionOverviewHistory.created_at,
        )
    )
    if matching_unlinked is not None:
        matching_unlinked.linked_revision_id = revision.id
        return delete_revision_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=matching_unlinked.id,
            user=user,
        )
    minimum_sort_order = db.scalar(
        select(func.min(LegacyIssueRevisionOverviewHistory.sort_order)).where(
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
        )
    )
    now = utcnow_naive()
    row = LegacyIssueRevisionOverviewHistory(
        id=new_id(),
        workspace_id=workspace.id,
        dataset_key=dataset_key,
        linked_revision_id=revision.id,
        origin="system",
        revision_no=revision.revision_no,
        revision_label=str(revision.revision_no) if revision.revision_no is not None else "-",
        summary=revision.note,
        revised_on=revision.published_at.date() if revision.published_at else None,
        source_filename=None,
        source_sha256=None,
        source_sheet=None,
        source_row=None,
        sort_order=(minimum_sort_order - 1) if minimum_sort_order is not None else 0,
        deleted_at=now,
        deleted_by_id=user.id,
        updated_at=now,
    )
    db.add(row)
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="overview_history_deleted",
        note=row.summary,
        details={
            "history_id": row.id,
            "previous": None,
            "deleted": _overview_history_snapshot(row),
        },
    )
    db.flush()
    return row


def get_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    revision_id: str,
    for_update: bool = False,
) -> LegacyIssueDataRevision:
    statement = (
        select(LegacyIssueDataRevision)
        .options(
            selectinload(LegacyIssueDataRevision.locked_by),
            selectinload(LegacyIssueDataRevision.created_by),
            selectinload(LegacyIssueDataRevision.published_by),
            selectinload(LegacyIssueDataRevision.canceled_by),
            selectinload(LegacyIssueDataRevision.reviewer),
            selectinload(LegacyIssueDataRevision.approver),
            selectinload(LegacyIssueDataRevision.review_requested_by),
            selectinload(LegacyIssueDataRevision.approval_requested_by),
            selectinload(LegacyIssueDataRevision.reviewed_by),
            selectinload(LegacyIssueDataRevision.approved_by),
        )
        .where(
            LegacyIssueDataRevision.id == revision_id,
            LegacyIssueDataRevision.workspace_id == workspace.id,
            LegacyIssueDataRevision.dataset_key == dataset_key,
        )
    )
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    revision = db.scalar(statement)
    if revision is None:
        raise localized_http_exception(status_code=404, code="legacy_issues.revision_not_found")
    return revision


def get_latest_published_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
) -> LegacyIssueDataRevision | None:
    return db.scalar(
        select(LegacyIssueDataRevision)
        .where(
            LegacyIssueDataRevision.workspace_id == workspace.id,
            LegacyIssueDataRevision.dataset_key == dataset_key,
            LegacyIssueDataRevision.status == REVISION_STATUS_PUBLISHED,
        )
        .order_by(
            LegacyIssueDataRevision.revision_no.desc().nullslast(),
            LegacyIssueDataRevision.published_at.desc().nullslast(),
            LegacyIssueDataRevision.created_at.desc(),
        )
        .limit(1)
    )


def get_active_draft_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    for_update: bool = False,
) -> LegacyIssueDataRevision | None:
    statement = (
        select(LegacyIssueDataRevision)
        .options(selectinload(LegacyIssueDataRevision.locked_by))
        .where(
            LegacyIssueDataRevision.workspace_id == workspace.id,
            LegacyIssueDataRevision.dataset_key == dataset_key,
            LegacyIssueDataRevision.status == REVISION_STATUS_DRAFT,
        )
        .order_by(LegacyIssueDataRevision.created_at.desc())
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return db.scalar(statement)


def ensure_initial_published_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User | None = None,
) -> LegacyIssueDataRevision:
    existing = get_latest_published_revision(db, workspace=workspace, dataset_key=dataset_key)
    if existing is not None:
        ensure_revision_partition(db, existing)
        if existing.dataset_key in REVISION_MEETING_DATASET_KEYS:
            ensure_published_revision_overview_history(
                db,
                workspace=workspace,
                revision=existing,
            )
        return existing
    db.scalar(select(Workspace.id).where(Workspace.id == workspace.id).with_for_update())
    existing = get_latest_published_revision(db, workspace=workspace, dataset_key=dataset_key)
    if existing is not None:
        ensure_revision_partition(db, existing)
        if existing.dataset_key in REVISION_MEETING_DATASET_KEYS:
            ensure_published_revision_overview_history(
                db,
                workspace=workspace,
                revision=existing,
            )
        return existing
    now = utcnow_naive()
    revision = LegacyIssueDataRevision(
        id=new_id(),
        workspace_id=workspace.id,
        dataset_key=dataset_key,
        revision_no=1,
        status=REVISION_STATUS_PUBLISHED,
        note="Initial revision",
        created_by_id=user.id if user else None,
        published_by_id=user.id if user else None,
        created_at=now,
        updated_at=now,
        published_at=now,
    )
    ensure_revision_partition(db, revision)
    db.add(revision)
    db.flush()
    if revision.dataset_key in REVISION_MEETING_DATASET_KEYS:
        ensure_published_revision_overview_history(
            db,
            workspace=workspace,
            revision=revision,
        )
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="initial_publish",
        note=revision.note,
    )
    return revision


def resolve_read_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    revision_id: str | None = None,
) -> RevisionContext:
    latest_published = ensure_initial_published_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
    )
    active_draft = get_active_draft_revision(db, workspace=workspace, dataset_key=dataset_key)
    current = (
        get_revision(db, workspace=workspace, dataset_key=dataset_key, revision_id=revision_id)
        if revision_id
        else latest_published
    )
    return RevisionContext(
        current=current,
        latest_published=latest_published,
        active_draft=active_draft,
    )


def require_draft_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    revision_id: str | None = None,
) -> LegacyIssueDataRevision:
    revision = (
        get_revision(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            revision_id=revision_id,
            for_update=True,
        )
        if revision_id
        else get_active_draft_revision(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            for_update=True,
        )
    )
    if revision is None or revision.status != REVISION_STATUS_DRAFT:
        raise localized_http_exception(
            status_code=409, code="legacy_issues.revision_draft_required"
        )
    return revision


def require_draft_revision_editor(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User,
    revision_id: str | None = None,
) -> LegacyIssueDataRevision:
    revision = require_draft_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_id=revision_id,
    )
    owner_id = draft_revision_owner_id(revision)
    if owner_id != user.id:
        raise localized_http_exception(status_code=403, code="legacy_issues.revision_locked")
    return revision


def draft_revision_owner_id(revision: LegacyIssueDataRevision) -> str | None:
    return revision.locked_by_id


def invalidate_revision_approval_for_content_change(
    db: Session,
    *,
    workspace: Workspace,
    revision: LegacyIssueDataRevision,
    user: User,
) -> bool:
    if revision.status != REVISION_STATUS_DRAFT:
        return False
    revision.updated_at = utcnow_naive()
    db.add(revision)
    workflow_fields = (
        "review_requested_by_id",
        "review_requested_at",
        "approval_requested_by_id",
        "approval_requested_at",
        "reviewed_by_id",
        "reviewed_at",
        "approved_by_id",
        "approved_at",
    )
    if not any(getattr(revision, field) is not None for field in workflow_fields):
        db.flush()
        return False
    for field in workflow_fields:
        setattr(revision, field, None)
    db.flush()
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="approval_reset",
    )
    return True


def create_draft_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User,
    base_revision_id: str | None = None,
    note: str | None = None,
) -> tuple[LegacyIssueDataRevision, bool]:
    active = get_active_draft_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        for_update=True,
    )
    if active is not None:
        ensure_revision_partition(db, active)
        if active.locked_by_id is None:
            now = utcnow_naive()
            active.locked_by_id = user.id
            active.updated_at = now
            db.add(active)
            db.flush()
            add_revision_event(
                db,
                workspace=workspace,
                revision=active,
                user=user,
                action="draft_edit_start",
            )
        return active, False
    base_revision = (
        get_revision(db, workspace=workspace, dataset_key=dataset_key, revision_id=base_revision_id)
        if base_revision_id
        else ensure_initial_published_revision(
            db, workspace=workspace, dataset_key=dataset_key, user=user
        )
    )
    if base_revision.status != REVISION_STATUS_PUBLISHED:
        raise localized_http_exception(
            status_code=409, code="legacy_issues.revision_restore_source_invalid"
        )
    ensure_revision_partition(db, base_revision)
    now = utcnow_naive()
    revision = LegacyIssueDataRevision(
        id=new_id(),
        workspace_id=workspace.id,
        dataset_key=dataset_key,
        revision_no=None,
        status=REVISION_STATUS_DRAFT,
        base_revision_id=base_revision.id,
        note=note,
        locked_by_id=user.id,
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    ensure_revision_partition(db, revision)
    db.add(revision)
    db.flush()
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="draft_create",
        note=note,
        details={
            "base_revision_id": base_revision.id,
            "base_revision_no": base_revision.revision_no,
        },
    )
    return revision, True


def release_draft_revision_editing(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User,
    revision_id: str,
) -> LegacyIssueDataRevision:
    revision = require_draft_revision_editor(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        user=user,
        revision_id=revision_id,
    )
    revision.locked_by_id = None
    revision.updated_at = utcnow_naive()
    db.add(revision)
    db.flush()
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="draft_save",
    )
    return revision


def publish_draft_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User,
    revision_id: str,
    note: str | None = None,
) -> LegacyIssueDataRevision:
    revision = require_draft_revision_editor(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        user=user,
        revision_id=revision_id,
    )
    require_revision_publish_approval(revision)
    next_revision_no = (
        int(
            db.scalar(
                select(func.max(LegacyIssueDataRevision.revision_no)).where(
                    LegacyIssueDataRevision.workspace_id == workspace.id,
                    LegacyIssueDataRevision.dataset_key == dataset_key,
                    LegacyIssueDataRevision.status == REVISION_STATUS_PUBLISHED,
                )
            )
            or 0
        )
        + 1
    )
    now = utcnow_naive()
    revision.status = REVISION_STATUS_PUBLISHED
    revision.revision_no = next_revision_no
    revision.note = note if note is not None else revision.note
    revision.locked_by_id = None
    revision.published_by_id = user.id
    revision.published_at = now
    revision.updated_at = now
    db.add(revision)
    db.flush()
    if revision.dataset_key in REVISION_MEETING_DATASET_KEYS:
        ensure_published_revision_overview_history(
            db,
            workspace=workspace,
            revision=revision,
        )
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="publish",
        note=note,
        details={"revision_no": next_revision_no},
    )
    return revision


def ensure_published_revision_overview_history(
    db: Session,
    *,
    workspace: Workspace,
    revision: LegacyIssueDataRevision,
) -> LegacyIssueRevisionOverviewHistory:
    """Ensure a published revision has one stable overview row without reviving hidden data."""

    if (
        revision.workspace_id != workspace.id
        or revision.status != REVISION_STATUS_PUBLISHED
        or revision.dataset_key not in REVISION_MEETING_DATASET_KEYS
    ):
        raise localized_http_exception(
            status_code=404,
            code="legacy_issues.revision_not_found",
        )
    linked = db.scalar(
        select(LegacyIssueRevisionOverviewHistory)
        .where(
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == revision.dataset_key,
            LegacyIssueRevisionOverviewHistory.linked_revision_id == revision.id,
        )
        .order_by(
            LegacyIssueRevisionOverviewHistory.deleted_at.asc().nulls_first(),
            LegacyIssueRevisionOverviewHistory.created_at.asc(),
        )
        .limit(1)
        .with_for_update()
    )
    if linked is not None:
        return linked

    matching_active = db.scalar(
        select(LegacyIssueRevisionOverviewHistory)
        .where(
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == revision.dataset_key,
            LegacyIssueRevisionOverviewHistory.linked_revision_id.is_(None),
            LegacyIssueRevisionOverviewHistory.revision_no == revision.revision_no,
            LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
        )
        .order_by(
            LegacyIssueRevisionOverviewHistory.sort_order.asc(),
            LegacyIssueRevisionOverviewHistory.created_at.asc(),
        )
        .limit(1)
        .with_for_update()
    )
    if matching_active is not None:
        matching_active.linked_revision_id = revision.id
        matching_active.updated_at = utcnow_naive()
        db.add(matching_active)
        db.flush()
        return matching_active

    minimum_sort_order = db.scalar(
        select(func.min(LegacyIssueRevisionOverviewHistory.sort_order)).where(
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == revision.dataset_key,
        )
    )
    author_user_id = revision.published_by_id or revision.created_by_id
    reviewer_user_id = revision.reviewed_by_id or revision.reviewer_id
    approver_user_id = revision.approved_by_id or revision.approver_id
    occupied_revision_no = db.scalar(
        select(LegacyIssueRevisionOverviewHistory.id)
        .where(
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == revision.dataset_key,
            LegacyIssueRevisionOverviewHistory.revision_no == revision.revision_no,
            LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
        )
        .limit(1)
    )
    row = LegacyIssueRevisionOverviewHistory(
        id=new_id(),
        workspace_id=workspace.id,
        dataset_key=revision.dataset_key,
        linked_revision_id=revision.id,
        origin="system",
        revision_no=None if occupied_revision_no is not None else revision.revision_no,
        revision_label=(str(revision.revision_no) if revision.revision_no is not None else "-"),
        summary=revision.note,
        revised_on=revision.published_at.date() if revision.published_at else None,
        author_user_id=author_user_id,
        reviewer_user_id=reviewer_user_id,
        approver_user_id=approver_user_id,
        author_name=_overview_history_user_snapshot(db, author_user_id),
        reviewer_name=_overview_history_user_snapshot(db, reviewer_user_id),
        approver_name=_overview_history_user_snapshot(db, approver_user_id),
        source_filename=None,
        source_sha256=None,
        source_sheet=None,
        source_row=None,
        sort_order=(minimum_sort_order - 1) if minimum_sort_order is not None else 0,
    )
    db.add(row)
    db.flush()
    return row


def _overview_history_user_snapshot(db: Session, user_id: str | None) -> str | None:
    user = db.get(User, user_id) if user_id is not None else None
    return _user_snapshot_name(user) if user is not None else None


def update_revision_note(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    revision_id: str,
    note: str | None,
) -> LegacyIssueDataRevision:
    revision = get_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_id=revision_id,
    )
    if revision.status == REVISION_STATUS_CANCELED:
        raise localized_http_exception(status_code=409, code="legacy_issues.revision_canceled")
    revision.note = note
    revision.updated_at = utcnow_naive()
    db.add(revision)
    db.flush()
    return revision


def update_revision_approval_assignees(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User,
    revision_id: str,
    reviewer_id: str | None,
    approver_id: str | None,
) -> LegacyIssueDataRevision:
    revision = require_draft_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_id=revision_id,
    )
    if revision.locked_by_id not in {None, user.id}:
        raise localized_http_exception(status_code=403, code="legacy_issues.revision_locked")
    _require_workspace_active_user(db, workspace=workspace, user_id=reviewer_id)
    _require_workspace_active_user(db, workspace=workspace, user_id=approver_id)

    reviewer_changed = reviewer_id != revision.reviewer_id
    approver_changed = approver_id != revision.approver_id
    if not reviewer_changed and not approver_changed:
        return revision

    now = utcnow_naive()
    if reviewer_changed:
        revision.reviewer_id = reviewer_id
        revision.review_requested_by_id = None
        revision.review_requested_at = None
        revision.reviewed_by_id = None
        revision.reviewed_at = None
    if approver_changed:
        revision.approver_id = approver_id
        revision.approval_requested_by_id = None
        revision.approval_requested_at = None
        revision.approved_by_id = None
        revision.approved_at = None
    revision.updated_at = now
    db.add(revision)
    db.flush()
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="approval_assignees_update",
        details={"reviewer_id": reviewer_id, "approver_id": approver_id},
    )
    return revision


def request_revision_approval(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User,
    revision_id: str,
) -> tuple[LegacyIssueDataRevision, list[tuple[str, User]]]:
    revision = require_draft_revision_editor(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        user=user,
        revision_id=revision_id,
    )
    recipients: list[tuple[str, User]] = []
    now = utcnow_naive()
    reviewer = _require_workspace_active_user(
        db,
        workspace=workspace,
        user_id=revision.reviewer_id,
        required=False,
    )
    approver = _require_workspace_active_user(
        db,
        workspace=workspace,
        user_id=revision.approver_id,
        required=False,
    )
    if reviewer is not None and revision.reviewed_at is None:
        revision.review_requested_by_id = user.id
        revision.review_requested_at = now
        recipients.append(("review", reviewer))
    if approver is not None and revision.approved_at is None:
        revision.approval_requested_by_id = user.id
        revision.approval_requested_at = now
        recipients.append(("approval", approver))
    if not recipients:
        raise localized_http_exception(
            status_code=409, code="legacy_issues.revision_request_target_required"
        )
    revision.updated_at = now
    db.add(revision)
    db.flush()
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="approval_request",
        details={"roles": [role for role, _recipient in recipients]},
    )
    return revision, recipients


def complete_revision_review(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User,
    revision_id: str,
) -> LegacyIssueDataRevision:
    revision = require_draft_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_id=revision_id,
    )
    if revision.reviewer_id != user.id:
        raise localized_http_exception(
            status_code=403, code="legacy_issues.revision_review_assignee_required"
        )
    now = utcnow_naive()
    revision.reviewed_by_id = user.id
    revision.reviewed_at = now
    revision.updated_at = now
    db.add(revision)
    db.flush()
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="review_complete",
    )
    return revision


def complete_revision_approval(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    user: User,
    revision_id: str,
) -> LegacyIssueDataRevision:
    revision = require_draft_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_id=revision_id,
    )
    if revision.approver_id != user.id:
        raise localized_http_exception(
            status_code=403, code="legacy_issues.revision_approval_assignee_required"
        )
    now = utcnow_naive()
    revision.approved_by_id = user.id
    revision.approved_at = now
    revision.updated_at = now
    db.add(revision)
    db.flush()
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="approval_complete",
    )
    return revision


def require_revision_publish_approval(revision: LegacyIssueDataRevision) -> None:
    if not (
        revision.reviewer_id
        and revision.approver_id
        and revision.reviewed_at is not None
        and revision.approved_at is not None
    ):
        raise localized_http_exception(
            status_code=409, code="legacy_issues.revision_approval_required"
        )


def _require_workspace_active_user(
    db: Session,
    *,
    workspace: Workspace,
    user_id: str | None,
    required: bool = True,
) -> User | None:
    if user_id is None:
        return None
    user = db.scalar(
        select(User)
        .join(WorkspaceUserBinding, WorkspaceUserBinding.user_id == User.id)
        .where(
            User.id == user_id,
            User.status == "active",
            WorkspaceUserBinding.workspace_id == workspace.id,
        )
        .limit(1)
    )
    if user is None and required:
        raise localized_http_exception(status_code=404, code="admin.workspace_member_not_found")
    return user


def _user_snapshot_name(user: User) -> str:
    return user.display_name or user.full_name or user.email


def _require_overview_history_admin(db: Session, *, user: User) -> None:
    if not is_platform_admin_user(user, db):
        raise localized_http_exception(
            status_code=403,
            code="admin.platform_admin_required",
        )


def _require_overview_history_event_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
) -> LegacyIssueDataRevision:
    latest_revision = get_latest_published_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
    )
    if latest_revision is None:
        raise localized_http_exception(
            status_code=404,
            code="legacy_issues.revision_not_found",
        )
    return latest_revision


def _get_published_overview_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    revision_id: str,
) -> LegacyIssueDataRevision:
    revision = db.scalar(
        select(LegacyIssueDataRevision)
        .where(
            LegacyIssueDataRevision.id == revision_id,
            LegacyIssueDataRevision.workspace_id == workspace.id,
            LegacyIssueDataRevision.dataset_key == dataset_key,
            LegacyIssueDataRevision.status == REVISION_STATUS_PUBLISHED,
        )
        .with_for_update()
    )
    if revision is None:
        raise localized_http_exception(
            status_code=404,
            code="legacy_issues.revision_not_found",
        )
    return revision


def _link_overview_history_to_matching_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    row: LegacyIssueRevisionOverviewHistory,
) -> None:
    if row.linked_revision_id is not None or row.revision_no is None:
        return
    revision = db.scalar(
        select(LegacyIssueDataRevision)
        .where(
            LegacyIssueDataRevision.workspace_id == workspace.id,
            LegacyIssueDataRevision.dataset_key == dataset_key,
            LegacyIssueDataRevision.status == REVISION_STATUS_PUBLISHED,
            LegacyIssueDataRevision.revision_no == row.revision_no,
        )
        .with_for_update()
    )
    if revision is not None:
        row.linked_revision_id = revision.id


def _ensure_overview_revision_no_available(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    revision_no: int | None,
    linked_revision_id: str | None = None,
    exclude_history_id: str | None = None,
) -> None:
    if revision_no is None:
        return
    with db.no_autoflush:
        canonical_revision_id = db.scalar(
            select(LegacyIssueDataRevision.id).where(
                LegacyIssueDataRevision.workspace_id == workspace.id,
                LegacyIssueDataRevision.dataset_key == dataset_key,
                LegacyIssueDataRevision.status == REVISION_STATUS_PUBLISHED,
                LegacyIssueDataRevision.revision_no == revision_no,
            )
        )
    if canonical_revision_id is not None and canonical_revision_id != linked_revision_id:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.revision_overview_number_exists",
        )
    statement = select(LegacyIssueRevisionOverviewHistory.id).where(
        LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
        LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
        LegacyIssueRevisionOverviewHistory.revision_no == revision_no,
        LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
    )
    if exclude_history_id is not None:
        statement = statement.where(LegacyIssueRevisionOverviewHistory.id != exclude_history_id)
    with db.no_autoflush:
        existing_history_id = db.scalar(statement.limit(1))
    if existing_history_id is not None:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.revision_overview_number_exists",
        )


def _flush_overview_history_mutation(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.revision_overview_number_exists",
        ) from error


def _overview_history_snapshot(
    row: LegacyIssueRevisionOverviewHistory,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "linked_revision_id": row.linked_revision_id,
        "origin": row.origin,
        "revision_no": row.revision_no,
        "revision_label": row.revision_label,
        "summary": row.summary,
        "revised_on": row.revised_on.isoformat() if row.revised_on else None,
        "vehicle_models": row.vehicle_models,
        "author_user_id": row.author_user_id,
        "reviewer_user_id": row.reviewer_user_id,
        "approver_user_id": row.approver_user_id,
        "author_name": row.author_name,
        "reviewer_name": row.reviewer_name,
        "approver_name": row.approver_name,
        "source_filename": row.source_filename,
        "source_sha256": row.source_sha256,
        "source_sheet": row.source_sheet,
        "source_row": row.source_row,
        "sort_order": row.sort_order,
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        "deleted_by_id": row.deleted_by_id,
    }


def _resolve_overview_history_actor(
    db: Session,
    *,
    workspace: Workspace,
    existing_user_id: str | None,
    existing_name: str | None,
    submitted_user_id: str | None,
    submitted_name: str | None,
) -> tuple[str | None, str | None]:
    if submitted_user_id is None:
        return None, submitted_name
    if submitted_user_id == existing_user_id:
        return existing_user_id, existing_name
    selected_user = _require_workspace_active_user(
        db,
        workspace=workspace,
        user_id=submitted_user_id,
    )
    if selected_user is None:  # pragma: no cover - required lookup raises first
        raise localized_http_exception(
            status_code=404,
            code="admin.workspace_member_not_found",
        )
    return selected_user.id, _user_snapshot_name(selected_user)


def cancel_draft_revision(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    module_key: str,
    user: User,
    revision_id: str,
    note: str | None = None,
    force: bool = False,
) -> LegacyIssueDataRevision:
    revision = require_draft_revision(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        revision_id=revision_id,
    )
    previous_locked_by_id = draft_revision_owner_id(revision)
    previous_locked_by_name = (
        revision.locked_by.full_name if revision.locked_by is not None else None
    )
    if previous_locked_by_id is None:
        raise localized_http_exception(status_code=403, code="legacy_issues.revision_locked")
    forced_by_authorized_editor = previous_locked_by_id != user.id
    authorization_source: str | None = None
    if forced_by_authorized_editor and not can_user_direct_edit_module(
        db,
        workspace=workspace,
        user=user,
        module_key=module_key,
    ):
        raise localized_http_exception(status_code=403, code="legacy_issues.revision_locked")
    if forced_by_authorized_editor:
        authorization_source = (
            "platform_admin" if is_platform_admin_user(user, db) else "module_direct_editor"
        )
    if forced_by_authorized_editor and not force:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.revision_force_cancel_confirmation_required",
        )
    now = utcnow_naive()
    revision.status = REVISION_STATUS_CANCELED
    revision.note = note if note is not None else revision.note
    revision.locked_by_id = None
    revision.canceled_by_id = user.id
    revision.canceled_at = now
    revision.updated_at = now
    db.add(revision)
    db.flush()
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=user,
        action="force_cancel" if forced_by_authorized_editor else "cancel",
        note=note,
        details=(
            {
                "forced_by_authorized_editor": True,
                "authorization_source": authorization_source,
                "module_key": module_key,
                "previous_locked_by_id": previous_locked_by_id,
                "previous_locked_by_name": previous_locked_by_name,
                "created_by_id": revision.created_by_id,
            }
            if forced_by_authorized_editor
            else None
        ),
    )
    if forced_by_authorized_editor:
        record_audit_log(
            db,
            action="legacy_issues.revision.force_cancel",
            entity_kind="legacy_issue_data_revision",
            entity_id=revision.id,
            actor_user_id=user.id,
            summary="Authorized module editor force-canceled an active legacy issue draft.",
            payload={
                "workspace_id": workspace.id,
                "dataset_key": dataset_key,
                "module_key": module_key,
                "authorization_source": authorization_source,
                "previous_locked_by_id": previous_locked_by_id,
                "previous_locked_by_name": previous_locked_by_name,
                "created_by_id": revision.created_by_id,
            },
        )
    return revision


def add_revision_event(
    db: Session,
    *,
    workspace: Workspace,
    revision: LegacyIssueDataRevision,
    user: User | None,
    action: str,
    note: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        LegacyIssueDataRevisionEvent(
            id=new_id(),
            workspace_id=workspace.id,
            revision_id=revision.id,
            dataset_key=revision.dataset_key,
            action=action,
            actor_user_id=user.id if user else None,
            note=note,
            details=details,
            created_at=utcnow_naive(),
        )
    )
