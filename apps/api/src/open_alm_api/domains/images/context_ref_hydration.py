"""DB-backed hydration policy for image generation context references."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import Team, User, Workspace
from open_alm_api.domains.docs.models import NativeDoc, NativeDocPage
from open_alm_api.domains.docs.service import can_read_native_doc_for_rag
from open_alm_api.domains.images.context_refs import (
    DOC_CONTEXT_PAGE_LIMIT,
    TASK_LIST_CONTEXT_TASK_LIMIT,
    doc_page_snapshot,
    hydrated_context_ref,
    meeting_snapshot,
    normalize_context_ref,
    task_list_snapshot,
    task_snapshot,
)
from open_alm_api.domains.meeting.models import Meeting
from open_alm_api.domains.meeting.service import can_read_meeting_for_rag
from open_alm_api.domains.pms.access import can_read_task_for_rag, has_list_access
from open_alm_api.domains.pms.models import Task, TaskList


def hydrate_context_refs(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    raw_refs: list[Any],
) -> list[dict[str, Any]]:
    """Refresh context ref snapshots by re-loading accessible entities."""

    hydrated: list[dict[str, Any]] = []
    for ref in raw_refs or []:
        normalized = normalize_context_ref(ref)
        if normalized is None:
            continue
        kind, ref_id = normalized
        snapshot = _snapshot_for_ref(
            db,
            workspace=workspace,
            user=user,
            kind=kind,
            ref_id=ref_id,
        )
        if snapshot is None:
            continue
        hydrated.append(
            hydrated_context_ref(kind=kind, ref_id=ref_id, snapshot=snapshot, raw_ref=ref)
        )
    return hydrated


def _snapshot_for_ref(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    kind: str,
    ref_id: str,
) -> dict[str, Any] | None:
    if kind == "meeting":
        return _meeting_context_snapshot(db, workspace=workspace, user=user, ref_id=ref_id)
    if kind == "doc":
        return _doc_context_snapshot(db, workspace=workspace, user=user, ref_id=ref_id)
    if kind == "task":
        return _task_context_snapshot(db, workspace=workspace, user=user, ref_id=ref_id)
    return None


def _meeting_context_snapshot(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    ref_id: str,
) -> dict[str, Any] | None:
    if not can_read_meeting_for_rag(
        db,
        user=user,
        workspace_id=workspace.id,
        meeting_id=ref_id,
    ):
        return None
    meeting = db.scalar(
        select(Meeting).where(
            Meeting.id == ref_id,
            Meeting.workspace_id == workspace.id,
        )
    )
    return meeting_snapshot(meeting) if meeting is not None else None


def _doc_context_snapshot(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    ref_id: str,
) -> dict[str, Any] | None:
    if not can_read_native_doc_for_rag(db, user=user, doc_id=ref_id):
        return None
    doc = db.scalar(
        select(NativeDoc).where(
            NativeDoc.id == ref_id,
            NativeDoc.workspace_id == workspace.id,
            NativeDoc.trashed_at.is_(None),
        )
    )
    if doc is None:
        return None
    pages = list(
        db.scalars(
            select(NativeDocPage)
            .where(
                NativeDocPage.doc_id == doc.id,
                NativeDocPage.trashed_at.is_(None),
            )
            .order_by(NativeDocPage.sort_order.asc())
            .limit(DOC_CONTEXT_PAGE_LIMIT)
        )
    )
    return doc_page_snapshot(doc, pages)


def _task_context_snapshot(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    ref_id: str,
) -> dict[str, Any] | None:
    task_list = db.scalar(
        select(TaskList)
        .join(Team, Team.id == TaskList.team_id)
        .where(
            TaskList.id == ref_id,
            Team.workspace_id == workspace.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
        )
    )
    if task_list is not None:
        return _task_list_context_snapshot(db, user=user, task_list=task_list)
    return _single_task_context_snapshot(db, workspace=workspace, user=user, ref_id=ref_id)


def _task_list_context_snapshot(
    db: Session,
    *,
    user: User,
    task_list: TaskList,
) -> dict[str, Any] | None:
    if not has_list_access(db, user, task_list.id):
        return None
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.list_id == task_list.id, Task.archived.is_(False))
            .order_by(Task.created_at.desc())
            .limit(TASK_LIST_CONTEXT_TASK_LIMIT)
        )
    )
    return task_list_snapshot(task_list, tasks)


def _single_task_context_snapshot(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    ref_id: str,
) -> dict[str, Any] | None:
    task = db.scalar(
        select(Task)
        .join(TaskList, TaskList.id == Task.list_id)
        .join(Team, Team.id == TaskList.team_id)
        .where(
            Task.id == ref_id,
            Task.archived.is_(False),
            Team.workspace_id == workspace.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
        )
    )
    if task is None or not can_read_task_for_rag(db, user=user, task_id=task.id):
        return None
    return task_snapshot(task)
