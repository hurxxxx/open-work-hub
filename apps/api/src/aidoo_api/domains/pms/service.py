from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.auth.access import bind_current_workspace
from aidoo_api.domains.auth.models import TeamMember, User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.media.router import sync_embedded_media
from aidoo_api.domains.pms.access import _ensure_issue_readable, _ensure_list_editor
from aidoo_api.domains.pms.rag_sync import enqueue_issue_rag_sync
from aidoo_api.domains.pms.models import (
    Attachment,
    Issue,
    IssueActivityLog,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    Notification,
    TaskList,
    TimeEntry,
)
from aidoo_api.domains.rag.contracts import RagSyncOperation


ISSUE_STATUS_LABELS = {
    "backlog": "Backlog",
    "todo": "Todo",
    "in_progress": "In Progress",
    "done": "Done",
    "canceled": "Canceled",
}
ISSUE_STATUS_PROGRESS = {
    "backlog": 0.0,
    "todo": 0.0,
    "in_progress": 0.5,
    "done": 1.0,
    "canceled": None,
}
PRIORITY_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "critical": "Critical",
}
CATEGORY_PROGRESS = {
    "backlog": 0.0,
    "active": 0.5,
    "done": 1.0,
    "canceled": None,
}


def _router():
    from aidoo_api.domains.pms import router as pms_router

    return pms_router


def _bind_workspace_context(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
) -> None:
    bind_current_workspace(db, workspace)
    if principal.workspace_id != workspace.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PMS principal workspace mismatch.",
        )
    if principal.kind == "user" and principal.user_id not in {None, user.id}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PMS principal user mismatch.",
        )


def _require_user_write_principal(principal: CallerPrincipal) -> None:
    if principal.kind != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PMS write operations require a user principal.",
        )


