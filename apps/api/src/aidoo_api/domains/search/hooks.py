from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.domains.auth.models import Team
from aidoo_api.domains.docs.models import NativeDoc
from aidoo_api.domains.meeting.models import Meeting
from aidoo_api.domains.planner.models import PlannerEvent
from aidoo_api.domains.pms.models import Issue, IssueLabel, Label, TaskList, TaskListStatus
from aidoo_api.domains.search.outbox import enqueue_search_index_job
from aidoo_api.domains.search.schemas import SearchEntityType


def enqueue_doc_search_index(
    db: Session,
    *,
    doc: NativeDoc,
    operation: str = "upsert",
) -> None:
    enqueue_search_index_job(
        db,
        workspace_id=doc.workspace_id,
        entity_type=SearchEntityType.DOC,
        entity_id=doc.id,
        operation=operation,
    )


def enqueue_doc_search_index_by_id(
    db: Session,
    *,
    doc_id: str,
    operation: str = "upsert",
) -> None:
    doc = db.get(NativeDoc, doc_id)
    if doc is None:
        return
    enqueue_doc_search_index(db, doc=doc, operation=operation)


def enqueue_meeting_search_index(
    db: Session,
    *,
    meeting: Meeting,
    operation: str = "upsert",
) -> None:
    enqueue_search_index_job(
        db,
        workspace_id=meeting.workspace_id,
        entity_type=SearchEntityType.MEETING,
        entity_id=meeting.id,
        operation=operation,
    )


def enqueue_meeting_search_index_by_id(
    db: Session,
    *,
    meeting_id: str,
    operation: str = "upsert",
) -> None:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        return
    enqueue_meeting_search_index(db, meeting=meeting, operation=operation)


def enqueue_issue_search_index(
    db: Session,
    *,
    issue: Issue,
    operation: str = "upsert",
) -> None:
    workspace_id = load_issue_workspace_id(db, issue_id=issue.id)
    if workspace_id is None:
        return
    enqueue_search_index_job(
        db,
        workspace_id=workspace_id,
        entity_type=SearchEntityType.PMS_ISSUE,
        entity_id=issue.id,
        operation=operation,
    )


def enqueue_issue_search_index_by_id(
    db: Session,
    *,
    issue_id: str,
    operation: str = "upsert",
) -> None:
    workspace_id = load_issue_workspace_id(db, issue_id=issue_id)
    if workspace_id is None:
        return
    enqueue_search_index_job(
        db,
        workspace_id=workspace_id,
        entity_type=SearchEntityType.PMS_ISSUE,
        entity_id=issue_id,
        operation=operation,
    )


def enqueue_planner_event_search_index(
    db: Session,
    *,
    event: PlannerEvent,
    operation: str = "upsert",
) -> None:
    enqueue_search_index_job(
        db,
        workspace_id=event.workspace_id,
        entity_type=SearchEntityType.PLANNER_EVENT,
        entity_id=event.id,
        operation=operation,
    )


def enqueue_task_list_issue_search_recompute(
    db: Session,
    *,
    task_list: TaskList,
    operation: str = "upsert",
) -> None:
    workspace_id = load_task_list_workspace_id(db, list_id=task_list.id)
    if workspace_id is None:
        return
    issue_ids = db.scalars(select(Issue.id).where(Issue.list_id == task_list.id)).all()
    for issue_id in sorted(issue_id for issue_id in issue_ids if issue_id):
        enqueue_search_index_job(
            db,
            workspace_id=workspace_id,
            entity_type=SearchEntityType.PMS_ISSUE,
            entity_id=str(issue_id),
            operation=operation,
        )


def enqueue_label_issue_search_recompute(
    db: Session,
    *,
    label: Label,
    issue_ids: list[str] | None = None,
    operation: str = "upsert",
) -> None:
    workspace_id = load_task_list_workspace_id(db, list_id=label.list_id)
    if workspace_id is None:
        return
    resolved_issue_ids = issue_ids
    if resolved_issue_ids is None:
        resolved_issue_ids = list(db.scalars(select(IssueLabel.issue_id).where(IssueLabel.label_id == label.id)))
    for issue_id in sorted({issue_id for issue_id in resolved_issue_ids if issue_id}):
        enqueue_search_index_job(
            db,
            workspace_id=workspace_id,
            entity_type=SearchEntityType.PMS_ISSUE,
            entity_id=issue_id,
            operation=operation,
        )


def enqueue_task_list_status_issue_search_recompute(
    db: Session,
    *,
    task_status: TaskListStatus,
    operation: str = "upsert",
) -> None:
    task_list = db.get(TaskList, task_status.list_id)
    if task_list is None:
        return
    enqueue_task_list_issue_search_recompute(db, task_list=task_list, operation=operation)


def load_issue_workspace_id(db: Session, *, issue_id: str) -> str | None:
    return db.scalar(
        select(Team.workspace_id)
        .join(TaskList, TaskList.team_id == Team.id)
        .join(Issue, Issue.list_id == TaskList.id)
        .where(Issue.id == issue_id)
    )


def load_task_list_workspace_id(db: Session, *, list_id: str) -> str | None:
    return db.scalar(
        select(Team.workspace_id)
        .join(TaskList, TaskList.team_id == Team.id)
        .where(TaskList.id == list_id)
    )
