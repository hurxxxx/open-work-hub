from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.auth.models import Team
from aidoo_api.domains.meeting.models import MeetingTaskLink
from aidoo_api.domains.pms.models import Issue, IssueLabel, IssueUserAccess, Label, Milestone, TaskList
from aidoo_api.domains.rag.contracts import RagSyncOperation
from aidoo_api.domains.rag.outbox import enqueue_rag_sync_job, enqueue_rag_visibility_recompute_job
from aidoo_api.domains.rag.pms_projection import PMS_ISSUE_RESOURCE_TYPE
from aidoo_api.domains.search.hooks import (
    enqueue_issue_search_index,
    enqueue_issue_search_index_by_id,
    enqueue_label_issue_search_recompute,
    enqueue_task_list_issue_search_recompute,
)


PMS_MEETING_VISIBILITY_SCOPE = "pms_meeting"
PMS_TASK_LIST_RECOMPUTE_SCOPE = "pms_task_list"
PMS_LABEL_RECOMPUTE_SCOPE = "pms_label"
PMS_MILESTONE_RECOMPUTE_SCOPE = "pms_milestone"


def enqueue_issue_rag_sync(
    db: Session,
    *,
    issue: Issue,
    operation: RagSyncOperation,
) -> None:
    enqueue_issue_search_index(
        db,
        issue=issue,
        operation="delete" if operation == RagSyncOperation.DELETE else "upsert",
    )
    if not get_settings().rag_enabled:
        return
    workspace_id = _load_issue_workspace_id(db, issue_id=issue.id)
    if workspace_id is None:
        return
    enqueue_rag_sync_job(
        db,
        workspace_id=workspace_id,
        resource_type=PMS_ISSUE_RESOURCE_TYPE,
        resource_id=issue.id,
        operation=operation,
    )


def enqueue_issue_rag_sync_by_id(
    db: Session,
    *,
    issue_id: str,
    operation: RagSyncOperation,
) -> None:
    issue = db.get(Issue, issue_id)
    if issue is None:
        return
    enqueue_issue_rag_sync(
        db,
        issue=issue,
        operation=operation,
    )


def enqueue_meeting_issue_visibility_recompute(
    db: Session,
    *,
    meeting_id: str,
    issue_ids: list[str] | None = None,
) -> None:
    for issue_id in _collect_meeting_issue_ids(db, meeting_id=meeting_id, issue_ids=issue_ids):
        enqueue_issue_search_index_by_id(
            db,
            issue_id=issue_id,
            operation="upsert",
        )
    if not get_settings().rag_enabled:
        return
    grouped_issue_ids = _group_issue_ids_by_workspace(db, issue_ids or [])
    for workspace_id, scoped_issue_ids in grouped_issue_ids.items():
        enqueue_rag_visibility_recompute_job(
            db,
            workspace_id=workspace_id,
            scope_type=PMS_MEETING_VISIBILITY_SCOPE,
            scope_id=meeting_id,
            cursor={"issue_ids": scoped_issue_ids, "operation": RagSyncOperation.VISIBILITY_UPDATE.value},
        )


def enqueue_task_list_issue_recompute(
    db: Session,
    *,
    task_list: TaskList,
) -> None:
    enqueue_task_list_issue_search_recompute(db, task_list=task_list)
    if not get_settings().rag_enabled or task_list.team_id is None:
        return
    team = db.get(Team, task_list.team_id)
    if team is None:
        return
    enqueue_rag_visibility_recompute_job(
        db,
        workspace_id=team.workspace_id,
        scope_type=PMS_TASK_LIST_RECOMPUTE_SCOPE,
        scope_id=task_list.id,
        cursor={"operation": RagSyncOperation.UPSERT.value},
    )


def enqueue_label_issue_recompute(
    db: Session,
    *,
    label: Label,
    issue_ids: list[str] | None = None,
) -> None:
    enqueue_label_issue_search_recompute(db, label=label, issue_ids=issue_ids)
    if not get_settings().rag_enabled:
        return
    workspace_id = _load_list_workspace_id(db, list_id=label.list_id)
    if workspace_id is None:
        return
    cursor = {"operation": RagSyncOperation.UPSERT.value}
    normalized_issue_ids = sorted({issue_id for issue_id in issue_ids or [] if issue_id})
    if normalized_issue_ids:
        cursor["issue_ids"] = normalized_issue_ids
    enqueue_rag_visibility_recompute_job(
        db,
        workspace_id=workspace_id,
        scope_type=PMS_LABEL_RECOMPUTE_SCOPE,
        scope_id=label.id,
        cursor=cursor,
    )


def enqueue_milestone_issue_recompute(
    db: Session,
    *,
    milestone: Milestone,
) -> None:
    if not get_settings().rag_enabled:
        return
    workspace_id = _load_list_workspace_id(db, list_id=milestone.list_id)
    if workspace_id is None:
        return
    enqueue_rag_visibility_recompute_job(
        db,
        workspace_id=workspace_id,
        scope_type=PMS_MILESTONE_RECOMPUTE_SCOPE,
        scope_id=milestone.id,
        cursor={"operation": RagSyncOperation.UPSERT.value},
    )


def _group_issue_ids_by_workspace(
    db: Session,
    issue_ids: list[str],
) -> dict[str, list[str]]:
    normalized_issue_ids = sorted({issue_id for issue_id in issue_ids if issue_id})
    if not normalized_issue_ids:
        return {}

    rows = db.execute(
        select(Issue.id, Team.workspace_id)
        .join(TaskList, TaskList.id == Issue.list_id)
        .join(Team, Team.id == TaskList.team_id)
        .where(Issue.id.in_(normalized_issue_ids))
    ).all()
    grouped: dict[str, list[str]] = defaultdict(list)
    for issue_id, workspace_id in rows:
        grouped[str(workspace_id)].append(str(issue_id))
    return {workspace_id: sorted(issue_ids) for workspace_id, issue_ids in grouped.items()}


def _load_issue_workspace_id(
    db: Session,
    *,
    issue_id: str,
) -> str | None:
    return db.scalar(
        select(Team.workspace_id)
        .join(TaskList, TaskList.team_id == Team.id)
        .join(Issue, Issue.list_id == TaskList.id)
        .where(Issue.id == issue_id)
    )


def _load_list_workspace_id(
    db: Session,
    *,
    list_id: str,
) -> str | None:
    return db.scalar(
        select(Team.workspace_id)
        .join(TaskList, TaskList.team_id == Team.id)
        .where(TaskList.id == list_id)
    )


def collect_label_issue_ids(
    db: Session,
    *,
    label_id: str,
) -> list[str]:
    return sorted(
        str(issue_id)
        for issue_id in db.scalars(select(IssueLabel.issue_id).where(IssueLabel.label_id == label_id))
        if issue_id
    )


def _collect_meeting_issue_ids(
    db: Session,
    *,
    meeting_id: str,
    issue_ids: list[str] | None,
) -> list[str]:
    resolved = {str(issue_id) for issue_id in issue_ids or [] if issue_id}
    if not resolved:
        resolved.update(
            str(issue_id)
            for issue_id in db.scalars(select(MeetingTaskLink.issue_id).where(MeetingTaskLink.meeting_id == meeting_id))
            if issue_id
        )
        resolved.update(
            str(issue_id)
            for issue_id in db.scalars(
                select(IssueUserAccess.issue_id).where(
                    IssueUserAccess.granted_by_meeting_id == meeting_id,
                    IssueUserAccess.revoked_at.is_(None),
                )
            )
            if issue_id
        )
    return sorted(resolved)