def _stable_replay_id(approved_call_id: str, suffix: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pms:{approved_call_id}:{suffix}"))


def _space_member_ids(db: Session, space_id: str) -> set[str]:
    return set(db.scalars(select(TeamMember.user_id).where(TeamMember.team_id == space_id)))


def _issue_progress(status_value: str, task_list: TaskList | None = None) -> float | None:
    result = ISSUE_STATUS_PROGRESS.get(status_value)
    if result is not None or status_value in ISSUE_STATUS_PROGRESS:
        return result
    if task_list is not None:
        for list_status in getattr(task_list, "statuses", []):
            if list_status.slug == status_value:
                return CATEGORY_PROGRESS.get(list_status.category, 0.5)
    return 0.5


def _issue_reference(issue: Issue) -> str:
    return f"{issue.task_list.key}-{issue.issue_number}"


def _serialize_issue_labels(issue: Issue) -> list[dict[str, str]]:
    return [
        {
            "id": link.label.id,
            "name": link.label.name,
            "color": link.label.color,
        }
        for link in issue.label_links
    ]


def _serialize_issue_summary(issue: Issue) -> dict[str, Any]:
    return {
        "id": issue.id,
        "list_id": issue.list_id,
        "reference": _issue_reference(issue),
        "title": issue.title,
        "description": issue.description,
        "description_blocks": issue.description_blocks,
        "parent_id": issue.parent_id,
        "subtask_count": len(issue.subtasks) if issue.subtasks else 0,
        "status": issue.status,
        "status_label": ISSUE_STATUS_LABELS.get(issue.status, issue.status.replace("_", " ").title()),
        "priority": issue.priority,
        "priority_label": PRIORITY_LABELS[issue.priority],
        "assignee_id": issue.assignee_id,
        "assignee_name": getattr(issue.assignee, "full_name", None),
        "assignee_ids": [link.user_id for link in getattr(issue, "assignee_links", [])],
        "assignee_names": [getattr(link.user, "full_name", "") for link in getattr(issue, "assignee_links", [])],
        "reporter_id": issue.reporter_id,
        "reporter_name": issue.reporter.full_name,
        "milestone_id": issue.milestone_id,
        "milestone_title": getattr(issue.milestone, "title", None),
        "start_date": issue.start_date,
        "due_date": issue.due_date,
        "board_position": issue.board_position,
        "archived": issue.archived,
        "progress": _issue_progress(issue.status, issue.task_list),
        "comments_count": len(issue.comments),
        "checklist_total": len(issue.checklist_items) if issue.checklist_items else 0,
        "checklist_done": sum(1 for item in issue.checklist_items if item.completed) if issue.checklist_items else 0,
        "estimate_hours": issue.estimate_hours,
        "time_spent_minutes": sum(entry.duration_minutes for entry in issue.time_entries) if issue.time_entries else 0,
        "recurrence_rule": issue.recurrence_rule,
        "labels": _serialize_issue_labels(issue),
        "updated_at": issue.updated_at,
    }


def _serialize_comment_item(comment: IssueComment) -> dict[str, Any]:
    return {
        "id": comment.id,
        "issue_id": comment.issue_id,
        "author_id": comment.author_id,
        "author_name": comment.author.full_name,
        "body": comment.body,
        "body_blocks": comment.body_blocks,
        "created_at": comment.created_at,
    }


def _log_issue_activity(
    db: Session,
    issue_id: str,
    actor_id: str | None,
    action: str,
    message: str,
    *,
    field_name: str | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    stable_key: str | None = None,
) -> None:
    if stable_key is not None and db.get(IssueActivityLog, stable_key) is not None:
        return
    db.add(
        IssueActivityLog(
            id=stable_key or new_id(),
            issue_id=issue_id,
            actor_id=actor_id,
            action=action,
            field_name=field_name,
            from_value=from_value,
            to_value=to_value,
            message=message,
        )
    )


def _create_notification(
    db: Session,
    user_id: str,
    ntype: str,
    title: str,
    body: str,
    *,
    reference_type: str = "issue",
    reference_id: str | None = None,
    stable_key: str | None = None,
) -> None:
    if stable_key is not None and db.get(Notification, stable_key) is not None:
        return
    db.add(
        Notification(
            id=stable_key or new_id(),
            user_id=user_id,
            type=ntype,
            title=title,
            body=body,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    )


def _extract_mentions_from_blocks(blocks: list[dict], out: set[str]) -> None:
    import re

    for block in blocks:
        if not isinstance(block, dict):
            continue
        for content_item in block.get("content", []):
            if not isinstance(content_item, dict):
                continue
            if content_item.get("type") == "mention":
                user_id = content_item.get("props", {}).get("user_id") or content_item.get("attrs", {}).get("id")
                if user_id:
                    out.add(user_id)
            text = content_item.get("text", "")
            if text:
                out.update(re.findall(r"@([0-9a-f-]{36})", text))
        for child in block.get("children", []):
            if isinstance(child, dict):
                _extract_mentions_from_blocks([child], out)


def _next_issue_number(db: Session, list_id: str) -> int:
    current = db.scalar(select(func.max(Issue.issue_number)).where(Issue.list_id == list_id))
    return int(current or 0) + 1


def _next_issue_board_position(db: Session, list_id: str, status_value: str) -> int:
    current = db.scalar(
        select(func.max(Issue.board_position)).where(
            Issue.list_id == list_id,
            Issue.status == status_value,
        )
    )
    return int(current or 0) + 1


def _validate_issue_assignee(db: Session, task_list: TaskList, assignee_id: str | None) -> None:
    if assignee_id is None:
        return
    if task_list.team_id is None or assignee_id not in _space_member_ids(db, task_list.team_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignee must be a task list member.")


def _validate_issue_assignees(
    db: Session,
    task_list: TaskList,
    assignee_ids: list[str],
) -> list[User]:
    if not assignee_ids:
        return []
    if task_list.team_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task list space is not set.")

    member_ids = _space_member_ids(db, task_list.team_id)
    validated_users: list[User] = []
    seen_user_ids: set[str] = set()
    for assignee_id in assignee_ids:
        if assignee_id in seen_user_ids:
            continue
        seen_user_ids.add(assignee_id)
        if assignee_id not in member_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignees must be task list members.",
            )
        assignee = db.scalar(select(User).where(User.id == assignee_id))
        if assignee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        validated_users.append(assignee)
    return validated_users


def _validate_milestone(task_list: TaskList, milestone_id: str | None) -> None:
    if milestone_id is None:
        return
    if milestone_id not in {milestone.id for milestone in task_list.milestones}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Milestone does not belong to this list.")


def _validate_parent_issue(
    db: Session,
    task_list: TaskList,
    parent_id: str | None,
    *,
    issue_id: str | None = None,
) -> None:
    if parent_id is None:
        return

    parent = db.scalar(select(Issue).where(Issue.id == parent_id))
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent issue not found.")
    if parent.list_id != task_list.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent issue must belong to the same list.",
        )
    if issue_id is not None and parent.id == issue_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Issue cannot be its own parent.",
        )

    visited: set[str] = set()
    ancestor: Issue | None = parent
    while ancestor is not None:
        if ancestor.id in visited:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Issue parent relationship cannot contain a cycle.",
            )
        visited.add(ancestor.id)
        if issue_id is not None and ancestor.parent_id == issue_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Issue parent relationship cannot contain a cycle.",
            )
        if ancestor.parent_id is None:
            break
        ancestor = db.scalar(select(Issue).where(Issue.id == ancestor.parent_id))


