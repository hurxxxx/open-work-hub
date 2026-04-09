from __future__ import annotations

import csv
from io import BytesIO, StringIO
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.access import get_or_create_default_pms_space
from aidoo_api.domains.auth.dependencies import require_current_user
from aidoo_api.domains.auth.models import Team, TeamMember, User
from aidoo_api.domains.auth.security import new_id
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import get_minio_client
from aidoo_api.domains.media.router import sync_embedded_media, cleanup_media_for_resource
from aidoo_api.domains.pms.models import (
    Attachment,
    ChecklistItem,
    CustomField,
    CustomFieldValue,
    Doc,
    Folder,
    Issue,
    IssueActivityLog,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    Label,
    Milestone,
    Notification,
    Project,
    ProjectMember,
    ProjectStatus,
    ScheduleDependency,
    SpaceDoc,
    SpaceDocPage,
    TaskTemplate,
    TimeEntry,
)


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
PROJECT_STATUS_LABELS = {
    "planned": "Planned",
    "active": "Active",
    "on_hold": "On Hold",
    "done": "Done",
}
MILESTONE_STATUS_LABELS = {
    "planned": "Planned",
    "active": "Active",
    "complete": "Complete",
}
PRIORITY_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "critical": "Critical",
}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    q: str = ""


class ProjectCreateRequest(BaseModel):
    key: str | None = Field(default=None, min_length=2, max_length=24, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(..., min_length=2, max_length=140)
    description: str = Field(default="", max_length=4000)
    team_id: str | None = None
    folder_id: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["planned", "active", "on_hold", "done"] | None = None
    archived: bool | None = None
    folder_id: str | None = None


class ProjectMemberCreateRequest(BaseModel):
    user_id: str
    role: Literal["owner", "admin", "editor", "viewer", "member"] = "member"


class MilestoneCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=140)
    description: str = Field(default="", max_length=4000)
    status: Literal["planned", "active", "complete"] = "planned"
    start_date: date | None = None
    due_date: date | None = None
    sort_order: int = 0


class MilestoneUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["planned", "active", "complete"] | None = None
    start_date: date | None = None
    due_date: date | None = None
    sort_order: int | None = None


class IssueCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=180)
    description: str = Field(default="", max_length=4000)
    description_blocks: list[dict] | None = None
    status: str = "backlog"
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    assignee_id: str | None = None
    milestone_id: str | None = None
    parent_id: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimate_hours: float | None = None
    recurrence_rule: str | None = None
    label_ids: list[str] = Field(default_factory=list)


class IssueUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    description_blocks: list[dict] | None = None
    parent_id: str | None = None
    status: str | None = None
    priority: Literal["low", "medium", "high", "critical"] | None = None
    assignee_id: str | None = None
    milestone_id: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    board_position: int | None = None
    archived: bool | None = None
    estimate_hours: float | None = None
    recurrence_rule: str | None = None
    label_ids: list[str] | None = None


class IssueCommentCreateRequest(BaseModel):
    body: str = Field(default="", max_length=4000)
    body_blocks: list[dict] | None = None


class DependencyCreateRequest(BaseModel):
    predecessor_kind: Literal["issue"] = "issue"
    predecessor_id: str
    successor_kind: Literal["issue"] = "issue"
    successor_id: str
    relation_type: Literal["blocks"] = "blocks"


class BulkUpdateRequest(BaseModel):
    issue_ids: list[str] = Field(..., min_length=1, max_length=50)
    status: str | None = None
    priority: Literal["low", "medium", "high", "critical"] | None = None
    assignee_id: str | None = None
    add_label_ids: list[str] = Field(default_factory=list)
    remove_label_ids: list[str] = Field(default_factory=list)
    archived: bool | None = None
    delete: bool = False


class BulkUpdateResponse(BaseModel):
    updated_count: int
    deleted_count: int


class ProjectListItem(BaseModel):
    id: str
    key: str
    name: str
    description: str
    status: str
    archived: bool
    team_id: str | None
    team_name: str | None
    folder_id: str | None = None
    folder_name: str | None = None
    role: str
    progress: float
    member_count: int
    milestone_count: int
    issue_count: int
    overdue_issue_count: int
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectListItem]
    total: int
    page: int
    page_size: int


class ProjectMemberItem(BaseModel):
    user_id: str
    email: str
    full_name: str
    is_admin: bool
    role: str
    joined_at: datetime


class ProjectMemberListResponse(BaseModel):
    items: list[ProjectMemberItem]
    total: int
    page: int
    page_size: int


class MilestoneItem(BaseModel):
    id: str
    project_id: str
    title: str
    description: str
    status: str
    start_date: date | None
    due_date: date | None
    sort_order: int
    progress: float
    issue_count: int
    completed_issue_count: int
    updated_at: datetime


class MilestoneListResponse(BaseModel):
    items: list[MilestoneItem]
    total: int
    page: int
    page_size: int


class LabelItem(BaseModel):
    id: str
    name: str
    color: str


class LabelListResponse(BaseModel):
    items: list[LabelItem]
    total: int
    page: int
    page_size: int


class ProjectStatusItem(BaseModel):
    id: str
    slug: str
    name: str
    color: str
    category: str
    sort_order: int


class ProjectStatusListResponse(BaseModel):
    items: list[ProjectStatusItem]


class ProjectStatusCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    color: str = Field(default="#6b7280", max_length=24)
    category: Literal["backlog", "active", "done", "canceled"] = "active"
    sort_order: int = 0


class ProjectStatusUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, max_length=24)
    category: Literal["backlog", "active", "done", "canceled"] | None = None
    sort_order: int | None = None


class TaskTemplateItem(BaseModel):
    id: str
    project_id: str
    name: str
    description: str
    default_status: str
    default_priority: str
    checklist_items: list[dict] | None = None
    created_at: datetime


class TaskTemplateListResponse(BaseModel):
    items: list[TaskTemplateItem]


class TaskTemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=140)
    description: str = Field(default="", max_length=4000)
    default_status: str = "backlog"
    default_priority: Literal["low", "medium", "high", "critical"] = "medium"
    checklist_items: list[dict] | None = None


class TaskTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    default_status: str | None = None
    default_priority: Literal["low", "medium", "high", "critical"] | None = None
    checklist_items: list[dict] | None = None


class CustomFieldItem(BaseModel):
    id: str
    project_id: str
    name: str
    field_type: str
    options: list[str] | None = None
    sort_order: int


class CustomFieldListResponse(BaseModel):
    items: list[CustomFieldItem]


class CustomFieldCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    field_type: Literal["text", "number", "date", "select"] = "text"
    options: list[str] | None = None
    sort_order: int = 0


class CustomFieldValueItem(BaseModel):
    field_id: str
    value: str


class SetCustomFieldValueRequest(BaseModel):
    field_id: str
    value: str = ""


class LabelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=48)
    color: str = Field(default="#1f2d38", max_length=24)


class LabelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=48)
    color: str | None = Field(default=None, max_length=24)


class ChecklistItemCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    sort_order: int = 0


class ChecklistItemUpdateRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=500)
    completed: bool | None = None
    sort_order: int | None = None


class ChecklistReorderRequest(BaseModel):
    item_ids: list[str]


class ChecklistItemResponse(BaseModel):
    id: str
    issue_id: str
    text: str
    completed: bool
    sort_order: int
    created_at: datetime


class TimeEntryCreateRequest(BaseModel):
    duration_minutes: int = Field(..., ge=1, le=1440)
    description: str = Field(default="", max_length=500)
    entry_date: date


class TimeEntryUpdateRequest(BaseModel):
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    description: str | None = Field(default=None, max_length=500)
    entry_date: date | None = None


class TimeEntryItem(BaseModel):
    id: str
    issue_id: str
    user_id: str
    user_name: str
    duration_minutes: int
    description: str
    entry_date: date
    created_at: datetime


class IssueListItem(BaseModel):
    id: str
    project_id: str
    reference: str
    title: str
    description: str
    description_blocks: list[dict] | None = None
    parent_id: str | None = None
    subtask_count: int = 0
    status: str
    status_label: str
    priority: str
    priority_label: str
    assignee_id: str | None
    assignee_name: str | None
    assignee_ids: list[str] = []
    assignee_names: list[str] = []
    reporter_id: str
    reporter_name: str
    milestone_id: str | None
    milestone_title: str | None
    start_date: date | None
    due_date: date | None
    board_position: int
    archived: bool
    progress: float | None
    comments_count: int
    checklist_total: int = 0
    checklist_done: int = 0
    estimate_hours: float | None = None
    time_spent_minutes: int = 0
    recurrence_rule: str | None = None
    labels: list[LabelItem]
    updated_at: datetime


class IssueListResponse(BaseModel):
    items: list[IssueListItem]
    total: int
    page: int
    page_size: int


class DependencyItem(BaseModel):
    id: str
    predecessor_kind: str
    predecessor_id: str
    successor_kind: str
    successor_id: str
    relation_type: str


class IssueCommentItem(BaseModel):
    id: str
    issue_id: str
    author_id: str
    author_name: str
    body: str
    body_blocks: list[dict] | None = None
    created_at: datetime


class ActivityLogItem(BaseModel):
    id: str
    issue_id: str
    actor_id: str | None
    actor_name: str | None
    action: str
    field_name: str | None
    from_value: str | None
    to_value: str | None
    message: str
    created_at: datetime


class ActivityLogListResponse(BaseModel):
    items: list[ActivityLogItem]
    total: int
    page: int
    page_size: int


class AttachmentItem(BaseModel):
    id: str
    issue_id: str
    filename: str
    content_type: str
    size_bytes: int
    download_url: str
    uploaded_by_id: str
    uploaded_by_name: str
    created_at: datetime


class NotificationItem(BaseModel):
    id: str
    type: str
    title: str
    body: str
    reference_type: str
    reference_id: str | None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    count: int


class IssueDetailResponse(BaseModel):
    issue: IssueListItem
    comments: list[IssueCommentItem]
    dependencies: list[DependencyItem]
    subtasks: list[IssueListItem] = []
    attachments: list[AttachmentItem] = []
    checklist_items: list[ChecklistItemResponse] = []
    time_entries: list[TimeEntryItem] = []


class StatusCountItem(BaseModel):
    status: str
    label: str
    count: int


class PriorityCountItem(BaseModel):
    priority: str
    label: str
    count: int


class RecentActivityItem(BaseModel):
    id: str
    issue_id: str
    issue_reference: str
    message: str
    actor_name: str | None
    created_at: datetime


class DashboardProjectItem(BaseModel):
    project_id: str
    key: str
    name: str
    progress: float
    open_issue_count: int
    overdue_issue_count: int
    next_due_date: date | None


class DashboardSummaryResponse(BaseModel):
    project_count: int
    active_issue_count: int
    overdue_issue_count: int
    my_issue_count: int
    milestone_due_soon_count: int
    status_counts: list[StatusCountItem]
    priority_counts: list[PriorityCountItem]
    projects: list[DashboardProjectItem]
    recent_activity: list[RecentActivityItem]


router = APIRouter(prefix="/pms", tags=["pms"])


def _paginate[T](items: list[T], page: int, page_size: int) -> tuple[list[T], int]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total


PROJECT_ROLE_RANK = {
    "viewer": 0,
    "member": 1,
    "editor": 2,
    "admin": 3,
    "owner": 4,
}
SPACE_TEAM_EDITOR_ROLES = {"member", "team_admin", "workspace_admin", "admin", "owner", "editor"}
SPACE_TEAM_MANAGER_ROLES = {"team_admin", "workspace_admin", "admin", "owner"}
PROJECT_EDITOR_ROLES = {"member", "editor", "admin", "owner"}
PROJECT_MANAGER_ROLES = {"admin", "owner"}


def _best_project_role(db: Session, user: User, space_id: str) -> str | None:
    roles = list(
        db.scalars(
            select(ProjectMember.role)
            .join(Project, Project.id == ProjectMember.project_id)
            .join(Team, Team.id == Project.team_id)
            .where(
                ProjectMember.user_id == user.id,
                Project.team_id == space_id,
                Team.trashed_at.is_(None),
            )
        )
    )
    if not roles:
        return None
    return max(roles, key=lambda role: PROJECT_ROLE_RANK.get(role, -1))


def _is_active_space_id(db: Session, space_id: str) -> bool:
    return (
        db.scalar(
            select(Team.id).where(
                Team.id == space_id,
                Team.trashed_at.is_(None),
            )
        )
        is not None
    )


