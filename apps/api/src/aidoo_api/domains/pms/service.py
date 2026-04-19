from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.auth.access import bind_current_workspace
from aidoo_api.domains.auth.models import User, Workspace


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