def _set_issue_labels(db: Session, issue: Issue, label_ids: list[str], task_list: TaskList) -> None:
    if not label_ids:
        issue.label_links.clear()
        return

    allowed_labels = {label.id: label for label in task_list.labels}
    if any(label_id not in allowed_labels for label_id in label_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more labels are invalid for this list.",
        )

    issue.label_links.clear()
    for label_id in label_ids:
        issue.label_links.append(IssueLabel(id=new_id(), label_id=label_id))


def _set_issue_assignees(issue: Issue, assignees: list[User]) -> None:
    issue.assignee_links.clear()
    for assignee in assignees:
        issue.assignee_links.append(IssueAssignee(id=new_id(), user_id=assignee.id, user=assignee))
    primary_assignee = assignees[0] if assignees else None
    issue.assignee_id = primary_assignee.id if primary_assignee is not None else None
    issue.assignee = primary_assignee


def _get_issue_for_user(
    db: Session,
    user: User,
    issue_id: str,
    *,
    require_editor: bool = False,
) -> tuple[Issue, TaskList]:
    issue = db.scalar(
        select(Issue)
        .options(
            selectinload(Issue.task_list).selectinload(TaskList.labels),
            selectinload(Issue.task_list).selectinload(TaskList.statuses),
            selectinload(Issue.milestone),
            selectinload(Issue.assignee),
            selectinload(Issue.reporter),
            selectinload(Issue.comments).selectinload(IssueComment.author),
            selectinload(Issue.activity_logs).selectinload(IssueActivityLog.actor),
            selectinload(Issue.label_links).selectinload(IssueLabel.label),
            selectinload(Issue.subtasks).selectinload(Issue.assignee),
            selectinload(Issue.subtasks).selectinload(Issue.reporter),
            selectinload(Issue.subtasks).selectinload(Issue.milestone),
            selectinload(Issue.subtasks).selectinload(Issue.comments),
            selectinload(Issue.subtasks).selectinload(Issue.label_links).selectinload(IssueLabel.label),
            selectinload(Issue.subtasks).selectinload(Issue.subtasks),
            selectinload(Issue.subtasks).selectinload(Issue.checklist_items),
            selectinload(Issue.subtasks).selectinload(Issue.time_entries),
            selectinload(Issue.attachments).selectinload(Attachment.uploaded_by),
            selectinload(Issue.checklist_items),
            selectinload(Issue.time_entries).selectinload(TimeEntry.user),
            selectinload(Issue.assignee_links).selectinload(IssueAssignee.user),
        )
        .where(Issue.id == issue_id)
    )
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")

    if require_editor:
        task_list, _ = _ensure_list_editor(db, user, issue.list_id)
    else:
        _ensure_issue_readable(db, user, issue)
        task_list = issue.task_list
    return issue, task_list


def list_spaces(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
) -> list[dict[str, Any]]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()
    spaces = list(db.scalars(helpers._space_query_for_user(db, user).order_by(helpers.Team.name.asc())))
    return [
        helpers._serialize_space(space, helpers.resolve_team_role(db, user, space)).model_dump()
        for space in spaces
    ]