def _ensure_space_access(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team = db.scalar(
        select(Team)
        .options(selectinload(Team.members))
        .where(
            Team.id == space_id,
            Team.trashed_at.is_(None),
        )
    )
    if team is None:
        raise HTTPException(status_code=404, detail="Space not found.")

    if user.is_admin:
        return team, "owner"

    team_membership = next((member for member in team.members if member.user_id == user.id), None)
    if team_membership is not None:
        return team, team_membership.role

    project_role = _best_project_role(db, user, space_id)
    if project_role is not None:
        return team, project_role

    raise HTTPException(status_code=403, detail="Space access required.")


def _ensure_space_editor(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team, role = _ensure_space_access(db, user, space_id)
    if user.is_admin:
        return team, role

    if role in SPACE_TEAM_EDITOR_ROLES or role in PROJECT_EDITOR_ROLES:
        return team, role

    raise HTTPException(status_code=403, detail="Viewer role cannot modify space data.")


def _ensure_space_manager(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team, role = _ensure_space_access(db, user, space_id)
    if user.is_admin:
        return team, role

    if role in SPACE_TEAM_MANAGER_ROLES or role in PROJECT_MANAGER_ROLES:
        return team, role

    raise HTTPException(status_code=403, detail="Space owner/admin access required.")


def _accessible_space_ids(db: Session, user: User) -> set[str]:
    if user.is_admin:
        return set(db.scalars(select(Team.id).where(Team.trashed_at.is_(None))))

    space_ids = set(
        db.scalars(
            select(TeamMember.team_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                TeamMember.user_id == user.id,
                Team.trashed_at.is_(None),
            )
        )
    )
    space_ids.update(
        team_id
        for team_id in db.scalars(
            select(Project.team_id)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .join(Team, Team.id == Project.team_id)
            .where(
                ProjectMember.user_id == user.id,
                Project.team_id.is_not(None),
                Team.trashed_at.is_(None),
            )
        )
        if team_id is not None
    )
    return space_ids


def _validate_folder_membership(db: Session, team_id: str, folder_id: str | None) -> None:
    if folder_id is None:
        return

    folder = db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found.")
    if folder.team_id != team_id:
        raise HTTPException(status_code=400, detail="Folder must belong to the same space.")


def _ensure_project_access(db: Session, user: User, project_id: str) -> tuple[Project, str]:
    project = db.scalar(
        select(Project)
        .options(
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.milestones),
        )
        .where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if project.team_id is not None and not _is_active_space_id(db, project.team_id):
        raise HTTPException(status_code=404, detail="Project not found.")

    if user.is_admin:
        return project, "owner"

    membership = next((member for member in project.members if member.user_id == user.id), None)
    if membership is None:
        raise HTTPException(status_code=403, detail="Project membership required.")

    return project, membership.role


def _ensure_project_owner(db: Session, user: User, project_id: str) -> tuple[Project, str]:
    project, role = _ensure_project_access(db, user, project_id)
    if not user.is_admin and role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Project owner/admin access required.")
    return project, role


def _ensure_project_editor(db: Session, user: User, project_id: str) -> tuple[Project, str]:
    """Allow owner, admin, editor, and member roles. Block viewers."""
    project, role = _ensure_project_access(db, user, project_id)
    if not user.is_admin and role == "viewer":
        raise HTTPException(status_code=403, detail="Viewer role cannot modify project data.")
    return project, role


def _accessible_projects_query(user: User):
    active_space_ids = select(Team.id).where(Team.trashed_at.is_(None))
    if user.is_admin:
        return select(Project).where(
            or_(
                Project.team_id.is_(None),
                Project.team_id.in_(active_space_ids),
            )
        )

    return (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user.id,
            or_(
                Project.team_id.is_(None),
                Project.team_id.in_(active_space_ids),
            ),
        )
    )


CATEGORY_PROGRESS = {
    "backlog": 0.0,
    "active": 0.5,
    "done": 1.0,
    "canceled": None,
}


def _issue_progress(status_value: str, project: Project | None = None) -> float | None:
    result = ISSUE_STATUS_PROGRESS.get(status_value)
    if result is not None or status_value in ISSUE_STATUS_PROGRESS:
        return result
    # Fallback: look up category from project custom statuses
    if project is not None:
        for ps in getattr(project, "statuses", []):
            if ps.slug == status_value:
                return CATEGORY_PROGRESS.get(ps.category, 0.5)
    return 0.5  # Unknown status defaults to active


def _is_closed_status(status_value: str, project: Project | None = None) -> bool:
    """Check if a status represents a closed state (done or canceled)."""
    if status_value in {"done", "canceled"}:
        return True
    if project is not None:
        for ps in getattr(project, "statuses", []):
            if ps.slug == status_value:
                return ps.category in {"done", "canceled"}
    return False


def _is_done_status(status_value: str, project: Project | None = None) -> bool:
    """Check if a status represents a completed state."""
    if status_value == "done":
        return True
    if project is not None:
        for ps in getattr(project, "statuses", []):
            if ps.slug == status_value:
                return ps.category == "done"
    return False


def _calculate_progress(issues: list[Issue], project: Project | None = None) -> float:
    progress_values = [
        progress
        for issue in issues
        if not issue.archived
        for progress in [_issue_progress(issue.status, project)]
        if progress is not None
    ]
    if not progress_values:
        return 0.0
    return round(sum(progress_values) / len(progress_values), 2)


def _serialize_labels(issue: Issue) -> list[LabelItem]:
    return [
        LabelItem(id=link.label.id, name=link.label.name, color=link.label.color)
        for link in issue.label_links
    ]


def _issue_reference(issue: Issue) -> str:
    return f"{issue.project.key}-{issue.issue_number}"


def _serialize_issue(issue: Issue) -> IssueListItem:
    return IssueListItem(
        id=issue.id,
        project_id=issue.project_id,
        reference=_issue_reference(issue),
        title=issue.title,
        description=issue.description,
        description_blocks=issue.description_blocks,
        parent_id=issue.parent_id,
        subtask_count=len(issue.subtasks) if issue.subtasks else 0,
        status=issue.status,
        status_label=ISSUE_STATUS_LABELS.get(issue.status, issue.status.replace("_", " ").title()),
        priority=issue.priority,
        priority_label=PRIORITY_LABELS[issue.priority],
        assignee_id=issue.assignee_id,
        assignee_name=getattr(issue.assignee, "full_name", None),
        assignee_ids=[link.user_id for link in getattr(issue, "assignee_links", [])],
        assignee_names=[getattr(link.user, "full_name", "") for link in getattr(issue, "assignee_links", [])],
        reporter_id=issue.reporter_id,
        reporter_name=issue.reporter.full_name,
        milestone_id=issue.milestone_id,
        milestone_title=getattr(issue.milestone, "title", None),
        start_date=issue.start_date,
        due_date=issue.due_date,
        board_position=issue.board_position,
        archived=issue.archived,
        progress=_issue_progress(issue.status, issue.project),
        comments_count=len(issue.comments),
        checklist_total=len(issue.checklist_items) if issue.checklist_items else 0,
        checklist_done=sum(1 for ci in issue.checklist_items if ci.completed) if issue.checklist_items else 0,
        estimate_hours=issue.estimate_hours,
        time_spent_minutes=sum(te.duration_minutes for te in issue.time_entries) if issue.time_entries else 0,
        recurrence_rule=issue.recurrence_rule,
        labels=_serialize_labels(issue),
        updated_at=issue.updated_at,
    )


def _serialize_project(project: Project, role: str, team_name: str | None = None) -> ProjectListItem:
    overdue_issue_count = sum(
        1
        for issue in project.issues
        if (
            not issue.archived
            and not _is_closed_status(issue.status, project)
            and issue.due_date is not None
            and issue.due_date < date.today()
        )
    )
    return ProjectListItem(
        id=project.id,
        key=project.key,
        name=project.name,
        description=project.description,
        status=project.status,
        archived=project.archived,
        team_id=project.team_id,
        team_name=team_name,
        folder_id=project.folder_id,
        folder_name=getattr(project.folder, "name", None) if project.folder_id else None,
        role=role,
        progress=_calculate_progress(project.issues, project),
        member_count=len(project.members),
        milestone_count=len(project.milestones),
        issue_count=len(project.issues),
        overdue_issue_count=overdue_issue_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _serialize_milestone(milestone: Milestone) -> MilestoneItem:
    issues = list(milestone.issues)
    completed_issue_count = sum(1 for issue in issues if _is_done_status(issue.status))
    return MilestoneItem(
        id=milestone.id,
        project_id=milestone.project_id,
        title=milestone.title,
        description=milestone.description,
        status=milestone.status,
        start_date=milestone.start_date,
        due_date=milestone.due_date,
        sort_order=milestone.sort_order,
        progress=_calculate_progress(issues),
        issue_count=len(issues),
        completed_issue_count=completed_issue_count,
        updated_at=milestone.updated_at,
    )


def _serialize_comment(comment: IssueComment) -> IssueCommentItem:
    return IssueCommentItem(
        id=comment.id,
        issue_id=comment.issue_id,
        author_id=comment.author_id,
        author_name=comment.author.full_name,
        body=comment.body,
        body_blocks=comment.body_blocks,
        created_at=comment.created_at,
    )


def _serialize_activity(log: IssueActivityLog, reference_lookup: dict[str, str]) -> ActivityLogItem:
    return ActivityLogItem(
        id=log.id,
        issue_id=log.issue_id,
        actor_id=log.actor_id,
        actor_name=getattr(log.actor, "full_name", None),
        action=log.action,
        field_name=log.field_name,
        from_value=log.from_value,
        to_value=log.to_value,
        message=log.message,
        created_at=log.created_at,
    )


def _project_role(project: Project, user: User) -> str:
    if user.is_admin:
        return "owner"
    membership = next((member for member in project.members if member.user_id == user.id), None)
    return membership.role if membership is not None else "member"


DEFAULT_PROJECT_STATUSES: list[tuple[str, str, str, str, int]] = [
    # (slug, name, color, category, sort_order)
    ("backlog", "Backlog", "#6b7280", "backlog", 0),
    ("todo", "Todo", "#3b82f6", "active", 1),
    ("in_progress", "In Progress", "#f59e0b", "active", 2),
    ("done", "Done", "#22c55e", "done", 3),
    ("canceled", "Canceled", "#ef4444", "canceled", 4),
]


def _auto_key_from_name(name: str) -> str:
    """Generate a short key from name (initials of words, or romanized first chars)."""
    import re as _re
    import unicodedata as _ud

    cleaned = _ud.normalize("NFKD", name).encode("ascii", "ignore").decode()
    cleaned = _re.sub(r"[^A-Za-z0-9\\s]", "", cleaned).strip()
    if cleaned:
        words = cleaned.upper().split()
        key = "".join(w[0] for w in words if w)[:6]
        if len(key) >= 2:
            return key
        return cleaned[:6].upper()
    return "LS"


def _unique_key(db: Session, base_name: str) -> str:
    """Generate a unique project key from a name."""
    resolved = _auto_key_from_name(base_name)
    base = resolved
    counter = 1
    while db.scalar(select(Project).where(func.lower(Project.key) == resolved.lower())):
        resolved = f"{base}{counter}"
        counter += 1
    return resolved


def _create_default_statuses(db: Session, project_id: str) -> None:
    for slug, name, color, category, sort_order in DEFAULT_PROJECT_STATUSES:
        db.add(
            ProjectStatus(
                id=new_id(),
                project_id=project_id,
                slug=slug,
                name=name,
                color=color,
                category=category,
                sort_order=sort_order,
            )
        )


def _create_default_labels(db: Session, project_id: str) -> None:
    for name, color in [
        ("blocked", "#b45309"),
        ("customer", "#1d4ed8"),
        ("qa", "#0f766e"),
    ]:
        db.add(Label(id=new_id(), project_id=project_id, name=name, color=color))


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
) -> None:
    db.add(
        IssueActivityLog(
            id=new_id(),
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
    reference_type: str = "issue",
    reference_id: str | None = None,
) -> None:
    db.add(
        Notification(
            id=new_id(),
            user_id=user_id,
            type=ntype,
            title=title,
            body=body,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    )


def _extract_mentions_from_blocks(blocks: list[dict], out: set[str]) -> None:
    """Recursively extract @mention user IDs from BlockNote-style content blocks."""
    import re

    for block in blocks:
        if isinstance(block, dict):
            # Check inline content for mention-type nodes
            for content_item in block.get("content", []):
                if isinstance(content_item, dict):
                    if content_item.get("type") == "mention":
                        uid = content_item.get("props", {}).get("user_id") or content_item.get("attrs", {}).get("id")
                        if uid:
                            out.add(uid)
                    text = content_item.get("text", "")
                    if text:
                        out.update(re.findall(r"@([0-9a-f-]{36})", text))
            # Recurse into children
            for child in block.get("children", []):
                if isinstance(child, dict):
                    _extract_mentions_from_blocks([child], out)


def _build_attachment_download_url(storage_key: str) -> str:
    settings = get_settings()
    client = get_minio_client()
    return client.presigned_get_object(
        settings.minio_bucket,
        storage_key,
        expires=timedelta(hours=1),
    )


def _next_issue_number(db: Session, project_id: str) -> int:
    current = db.scalar(select(func.max(Issue.issue_number)).where(Issue.project_id == project_id))
    return int(current or 0) + 1


def _next_issue_board_position(db: Session, project_id: str, status_value: str) -> int:
    current = db.scalar(
        select(func.max(Issue.board_position)).where(
            Issue.project_id == project_id,
            Issue.status == status_value,
        )
    )
    return int(current or 0) + 1


def _validate_member_user(db: Session, project: Project, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if any(member.user_id == user_id for member in project.members):
        raise HTTPException(status_code=409, detail="User is already a project member.")
    return user


def _validate_issue_assignee(project: Project, assignee_id: str | None) -> None:
    if assignee_id is None:
        return
    if assignee_id not in {member.user_id for member in project.members}:
        raise HTTPException(status_code=400, detail="Assignee must be a project member.")


def _validate_milestone(project: Project, milestone_id: str | None) -> None:
    if milestone_id is None:
        return
    if milestone_id not in {milestone.id for milestone in project.milestones}:
        raise HTTPException(status_code=400, detail="Milestone does not belong to this project.")


def _validate_parent_issue(
    db: Session,
    project: Project,
    parent_id: str | None,
    *,
    issue_id: str | None = None,
) -> None:
    if parent_id is None:
        return

    parent = db.scalar(select(Issue).where(Issue.id == parent_id))
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent issue not found.")
    if parent.project_id != project.id:
        raise HTTPException(status_code=400, detail="Parent issue must belong to the same project.")
    if issue_id is not None and parent.id == issue_id:
        raise HTTPException(status_code=409, detail="Issue cannot be its own parent.")

    visited: set[str] = set()
    ancestor: Issue | None = parent
    while ancestor is not None:
        if ancestor.id in visited:
            raise HTTPException(status_code=409, detail="Issue parent relationship cannot contain a cycle.")
        visited.add(ancestor.id)
        if issue_id is not None and ancestor.parent_id == issue_id:
            raise HTTPException(status_code=409, detail="Issue parent relationship cannot contain a cycle.")
        if ancestor.parent_id is None:
            break
        ancestor = db.scalar(select(Issue).where(Issue.id == ancestor.parent_id))


def _set_issue_labels(db: Session, issue: Issue, label_ids: list[str], project: Project) -> None:
    if not label_ids:
        issue.label_links.clear()
        return

    allowed_labels = {label.id: label for label in project.labels}
    if any(label_id not in allowed_labels for label_id in label_ids):
        raise HTTPException(status_code=400, detail="One or more labels are invalid for this project.")

    issue.label_links.clear()
    for label_id in label_ids:
        issue.label_links.append(IssueLabel(id=new_id(), label_id=label_id))


def _get_issue_for_user(
    db: Session,
    user: User,
    issue_id: str,
    *,
    require_editor: bool = False,
) -> tuple[Issue, Project]:
    issue = db.scalar(
        select(Issue)
        .options(
            selectinload(Issue.project).selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Issue.project).selectinload(Project.labels),
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
        raise HTTPException(status_code=404, detail="Issue not found.")

    if require_editor:
        project, _ = _ensure_project_editor(db, user, issue.project_id)
    else:
        project, _ = _ensure_project_access(db, user, issue.project_id)
    return issue, project


@router.get("/projects", response_model=ProjectListResponse)
@router.get("/lists", response_model=ProjectListResponse)
def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="updated_at"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    q: str = Query(default=""),
    archived: bool | None = None,
    team_id: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectListResponse:
    if team_id is not None:
        _ensure_space_access(db, current_user, team_id)

    projects = list(
        db.scalars(
            _accessible_projects_query(current_user).options(
                selectinload(Project.members).selectinload(ProjectMember.user),
                selectinload(Project.milestones),
                selectinload(Project.issues).selectinload(Issue.comments),
                selectinload(Project.issues).selectinload(Issue.subtasks),
            )
        )
    )

    q_lower = q.strip().lower()
    if archived is not None:
        projects = [project for project in projects if project.archived is archived]
    if team_id is not None:
        projects = [project for project in projects if project.team_id == team_id]
    if q_lower:
        projects = [
            project
            for project in projects
            if q_lower in project.name.lower()
            or q_lower in project.key.lower()
            or q_lower in project.description.lower()
        ]

    reverse = sort_dir == "desc"
    if sort_by == "name":
        projects.sort(key=lambda project: project.name.lower(), reverse=reverse)
    elif sort_by == "key":
        projects.sort(key=lambda project: project.key.lower(), reverse=reverse)
    elif sort_by == "progress":
        projects.sort(key=lambda project: _calculate_progress(project.issues), reverse=reverse)
    else:
        projects.sort(key=lambda project: project.updated_at, reverse=reverse)

    # Build team name lookup
    team_ids = {p.team_id for p in projects if p.team_id}
    team_names: dict[str, str] = {}
    if team_ids:
        teams = db.scalars(
            select(Team).where(
                Team.id.in_(team_ids),
                Team.trashed_at.is_(None),
            )
        )
        team_names = {t.id: t.name for t in teams}

    serialized = [
        _serialize_project(project, _project_role(project, current_user), team_names.get(project.team_id, None) if project.team_id else None)
        for project in projects
    ]
    page_items, total = _paginate(serialized, page, page_size)
    return ProjectListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.get("/spaces/{space_id}/lists", response_model=ProjectListResponse)
def list_space_lists(
    space_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="updated_at"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    q: str = Query(default=""),
    archived: bool | None = None,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectListResponse:
    _ensure_space_access(db, current_user, space_id)
    return list_projects(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        q=q,
        archived=archived,
        team_id=space_id,
        db=db,
        current_user=current_user,
    )


@router.post("/projects", response_model=ProjectListItem, status_code=status.HTTP_201_CREATED)
@router.post("/lists", response_model=ProjectListItem, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectListItem:
    resolved_key = payload.key.upper() if payload.key else _unique_key(db, payload.name)

    resolved_team_name: str | None = None
    resolved_team_id = payload.team_id
    if resolved_team_id:
        team, _role = _ensure_space_editor(db, current_user, resolved_team_id)
        resolved_team_name = team.name
    else:
        team = get_or_create_default_pms_space(db)
        resolved_team_id = team.id
        resolved_team_name = team.name

    _validate_folder_membership(db, resolved_team_id, payload.folder_id)

    project = Project(
        id=new_id(),
        key=resolved_key,
        name=payload.name.strip(),
        description=payload.description.strip(),
        status="active",
        team_id=resolved_team_id,
        folder_id=payload.folder_id,
        created_by_id=current_user.id,
    )
    db.add(project)
    db.add(
        ProjectMember(
            id=new_id(),
            project_id=project.id,
            user_id=current_user.id,
            role="owner",
        )
    )
    _create_default_labels(db, project.id)
    _create_default_statuses(db, project.id)
    db.commit()
    db.refresh(project)
    project = db.scalar(
        select(Project)
        .options(
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.milestones),
            selectinload(Project.issues).selectinload(Issue.comments),
        )
        .where(Project.id == project.id)
    )
    return _serialize_project(project, "owner", resolved_team_name)


@router.get("/projects/{project_id}", response_model=ProjectListItem)
@router.get("/lists/{project_id}", response_model=ProjectListItem)
def get_project(
    project_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectListItem:
    project, role = _ensure_project_access(db, current_user, project_id)
    project = db.scalar(
        select(Project)
        .options(
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.milestones),
            selectinload(Project.issues).selectinload(Issue.comments),
        )
        .where(Project.id == project.id)
    )
    t_name = db.scalar(select(Team.name).where(Team.id == project.team_id)) if project.team_id else None
    return _serialize_project(project, role, t_name)


@router.patch("/projects/{project_id}", response_model=ProjectListItem)
@router.patch("/lists/{project_id}", response_model=ProjectListItem)
def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectListItem:
    project, role = _ensure_project_owner(db, current_user, project_id)
    if "folder_id" in payload.model_fields_set:
        _validate_folder_membership(db, project.team_id, payload.folder_id)
        project.folder_id = payload.folder_id

    for field_name in ["name", "description", "status", "archived"]:
        if field_name not in payload.model_fields_set:
            continue
        value = getattr(payload, field_name)
        if value is None:
            continue
        setattr(project, field_name, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(project)
    project = db.scalar(
        select(Project)
        .options(
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.milestones),
            selectinload(Project.issues).selectinload(Issue.comments),
        )
        .where(Project.id == project.id)
    )
    t_name = db.scalar(select(Team.name).where(Team.id == project.team_id)) if project.team_id else None
    return _serialize_project(project, role, t_name)


@router.get("/projects/{project_id}/members", response_model=ProjectMemberListResponse)
@router.get("/lists/{project_id}/members", response_model=ProjectMemberListResponse)
def list_project_members(
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectMemberListResponse:
    project, _ = _ensure_project_access(db, current_user, project_id)
    members = [
        ProjectMemberItem(
            user_id=member.user_id,
            email=member.user.email,
            full_name=member.user.full_name,
            is_admin=member.user.is_admin,
            role=member.role,
            joined_at=member.joined_at,
        )
        for member in sorted(project.members, key=lambda item: (item.role != "owner", item.user.full_name.lower()))
    ]
    page_items, total = _paginate(members, page, page_size)
    return ProjectMemberListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMemberItem,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/lists/{project_id}/members",
    response_model=ProjectMemberItem,
    status_code=status.HTTP_201_CREATED,
)
def add_project_member(
    project_id: str,
    payload: ProjectMemberCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectMemberItem:
    project, _ = _ensure_project_owner(db, current_user, project_id)
    user = _validate_member_user(db, project, payload.user_id)
    member = ProjectMember(
        id=new_id(),
        project_id=project.id,
        user_id=user.id,
        role=payload.role,
    )
    db.add(member)
    db.commit()
    return ProjectMemberItem(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_admin=user.is_admin,
        role=member.role,
        joined_at=member.joined_at,
    )


class MemberRoleUpdateRequest(BaseModel):
    role: Literal["owner", "admin", "editor", "viewer", "member"]


@router.patch("/projects/{project_id}/members/{user_id}/role", response_model=ProjectMemberItem)
@router.patch("/lists/{project_id}/members/{user_id}/role", response_model=ProjectMemberItem)
def update_member_role(
    project_id: str,
    user_id: str,
    payload: MemberRoleUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectMemberItem:
    project, _ = _ensure_project_owner(db, current_user, project_id)
    membership = next((m for m in project.members if m.user_id == user_id), None)
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    membership.role = payload.role
    db.commit()
    db.refresh(membership)
    user = membership.user
    return ProjectMemberItem(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_admin=user.is_admin,
        role=membership.role,
        joined_at=membership.joined_at,
    )


@router.delete("/projects/{project_id}/members/{user_id}")
@router.delete("/lists/{project_id}/members/{user_id}")
def remove_project_member(
    project_id: str,
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    project, _ = _ensure_project_owner(db, current_user, project_id)
    membership = next((m for m in project.members if m.user_id == user_id), None)
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    if membership.role == "owner" and sum(1 for m in project.members if m.role == "owner") == 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last owner.")
    db.delete(membership)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/milestones", response_model=MilestoneListResponse)
@router.get("/lists/{project_id}/milestones", response_model=MilestoneListResponse)
def list_milestones(
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="sort_order"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MilestoneListResponse:
    project, _ = _ensure_project_access(db, current_user, project_id)
    milestones = list(project.milestones)
    reverse = sort_dir == "desc"
    if sort_by == "due_date":
        milestones.sort(key=lambda milestone: milestone.due_date or date.max, reverse=reverse)
    elif sort_by == "updated_at":
        milestones.sort(key=lambda milestone: milestone.updated_at, reverse=reverse)
    else:
        milestones.sort(key=lambda milestone: milestone.sort_order, reverse=reverse)
    serialized = [_serialize_milestone(milestone) for milestone in milestones]
    page_items, total = _paginate(serialized, page, page_size)
    return MilestoneListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.post(
    "/projects/{project_id}/milestones",
    response_model=MilestoneItem,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/lists/{project_id}/milestones",
    response_model=MilestoneItem,
    status_code=status.HTTP_201_CREATED,
)
def create_milestone(
    project_id: str,
    payload: MilestoneCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MilestoneItem:
    project, _ = _ensure_project_owner(db, current_user, project_id)
    milestone = Milestone(
        id=new_id(),
        project_id=project.id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        status=payload.status,
        start_date=payload.start_date,
        due_date=payload.due_date,
        sort_order=payload.sort_order,
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return _serialize_milestone(milestone)


@router.patch("/milestones/{milestone_id}", response_model=MilestoneItem)
def update_milestone(
    milestone_id: str,
    payload: MilestoneUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MilestoneItem:
    milestone = db.scalar(
        select(Milestone)
        .options(selectinload(Milestone.project).selectinload(Project.members).selectinload(ProjectMember.user))
        .where(Milestone.id == milestone_id)
    )
    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found.")
    _ensure_project_owner(db, current_user, milestone.project_id)
    for field_name in ["title", "description", "status", "start_date", "due_date", "sort_order"]:
        value = getattr(payload, field_name)
        if value is not None:
            setattr(milestone, field_name, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(milestone)
    milestone = db.scalar(
        select(Milestone).options(selectinload(Milestone.issues)).where(Milestone.id == milestone_id)
    )
    return _serialize_milestone(milestone)


@router.get("/projects/{project_id}/labels", response_model=LabelListResponse)
@router.get("/lists/{project_id}/labels", response_model=LabelListResponse)
def list_project_labels(
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LabelListResponse:
    _ensure_project_access(db, current_user, project_id)
    labels = list(db.scalars(select(Label).where(Label.project_id == project_id).order_by(Label.name)))
    items = [LabelItem(id=label.id, name=label.name, color=label.color) for label in labels]
    page_items, total = _paginate(items, page, page_size)
    return LabelListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.post("/projects/{project_id}/labels", response_model=LabelItem, status_code=status.HTTP_201_CREATED)
@router.post("/lists/{project_id}/labels", response_model=LabelItem, status_code=status.HTTP_201_CREATED)
def create_project_label(
    project_id: str,
    payload: LabelCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LabelItem:
    _ensure_project_owner(db, current_user, project_id)
    existing = db.scalar(
        select(Label).where(Label.project_id == project_id, func.lower(Label.name) == payload.name.strip().lower())
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Label name already exists in this project.")
    label = Label(id=new_id(), project_id=project_id, name=payload.name.strip(), color=payload.color)
    db.add(label)
    db.commit()
    db.refresh(label)
    return LabelItem(id=label.id, name=label.name, color=label.color)


@router.patch("/labels/{label_id}", response_model=LabelItem)
def update_label(
    label_id: str,
    payload: LabelUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LabelItem:
    label = db.scalar(select(Label).where(Label.id == label_id))
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found.")
    _ensure_project_owner(db, current_user, label.project_id)
    if payload.name is not None:
        normalized_name = payload.name.strip()
        existing = db.scalar(
            select(Label).where(
                Label.project_id == label.project_id,
                Label.id != label.id,
                func.lower(Label.name) == normalized_name.lower(),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="Label name already exists in this project.")
        label.name = normalized_name
    if payload.color is not None:
        label.color = payload.color
    db.commit()
    db.refresh(label)
    return LabelItem(id=label.id, name=label.name, color=label.color)


@router.delete("/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    label_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> None:
    label = db.scalar(select(Label).where(Label.id == label_id))
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found.")
    _ensure_project_owner(db, current_user, label.project_id)
    db.delete(label)
    db.commit()


@router.get("/projects/{project_id}/issues", response_model=IssueListResponse)
@router.get("/lists/{project_id}/issues", response_model=IssueListResponse)
def list_issues(
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    sort_by: str = Query(default="board_position"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    q: str = Query(default=""),
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    assignee_id: str | None = None,
    priority: str | None = None,
    label_id: str | None = None,
    milestone_id: str | None = None,
    archived: bool | None = None,
    due_date_from: date | None = None,
    due_date_to: date | None = None,
    start_date_from: date | None = None,
    start_date_to: date | None = None,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> IssueListResponse:
    _ensure_project_access(db, current_user, project_id)
    issues = list(
        db.scalars(
            select(Issue)
            .options(
                selectinload(Issue.project),
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
            .where(Issue.project_id == project_id)
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
            or q_lower in _issue_reference(issue).lower()
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

    serialized = [_serialize_issue(issue) for issue in issues]
    page_items, total = _paginate(serialized, page, page_size)
    return IssueListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.post(
    "/projects/{project_id}/issues",
    response_model=IssueListItem,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/lists/{project_id}/issues",
    response_model=IssueListItem,
    status_code=status.HTTP_201_CREATED,
)
def create_issue(
    project_id: str,
    payload: IssueCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> IssueListItem:
    project, _ = _ensure_project_editor(db, current_user, project_id)
    _validate_issue_assignee(project, payload.assignee_id)
    _validate_milestone(project, payload.milestone_id)
    _validate_parent_issue(db, project, payload.parent_id)
    next_position = _next_issue_board_position(db, project_id, payload.status)
    issue = Issue(
        id=new_id(),
        project_id=project.id,
        issue_number=_next_issue_number(db, project.id),
        title=payload.title.strip(),
        description=payload.description.strip(),
        description_blocks=payload.description_blocks,
        parent_id=payload.parent_id,
        status=payload.status,
        priority=payload.priority,
        assignee_id=payload.assignee_id,
        reporter_id=current_user.id,
        milestone_id=payload.milestone_id,
        start_date=payload.start_date,
        due_date=payload.due_date,
        estimate_hours=payload.estimate_hours,
        recurrence_rule=payload.recurrence_rule,
        board_position=next_position,
    )
    db.add(issue)
    db.flush()
    _set_issue_labels(db, issue, payload.label_ids, project)
    if payload.description_blocks:
        sync_embedded_media(db, payload.description_blocks, "issue", issue.id, current_user)
    _log_issue_activity(
        db,
        issue.id,
        current_user.id,
        "created",
        f"{current_user.full_name} created {_issue_reference(issue)}.",
    )
    db.commit()
    issue = db.scalar(
        select(Issue)
        .options(
            selectinload(Issue.project),
            selectinload(Issue.milestone),
            selectinload(Issue.assignee),
            selectinload(Issue.reporter),
            selectinload(Issue.comments),
            selectinload(Issue.label_links).selectinload(IssueLabel.label),
            selectinload(Issue.subtasks),
            selectinload(Issue.checklist_items),
            selectinload(Issue.time_entries),
        )
        .where(Issue.id == issue.id)
    )
    return _serialize_issue(issue)


@router.get("/issues/{issue_id}", response_model=IssueDetailResponse)
def get_issue(
    issue_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> IssueDetailResponse:
    issue, project = _get_issue_for_user(db, current_user, issue_id)
    dependencies = list(
        db.scalars(
            select(ScheduleDependency).where(
                ScheduleDependency.project_id == project.id,
                or_(
                    ScheduleDependency.predecessor_id == issue.id,
                    ScheduleDependency.successor_id == issue.id,
                ),
            )
        )
    )
    return IssueDetailResponse(
        issue=_serialize_issue(issue),
        comments=[_serialize_comment(comment) for comment in sorted(issue.comments, key=lambda item: item.created_at)],
        dependencies=[
            DependencyItem(
                id=dependency.id,
                predecessor_kind=dependency.predecessor_kind,
                predecessor_id=dependency.predecessor_id,
                successor_kind=dependency.successor_kind,
                successor_id=dependency.successor_id,
                relation_type=dependency.relation_type,
            )
            for dependency in dependencies
        ],
        subtasks=[
            _serialize_issue(sub)
            for sub in sorted(issue.subtasks, key=lambda s: s.created_at)
            if not sub.archived
        ],
        attachments=[
            AttachmentItem(
                id=att.id,
                issue_id=att.issue_id,
                filename=att.filename,
                content_type=att.content_type,
                size_bytes=att.size_bytes,
                download_url=_build_attachment_download_url(att.storage_key),
                uploaded_by_id=att.uploaded_by_id,
                uploaded_by_name=att.uploaded_by.full_name,
                created_at=att.created_at,
            )
            for att in sorted(issue.attachments, key=lambda a: a.created_at)
        ],
        checklist_items=[
            ChecklistItemResponse(
                id=ci.id,
                issue_id=ci.issue_id,
                text=ci.text,
                completed=ci.completed,
                sort_order=ci.sort_order,
                created_at=ci.created_at,
            )
            for ci in sorted(issue.checklist_items, key=lambda c: c.sort_order)
        ],
        time_entries=[
            TimeEntryItem(
                id=te.id,
                issue_id=te.issue_id,
                user_id=te.user_id,
                user_name=te.user.full_name,
                duration_minutes=te.duration_minutes,
                description=te.description,
                entry_date=te.entry_date,
                created_at=te.created_at,
            )
            for te in sorted(issue.time_entries, key=lambda t: t.created_at, reverse=True)
        ],
    )


@router.patch("/issues/{issue_id}", response_model=IssueListItem)
def update_issue(
    issue_id: str,
    payload: IssueUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> IssueListItem:
    issue, project = _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    if "assignee_id" in payload.model_fields_set:
        _validate_issue_assignee(project, payload.assignee_id)
    if "milestone_id" in payload.model_fields_set:
        _validate_milestone(project, payload.milestone_id)
    if "parent_id" in payload.model_fields_set:
        _validate_parent_issue(db, project, payload.parent_id, issue_id=issue.id)

    old_status = issue.status
    nullable_fields = {
        "assignee_id",
        "milestone_id",
        "start_date",
        "due_date",
        "recurrence_rule",
    }
    field_specs = [
        ("title", "updated title"),
        ("description", "updated description"),
        ("status", "changed status"),
        ("priority", "changed priority"),
        ("assignee_id", "changed assignee"),
        ("milestone_id", "changed milestone"),
        ("start_date", "updated start date"),
        ("due_date", "updated due date"),
        ("board_position", "reordered board position"),
        ("archived", "changed archive state"),
        ("estimate_hours", "updated estimate"),
        ("recurrence_rule", "updated recurrence"),
    ]
    for field_name, message in field_specs:
        if field_name not in payload.model_fields_set:
            continue
        value = getattr(payload, field_name)
        if value is None and field_name not in nullable_fields:
            continue
        previous = getattr(issue, field_name)
        normalized_value = value.strip() if isinstance(value, str) else value
        if previous == normalized_value:
            continue
        setattr(issue, field_name, normalized_value)
        _log_issue_activity(
            db,
            issue.id,
            current_user.id,
            "updated",
            f"{current_user.full_name} {message} for {_issue_reference(issue)}.",
            field_name=field_name,
            from_value=str(previous) if previous is not None else None,
            to_value=str(normalized_value) if normalized_value is not None else None,
        )

    if "parent_id" in payload.model_fields_set:
        previous = issue.parent_id
        issue.parent_id = payload.parent_id
        if previous != payload.parent_id:
            _log_issue_activity(
                db,
                issue.id,
                current_user.id,
                "updated",
                f"{current_user.full_name} {'removed parent' if payload.parent_id is None else 'changed parent'} for {_issue_reference(issue)}.",
                field_name="parent_id",
                from_value=previous,
                to_value=payload.parent_id,
            )

    if "description_blocks" in payload.model_fields_set:
        issue.description_blocks = payload.description_blocks
        sync_embedded_media(db, payload.description_blocks, "issue", issue.id, current_user)
        _log_issue_activity(
            db,
            issue.id,
            current_user.id,
            "updated",
            f"{current_user.full_name} updated description for {_issue_reference(issue)}.",
            field_name="description_blocks",
        )

    if payload.label_ids is not None:
        _set_issue_labels(db, issue, payload.label_ids, project)
        _log_issue_activity(
            db,
            issue.id,
            current_user.id,
            "updated",
            f"{current_user.full_name} updated labels for {_issue_reference(issue)}.",
            field_name="label_ids",
        )

    if payload.status is not None and payload.status != old_status and payload.board_position is None:
        issue.board_position = _next_issue_board_position(db, issue.project_id, payload.status)

    # Notification triggers
    ref = _issue_reference(issue)
    if payload.assignee_id is not None and payload.assignee_id != current_user.id:
        _create_notification(
            db, payload.assignee_id, "assigned",
            f"{ref} assigned to you",
            f"{current_user.full_name} assigned {ref} ({issue.title}) to you.",
            reference_id=issue.id,
        )
    if payload.status is not None and payload.status != old_status and issue.assignee_id and issue.assignee_id != current_user.id:
        _create_notification(
            db, issue.assignee_id, "status_changed",
            f"{ref} status → {ISSUE_STATUS_LABELS.get(payload.status, payload.status)}",
            f"{current_user.full_name} changed status of {ref} to {ISSUE_STATUS_LABELS.get(payload.status, payload.status)}.",
            reference_id=issue.id,
        )

    db.commit()
    issue = db.scalar(
        select(Issue)
        .options(
            selectinload(Issue.project),
            selectinload(Issue.milestone),
            selectinload(Issue.assignee),
            selectinload(Issue.reporter),
            selectinload(Issue.comments),
            selectinload(Issue.label_links).selectinload(IssueLabel.label),
            selectinload(Issue.subtasks),
            selectinload(Issue.checklist_items),
            selectinload(Issue.time_entries),
        )
        .where(Issue.id == issue.id)
    )
    return _serialize_issue(issue)


@router.patch("/projects/{project_id}/issues/bulk", response_model=BulkUpdateResponse)
@router.patch("/lists/{project_id}/issues/bulk", response_model=BulkUpdateResponse)
def bulk_update_issues(
    project_id: str,
    payload: BulkUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BulkUpdateResponse:
    project, _role = _ensure_project_editor(db, current_user, project_id)
    issue_map = {
        issue.id: issue
        for issue in db.scalars(
            select(Issue)
            .options(
                selectinload(Issue.project),
                selectinload(Issue.label_links).selectinload(IssueLabel.label),
                selectinload(Issue.assignee),
            )
            .where(Issue.id.in_(payload.issue_ids), Issue.project_id == project_id)
        )
    }
    ordered_issues = [issue_map[issue_id] for issue_id in payload.issue_ids if issue_id in issue_map]
    if not ordered_issues:
        raise HTTPException(status_code=404, detail="No matching issues found.")

    if payload.delete:
        media_keys: list[str] = []
        for issue in ordered_issues:
            for child in getattr(issue, "subtasks", []):
                child.parent_id = None
            media_keys.extend(cleanup_media_for_resource(db, "issue", issue.id))
            db.delete(issue)
        db.commit()
        if media_keys:
            settings = get_settings()
            client = get_minio_client()
            for key in media_keys:
                try:
                    client.remove_object(settings.minio_bucket, key)
                except Exception:
                    pass
        return BulkUpdateResponse(updated_count=0, deleted_count=len(ordered_issues))

    label_map = {label.id: label for label in project.labels}
    updated = 0
    next_position = None
    if payload.status is not None:
        next_position = _next_issue_board_position(db, project_id, payload.status)

    for issue in ordered_issues:
        changed = False
        if payload.status is not None and issue.status != payload.status:
            _log_issue_activity(db, issue.id, current_user.id, "updated", f"{current_user.full_name} updated status.", field_name="status", from_value=issue.status, to_value=payload.status)
            issue.status = payload.status
            if next_position is not None:
                issue.board_position = next_position
                next_position += 1
            changed = True
        if payload.priority is not None and issue.priority != payload.priority:
            _log_issue_activity(db, issue.id, current_user.id, "updated", f"{current_user.full_name} updated priority.", field_name="priority", from_value=issue.priority, to_value=payload.priority)
            issue.priority = payload.priority
            changed = True
        if "assignee_id" in payload.model_fields_set and payload.assignee_id != issue.assignee_id:
            _validate_issue_assignee(project, payload.assignee_id)
            old_name = getattr(issue.assignee, "full_name", "Unassigned")
            issue.assignee_id = payload.assignee_id
            _log_issue_activity(db, issue.id, current_user.id, "updated", f"{current_user.full_name} updated assignee.", field_name="assignee", from_value=old_name, to_value=payload.assignee_id or "Unassigned")
            changed = True
        if payload.archived is not None and issue.archived != payload.archived:
            issue.archived = payload.archived
            _log_issue_activity(db, issue.id, current_user.id, "updated", f"{current_user.full_name} {'archived' if payload.archived else 'unarchived'} issue.", field_name="archived", from_value=str(not payload.archived), to_value=str(payload.archived))
            changed = True
        if payload.add_label_ids:
            existing_ids = {link.label_id for link in issue.label_links}
            for lid in payload.add_label_ids:
                if lid not in existing_ids and lid in label_map:
                    issue.label_links.append(IssueLabel(id=new_id(), label_id=lid))
                    changed = True
        if payload.remove_label_ids:
            issue.label_links = [link for link in issue.label_links if link.label_id not in payload.remove_label_ids]
            changed = True
        if changed:
            updated += 1

    db.commit()
    return BulkUpdateResponse(updated_count=updated, deleted_count=0)


@router.delete("/issues/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(
    issue_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> None:
    issue, _project = _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    for child in issue.subtasks:
        child.parent_id = None
    media_keys = cleanup_media_for_resource(db, "issue", issue.id)
    db.delete(issue)
    db.commit()
    # Post-commit MinIO cleanup — DB is authoritative, best-effort storage delete
    if media_keys:
        settings = get_settings()
        client = get_minio_client()
        for key in media_keys:
            try:
                client.remove_object(settings.minio_bucket, key)
            except Exception:
                pass


@router.post(
    "/issues/{issue_id}/comments",
    response_model=IssueCommentItem,
    status_code=status.HTTP_201_CREATED,
)
def create_issue_comment(
    issue_id: str,
    payload: IssueCommentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> IssueCommentItem:
    issue, _ = _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    comment = IssueComment(
        id=new_id(),
        issue_id=issue.id,
        author_id=current_user.id,
        body=payload.body.strip(),
        body_blocks=payload.body_blocks,
    )
    db.add(comment)
    _log_issue_activity(
        db,
        issue.id,
        current_user.id,
        "commented",
        f"{current_user.full_name} added a comment to {_issue_reference(issue)}.",
    )
    # Notify assignee and reporter (excluding comment author)
    ref = _issue_reference(issue)
    notify_ids = {uid for uid in [issue.assignee_id, issue.reporter_id] if uid and uid != current_user.id}
    for uid in notify_ids:
        _create_notification(
            db, uid, "commented",
            f"New comment on {ref}",
            f"{current_user.full_name} commented on {ref} ({issue.title}).",
            reference_id=issue.id,
        )

    # Parse @mentions from comment body and body_blocks
    import re

    mentioned_ids: set[str] = set()
    if payload.body:
        mentioned_ids.update(re.findall(r"@([0-9a-f-]{36})", payload.body))
    if payload.body_blocks:
        _extract_mentions_from_blocks(payload.body_blocks, mentioned_ids)
    mentioned_ids -= notify_ids
    mentioned_ids.discard(current_user.id)
    for uid in mentioned_ids:
        user = db.scalar(select(User).where(User.id == uid))
        if user is not None:
            _create_notification(
                db, uid, "mentioned",
                f"Mentioned in {ref}",
                f"{current_user.full_name} mentioned you in a comment on {ref}.",
                reference_id=issue.id,
            )

    db.commit()
    comment = db.scalar(
        select(IssueComment).options(selectinload(IssueComment.author)).where(IssueComment.id == comment.id)
    )
    return _serialize_comment(comment)


@router.get("/issues/{issue_id}/activity-logs", response_model=ActivityLogListResponse)
def list_issue_activity_logs(
    issue_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ActivityLogListResponse:
    issue, _ = _get_issue_for_user(db, current_user, issue_id)
    logs = list(
        db.scalars(
            select(IssueActivityLog)
            .options(selectinload(IssueActivityLog.actor))
            .where(IssueActivityLog.issue_id == issue.id)
            .order_by(IssueActivityLog.created_at.desc())
        )
    )
    reference_lookup = {issue.id: _issue_reference(issue)}
    serialized = [_serialize_activity(log, reference_lookup) for log in logs]
    page_items, total = _paginate(serialized, page, page_size)
    return ActivityLogListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.post("/dependencies", response_model=DependencyItem, status_code=status.HTTP_201_CREATED)
def create_dependency(
    payload: DependencyCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DependencyItem:
    predecessor_issue, predecessor_project = _get_issue_for_user(db, current_user, payload.predecessor_id, require_editor=True)
    successor_issue, successor_project = _get_issue_for_user(db, current_user, payload.successor_id, require_editor=True)
    if predecessor_project.id != successor_project.id:
        raise HTTPException(status_code=400, detail="Dependencies must stay within the same project.")

    dependency = ScheduleDependency(
        id=new_id(),
        project_id=predecessor_project.id,
        predecessor_kind=payload.predecessor_kind,
        predecessor_id=predecessor_issue.id,
        successor_kind=payload.successor_kind,
        successor_id=successor_issue.id,
        relation_type=payload.relation_type,
    )
    db.add(dependency)
    _log_issue_activity(
        db,
        successor_issue.id,
        current_user.id,
        "dependency_added",
        f"{current_user.full_name} linked {_issue_reference(predecessor_issue)} to {_issue_reference(successor_issue)}.",
    )
    db.commit()
    return DependencyItem(
        id=dependency.id,
        predecessor_kind=dependency.predecessor_kind,
        predecessor_id=dependency.predecessor_id,
        successor_kind=dependency.successor_kind,
        successor_id=dependency.successor_id,
        relation_type=dependency.relation_type,
    )


@router.delete("/dependencies/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dependency(
    dependency_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    dependency = db.scalar(select(ScheduleDependency).where(ScheduleDependency.id == dependency_id))
    if dependency is None:
        raise HTTPException(status_code=404, detail="Dependency not found.")
    _ensure_project_editor(db, current_user, dependency.project_id)
    db.delete(dependency)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    project_id: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DashboardSummaryResponse:
    projects = list(
        db.scalars(
            _accessible_projects_query(current_user).options(
                selectinload(Project.members).selectinload(ProjectMember.user),
                selectinload(Project.milestones).selectinload(Milestone.issues),
                selectinload(Project.issues)
                .selectinload(Issue.comments),
                selectinload(Project.issues).selectinload(Issue.assignee),
                selectinload(Project.issues).selectinload(Issue.reporter),
            )
        )
    )
    if project_id:
        projects = [project for project in projects if project.id == project_id]
    issues = [issue for project in projects for issue in project.issues if not issue.archived]
    active_issues = [issue for issue in issues if issue.status not in {"done", "canceled"}]
    overdue_issues = [
        issue
        for issue in active_issues
        if issue.due_date is not None and issue.due_date < date.today()
    ]
    milestone_due_soon_count = sum(
        1
        for project in projects
        for milestone in project.milestones
        if milestone.due_date is not None and milestone.due_date <= date.today() + timedelta(days=14)
    )

    status_counts = [
        StatusCountItem(
            status=status_key,
            label=label,
            count=sum(1 for issue in issues if issue.status == status_key),
        )
        for status_key, label in ISSUE_STATUS_LABELS.items()
    ]
    priority_counts = [
        PriorityCountItem(
            priority=priority_key,
            label=label,
            count=sum(1 for issue in issues if issue.priority == priority_key),
        )
        for priority_key, label in PRIORITY_LABELS.items()
    ]

    recent_logs = list(
        db.scalars(
            select(IssueActivityLog)
            .join(Issue, Issue.id == IssueActivityLog.issue_id)
            .options(selectinload(IssueActivityLog.actor), selectinload(IssueActivityLog.issue).selectinload(Issue.project))
            .where(Issue.project_id.in_([project.id for project in projects] or ["__none__"]))
            .order_by(IssueActivityLog.created_at.desc())
            .limit(8)
        )
    )
    recent_activity = [
        RecentActivityItem(
            id=log.id,
            issue_id=log.issue_id,
            issue_reference=_issue_reference(log.issue),
            message=log.message,
            actor_name=getattr(log.actor, "full_name", None),
            created_at=log.created_at,
        )
        for log in recent_logs
    ]

    project_cards = []
    for project in projects:
        issue_progress_scope = [issue for issue in project.issues if not issue.archived]
        open_issue_count = sum(
            1 for issue in issue_progress_scope if issue.status not in {"done", "canceled"}
        )
        overdue_issue_count = sum(
            1
            for issue in issue_progress_scope
            if issue.status not in {"done", "canceled"}
            and issue.due_date is not None
            and issue.due_date < date.today()
        )
        due_dates = sorted(
            issue.due_date
            for issue in issue_progress_scope
            if issue.due_date is not None and issue.status not in {"done", "canceled"}
        )
        project_cards.append(
            DashboardProjectItem(
                project_id=project.id,
                key=project.key,
                name=project.name,
                progress=_calculate_progress(issue_progress_scope),
                open_issue_count=open_issue_count,
                overdue_issue_count=overdue_issue_count,
                next_due_date=due_dates[0] if due_dates else None,
            )
        )

    return DashboardSummaryResponse(
        project_count=len(projects),
        active_issue_count=len(active_issues),
        overdue_issue_count=len(overdue_issues),
        my_issue_count=sum(1 for issue in active_issues if issue.assignee_id == current_user.id),
        milestone_due_soon_count=milestone_due_soon_count,
        status_counts=status_counts,
        priority_counts=priority_counts,
        projects=project_cards,
        recent_activity=recent_activity,
    )


MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post(
    "/issues/{issue_id}/attachments",
    response_model=AttachmentItem,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    issue_id: str,
    file: UploadFile,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> AttachmentItem:
    issue, project = _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File size exceeds 50 MB limit.")

    settings = get_settings()
    client = get_minio_client()
    attachment_id = new_id()
    storage_key = f"pms/{project.id}/{issue.id}/{attachment_id}/{file.filename}"
    client.put_object(
        settings.minio_bucket,
        storage_key,
        BytesIO(data),
        length=len(data),
        content_type=file.content_type or "application/octet-stream",
    )
    attachment = Attachment(
        id=attachment_id,
        issue_id=issue.id,
        filename=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        storage_key=storage_key,
        uploaded_by_id=current_user.id,
    )
    db.add(attachment)
    _log_issue_activity(
        db,
        issue.id,
        current_user.id,
        "attachment_added",
        f"{current_user.full_name} attached {file.filename} to {_issue_reference(issue)}.",
    )
    db.commit()
    db.refresh(attachment)
    return AttachmentItem(
        id=attachment.id,
        issue_id=attachment.issue_id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        download_url=_build_attachment_download_url(attachment.storage_key),
        uploaded_by_id=attachment.uploaded_by_id,
        uploaded_by_name=current_user.full_name,
        created_at=attachment.created_at,
    )


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RedirectResponse:
    attachment = db.scalar(select(Attachment).where(Attachment.id == attachment_id))
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    _ensure_project_access(db, current_user, db.scalar(select(Issue.project_id).where(Issue.id == attachment.issue_id)))

    url = _build_attachment_download_url(attachment.storage_key)
    return RedirectResponse(url=url, status_code=302)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    attachment = db.scalar(
        select(Attachment).options(selectinload(Attachment.issue).selectinload(Issue.project)).where(Attachment.id == attachment_id)
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    _ensure_project_editor(db, current_user, attachment.issue.project_id)

    settings = get_settings()
    client = get_minio_client()
    client.remove_object(settings.minio_bucket, attachment.storage_key)

    _log_issue_activity(
        db,
        attachment.issue_id,
        current_user.id,
        "attachment_removed",
        f"{current_user.full_name} removed {attachment.filename} from {_issue_reference(attachment.issue)}.",
    )
    db.delete(attachment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Notifications ────────────────────────────────────────────────────


@router.get("/notifications", response_model=NotificationListResponse)
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NotificationListResponse:
    rows = list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .order_by(Notification.created_at.desc())
        )
    )
    page_items, total = _paginate(
        [
            NotificationItem(
                id=n.id,
                type=n.type,
                title=n.title,
                body=n.body,
                reference_type=n.reference_type,
                reference_id=n.reference_id,
                is_read=n.is_read,
                created_at=n.created_at,
            )
            for n in rows
        ],
        page,
        page_size,
    )
    return NotificationListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
def get_unread_count(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> UnreadCountResponse:
    count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    ) or 0
    return UnreadCountResponse(count=count)


@router.patch("/notifications/{notification_id}/read", response_model=NotificationItem)
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NotificationItem:
    notification = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user.id)
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    notification.is_read = True
    db.commit()
    return NotificationItem(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        body=notification.body,
        reference_type=notification.reference_type,
        reference_id=notification.reference_id,
        is_read=notification.is_read,
        created_at=notification.created_at,
    )


@router.patch("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_notifications_read(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    from sqlalchemy import update as sa_update

    db.execute(
        sa_update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Checklist ────────────────────────────────────────────────────────────────


@router.post("/issues/{issue_id}/checklist", response_model=ChecklistItemResponse, status_code=status.HTTP_201_CREATED)
def create_checklist_item(
    issue_id: str,
    payload: ChecklistItemCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ChecklistItemResponse:
    issue, _project = _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    item = ChecklistItem(
        id=new_id(),
        issue_id=issue.id,
        text=payload.text,
        sort_order=payload.sort_order,
    )
    db.add(item)
    _log_issue_activity(
        db,
        issue.id,
        current_user.id,
        "checklist_added",
        f"{current_user.full_name} added checklist item.",
    )
    db.commit()
    return ChecklistItemResponse(
        id=item.id,
        issue_id=item.issue_id,
        text=item.text,
        completed=item.completed,
        sort_order=item.sort_order,
        created_at=item.created_at,
    )


@router.patch("/checklist/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_item(
    item_id: str,
    payload: ChecklistItemUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ChecklistItemResponse:
    item = db.scalar(
        select(ChecklistItem)
        .options(selectinload(ChecklistItem.issue).selectinload(Issue.project))
        .where(ChecklistItem.id == item_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Checklist item not found.")
    _ensure_project_editor(db, current_user, item.issue.project_id)

    if payload.text is not None:
        item.text = payload.text
    if payload.completed is not None and payload.completed != item.completed:
        item.completed = payload.completed
        action = "checklist_checked" if payload.completed else "checklist_unchecked"
        _log_issue_activity(
            db,
            item.issue_id,
            current_user.id,
            action,
            f"{current_user.full_name} {'checked' if payload.completed else 'unchecked'} \"{item.text}\".",
        )
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order

    db.commit()
    return ChecklistItemResponse(
        id=item.id,
        issue_id=item.issue_id,
        text=item.text,
        completed=item.completed,
        sort_order=item.sort_order,
        created_at=item.created_at,
    )


@router.delete("/checklist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    item = db.scalar(
        select(ChecklistItem)
        .options(selectinload(ChecklistItem.issue).selectinload(Issue.project))
        .where(ChecklistItem.id == item_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Checklist item not found.")
    _ensure_project_editor(db, current_user, item.issue.project_id)
    _log_issue_activity(
        db,
        item.issue_id,
        current_user.id,
        "checklist_removed",
        f"{current_user.full_name} removed checklist item \"{item.text}\".",
    )
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/issues/{issue_id}/checklist/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_checklist(
    issue_id: str,
    payload: ChecklistReorderRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    items = list(
        db.scalars(
            select(ChecklistItem).where(ChecklistItem.issue_id == issue_id)
        )
    )
    item_map = {item.id: item for item in items}
    for idx, item_id in enumerate(payload.item_ids):
        if item_id in item_map:
            item_map[item_id].sort_order = idx
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Time Tracking ────────────────────────────────────────────────────────────


@router.post("/issues/{issue_id}/time-entries", response_model=TimeEntryItem, status_code=status.HTTP_201_CREATED)
def create_time_entry(
    issue_id: str,
    payload: TimeEntryCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TimeEntryItem:
    issue, _project = _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    entry = TimeEntry(
        id=new_id(),
        issue_id=issue.id,
        user_id=current_user.id,
        duration_minutes=payload.duration_minutes,
        description=payload.description.strip(),
        entry_date=payload.entry_date,
    )
    db.add(entry)
    hours = payload.duration_minutes / 60
    _log_issue_activity(
        db,
        issue.id,
        current_user.id,
        "time_tracked",
        f"{current_user.full_name} logged {hours:.1f}h.",
    )
    db.commit()
    return TimeEntryItem(
        id=entry.id,
        issue_id=entry.issue_id,
        user_id=entry.user_id,
        user_name=current_user.full_name,
        duration_minutes=entry.duration_minutes,
        description=entry.description,
        entry_date=entry.entry_date,
        created_at=entry.created_at,
    )


@router.patch("/time-entries/{entry_id}", response_model=TimeEntryItem)
def update_time_entry(
    entry_id: str,
    payload: TimeEntryUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TimeEntryItem:
    entry = db.scalar(
        select(TimeEntry)
        .options(selectinload(TimeEntry.issue).selectinload(Issue.project), selectinload(TimeEntry.user))
        .where(TimeEntry.id == entry_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Time entry not found.")
    _ensure_project_editor(db, current_user, entry.issue.project_id)

    if payload.duration_minutes is not None:
        entry.duration_minutes = payload.duration_minutes
    if payload.description is not None:
        entry.description = payload.description.strip()
    if payload.entry_date is not None:
        entry.entry_date = payload.entry_date

    db.commit()
    return TimeEntryItem(
        id=entry.id,
        issue_id=entry.issue_id,
        user_id=entry.user_id,
        user_name=entry.user.full_name,
        duration_minutes=entry.duration_minutes,
        description=entry.description,
        entry_date=entry.entry_date,
        created_at=entry.created_at,
    )


@router.delete("/time-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_entry(
    entry_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    entry = db.scalar(
        select(TimeEntry)
        .options(selectinload(TimeEntry.issue).selectinload(Issue.project))
        .where(TimeEntry.id == entry_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Time entry not found.")
    _ensure_project_editor(db, current_user, entry.issue.project_id)
    _log_issue_activity(
        db,
        entry.issue_id,
        current_user.id,
        "time_removed",
        f"{current_user.full_name} removed time entry.",
    )
    db.delete(entry)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Project Statuses (Custom Workflow) ──────────────────────────────


def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "_")[:40]


def _serialize_status(s: ProjectStatus) -> ProjectStatusItem:
    return ProjectStatusItem(
        id=s.id,
        slug=s.slug,
        name=s.name,
        color=s.color,
        category=s.category,
        sort_order=s.sort_order,
    )


@router.get("/projects/{project_id}/statuses", response_model=ProjectStatusListResponse)
@router.get("/lists/{project_id}/statuses", response_model=ProjectStatusListResponse)
def list_project_statuses(
    project_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectStatusListResponse:
    project, _ = _ensure_project_access(db, current_user, project_id)
    statuses = list(
        db.scalars(
            select(ProjectStatus)
            .where(ProjectStatus.project_id == project_id)
            .order_by(ProjectStatus.sort_order)
        )
    )
    # Auto-seed default statuses for existing projects that don't have any
    if not statuses:
        _create_default_statuses(db, project_id)
        db.commit()
        statuses = list(
            db.scalars(
                select(ProjectStatus)
                .where(ProjectStatus.project_id == project_id)
                .order_by(ProjectStatus.sort_order)
            )
        )
    return ProjectStatusListResponse(items=[_serialize_status(s) for s in statuses])


@router.post(
    "/projects/{project_id}/statuses",
    response_model=ProjectStatusItem,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/lists/{project_id}/statuses",
    response_model=ProjectStatusItem,
    status_code=status.HTTP_201_CREATED,
)
def create_project_status(
    project_id: str,
    payload: ProjectStatusCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectStatusItem:
    _ensure_project_owner(db, current_user, project_id)
    slug = _slugify(payload.name)
    existing = db.scalar(
        select(ProjectStatus).where(
            ProjectStatus.project_id == project_id,
            ProjectStatus.slug == slug,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Status with this name already exists.")

    ps = ProjectStatus(
        id=new_id(),
        project_id=project_id,
        slug=slug,
        name=payload.name.strip(),
        color=payload.color,
        category=payload.category,
        sort_order=payload.sort_order,
    )
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return _serialize_status(ps)


@router.patch("/project-statuses/{status_id}", response_model=ProjectStatusItem)
def update_project_status(
    status_id: str,
    payload: ProjectStatusUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ProjectStatusItem:
    ps = db.scalar(select(ProjectStatus).where(ProjectStatus.id == status_id))
    if ps is None:
        raise HTTPException(status_code=404, detail="Status not found.")
    _ensure_project_owner(db, current_user, ps.project_id)

    if payload.name is not None:
        normalized_name = payload.name.strip()
        existing = db.scalar(
            select(ProjectStatus).where(
                ProjectStatus.project_id == ps.project_id,
                ProjectStatus.id != ps.id,
                func.lower(ProjectStatus.name) == normalized_name.lower(),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="Status with this name already exists.")
        ps.name = normalized_name
    if payload.color is not None:
        ps.color = payload.color
    if payload.category is not None:
        ps.category = payload.category
    if payload.sort_order is not None:
        ps.sort_order = payload.sort_order

    db.commit()
    db.refresh(ps)
    return _serialize_status(ps)


@router.delete("/project-statuses/{status_id}")
def delete_project_status(
    status_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    ps = db.scalar(select(ProjectStatus).where(ProjectStatus.id == status_id))
    if ps is None:
        raise HTTPException(status_code=404, detail="Status not found.")
    _ensure_project_owner(db, current_user, ps.project_id)

    # Prevent deleting if issues use this status
    count = db.scalar(
        select(func.count())
        .select_from(Issue)
        .where(Issue.project_id == ps.project_id, Issue.status == ps.slug)
    )
    if count and count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete status: {count} issue(s) are using it.",
        )

    db.delete(ps)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── CSV Export ──────────────────────────────────────────────────────


@router.get("/projects/{project_id}/export")
@router.get("/lists/{project_id}/export")
def export_project_issues(
    project_id: str,
    format: str = Query(default="csv"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    project, _ = _ensure_project_access(db, current_user, project_id)

    issues = list(
        db.scalars(
            select(Issue)
            .options(
                selectinload(Issue.project),
                selectinload(Issue.assignee),
                selectinload(Issue.reporter),
                selectinload(Issue.milestone),
                selectinload(Issue.label_links).selectinload(IssueLabel.label),
                selectinload(Issue.comments),
                selectinload(Issue.checklist_items),
                selectinload(Issue.time_entries),
                selectinload(Issue.subtasks),
            )
            .where(Issue.project_id == project_id)
            .order_by(Issue.issue_number)
        )
    )

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Reference", "Title", "Status", "Priority",
        "Assignee", "Reporter", "Milestone",
        "Start Date", "Due Date", "Labels",
        "Estimate Hours", "Time Spent (min)",
        "Checklist Done/Total", "Comments",
        "Created", "Updated",
    ])
    for issue in issues:
        ref = f"{project.key}-{issue.issue_number}"
        label_str = ", ".join(link.label.name for link in issue.label_links)
        checklist_str = f"{sum(1 for c in issue.checklist_items if c.completed)}/{len(issue.checklist_items)}" if issue.checklist_items else ""
        writer.writerow([
            ref,
            issue.title,
            issue.status,
            issue.priority,
            getattr(issue.assignee, "full_name", ""),
            getattr(issue.reporter, "full_name", ""),
            getattr(issue.milestone, "title", ""),
            str(issue.start_date or ""),
            str(issue.due_date or ""),
            label_str,
            issue.estimate_hours or "",
            sum(te.duration_minutes for te in issue.time_entries) if issue.time_entries else 0,
            checklist_str,
            len(issue.comments),
            issue.created_at.isoformat(),
            issue.updated_at.isoformat(),
        ])

    content = buf.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{project.key}_issues.csv"',
        },
    )


# ── Task Templates ──────────────────────────────────────────────────


def _serialize_template(t: TaskTemplate) -> TaskTemplateItem:
    return TaskTemplateItem(
        id=t.id,
        project_id=t.project_id,
        name=t.name,
        description=t.description,
        default_status=t.default_status,
        default_priority=t.default_priority,
        checklist_items=t.checklist_items,
        created_at=t.created_at,
    )


@router.get("/projects/{project_id}/templates", response_model=TaskTemplateListResponse)
@router.get("/lists/{project_id}/templates", response_model=TaskTemplateListResponse)
def list_templates(
    project_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskTemplateListResponse:
    _ensure_project_access(db, current_user, project_id)
    templates = list(
        db.scalars(
            select(TaskTemplate)
            .where(TaskTemplate.project_id == project_id)
            .order_by(TaskTemplate.created_at.desc())
        )
    )
    return TaskTemplateListResponse(items=[_serialize_template(t) for t in templates])


@router.post(
    "/projects/{project_id}/templates",
    response_model=TaskTemplateItem,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/lists/{project_id}/templates",
    response_model=TaskTemplateItem,
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    project_id: str,
    payload: TaskTemplateCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskTemplateItem:
    _ensure_project_editor(db, current_user, project_id)
    t = TaskTemplate(
        id=new_id(),
        project_id=project_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        default_status=payload.default_status,
        default_priority=payload.default_priority,
        checklist_items=payload.checklist_items,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _serialize_template(t)


@router.patch("/templates/{template_id}", response_model=TaskTemplateItem)
def update_template(
    template_id: str,
    payload: TaskTemplateUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskTemplateItem:
    t = db.scalar(select(TaskTemplate).where(TaskTemplate.id == template_id))
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    _ensure_project_editor(db, current_user, t.project_id)

    if payload.name is not None:
        t.name = payload.name.strip()
    if payload.description is not None:
        t.description = payload.description.strip()
    if payload.default_status is not None:
        t.default_status = payload.default_status
    if payload.default_priority is not None:
        t.default_priority = payload.default_priority
    if payload.checklist_items is not None:
        t.checklist_items = payload.checklist_items

    db.commit()
    db.refresh(t)
    return _serialize_template(t)


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    t = db.scalar(select(TaskTemplate).where(TaskTemplate.id == template_id))
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    _ensure_project_editor(db, current_user, t.project_id)
    db.delete(t)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Custom Fields ───────────────────────────────────────────────────


@router.get("/projects/{project_id}/custom-fields", response_model=CustomFieldListResponse)
@router.get("/lists/{project_id}/custom-fields", response_model=CustomFieldListResponse)
def list_custom_fields(
    project_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CustomFieldListResponse:
    _ensure_project_access(db, current_user, project_id)
    fields = list(
        db.scalars(
            select(CustomField)
            .where(CustomField.project_id == project_id)
            .order_by(CustomField.sort_order)
        )
    )
    return CustomFieldListResponse(
        items=[
            CustomFieldItem(
                id=f.id,
                project_id=f.project_id,
                name=f.name,
                field_type=f.field_type,
                options=f.options,
                sort_order=f.sort_order,
            )
            for f in fields
        ]
    )


@router.post(
    "/projects/{project_id}/custom-fields",
    response_model=CustomFieldItem,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/lists/{project_id}/custom-fields",
    response_model=CustomFieldItem,
    status_code=status.HTTP_201_CREATED,
)
def create_custom_field(
    project_id: str,
    payload: CustomFieldCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CustomFieldItem:
    _ensure_project_owner(db, current_user, project_id)
    f = CustomField(
        id=new_id(),
        project_id=project_id,
        name=payload.name.strip(),
        field_type=payload.field_type,
        options=payload.options,
        sort_order=payload.sort_order,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return CustomFieldItem(
        id=f.id, project_id=f.project_id, name=f.name,
        field_type=f.field_type, options=f.options, sort_order=f.sort_order,
    )


@router.delete("/custom-fields/{field_id}")
def delete_custom_field(
    field_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    f = db.scalar(select(CustomField).where(CustomField.id == field_id))
    if f is None:
        raise HTTPException(status_code=404, detail="Custom field not found.")
    _ensure_project_owner(db, current_user, f.project_id)
    # Delete all values for this field
    for v in db.scalars(select(CustomFieldValue).where(CustomFieldValue.field_id == field_id)):
        db.delete(v)
    db.delete(f)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/issues/{issue_id}/custom-field-values", response_model=list[CustomFieldValueItem])
def list_issue_custom_field_values(
    issue_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[CustomFieldValueItem]:
    issue = db.scalar(select(Issue).where(Issue.id == issue_id))
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    _ensure_project_access(db, current_user, issue.project_id)
    values = list(
        db.scalars(select(CustomFieldValue).where(CustomFieldValue.issue_id == issue_id))
    )
    return [CustomFieldValueItem(field_id=v.field_id, value=v.value) for v in values]


@router.put("/issues/{issue_id}/custom-field-values")
def set_issue_custom_field_value(
    issue_id: str,
    payload: SetCustomFieldValueRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CustomFieldValueItem:
    issue = db.scalar(select(Issue).where(Issue.id == issue_id))
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    _ensure_project_editor(db, current_user, issue.project_id)

    # Validate field belongs to same project
    field = db.scalar(select(CustomField).where(CustomField.id == payload.field_id))
    if field is None or field.project_id != issue.project_id:
        raise HTTPException(status_code=400, detail="Custom field does not belong to this project.")

    existing = db.scalar(
        select(CustomFieldValue).where(
            CustomFieldValue.issue_id == issue_id,
            CustomFieldValue.field_id == payload.field_id,
        )
    )
    if existing:
        existing.value = payload.value
    else:
        db.add(CustomFieldValue(id=new_id(), issue_id=issue_id, field_id=payload.field_id, value=payload.value))
    db.commit()
    return CustomFieldValueItem(field_id=payload.field_id, value=payload.value)


# ── Issue Assignees (Multiple) ──────────────────────────────────────


class IssueAssigneeItem(BaseModel):
    user_id: str
    full_name: str


class SetIssueAssigneesRequest(BaseModel):
    user_ids: list[str] = Field(..., max_length=20)


@router.put("/issues/{issue_id}/assignees", response_model=list[IssueAssigneeItem])
def set_issue_assignees(
    issue_id: str,
    payload: SetIssueAssigneesRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[IssueAssigneeItem]:
    issue, project = _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    member_ids = {member.user_id for member in project.members}

    # Clear existing assignee links
    for link in list(issue.assignee_links):
        db.delete(link)
    db.flush()

    # Add new ones (validate all users first)
    result: list[IssueAssigneeItem] = []
    validated_user_ids: list[str] = []
    for uid in payload.user_ids:
        if uid not in member_ids:
            raise HTTPException(status_code=400, detail="Assignees must be project members.")
        user = db.scalar(select(User).where(User.id == uid))
        if user is None:
            raise HTTPException(status_code=404, detail="User not found.")
        db.add(IssueAssignee(id=new_id(), issue_id=issue_id, user_id=uid))
        result.append(IssueAssigneeItem(user_id=uid, full_name=user.full_name))
        validated_user_ids.append(uid)

    # Update primary assignee_id to the first validated user (or clear)
    issue.assignee_id = validated_user_ids[0] if validated_user_ids else None

    db.commit()
    return result


# ── Folders ─────────────────────────────────────────────────────────


class FolderItem(BaseModel):
    id: str
    team_id: str | None
    name: str
    sort_order: int
    project_count: int = 0


class FolderListResponse(BaseModel):
    items: list[FolderItem]


class FolderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=140)
    team_id: str | None = None
    sort_order: int = 0


class FolderUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=140)
    sort_order: int | None = None


@router.get("/folders", response_model=FolderListResponse)
def list_folders(
    team_id: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> FolderListResponse:
    q = select(Folder).order_by(Folder.sort_order)
    if team_id:
        _ensure_space_access(db, current_user, team_id)
        q = q.where(Folder.team_id == team_id)
    elif current_user.is_admin:
        q = q.where(
            or_(
                Folder.team_id.is_(None),
                Folder.team_id.in_(select(Team.id).where(Team.trashed_at.is_(None))),
            )
        )
    elif not current_user.is_admin:
        accessible_team_ids = _accessible_space_ids(db, current_user)
        if accessible_team_ids:
            q = q.where(Folder.team_id.in_(accessible_team_ids))
        else:
            q = q.where(Folder.id == "__none__")
    folders = list(db.scalars(q))

    # Count projects per folder
    folder_ids = [f.id for f in folders]
    project_counts: dict[str, int] = {}
    if folder_ids:
        for fid in folder_ids:
            cnt = db.scalar(
                select(func.count()).select_from(Project).where(Project.folder_id == fid)
            )
            project_counts[fid] = cnt or 0

    return FolderListResponse(
        items=[
            FolderItem(
                id=f.id, team_id=f.team_id, name=f.name,
                sort_order=f.sort_order,
                project_count=project_counts.get(f.id, 0),
            )
            for f in folders
        ]
    )


@router.post("/folders", response_model=FolderItem, status_code=status.HTTP_201_CREATED)
def create_folder(
    payload: FolderCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> FolderItem:
    resolved_team_id = payload.team_id
    if resolved_team_id is None:
        resolved_team_id = get_or_create_default_pms_space(db).id
    _ensure_space_manager(db, current_user, resolved_team_id)
    folder = Folder(
        id=new_id(),
        team_id=resolved_team_id,
        name=payload.name.strip(),
        sort_order=payload.sort_order,
    )
    db.add(folder)

    # Auto-create a default list inside the new folder
    default_key = _unique_key(db, "List")
    default_project = Project(
        id=new_id(),
        key=default_key,
        name="List",
        description="",
        status="active",
        team_id=resolved_team_id,
        folder_id=folder.id,
        created_by_id=current_user.id,
    )
    db.add(default_project)
    db.add(ProjectMember(id=new_id(), project_id=default_project.id, user_id=current_user.id, role="owner"))
    _create_default_statuses(db, default_project.id)
    _create_default_labels(db, default_project.id)

    db.commit()
    db.refresh(folder)
    return FolderItem(
        id=folder.id, team_id=folder.team_id, name=folder.name,
        sort_order=folder.sort_order, project_count=1,
    )


@router.patch("/folders/{folder_id}", response_model=FolderItem)
def update_folder(
    folder_id: str,
    payload: FolderUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> FolderItem:
    folder = db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found.")
    if folder.team_id is None:
        raise HTTPException(status_code=409, detail="Folder space is not set.")
    _ensure_space_manager(db, current_user, folder.team_id)
    if payload.name is not None:
        folder.name = payload.name.strip()
    if payload.sort_order is not None:
        folder.sort_order = payload.sort_order
    db.commit()
    db.refresh(folder)
    cnt = db.scalar(select(func.count()).select_from(Project).where(Project.folder_id == folder_id)) or 0
    return FolderItem(
        id=folder.id, team_id=folder.team_id, name=folder.name,
        sort_order=folder.sort_order, project_count=cnt,
    )


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    folder = db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found.")
    if folder.team_id is None:
        raise HTTPException(status_code=409, detail="Folder space is not set.")
    _ensure_space_manager(db, current_user, folder.team_id)
    # Unlink projects from this folder (don't delete them)
    for p in db.scalars(select(Project).where(Project.folder_id == folder_id)):
        p.folder_id = None
    db.delete(folder)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Docs (Wiki) ─────────────────────────────────────────────────────


class DocItem(BaseModel):
    id: str
    project_id: str
    title: str
    content_blocks: list[dict] | None = None
    created_by_id: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime


class DocListResponse(BaseModel):
    items: list[DocItem]


class DocCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content_blocks: list[dict] | None = None


class DocUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content_blocks: list[dict] | None = None


def _serialize_doc(d: Doc) -> DocItem:
    return DocItem(
        id=d.id, project_id=d.project_id, title=d.title,
        content_blocks=d.content_blocks,
        created_by_id=d.created_by_id,
        created_by_name=getattr(d.created_by, "full_name", ""),
        created_at=d.created_at, updated_at=d.updated_at,
    )


# ── Space Docs (collections) ─────────────────────────────────────────


class SpaceDocItem(BaseModel):
    id: str
    team_id: str
    title: str
    created_by_id: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None


class SpaceDocListResponse(BaseModel):
    items: list[SpaceDocItem]


class SpaceDocCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class SpaceDocUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


def _serialize_space_doc(doc: SpaceDoc) -> SpaceDocItem:
    return SpaceDocItem(
        id=doc.id,
        team_id=doc.team_id,
        title=doc.title,
        created_by_id=doc.created_by_id,
        created_by_name=getattr(doc.created_by, "full_name", ""),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        trashed_at=doc.trashed_at,
    )


def _get_active_space_doc(
    db: Session,
    doc_id: str,
    *,
    with_created_by: bool = False,
) -> SpaceDoc | None:
    query = select(SpaceDoc).where(
        SpaceDoc.id == doc_id,
        SpaceDoc.trashed_at.is_(None),
    )
    if with_created_by:
        query = query.options(selectinload(SpaceDoc.created_by))
    return db.scalar(query)


def _get_active_space_doc_page(
    db: Session,
    page_id: str,
    *,
    with_created_by: bool = False,
) -> SpaceDocPage | None:
    query = select(SpaceDocPage).where(
        SpaceDocPage.id == page_id,
        SpaceDocPage.trashed_at.is_(None),
    )
    if with_created_by:
        query = query.options(selectinload(SpaceDocPage.created_by))
    return db.scalar(query)


def _require_space_doc_access(
    db: Session,
    current_user: User,
    doc_id: str,
    *,
    write: bool = False,
) -> SpaceDoc:
    doc = _get_active_space_doc(db, doc_id, with_created_by=True)
    if doc is None:
        raise HTTPException(status_code=404, detail="SpaceDoc not found.")
    if write:
        _ensure_space_editor(db, current_user, doc.team_id)
    else:
        _ensure_space_access(db, current_user, doc.team_id)
    return doc


def _require_space_doc_in_space(db: Session, space_id: str, doc_id: str) -> SpaceDoc:
    doc = _get_active_space_doc(db, doc_id)
    if doc is None or doc.team_id != space_id:
        raise HTTPException(status_code=404, detail="SpaceDoc not found.")
    return doc


@router.get("/spaces/{space_id}/docs", response_model=SpaceDocListResponse)
def list_space_docs(
    space_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceDocListResponse:
    _ensure_space_access(db, current_user, space_id)
    items = db.scalars(
        select(SpaceDoc)
        .options(selectinload(SpaceDoc.created_by))
        .where(
            SpaceDoc.team_id == space_id,
            SpaceDoc.trashed_at.is_(None),
        )
        .order_by(SpaceDoc.updated_at.desc())
    ).all()
    return SpaceDocListResponse(items=[_serialize_space_doc(d) for d in items])


@router.post("/spaces/{space_id}/docs", response_model=SpaceDocItem, status_code=status.HTTP_201_CREATED)
def create_space_doc(
    space_id: str,
    payload: SpaceDocCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceDocItem:
    _ensure_space_editor(db, current_user, space_id)
    doc = SpaceDoc(
        id=new_id(),
        team_id=space_id,
        title=payload.title.strip(),
        created_by_id=current_user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc, ["created_by"])
    return _serialize_space_doc(doc)


@router.get("/space-docs/{doc_id}", response_model=SpaceDocItem)
def get_space_doc(
    doc_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceDocItem:
    doc = _require_space_doc_access(db, current_user, doc_id)
    return _serialize_space_doc(doc)


@router.patch("/space-docs/{doc_id}", response_model=SpaceDocItem)
def update_space_doc(
    doc_id: str,
    payload: SpaceDocUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceDocItem:
    doc = _require_space_doc_access(db, current_user, doc_id, write=True)
    if payload.title is not None:
        doc.title = payload.title.strip()
    db.add(doc)
    db.commit()
    db.refresh(doc, ["created_by"])
    return _serialize_space_doc(doc)


@router.delete("/space-docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_space_doc(
    doc_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> None:
    doc = _require_space_doc_access(db, current_user, doc_id, write=True)
    deleted_at = _utcnow()
    doc.trashed_at = deleted_at
    pages = list(
        db.scalars(
            select(SpaceDocPage).where(
                SpaceDocPage.space_doc_id == doc.id,
                SpaceDocPage.trashed_at.is_(None),
            )
        )
    )
    for page in pages:
        page.trashed_at = deleted_at
        db.add(page)
    db.add(doc)
    db.commit()


# ── Space Doc Pages ──────────────────────────────────────────────────


class SpaceDocPageItem(BaseModel):
    id: str
    team_id: str
    space_doc_id: str
    parent_id: str | None = None
    title: str
    content_blocks: list[dict] | None = None
    sort_order: int
    created_by_id: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None


class SpaceDocPageListResponse(BaseModel):
    items: list[SpaceDocPageItem]


class SpaceDocPageCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    space_doc_id: str
    parent_id: str | None = None
    content_blocks: list[dict] | None = None
    sort_order: int | None = None


class SpaceDocPageUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: str | None = None
    content_blocks: list[dict] | None = None
    sort_order: int | None = None


def _serialize_space_doc_page(page: SpaceDocPage) -> SpaceDocPageItem:
    return SpaceDocPageItem(
        id=page.id,
        team_id=page.team_id,
        space_doc_id=page.space_doc_id,
        parent_id=page.parent_id,
        title=page.title,
        content_blocks=page.content_blocks,
        sort_order=page.sort_order,
        created_by_id=page.created_by_id,
        created_by_name=getattr(page.created_by, "full_name", ""),
        created_at=page.created_at,
        updated_at=page.updated_at,
        trashed_at=page.trashed_at,
    )


def _validate_space_doc_parent(
    db: Session,
    team_id: str,
    space_doc_id: str,
    parent_id: str | None,
    *,
    page_id: str | None = None,
) -> None:
    if parent_id is None:
        return

    parent = _get_active_space_doc_page(db, parent_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent page not found.")
    if parent.team_id != team_id:
        raise HTTPException(status_code=400, detail="Parent page must belong to the same space.")
    if parent.space_doc_id != space_doc_id:
        raise HTTPException(status_code=409, detail="Parent page must belong to the same document collection.")
    if page_id is not None and parent.id == page_id:
        raise HTTPException(status_code=409, detail="Page cannot be its own parent.")

    visited: set[str] = set()
    ancestor: SpaceDocPage | None = parent
    while ancestor is not None:
        if ancestor.id in visited:
            raise HTTPException(status_code=409, detail="Page parent relationship cannot contain a cycle.")
        visited.add(ancestor.id)
        if page_id is not None and ancestor.parent_id == page_id:
            raise HTTPException(status_code=409, detail="Page parent relationship cannot contain a cycle.")
        if ancestor.parent_id is None:
            break
        ancestor = _get_active_space_doc_page(db, ancestor.parent_id)


def _collect_active_space_doc_page_subtree(
    db: Session,
    root_page: SpaceDocPage,
) -> list[SpaceDocPage]:
    pages = list(
        db.scalars(
            select(SpaceDocPage).where(
                SpaceDocPage.space_doc_id == root_page.space_doc_id,
                SpaceDocPage.trashed_at.is_(None),
            )
        )
    )
    by_parent: dict[str | None, list[SpaceDocPage]] = {}
    for page in pages:
        by_parent.setdefault(page.parent_id, []).append(page)

    subtree: list[SpaceDocPage] = []
    stack = [root_page]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current.id in seen:
            continue
        seen.add(current.id)
        subtree.append(current)
        stack.extend(by_parent.get(current.id, []))
    return subtree


@router.get("/projects/{project_id}/docs", response_model=DocListResponse)
@router.get("/lists/{project_id}/docs", response_model=DocListResponse)
def list_docs(
    project_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocListResponse:
    _ensure_project_access(db, current_user, project_id)
    docs = list(
        db.scalars(
            select(Doc)
            .options(selectinload(Doc.created_by))
            .where(Doc.project_id == project_id)
            .order_by(Doc.updated_at.desc())
        )
    )
    return DocListResponse(items=[_serialize_doc(d) for d in docs])


@router.post("/projects/{project_id}/docs", response_model=DocItem, status_code=status.HTTP_201_CREATED)
@router.post("/lists/{project_id}/docs", response_model=DocItem, status_code=status.HTTP_201_CREATED)
def create_doc(
    project_id: str,
    payload: DocCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocItem:
    _ensure_project_editor(db, current_user, project_id)
    d = Doc(
        id=new_id(), project_id=project_id,
        title=payload.title.strip(),
        content_blocks=payload.content_blocks,
        created_by_id=current_user.id,
    )
    db.add(d)
    db.flush()
    if payload.content_blocks:
        sync_embedded_media(db, payload.content_blocks, "doc", d.id, current_user)
    db.commit()
    d = db.scalar(select(Doc).options(selectinload(Doc.created_by)).where(Doc.id == d.id))
    return _serialize_doc(d)


@router.get("/docs/{doc_id}", response_model=DocItem)
def get_doc(
    doc_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocItem:
    d = db.scalar(select(Doc).options(selectinload(Doc.created_by)).where(Doc.id == doc_id))
    if d is None:
        raise HTTPException(status_code=404, detail="Doc not found.")
    _ensure_project_access(db, current_user, d.project_id)
    return _serialize_doc(d)


@router.patch("/docs/{doc_id}", response_model=DocItem)
def update_doc(
    doc_id: str,
    payload: DocUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DocItem:
    d = db.scalar(select(Doc).options(selectinload(Doc.created_by)).where(Doc.id == doc_id))
    if d is None:
        raise HTTPException(status_code=404, detail="Doc not found.")
    _ensure_project_editor(db, current_user, d.project_id)
    if payload.title is not None:
        d.title = payload.title.strip()
    if "content_blocks" in payload.model_fields_set:
        d.content_blocks = payload.content_blocks
        sync_embedded_media(db, payload.content_blocks, "doc", d.id, current_user)
    db.commit()
    db.refresh(d)
    return _serialize_doc(d)


@router.delete("/docs/{doc_id}")
def delete_doc(
    doc_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    d = db.scalar(select(Doc).where(Doc.id == doc_id))
    if d is None:
        raise HTTPException(status_code=404, detail="Doc not found.")
    _ensure_project_editor(db, current_user, d.project_id)
    media_keys = cleanup_media_for_resource(db, "doc", d.id)
    db.delete(d)
    db.commit()
    if media_keys:
        settings = get_settings()
        client = get_minio_client()
        for key in media_keys:
            try:
                client.remove_object(settings.minio_bucket, key)
            except Exception:
                pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/spaces/{space_id}/docs/pages", response_model=SpaceDocPageListResponse)
def list_space_doc_pages(
    space_id: str,
    space_doc_id: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceDocPageListResponse:
    _ensure_space_access(db, current_user, space_id)
    if space_doc_id is None:
        raise HTTPException(status_code=400, detail="space_doc_id is required.")
    _require_space_doc_in_space(db, space_id, space_doc_id)
    query = (
        select(SpaceDocPage)
        .options(selectinload(SpaceDocPage.created_by))
        .where(
            SpaceDocPage.team_id == space_id,
            SpaceDocPage.space_doc_id == space_doc_id,
            SpaceDocPage.trashed_at.is_(None),
        )
    )
    pages = list(
        db.scalars(
            query.order_by(
                SpaceDocPage.parent_id.nullsfirst(),
                SpaceDocPage.sort_order,
                SpaceDocPage.created_at,
            )
        )
    )
    return SpaceDocPageListResponse(items=[_serialize_space_doc_page(page) for page in pages])


@router.post("/spaces/{space_id}/docs/pages", response_model=SpaceDocPageItem, status_code=status.HTTP_201_CREATED)
def create_space_doc_page(
    space_id: str,
    payload: SpaceDocPageCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceDocPageItem:
    _ensure_space_editor(db, current_user, space_id)
    _require_space_doc_in_space(db, space_id, payload.space_doc_id)
    _validate_space_doc_parent(db, space_id, payload.space_doc_id, payload.parent_id)
    sort_order = payload.sort_order
    if sort_order is None:
        sibling_count = db.scalar(
            select(func.count())
            .select_from(SpaceDocPage)
            .where(
                SpaceDocPage.team_id == space_id,
                SpaceDocPage.space_doc_id == payload.space_doc_id,
                SpaceDocPage.parent_id == payload.parent_id,
                SpaceDocPage.trashed_at.is_(None),
            )
        ) or 0
        sort_order = sibling_count

    page = SpaceDocPage(
        id=new_id(),
        team_id=space_id,
        parent_id=payload.parent_id,
        space_doc_id=payload.space_doc_id,
        title=payload.title.strip(),
        content_blocks=payload.content_blocks,
        sort_order=sort_order,
        created_by_id=current_user.id,
    )
    db.add(page)
    db.flush()
    if payload.content_blocks:
        sync_embedded_media(db, payload.content_blocks, "space_doc_page", page.id, current_user)
    db.commit()
    page = db.scalar(
        select(SpaceDocPage)
        .options(selectinload(SpaceDocPage.created_by))
        .where(SpaceDocPage.id == page.id)
    )
    return _serialize_space_doc_page(page)


@router.get("/space-doc-pages/{page_id}", response_model=SpaceDocPageItem)
def get_space_doc_page(
    page_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceDocPageItem:
    page = _get_active_space_doc_page(db, page_id, with_created_by=True)
    if page is None:
        raise HTTPException(status_code=404, detail="Space doc page not found.")
    _ensure_space_access(db, current_user, page.team_id)
    return _serialize_space_doc_page(page)


@router.patch("/space-doc-pages/{page_id}", response_model=SpaceDocPageItem)
def update_space_doc_page(
    page_id: str,
    payload: SpaceDocPageUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceDocPageItem:
    page = _get_active_space_doc_page(db, page_id, with_created_by=True)
    if page is None:
        raise HTTPException(status_code=404, detail="Space doc page not found.")
    _ensure_space_editor(db, current_user, page.team_id)
    if "parent_id" in payload.model_fields_set:
        _validate_space_doc_parent(db, page.team_id, page.space_doc_id, payload.parent_id, page_id=page.id)
        page.parent_id = payload.parent_id
    if "title" in payload.model_fields_set and payload.title is not None:
        page.title = payload.title.strip()
    if "content_blocks" in payload.model_fields_set:
        page.content_blocks = payload.content_blocks
        sync_embedded_media(db, payload.content_blocks, "space_doc_page", page.id, current_user)
    if "sort_order" in payload.model_fields_set and payload.sort_order is not None:
        page.sort_order = payload.sort_order
    db.commit()
    db.refresh(page)
    return _serialize_space_doc_page(page)


@router.delete("/space-doc-pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_space_doc_page(
    page_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    page = _get_active_space_doc_page(db, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Space doc page not found.")
    _ensure_space_editor(db, current_user, page.team_id)
    deleted_at = _utcnow()
    for descendant in _collect_active_space_doc_page_subtree(db, page):
        descendant.trashed_at = deleted_at
        db.add(descendant)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