def list_task_lists(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "updated_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    q: str = "",
    archived: bool | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()

    if team_id is not None:
        helpers._ensure_space_access(db, user, team_id)

    task_lists = list(
        db.scalars(
            helpers._accessible_task_lists_query(db, user).options(
                selectinload(helpers.TaskList.milestones),
                selectinload(helpers.TaskList.issues).selectinload(helpers.Issue.comments),
                selectinload(helpers.TaskList.issues).selectinload(helpers.Issue.subtasks),
                joinedload(helpers.TaskList.folder),
            )
        )
    )

    q_lower = q.strip().lower()
    if archived is not None:
        task_lists = [task_list for task_list in task_lists if task_list.archived is archived]
    if team_id is not None:
        task_lists = [task_list for task_list in task_lists if task_list.team_id == team_id]
    if q_lower:
        task_lists = [
            task_list
            for task_list in task_lists
            if q_lower in task_list.name.lower()
            or q_lower in task_list.key.lower()
            or q_lower in task_list.description.lower()
        ]

    reverse = sort_dir == "desc"
    if sort_by == "name":
        task_lists.sort(key=lambda task_list: task_list.name.lower(), reverse=reverse)
    elif sort_by == "key":
        task_lists.sort(key=lambda task_list: task_list.key.lower(), reverse=reverse)
    elif sort_by == "progress":
        task_lists.sort(
            key=lambda task_list: helpers._calculate_progress(task_list.issues),
            reverse=reverse,
        )
    elif sort_by == "sort_order":
        task_lists.sort(
            key=lambda task_list: (
                task_list.folder_id or "",
                task_list.sort_order,
                task_list.name.lower(),
            )
        )
    else:
        task_lists.sort(key=lambda task_list: task_list.updated_at, reverse=reverse)

    team_ids = {task_list.team_id for task_list in task_lists if task_list.team_id}
    team_names: dict[str, str] = {}
    team_lookup: dict[str, Any] = {}
    team_member_counts: dict[str, int] = {}
    if team_ids:
        teams = list(
            db.scalars(
                select(helpers.Team)
                .where(
                    helpers.Team.id.in_(team_ids),
                    helpers.Team.trashed_at.is_(None),
                )
                .options(joinedload(helpers.Team.workspace), selectinload(helpers.Team.members))
            )
        )
        team_names = {team.id: team.name for team in teams}
        team_lookup = {team.id: team for team in teams}
        team_member_counts = {team.id: len(team.members) for team in teams}

    serialized = [
        helpers._serialize_task_list(
            task_list,
            helpers._task_list_role(db, task_list, user, team_lookup),
            team_names.get(task_list.team_id, None) if task_list.team_id else None,
            team_member_counts.get(task_list.team_id or "", 0),
        ).model_dump()
        for task_list in task_lists
    ]
    page_items, total = helpers._paginate(serialized, page, page_size)
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def list_issues(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    list_id: str,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "board_position",
    sort_dir: Literal["asc", "desc"] = "asc",
    q: str = "",
    status_filter: list[str] | None = None,
    assignee_id: str | None = None,
    priority: str | None = None,
    label_id: str | None = None,
    milestone_id: str | None = None,
    archived: bool | None = None,
    due_date_from: date | None = None,
    due_date_to: date | None = None,
    start_date_from: date | None = None,
    start_date_to: date | None = None,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()

    helpers._ensure_list_member(db, user, list_id)
    issues = list(
        db.scalars(
            select(helpers.Issue)
            .options(
                selectinload(helpers.Issue.task_list),
                selectinload(helpers.Issue.milestone),
                selectinload(helpers.Issue.assignee),
                selectinload(helpers.Issue.reporter),
                selectinload(helpers.Issue.comments),
                selectinload(helpers.Issue.label_links).selectinload(helpers.IssueLabel.label),
                selectinload(helpers.Issue.subtasks),
                selectinload(helpers.Issue.checklist_items),
                selectinload(helpers.Issue.time_entries),
                selectinload(helpers.Issue.assignee_links).selectinload(helpers.IssueAssignee.user),
            )
            .where(helpers.Issue.list_id == list_id)
        )
    )
    q_lower = q.strip().lower()
    if archived is not None:
        issues = [issue for issue in issues if issue.archived is archived]
    if status_filter:
        issues = [issue for issue in issues if issue.status in status_filter]
    if assignee_id:
        issues = [issue for issue in issues if issue.assignee_id == assignee_id]
    if priority:
        issues = [issue for issue in issues if issue.priority == priority]
    if label_id:
        issues = [issue for issue in issues if any(link.label_id == label_id for link in issue.label_links)]
    if milestone_id:
        issues = [issue for issue in issues if issue.milestone_id == milestone_id]
    if due_date_from:
        issues = [issue for issue in issues if issue.due_date and issue.due_date >= due_date_from]
    if due_date_to:
        issues = [issue for issue in issues if issue.due_date and issue.due_date <= due_date_to]
    if start_date_from:
        issues = [issue for issue in issues if issue.start_date and issue.start_date >= start_date_from]
    if start_date_to:
        issues = [issue for issue in issues if issue.start_date and issue.start_date <= start_date_to]
    if q_lower:
        issues = [
            issue
            for issue in issues
            if q_lower in issue.title.lower()
            or q_lower in issue.description.lower()
            or q_lower in helpers._issue_reference(issue).lower()
        ]

    reverse = sort_dir == "desc"
    if sort_by == "priority":
        order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        issues.sort(key=lambda issue: order[issue.priority], reverse=reverse)
    elif sort_by == "due_date":
        issues.sort(key=lambda issue: issue.due_date or date.max, reverse=reverse)
    elif sort_by == "updated_at":
        issues.sort(key=lambda issue: issue.updated_at, reverse=reverse)
    else:
        issues.sort(key=lambda issue: (issue.status, issue.board_position), reverse=reverse)

    serialized = [helpers._serialize_issue(issue).model_dump() for issue in issues]
    page_items, total = helpers._paginate(serialized, page, page_size)
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def search_issues(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    q: str = "",
    list_id: str | None = None,
    assignee_id: str | None = None,
    status_filter: list[str] | None = None,
    archived: bool | None = False,
    limit: int = 20,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()

    if list_id is not None:
        helpers._ensure_list_member(db, user, list_id)

    accessible_list_ids_subquery = helpers._accessible_task_lists_query(db, user).with_only_columns(
        helpers.TaskList.id
    )
    issues = list(
        db.scalars(
            select(helpers.Issue)
            .options(
                selectinload(helpers.Issue.task_list),
                selectinload(helpers.Issue.milestone),
                selectinload(helpers.Issue.assignee),
                selectinload(helpers.Issue.reporter),
                selectinload(helpers.Issue.comments),
                selectinload(helpers.Issue.label_links).selectinload(helpers.IssueLabel.label),
                selectinload(helpers.Issue.subtasks),
                selectinload(helpers.Issue.checklist_items),
                selectinload(helpers.Issue.time_entries),
                selectinload(helpers.Issue.assignee_links).selectinload(helpers.IssueAssignee.user),
            )
            .where(helpers.Issue.list_id.in_(accessible_list_ids_subquery))
        )
    )

    q_lower = q.strip().lower()
    if list_id is not None:
        issues = [issue for issue in issues if issue.list_id == list_id]
    if archived is not None:
        issues = [issue for issue in issues if issue.archived is archived]
    if status_filter:
        issues = [issue for issue in issues if issue.status in status_filter]
    if assignee_id:
        issues = [issue for issue in issues if issue.assignee_id == assignee_id]
    if q_lower:
        issues = [
            issue
            for issue in issues
            if q_lower in issue.title.lower()
            or q_lower in issue.description.lower()
            or q_lower in helpers._issue_reference(issue).lower()
        ]

    issues.sort(key=lambda issue: issue.updated_at, reverse=True)
    serialized = [helpers._serialize_issue(issue).model_dump() for issue in issues[:limit]]
    return {
        "items": serialized,
        "total": len(serialized),
        "page": 1,
        "page_size": limit,
    }


def list_assigned_issues(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    limit: int = 10,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()

    accessible_list_ids_subquery = helpers._accessible_task_lists_query(db, user).with_only_columns(
        helpers.TaskList.id
    )
    issues = list(
        db.scalars(
            select(helpers.Issue)
            .options(
                selectinload(helpers.Issue.task_list),
                selectinload(helpers.Issue.milestone),
                selectinload(helpers.Issue.assignee),
                selectinload(helpers.Issue.reporter),
                selectinload(helpers.Issue.comments),
                selectinload(helpers.Issue.label_links).selectinload(helpers.IssueLabel.label),
                selectinload(helpers.Issue.subtasks),
                selectinload(helpers.Issue.checklist_items),
                selectinload(helpers.Issue.time_entries),
                selectinload(helpers.Issue.assignee_links).selectinload(helpers.IssueAssignee.user),
            )
            .where(
                helpers.Issue.assignee_id == user.id,
                helpers.Issue.archived.is_(False),
                helpers.Issue.list_id.in_(accessible_list_ids_subquery),
            )
        )
    )

    issues = [issue for issue in issues if not helpers._is_closed_status(issue.status, issue.task_list)]
    issues.sort(
        key=lambda issue: (
            issue.due_date or date.max,
            -issue.updated_at.timestamp(),
        )
    )
    serialized = [helpers._serialize_issue(issue).model_dump() for issue in issues[:limit]]
    return {
        "items": serialized,
        "total": len(serialized),
        "page": 1,
        "page_size": limit,
    }


def get_issue_detail(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    issue_id: str,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()

    issue, task_list = helpers._get_issue_for_user(db, user, issue_id)
    dependencies = list(
        db.scalars(
            select(helpers.ScheduleDependency).where(
                helpers.ScheduleDependency.list_id == task_list.id,
                or_(
                    helpers.ScheduleDependency.predecessor_id == issue.id,
                    helpers.ScheduleDependency.successor_id == issue.id,
                ),
            )
        )
    )
    return {
        "issue": helpers._serialize_issue(issue).model_dump(),
        "comments": [
            helpers._serialize_comment(comment).model_dump()
            for comment in sorted(issue.comments, key=lambda item: item.created_at)
        ],
        "dependencies": [
            {
                "id": dependency.id,
                "predecessor_kind": dependency.predecessor_kind,
                "predecessor_id": dependency.predecessor_id,
                "successor_kind": dependency.successor_kind,
                "successor_id": dependency.successor_id,
                "relation_type": dependency.relation_type,
            }
            for dependency in dependencies
        ],
        "subtasks": [
            helpers._serialize_issue(subtask).model_dump()
            for subtask in sorted(issue.subtasks, key=lambda item: item.created_at)
            if not subtask.archived
        ],
        "attachments": [
            {
                "id": attachment.id,
                "issue_id": attachment.issue_id,
                "filename": attachment.filename,
                "content_type": attachment.content_type,
                "size_bytes": attachment.size_bytes,
                "download_url": helpers._build_attachment_download_url(attachment.storage_key),
                "uploaded_by_id": attachment.uploaded_by_id,
                "uploaded_by_name": attachment.uploaded_by.full_name,
                "created_at": attachment.created_at,
            }
            for attachment in sorted(issue.attachments, key=lambda item: item.created_at)
        ],
        "checklist_items": [
            {
                "id": checklist_item.id,
                "issue_id": checklist_item.issue_id,
                "text": checklist_item.text,
                "completed": checklist_item.completed,
                "sort_order": checklist_item.sort_order,
                "created_at": checklist_item.created_at,
            }
            for checklist_item in sorted(issue.checklist_items, key=lambda item: item.sort_order)
        ],
        "time_entries": [
            {
                "id": time_entry.id,
                "issue_id": time_entry.issue_id,
                "user_id": time_entry.user_id,
                "user_name": time_entry.user.full_name,
                "duration_minutes": time_entry.duration_minutes,
                "description": time_entry.description,
                "entry_date": time_entry.entry_date,
                "created_at": time_entry.created_at,
            }
            for time_entry in sorted(issue.time_entries, key=lambda item: item.created_at, reverse=True)
        ],
    }


def _reload_issue_summary(db: Session, *, issue_id: str) -> Any:
    return db.scalar(
        select(Issue)
        .options(
            selectinload(Issue.task_list).selectinload(TaskList.statuses),
            selectinload(Issue.milestone),
            selectinload(Issue.assignee),
            selectinload(Issue.reporter),
            selectinload(Issue.comments),
            selectinload(Issue.label_links).selectinload(IssueLabel.label),
            selectinload(Issue.subtasks),
            selectinload(Issue.checklist_items),
            selectinload(Issue.time_entries),
            selectinload(Issue.assignee_links).selectinload(IssueAssignee.user),
        )
        .where(Issue.id == issue_id)
    )


def _reload_comment(db: Session, *, comment_id: str) -> Any:
    return db.scalar(
        select(IssueComment)
        .options(selectinload(IssueComment.author))
        .where(IssueComment.id == comment_id)
    )


def create_issue(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    list_id: str,
    title: str,
    description: str = "",
    description_blocks: list[dict[str, Any]] | None = None,
    status: str = "backlog",
    priority: str = "medium",
    assignee_id: str | None = None,
    assignee_ids: list[str] | None = None,
    milestone_id: str | None = None,
    parent_id: str | None = None,
    start_date: date | None = None,
    due_date: date | None = None,
    estimate_hours: float | None = None,
    recurrence_rule: str | None = None,
    label_ids: list[str] | None = None,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    if approved_call_id is not None:
        try:
            existing_issue, _existing_task_list = _get_issue_for_user(
                db,
                user,
                approved_call_id,
                require_editor=True,
            )
        except HTTPException as error:
            if error.status_code != 404:
                raise
        else:
            return _serialize_issue_summary(existing_issue)

    task_list, _ = _ensure_list_editor(db, user, list_id)
    validated_assignees: list[User] | None = None
    if assignee_ids is not None:
        validated_assignees = _validate_issue_assignees(db, task_list, assignee_ids)
        assignee_id = validated_assignees[0].id if validated_assignees else None
    else:
        _validate_issue_assignee(db, task_list, assignee_id)
    _validate_milestone(task_list, milestone_id)
    _validate_parent_issue(db, task_list, parent_id)
    next_position = _next_issue_board_position(db, list_id, status)
    issue = Issue(
        id=approved_call_id or new_id(),
        list_id=task_list.id,
        issue_number=_next_issue_number(db, task_list.id),
        title=title.strip(),
        description=description.strip(),
        description_blocks=description_blocks,
        parent_id=parent_id,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
        reporter_id=user.id,
        milestone_id=milestone_id,
        start_date=start_date,
        due_date=due_date,
        estimate_hours=estimate_hours,
        recurrence_rule=recurrence_rule,
        board_position=next_position,
    )
    db.add(issue)
    db.flush()
    enqueue_issue_rag_sync(
        db,
        issue=issue,
        operation=RagSyncOperation.UPSERT,
    )
    if validated_assignees is not None:
        _set_issue_assignees(issue, validated_assignees)
    _set_issue_labels(db, issue, label_ids or [], task_list)
    if description_blocks:
        sync_embedded_media(db, description_blocks, "issue", issue.id, user)
    _log_issue_activity(
        db,
        issue.id,
        user.id,
        "created",
        f"{user.full_name} created {_issue_reference(issue)}.",
        stable_key=(
            _stable_replay_id(approved_call_id, "activity.created")
            if approved_call_id is not None
            else None
        ),
    )
    db.commit()
    reloaded = _reload_issue_summary(db, issue_id=issue.id)
    return _serialize_issue_summary(reloaded)


def update_issue(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    issue_id: str,
    provided_fields: set[str],
    title: str | None = None,
    description: str | None = None,
    description_blocks: list[dict[str, Any]] | None = None,
    parent_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assignee_id: str | None = None,
    assignee_ids: list[str] | None = None,
    milestone_id: str | None = None,
    start_date: date | None = None,
    due_date: date | None = None,
    board_position: int | None = None,
    archived: bool | None = None,
    estimate_hours: float | None = None,
    recurrence_rule: str | None = None,
    label_ids: list[str] | None = None,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    issue, task_list = _get_issue_for_user(db, user, issue_id, require_editor=True)
    rag_operation: RagSyncOperation | None = None
    effective_provided_fields = set(provided_fields)
    validated_assignees: list[User] | None = None
    if "assignee_ids" in effective_provided_fields:
        validated_assignees = _validate_issue_assignees(db, task_list, assignee_ids or [])
        assignee_id = validated_assignees[0].id if validated_assignees else None
        effective_provided_fields.add("assignee_id")
    elif "assignee_id" in effective_provided_fields:
        _validate_issue_assignee(db, task_list, assignee_id)
    if "milestone_id" in effective_provided_fields:
        _validate_milestone(task_list, milestone_id)
    if "parent_id" in effective_provided_fields:
        _validate_parent_issue(db, task_list, parent_id, issue_id=issue.id)

    old_status = issue.status
    nullable_fields = {
        "assignee_id",
        "milestone_id",
        "start_date",
        "due_date",
        "recurrence_rule",
    }
    field_specs: list[tuple[str, str, Any]] = [
        ("title", "updated title", title),
        ("description", "updated description", description),
        ("status", "changed status", status),
        ("priority", "changed priority", priority),
        ("assignee_id", "changed assignee", assignee_id),
        ("milestone_id", "changed milestone", milestone_id),
        ("start_date", "updated start date", start_date),
        ("due_date", "updated due date", due_date),
        ("board_position", "reordered board position", board_position),
        ("archived", "changed archive state", archived),
        ("estimate_hours", "updated estimate", estimate_hours),
        ("recurrence_rule", "updated recurrence", recurrence_rule),
    ]
    for field_name, message, value in field_specs:
        if field_name not in effective_provided_fields:
            continue
        if value is None and field_name not in nullable_fields:
            continue
        previous = getattr(issue, field_name)
        normalized_value = value.strip() if isinstance(value, str) else value
        if previous == normalized_value:
            continue
        setattr(issue, field_name, normalized_value)
        rag_operation = RagSyncOperation.UPSERT
        _log_issue_activity(
            db,
            issue.id,
            user.id,
            "updated",
            f"{user.full_name} {message} for {_issue_reference(issue)}.",
            field_name=field_name,
            from_value=str(previous) if previous is not None else None,
            to_value=str(normalized_value) if normalized_value is not None else None,
            stable_key=(
                _stable_replay_id(approved_call_id, f"activity.field.{field_name}")
                if approved_call_id is not None
                else None
            ),
        )

    if "parent_id" in effective_provided_fields:
        previous = issue.parent_id
        issue.parent_id = parent_id
        if previous != parent_id:
            rag_operation = RagSyncOperation.UPSERT
            _log_issue_activity(
                db,
                issue.id,
                user.id,
                "updated",
                f"{user.full_name} {'removed parent' if parent_id is None else 'changed parent'} for {_issue_reference(issue)}.",
                field_name="parent_id",
                from_value=previous,
                to_value=parent_id,
                stable_key=(
                    _stable_replay_id(approved_call_id, "activity.parent_id")
                    if approved_call_id is not None
                    else None
                ),
            )

    if "description_blocks" in effective_provided_fields:
        issue.description_blocks = description_blocks
        sync_embedded_media(db, description_blocks, "issue", issue.id, user)
        rag_operation = RagSyncOperation.UPSERT
        _log_issue_activity(
            db,
            issue.id,
            user.id,
            "updated",
            f"{user.full_name} updated description for {_issue_reference(issue)}.",
            field_name="description_blocks",
            stable_key=(
                _stable_replay_id(approved_call_id, "activity.description_blocks")
                if approved_call_id is not None
                else None
            ),
        )

    if "label_ids" in effective_provided_fields and label_ids is not None:
        _set_issue_labels(db, issue, label_ids, task_list)
        rag_operation = RagSyncOperation.UPSERT
        _log_issue_activity(
            db,
            issue.id,
            user.id,
            "updated",
            f"{user.full_name} updated labels for {_issue_reference(issue)}.",
            field_name="label_ids",
            stable_key=(
                _stable_replay_id(approved_call_id, "activity.label_ids")
                if approved_call_id is not None
                else None
            ),
        )
    if "assignee_ids" in effective_provided_fields and validated_assignees is not None:
        previous_assignee_ids = [link.user_id for link in list(issue.assignee_links)]
        new_assignee_ids = [assignee.id for assignee in validated_assignees]
        if previous_assignee_ids != new_assignee_ids:
            _set_issue_assignees(issue, validated_assignees)
            rag_operation = RagSyncOperation.UPSERT
            _log_issue_activity(
                db,
                issue.id,
                user.id,
                "updated",
                f"{user.full_name} updated assignees for {_issue_reference(issue)}.",
                field_name="assignee_ids",
                from_value=",".join(previous_assignee_ids) if previous_assignee_ids else None,
                to_value=",".join(new_assignee_ids) if new_assignee_ids else None,
                stable_key=(
                    _stable_replay_id(approved_call_id, "activity.assignee_ids")
                    if approved_call_id is not None
                    else None
                ),
            )

    if status is not None and status != old_status and board_position is None:
        issue.board_position = _next_issue_board_position(db, issue.list_id, status)
        rag_operation = RagSyncOperation.UPSERT

    ref = _issue_reference(issue)
    if assignee_id is not None and assignee_id != user.id and "assignee_id" in effective_provided_fields:
        _create_notification(
            db,
            assignee_id,
            "assigned",
            f"{ref} assigned to you",
            f"{user.full_name} assigned {ref} ({issue.title}) to you.",
            reference_id=issue.id,
            stable_key=(
                _stable_replay_id(approved_call_id, f"notification.assigned.{assignee_id}")
                if approved_call_id is not None
                else None
            ),
        )
    if status is not None and status != old_status and issue.assignee_id and issue.assignee_id != user.id:
        _create_notification(
            db,
            issue.assignee_id,
            "status_changed",
            f"{ref} status → {ISSUE_STATUS_LABELS.get(status, status)}",
            f"{user.full_name} changed status of {ref} to {ISSUE_STATUS_LABELS.get(status, status)}.",
            reference_id=issue.id,
            stable_key=(
                _stable_replay_id(
                    approved_call_id,
                    f"notification.status_changed.{issue.assignee_id}",
                )
                if approved_call_id is not None
                else None
            ),
        )

    if rag_operation is not None:
        enqueue_issue_rag_sync(
            db,
            issue=issue,
            operation=rag_operation,
        )
    db.commit()
    reloaded = _reload_issue_summary(db, issue_id=issue.id)
    return _serialize_issue_summary(reloaded)


def add_issue_comment(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    issue_id: str,
    body: str = "",
    body_blocks: list[dict[str, Any]] | None = None,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    if approved_call_id is not None:
        existing_comment = db.scalar(
            select(IssueComment)
            .options(selectinload(IssueComment.author))
            .where(IssueComment.id == approved_call_id)
        )
        if existing_comment is not None:
            _get_issue_for_user(db, user, existing_comment.issue_id, require_editor=True)
            return _serialize_comment_item(existing_comment)

    issue, _ = _get_issue_for_user(db, user, issue_id, require_editor=True)
    comment = IssueComment(
        id=approved_call_id or new_id(),
        issue_id=issue.id,
        author_id=user.id,
        body=body.strip(),
        body_blocks=body_blocks,
    )
    db.add(comment)
    enqueue_issue_rag_sync(
        db,
        issue=issue,
        operation=RagSyncOperation.UPSERT,
    )
    _log_issue_activity(
        db,
        issue.id,
        user.id,
        "commented",
        f"{user.full_name} added a comment to {_issue_reference(issue)}.",
        stable_key=(
            _stable_replay_id(approved_call_id, "activity.commented")
            if approved_call_id is not None
            else None
        ),
    )
    ref = _issue_reference(issue)
    notify_ids = {uid for uid in [issue.assignee_id, issue.reporter_id] if uid and uid != user.id}
    for uid in notify_ids:
        _create_notification(
            db,
            uid,
            "commented",
            f"New comment on {ref}",
            f"{user.full_name} commented on {ref} ({issue.title}).",
            reference_id=issue.id,
            stable_key=(
                _stable_replay_id(approved_call_id, f"notification.commented.{uid}")
                if approved_call_id is not None
                else None
            ),
        )

    import re

    mentioned_ids: set[str] = set()
    if body:
        mentioned_ids.update(re.findall(r"@([0-9a-f-]{36})", body))
    if body_blocks:
        _extract_mentions_from_blocks(body_blocks, mentioned_ids)
    mentioned_ids -= notify_ids
    mentioned_ids.discard(user.id)
    for uid in mentioned_ids:
        mentioned_user = db.scalar(select(User).where(User.id == uid))
        if mentioned_user is not None:
            _create_notification(
                db,
                uid,
                "mentioned",
                f"Mentioned in {ref}",
                f"{user.full_name} mentioned you in a comment on {ref}.",
                reference_id=issue.id,
                stable_key=(
                    _stable_replay_id(approved_call_id, f"notification.mentioned.{uid}")
                    if approved_call_id is not None
                    else None
                ),
            )

    db.commit()
    reloaded = _reload_comment(db, comment_id=comment.id)
    return _serialize_comment_item(reloaded)
