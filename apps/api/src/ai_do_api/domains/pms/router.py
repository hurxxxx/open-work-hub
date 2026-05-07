from __future__ import annotations

import csv
from io import BytesIO, StringIO
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.principal import user_principal
from ai_do_api.domains.auth.access import (
    get_current_workspace,
    get_or_create_default_pms_space,
    has_system_role,
    resolve_team_role,
    slugify,
)
from ai_do_api.domains.auth.dependencies import require_current_user, require_current_workspace
from ai_do_api.domains.auth.models import Team, TeamMember, User, Workspace
from ai_do_api.domains.auth.security import new_id
from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import get_minio_client
from ai_do_api.domains.media.service import cleanup_media_for_resource
from ai_do_api.domains.pms.models import (
    Attachment,
    ChecklistItem,
    CustomField,
    CustomFieldValue,
    Folder,
    Issue,
    IssueActivityLog,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    Label,
    Milestone,
    Notification,
    TaskList,
    TaskListStatus,
    ScheduleDependency,
    TaskTemplate,
    TimeEntry,
)
from ai_do_api.domains.pms.access import (
    _ensure_issue_readable,
    _ensure_list_editor,
    _ensure_list_member,
    _ensure_list_owner,
)
from ai_do_api.domains.pms.rag_sync import (
    collect_label_issue_ids,
    enqueue_issue_rag_sync,
    enqueue_label_issue_recompute,
    enqueue_milestone_issue_recompute,
    enqueue_task_list_issue_recompute,
)
from ai_do_api.domains.pms import service as pms_service
from ai_do_api.domains.rag.contracts import RagSyncOperation
from ai_do_api.domains.search.hooks import enqueue_task_list_status_issue_search_recompute


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
TASK_LIST_STATUS_LABELS = {
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


def _priority_label(priority: str) -> str:
    return PRIORITY_LABELS.get(priority, priority.replace("_", " ").title())


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    q: str = ""


class TaskListCreateRequest(BaseModel):
    key: str | None = Field(default=None, min_length=2, max_length=24, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(..., min_length=2, max_length=140)
    description: str = Field(default="", max_length=4000)
    team_id: str | None = None
    folder_id: str | None = None


class TaskListUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["planned", "active", "on_hold", "done"] | None = None
    archived: bool | None = None
    folder_id: str | None = None
    sort_order: int | None = None


class TaskListReorderItem(BaseModel):
    id: str
    folder_id: str | None = None
    sort_order: int = Field(ge=0)


class TaskListReorderRequest(BaseModel):
    items: list[TaskListReorderItem] = Field(min_length=1, max_length=200)


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
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

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


class TaskListItem(BaseModel):
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
    sort_order: int = 0
    role: str
    progress: float
    member_count: int
    milestone_count: int
    issue_count: int
    overdue_issue_count: int
    created_at: datetime
    updated_at: datetime


class TaskListsResponse(BaseModel):
    items: list[TaskListItem]
    total: int
    page: int
    page_size: int


class SpaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)


class SpaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class SpaceItem(BaseModel):
    id: str
    workspace_id: str
    workspace_key: str
    key: str
    name: str
    description: str
    member_count: int
    current_user_role: str | None
    created_at: datetime
    updated_at: datetime


class SpaceMemberItem(BaseModel):
    user_id: str
    email: str
    full_name: str
    is_admin: bool
    role: str
    joined_at: datetime


class SpaceUserItem(BaseModel):
    id: str
    email: str
    full_name: str


class SpaceMemberListResponse(BaseModel):
    items: list[SpaceMemberItem]
    total: int
    page: int
    page_size: int


class SpaceMemberCreateRequest(BaseModel):
    user_id: str
    role: Literal["owner", "admin", "viewer", "member"] = "member"


class SpaceMemberRoleUpdateRequest(BaseModel):
    role: Literal["owner", "admin", "viewer", "member"]


class MilestoneItem(BaseModel):
    id: str
    list_id: str
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


class TaskListStatusItem(BaseModel):
    id: str
    slug: str
    name: str
    color: str
    category: str
    sort_order: int


class TaskListStatusesResponse(BaseModel):
    items: list[TaskListStatusItem]


class TaskListStatusCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    color: str = Field(default="#6b7280", max_length=24)
    category: Literal["backlog", "active", "done", "canceled"] = "active"
    sort_order: int = 0


class TaskListStatusUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, max_length=24)
    category: Literal["backlog", "active", "done", "canceled"] | None = None
    sort_order: int | None = None


class TaskTemplateItem(BaseModel):
    id: str
    list_id: str
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
    list_id: str
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
    list_id: str
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
    action_url: str | None = None
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


class DashboardTaskListItem(BaseModel):
    list_id: str
    key: str
    name: str
    progress: float
    open_issue_count: int
    overdue_issue_count: int
    next_due_date: date | None


class DashboardSummaryResponse(BaseModel):
    list_count: int
    active_issue_count: int
    overdue_issue_count: int
    my_issue_count: int
    milestone_due_soon_count: int
    status_counts: list[StatusCountItem]
    priority_counts: list[PriorityCountItem]
    lists: list[DashboardTaskListItem]
    recent_activity: list[RecentActivityItem]


router = APIRouter(
    prefix="/pms",
    tags=["pms"],
)


def _paginate[T](items: list[T], page: int, page_size: int) -> tuple[list[T], int]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total


TASK_LIST_ROLE_RANK = {
    "viewer": 0,
    "member": 1,
    "admin": 2,
    "owner": 3,
}
SPACE_TEAM_EDITOR_ROLES = {"member", "admin", "owner"}
SPACE_TEAM_MANAGER_ROLES = {"admin", "owner"}
TASK_LIST_EDITOR_ROLES = {"member", "admin", "owner"}
TASK_LIST_MANAGER_ROLES = {"admin", "owner"}


def _is_pms_super_admin(db: Session, user: User) -> bool:
    return has_system_role(db, user, "platform_admin")


def _load_active_space(
    db: Session,
    space_id: str,
    *,
    include_members: bool = False,
) -> Team | None:
    workspace = _get_pms_workspace(db)
    query = select(Team).options(joinedload(Team.workspace)).where(
        Team.id == space_id,
        Team.active.is_(True),
        Team.trashed_at.is_(None),
        Team.workspace.has(Workspace.active.is_(True)),
        Team.workspace_id == workspace.id,
    )
    if include_members:
        query = query.options(selectinload(Team.members))
    return db.scalar(query)


def _serialize_space(team: Team, current_user_role: str | None) -> SpaceItem:
    return SpaceItem(
        id=team.id,
        workspace_id=team.workspace_id,
        workspace_key=team.workspace.key,
        key=team.key,
        name=team.name,
        description=team.description,
        member_count=len(team.members),
        current_user_role=current_user_role,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


def _serialize_space_member(db: Session, member: TeamMember) -> SpaceMemberItem:
    return SpaceMemberItem(
        user_id=member.user_id,
        email=member.user.email,
        full_name=member.user.full_name,
        is_admin=_is_pms_super_admin(db, member.user),
        role=member.role,
        joined_at=member.created_at,
    )


def _best_task_list_role(db: Session, user: User, space_id: str) -> str | None:
    workspace = _get_pms_workspace(db)
    team = db.scalar(
        select(Team)
        .options(joinedload(Team.workspace))
        .where(
            Team.id == space_id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
            Team.workspace_id == workspace.id,
        )
    )
    if team is None:
        return None
    return resolve_team_role(db, user, team)


def _is_active_space_id(db: Session, space_id: str) -> bool:
    workspace = _get_pms_workspace(db)
    return (
        db.scalar(
            select(Team.id).where(
                Team.id == space_id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
                Team.workspace.has(Workspace.active.is_(True)),
                Team.workspace_id == workspace.id,
            )
        )
        is not None
    )


def _ensure_space_access(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team = _load_active_space(db, space_id, include_members=True)
    if team is None:
        raise localized_http_exception(status_code=404, code="pms.space_not_found")

    role = resolve_team_role(db, user, team)
    if role is not None:
        return team, role

    raise localized_http_exception(status_code=403, code="pms.space_access_required")


def _ensure_space_editor(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team, role = _ensure_space_access(db, user, space_id)

    if role in SPACE_TEAM_EDITOR_ROLES:
        return team, role

    raise localized_http_exception(status_code=403, code="pms.space_viewer_modify_denied")


def _ensure_space_manager(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team, role = _ensure_space_access(db, user, space_id)

    if role in SPACE_TEAM_MANAGER_ROLES:
        return team, role

    raise localized_http_exception(status_code=403, code="pms.space_owner_admin_required")


def _ensure_space_owner(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team, role = _ensure_space_access(db, user, space_id)
    if role == "owner":
        return team, role
    raise localized_http_exception(status_code=403, code="pms.space_owner_required")


def _accessible_space_ids(db: Session, user: User) -> set[str]:
    workspace = _get_pms_workspace(db)
    direct_space_ids = set(
        db.scalars(
            select(TeamMember.team_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                TeamMember.user_id == user.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
                Team.workspace.has(Workspace.active.is_(True)),
                Team.workspace_id == workspace.id,
            )
        )
    )
    return direct_space_ids


def _load_space_members(db: Session, space_id: str) -> list[TeamMember]:
    return list(
        db.scalars(
            select(TeamMember)
            .options(selectinload(TeamMember.user))
            .where(TeamMember.team_id == space_id)
        )
    )


def _space_member_ids(db: Session, space_id: str) -> set[str]:
    return set(db.scalars(select(TeamMember.user_id).where(TeamMember.team_id == space_id)))


def _ensure_space_owner_survives(
    members: list[TeamMember],
    target_user_id: str,
    *,
    next_role: str | None,
) -> None:
    current_member = next((member for member in members if member.user_id == target_user_id), None)
    if current_member is None or current_member.role != "owner":
        return

    remaining = 0
    for member in members:
        role = next_role if member.user_id == target_user_id else member.role
        if role == "owner":
            remaining += 1

    if remaining < 1:
        raise localized_http_exception(
            status_code=409,
            code="pms.space_owner_must_remain",
        )


def _ensure_space_admin_change_allowed(
    db: Session,
    user: User,
    space_id: str,
    *,
    current_role: str | None,
    next_role: str | None,
) -> tuple[Team, str]:
    team, actor_role = _ensure_space_manager(db, user, space_id)
    if actor_role != "owner" and (
        current_role in SPACE_TEAM_MANAGER_ROLES or next_role in SPACE_TEAM_MANAGER_ROLES
    ):
        raise localized_http_exception(
            status_code=403,
            code="pms.space_owner_admin_manage_required",
        )
    return team, actor_role


def _get_pms_workspace(db: Session) -> Workspace:
    workspace = get_current_workspace(db)
    if workspace is None:
        raise localized_http_exception(status_code=500, code="pms.workspace_context_unavailable")
    return workspace


def _unique_space_key(db: Session, workspace_id: str, name: str) -> str:
    base = slugify(name) or "space"
    candidate = base
    counter = 1
    while db.scalar(
        select(Team.id).where(
            Team.workspace_id == workspace_id,
            Team.key == candidate,
        )
    ):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _space_query_for_user(db: Session, user: User):
    workspace = _get_pms_workspace(db)
    return (
        select(Team)
        .options(joinedload(Team.workspace), selectinload(Team.members))
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(
            TeamMember.user_id == user.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
            Team.workspace_id == workspace.id,
        )
    )


def _get_space_membership(
    db: Session,
    space_id: str,
    user_id: str,
) -> TeamMember | None:
    return db.scalar(
        select(TeamMember)
        .options(selectinload(TeamMember.user))
        .where(
            TeamMember.team_id == space_id,
            TeamMember.user_id == user_id,
        )
    )


def _validate_space_member_user(db: Session, space_id: str, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id, User.status == "active"))
    if user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    if user_id in _space_member_ids(db, space_id):
        raise localized_http_exception(status_code=409, code="pms.user_already_space_member")
    return user


def _validate_folder_membership(db: Session, team_id: str, folder_id: str | None) -> None:
    if folder_id is None:
        return

    folder = db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        raise localized_http_exception(status_code=404, code="pms.folder_not_found")
    if folder.team_id != team_id:
        raise localized_http_exception(status_code=400, code="pms.folder_same_space_required")


def _accessible_task_lists_query(db: Session, user: User):
    accessible_space_ids = _accessible_space_ids(db, user)
    if not accessible_space_ids:
        return select(TaskList).where(TaskList.id == "__none__")
    return select(TaskList).where(TaskList.team_id.in_(accessible_space_ids))


CATEGORY_PROGRESS = {
    "backlog": 0.0,
    "active": 0.5,
    "done": 1.0,
    "canceled": None,
}


def _issue_progress(status_value: str, task_list: TaskList | None = None) -> float | None:
    result = ISSUE_STATUS_PROGRESS.get(status_value)
    if result is not None or status_value in ISSUE_STATUS_PROGRESS:
        return result
    # Fallback: look up category from task_list custom statuses
    if task_list is not None:
        for ps in getattr(task_list, "statuses", []):
            if ps.slug == status_value:
                return CATEGORY_PROGRESS.get(ps.category, 0.5)
    return 0.5  # Unknown status defaults to active


def _is_closed_status(status_value: str, task_list: TaskList | None = None) -> bool:
    """Check if a status represents a closed state (done or canceled)."""
    if status_value in {"done", "canceled"}:
        return True
    if task_list is not None:
        for ps in getattr(task_list, "statuses", []):
            if ps.slug == status_value:
                return ps.category in {"done", "canceled"}
    return False


def _is_done_status(status_value: str, task_list: TaskList | None = None) -> bool:
    """Check if a status represents a completed state."""
    if status_value == "done":
        return True
    if task_list is not None:
        for ps in getattr(task_list, "statuses", []):
            if ps.slug == status_value:
                return ps.category == "done"
    return False


def _calculate_progress(issues: list[Issue], task_list: TaskList | None = None) -> float:
    progress_values = [
        progress
        for issue in issues
        if not issue.archived
        for progress in [_issue_progress(issue.status, task_list)]
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
    return f"{issue.task_list.key}-{issue.issue_number}"


def _serialize_issue(issue: Issue) -> IssueListItem:
    return IssueListItem(
        id=issue.id,
        list_id=issue.list_id,
        reference=_issue_reference(issue),
        title=issue.title,
        description=issue.description,
        description_blocks=issue.description_blocks,
        parent_id=issue.parent_id,
        subtask_count=len(issue.subtasks) if issue.subtasks else 0,
        status=issue.status,
        status_label=ISSUE_STATUS_LABELS.get(issue.status, issue.status.replace("_", " ").title()),
        priority=issue.priority,
        priority_label=_priority_label(issue.priority),
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
        progress=_issue_progress(issue.status, issue.task_list),
        comments_count=len(issue.comments),
        checklist_total=len(issue.checklist_items) if issue.checklist_items else 0,
        checklist_done=sum(1 for ci in issue.checklist_items if ci.completed) if issue.checklist_items else 0,
        estimate_hours=issue.estimate_hours,
        time_spent_minutes=sum(te.duration_minutes for te in issue.time_entries) if issue.time_entries else 0,
        recurrence_rule=issue.recurrence_rule,
        labels=_serialize_labels(issue),
        updated_at=issue.updated_at,
    )


def _serialize_task_list(
    task_list: TaskList,
    role: str,
    team_name: str | None = None,
    member_count: int | None = None,
) -> TaskListItem:
    overdue_issue_count = sum(
        1
        for issue in task_list.issues
        if (
            not issue.archived
            and not _is_closed_status(issue.status, task_list)
            and issue.due_date is not None
            and issue.due_date < date.today()
        )
    )
    return TaskListItem(
        id=task_list.id,
        key=task_list.key,
        name=task_list.name,
        description=task_list.description,
        status=task_list.status,
        archived=task_list.archived,
        team_id=task_list.team_id,
        team_name=team_name,
        folder_id=task_list.folder_id,
        folder_name=getattr(task_list.folder, "name", None) if task_list.folder_id else None,
        sort_order=task_list.sort_order,
        role=role,
        progress=_calculate_progress(task_list.issues, task_list),
        member_count=member_count if member_count is not None else 0,
        milestone_count=len(task_list.milestones),
        issue_count=len(task_list.issues),
        overdue_issue_count=overdue_issue_count,
        created_at=task_list.created_at,
        updated_at=task_list.updated_at,
    )


def _serialize_milestone(milestone: Milestone) -> MilestoneItem:
    issues = list(milestone.issues)
    completed_issue_count = sum(1 for issue in issues if _is_done_status(issue.status))
    return MilestoneItem(
        id=milestone.id,
        list_id=milestone.list_id,
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


def _task_list_role(db: Session, task_list: TaskList, user: User, team_lookup: dict[str, Team]) -> str:
    if task_list.team_id is None:
        return "viewer"
    team = team_lookup.get(task_list.team_id)
    if team is None:
        return "viewer"
    return resolve_team_role(db, user, team) or "viewer"


DEFAULT_TASK_LIST_STATUSES: list[tuple[str, str, str, str, int]] = [
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
    """Generate a unique task list key from a name."""
    resolved = _auto_key_from_name(base_name)
    base = resolved
    counter = 1
    while db.scalar(select(TaskList).where(func.lower(TaskList.key) == resolved.lower())):
        resolved = f"{base}{counter}"
        counter += 1
    return resolved


def _create_default_statuses(db: Session, list_id: str) -> None:
    for slug, name, color, category, sort_order in DEFAULT_TASK_LIST_STATUSES:
        db.add(
            TaskListStatus(
                id=new_id(),
                list_id=list_id,
                slug=slug,
                name=name,
                color=color,
                category=category,
                sort_order=sort_order,
            )
        )


def _create_default_labels(db: Session, list_id: str) -> None:
    for name, color in [
        ("blocked", "#b45309"),
        ("customer", "#1d4ed8"),
        ("qa", "#0f766e"),
    ]:
        db.add(Label(id=new_id(), list_id=list_id, name=name, color=color))


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
    pms_service._log_issue_activity(
        db,
        issue_id,
        actor_id,
        action,
        message,
        field_name=field_name,
        from_value=from_value,
        to_value=to_value,
    )


def _create_notification(
    db: Session,
    user_id: str,
    ntype: str,
    title: str,
    body: str,
    reference_type: str = "issue",
    reference_id: str | None = None,
    action_url: str | None = None,
) -> None:
    pms_service._create_notification(
        db,
        user_id,
        ntype,
        title,
        body,
        reference_type=reference_type,
        reference_id=reference_id,
        action_url=action_url,
    )


def _extract_mentions_from_blocks(blocks: list[dict], out: set[str]) -> None:
    pms_service._extract_mentions_from_blocks(blocks, out)


def _build_attachment_download_url(storage_key: str) -> str:
    settings = get_settings()
    client = get_minio_client()
    return client.presigned_get_object(
        settings.minio_bucket,
        storage_key,
        expires=timedelta(hours=1),
    )


def _next_issue_number(db: Session, list_id: str) -> int:
    return pms_service._next_issue_number(db, list_id)


def _next_issue_board_position(db: Session, list_id: str, status_value: str) -> int:
    return pms_service._next_issue_board_position(db, list_id, status_value)


def _validate_member_user(db: Session, task_list: TaskList, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    if task_list.team_id is None:
        raise localized_http_exception(status_code=409, code="pms.task_list_space_missing")
    if user_id in _space_member_ids(db, task_list.team_id):
        raise localized_http_exception(status_code=409, code="pms.user_already_task_list_member")
    return user


def _validate_issue_assignee(db: Session, task_list: TaskList, assignee_id: str | None) -> None:
    pms_service._validate_issue_assignee(db, task_list, assignee_id)


def _validate_milestone(task_list: TaskList, milestone_id: str | None) -> None:
    pms_service._validate_milestone(task_list, milestone_id)


def _validate_parent_issue(
    db: Session,
    task_list: TaskList,
    parent_id: str | None,
    *,
    issue_id: str | None = None,
) -> None:
    pms_service._validate_parent_issue(db, task_list, parent_id, issue_id=issue_id)


def _set_issue_labels(db: Session, issue: Issue, label_ids: list[str], task_list: TaskList) -> None:
    pms_service._set_issue_labels(db, issue, label_ids, task_list)


def _get_issue_for_user(
    db: Session,
    user: User,
    issue_id: str,
    *,
    require_editor: bool = False,
) -> tuple[Issue, TaskList]:
    return pms_service._get_issue_for_user(
        db,
        user,
        issue_id,
        require_editor=require_editor,
    )


@router.get("/spaces", response_model=list[SpaceItem])
def list_spaces(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> list[SpaceItem]:
    return pms_service.list_spaces(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.list_spaces",
        ),
        user=current_user,
    )


@router.get("/users", response_model=list[SpaceUserItem])
def list_pms_users(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[SpaceUserItem]:
    del current_user
    users = db.scalars(
        select(User)
        .where(User.status == "active")
        .order_by(User.full_name.asc(), User.email.asc())
    ).all()
    return [
        SpaceUserItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
        )
        for user in users
    ]


@router.post("/spaces", response_model=SpaceItem, status_code=status.HTTP_201_CREATED)
def create_space(
    payload: SpaceCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceItem:
    workspace = _get_pms_workspace(db)
    team = Team(
        id=new_id(),
        workspace_id=workspace.id,
        key=_unique_space_key(db, workspace.id, payload.name),
        name=payload.name.strip(),
        description=payload.description.strip(),
        active=True,
    )
    db.add(team)
    db.flush()
    db.add(
        TeamMember(
            id=new_id(),
            team_id=team.id,
            user_id=current_user.id,
            role="owner",
        )
    )
    db.commit()
    team = _load_active_space(db, team.id, include_members=True)
    assert team is not None
    return _serialize_space(team, "owner")


@router.patch("/spaces/{space_id}", response_model=SpaceItem)
def update_space(
    space_id: str,
    payload: SpaceUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceItem:
    team, role = _ensure_space_manager(db, current_user, space_id)
    if payload.name is not None:
        team.name = payload.name.strip()
    if payload.description is not None:
        team.description = payload.description.strip()
    db.add(team)
    db.commit()
    team = _load_active_space(db, team.id, include_members=True)
    assert team is not None
    return _serialize_space(team, role)


@router.delete("/spaces/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_space(
    space_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    team, _role = _ensure_space_manager(db, current_user, space_id)
    team.trashed_at = _utcnow()
    db.add(team)
    for task_list in db.scalars(select(TaskList).where(TaskList.team_id == team.id)):
        enqueue_task_list_issue_recompute(db, task_list=task_list)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/spaces/{space_id}/members", response_model=SpaceMemberListResponse)
def list_space_members(
    space_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceMemberListResponse:
    _ensure_space_access(db, current_user, space_id)
    members = [
        _serialize_space_member(db, member)
        for member in sorted(
            _load_space_members(db, space_id),
            key=lambda item: (item.role not in {"owner", "admin"}, item.user.full_name.lower()),
        )
    ]
    page_items, total = _paginate(members, page, page_size)
    return SpaceMemberListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.post("/spaces/{space_id}/members", response_model=SpaceMemberItem, status_code=status.HTTP_201_CREATED)
def add_space_member(
    space_id: str,
    payload: SpaceMemberCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceMemberItem:
    _ensure_space_admin_change_allowed(
        db,
        current_user,
        space_id,
        current_role=None,
        next_role=payload.role,
    )
    user = _validate_space_member_user(db, space_id, payload.user_id)
    membership = TeamMember(
        id=new_id(),
        team_id=space_id,
        user_id=user.id,
        role=payload.role,
    )
    db.add(membership)
    db.commit()
    membership = _get_space_membership(db, space_id, user.id)
    assert membership is not None
    return _serialize_space_member(db, membership)


@router.patch("/spaces/{space_id}/members/{user_id}", response_model=SpaceMemberItem)
def update_space_member(
    space_id: str,
    user_id: str,
    payload: SpaceMemberRoleUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> SpaceMemberItem:
    membership = _get_space_membership(db, space_id, user_id)
    if membership is None:
        raise localized_http_exception(status_code=404, code="pms.member_not_found")
    _ensure_space_admin_change_allowed(
        db,
        current_user,
        space_id,
        current_role=membership.role,
        next_role=payload.role,
    )
    members = _load_space_members(db, space_id)
    _ensure_space_owner_survives(members, user_id, next_role=payload.role)
    membership.role = payload.role
    db.add(membership)
    db.commit()
    membership = _get_space_membership(db, space_id, user_id)
    assert membership is not None
    return _serialize_space_member(db, membership)


@router.delete("/spaces/{space_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_space_member(
    space_id: str,
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    membership = _get_space_membership(db, space_id, user_id)
    if membership is None:
        raise localized_http_exception(status_code=404, code="pms.member_not_found")
    _ensure_space_admin_change_allowed(
        db,
        current_user,
        space_id,
        current_role=membership.role,
        next_role=None,
    )
    members = _load_space_members(db, space_id)
    _ensure_space_owner_survives(members, user_id, next_role=None)
    db.delete(membership)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/lists", response_model=TaskListsResponse)
def list_task_lists(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="updated_at"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    q: str = Query(default=""),
    archived: bool | None = None,
    team_id: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskListsResponse:
    return pms_service.list_task_lists(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.list_task_lists",
        ),
        user=current_user,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        q=q,
        archived=archived,
        team_id=team_id,
    )


@router.get("/spaces/{space_id}/lists", response_model=TaskListsResponse)
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
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskListsResponse:
    return pms_service.list_task_lists(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.list_space_lists",
        ),
        user=current_user,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        q=q,
        archived=archived,
        team_id=space_id,
    )


@router.post("/lists", response_model=TaskListItem, status_code=status.HTTP_201_CREATED)
def create_task_list(
    payload: TaskListCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListItem:
    resolved_key = payload.key.upper() if payload.key else _unique_key(db, payload.name)

    resolved_team_name: str | None = None
    resolved_team_id = payload.team_id
    if resolved_team_id:
        team, _role = _ensure_space_editor(db, current_user, resolved_team_id)
        resolved_team_name = team.name
    else:
        team = get_or_create_default_pms_space(db, workspace=_get_pms_workspace(db))
        resolved_team_id = team.id
        resolved_team_name = team.name

    _validate_folder_membership(db, resolved_team_id, payload.folder_id)

    task_list = TaskList(
        id=new_id(),
        key=resolved_key,
        name=payload.name.strip(),
        description=payload.description.strip(),
        status="active",
        team_id=resolved_team_id,
        folder_id=payload.folder_id,
        created_by_id=current_user.id,
    )
    db.add(task_list)
    if not db.scalar(
        select(TeamMember.id).where(TeamMember.team_id == resolved_team_id, TeamMember.user_id == current_user.id)
    ):
        db.add(TeamMember(id=new_id(), team_id=resolved_team_id, user_id=current_user.id, role="owner"))
    _create_default_labels(db, task_list.id)
    _create_default_statuses(db, task_list.id)
    db.commit()
    db.refresh(task_list)
    task_list = db.scalar(
        select(TaskList)
        .options(
            selectinload(TaskList.milestones),
            selectinload(TaskList.issues).selectinload(Issue.comments),
            joinedload(TaskList.folder),
        )
        .where(TaskList.id == task_list.id)
    )
    member_count = len(_load_space_members(db, resolved_team_id))
    return _serialize_task_list(task_list, "owner", resolved_team_name, member_count)


@router.get("/lists/{list_id}", response_model=TaskListItem)
def get_task_list(
    list_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListItem:
    task_list, role = _ensure_list_member(db, current_user, list_id)
    task_list = db.scalar(
        select(TaskList)
        .options(
            selectinload(TaskList.milestones),
            selectinload(TaskList.issues).selectinload(Issue.comments),
            joinedload(TaskList.folder),
        )
        .where(TaskList.id == task_list.id)
    )
    t_name = db.scalar(select(Team.name).where(Team.id == task_list.team_id)) if task_list.team_id else None
    member_count = len(_load_space_members(db, task_list.team_id)) if task_list.team_id else 0
    return _serialize_task_list(task_list, role, t_name, member_count)


@router.patch("/lists/{list_id}", response_model=TaskListItem)
def update_task_list(
    list_id: str,
    payload: TaskListUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListItem:
    fields_set = set(payload.model_fields_set)
    if fields_set and fields_set.issubset({"folder_id", "sort_order"}):
        task_list, role = _ensure_list_editor(db, current_user, list_id)
    else:
        task_list, role = _ensure_list_owner(db, current_user, list_id)
    if "folder_id" in payload.model_fields_set:
        _validate_folder_membership(db, task_list.team_id, payload.folder_id)
        task_list.folder_id = payload.folder_id
    if payload.sort_order is not None:
        task_list.sort_order = payload.sort_order

    for field_name in ["name", "description", "status", "archived"]:
        if field_name not in payload.model_fields_set:
            continue
        value = getattr(payload, field_name)
        if value is None:
            continue
        setattr(task_list, field_name, value.strip() if isinstance(value, str) else value)
    if fields_set - {"folder_id", "sort_order"}:
        enqueue_task_list_issue_recompute(db, task_list=task_list)
    db.commit()
    db.refresh(task_list)
    task_list = db.scalar(
        select(TaskList)
        .options(
            selectinload(TaskList.milestones),
            selectinload(TaskList.issues).selectinload(Issue.comments),
            joinedload(TaskList.folder),
        )
        .where(TaskList.id == task_list.id)
    )
    t_name = db.scalar(select(Team.name).where(Team.id == task_list.team_id)) if task_list.team_id else None
    member_count = len(_load_space_members(db, task_list.team_id)) if task_list.team_id else 0
    return _serialize_task_list(task_list, role, t_name, member_count)


@router.patch("/spaces/{space_id}/lists/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_space_lists(
    space_id: str,
    payload: TaskListReorderRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _ensure_space_editor(db, current_user, space_id)
    item_ids = [item.id for item in payload.items]
    if len(set(item_ids)) != len(item_ids):
        raise localized_http_exception(status_code=400, code="pms.duplicate_task_list_ids")

    task_lists = list(
        db.scalars(
            select(TaskList).where(
                TaskList.team_id == space_id,
                TaskList.id.in_(item_ids),
            )
        )
    )
    task_list_map = {task_list.id: task_list for task_list in task_lists}
    if len(task_list_map) != len(item_ids):
        raise localized_http_exception(status_code=404, code="pms.task_list_not_found")

    for item in payload.items:
        _validate_folder_membership(db, space_id, item.folder_id)
        task_list = task_list_map[item.id]
        task_list.folder_id = item.folder_id
        task_list.sort_order = item.sort_order

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/lists/{list_id}/milestones", response_model=MilestoneListResponse)
def list_milestones(
    list_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="sort_order"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MilestoneListResponse:
    task_list, _ = _ensure_list_member(db, current_user, list_id)
    milestones = list(task_list.milestones)
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
    "/lists/{list_id}/milestones",
    response_model=MilestoneItem,
    status_code=status.HTTP_201_CREATED,
)
def create_milestone(
    list_id: str,
    payload: MilestoneCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MilestoneItem:
    task_list, _ = _ensure_list_owner(db, current_user, list_id)
    milestone = Milestone(
        id=new_id(),
        list_id=task_list.id,
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
        .options(selectinload(Milestone.task_list))
        .where(Milestone.id == milestone_id)
    )
    if milestone is None:
        raise localized_http_exception(status_code=404, code="pms.milestone_not_found")
    _ensure_list_owner(db, current_user, milestone.list_id)
    for field_name in ["title", "description", "status", "start_date", "due_date", "sort_order"]:
        value = getattr(payload, field_name)
        if value is not None:
            setattr(milestone, field_name, value.strip() if isinstance(value, str) else value)
    enqueue_milestone_issue_recompute(db, milestone=milestone)
    db.commit()
    db.refresh(milestone)
    milestone = db.scalar(
        select(Milestone).options(selectinload(Milestone.issues)).where(Milestone.id == milestone_id)
    )
    return _serialize_milestone(milestone)


@router.get("/lists/{list_id}/labels", response_model=LabelListResponse)
def list_task_list_labels(
    list_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LabelListResponse:
    _ensure_list_member(db, current_user, list_id)
    labels = list(db.scalars(select(Label).where(Label.list_id == list_id).order_by(Label.name)))
    items = [LabelItem(id=label.id, name=label.name, color=label.color) for label in labels]
    page_items, total = _paginate(items, page, page_size)
    return LabelListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.post("/lists/{list_id}/labels", response_model=LabelItem, status_code=status.HTTP_201_CREATED)
def create_task_list_label(
    list_id: str,
    payload: LabelCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LabelItem:
    _ensure_list_owner(db, current_user, list_id)
    existing = db.scalar(
        select(Label).where(Label.list_id == list_id, func.lower(Label.name) == payload.name.strip().lower())
    )
    if existing is not None:
        raise localized_http_exception(status_code=409, code="pms.label_name_exists")
    label = Label(id=new_id(), list_id=list_id, name=payload.name.strip(), color=payload.color)
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
        raise localized_http_exception(status_code=404, code="pms.label_not_found")
    _ensure_list_owner(db, current_user, label.list_id)
    if payload.name is not None:
        normalized_name = payload.name.strip()
        existing = db.scalar(
            select(Label).where(
                Label.list_id == label.list_id,
                Label.id != label.id,
                func.lower(Label.name) == normalized_name.lower(),
            )
        )
        if existing is not None:
            raise localized_http_exception(status_code=409, code="pms.label_name_exists")
        label.name = normalized_name
    if payload.color is not None:
        label.color = payload.color
    enqueue_label_issue_recompute(db, label=label)
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
        raise localized_http_exception(status_code=404, code="pms.label_not_found")
    _ensure_list_owner(db, current_user, label.list_id)
    affected_issue_ids = collect_label_issue_ids(db, label_id=label.id)
    enqueue_label_issue_recompute(
        db,
        label=label,
        issue_ids=affected_issue_ids,
    )
    db.delete(label)
    db.commit()


@router.get("/lists/{list_id}/issues", response_model=IssueListResponse)
def list_issues(
    list_id: str,
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
    workspace: Workspace = Depends(require_current_workspace),
) -> IssueListResponse:
    return pms_service.list_issues(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.list_issues",
        ),
        user=current_user,
        list_id=list_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        q=q,
        status_filter=status_filter,
        assignee_id=assignee_id,
        priority=priority,
        label_id=label_id,
        milestone_id=milestone_id,
        archived=archived,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        start_date_from=start_date_from,
        start_date_to=start_date_to,
    )


@router.post(
    "/lists/{list_id}/issues",
    response_model=IssueListItem,
    status_code=status.HTTP_201_CREATED,
)
def create_issue(
    list_id: str,
    payload: IssueCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> IssueListItem:
    return pms_service.create_issue(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.create_issue",
        ),
        user=current_user,
        list_id=list_id,
        title=payload.title,
        description=payload.description,
        description_blocks=payload.description_blocks,
        status=payload.status,
        priority=payload.priority,
        assignee_id=payload.assignee_id,
        milestone_id=payload.milestone_id,
        parent_id=payload.parent_id,
        start_date=payload.start_date,
        due_date=payload.due_date,
        estimate_hours=payload.estimate_hours,
        recurrence_rule=payload.recurrence_rule,
        label_ids=payload.label_ids,
    )


@router.get("/issues/assigned", response_model=IssueListResponse)
def list_assigned_issues(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> IssueListResponse:
    return pms_service.list_assigned_issues(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.list_assigned_issues",
        ),
        user=current_user,
        limit=limit,
    )


@router.get("/issues/{issue_id}", response_model=IssueDetailResponse)
def get_issue(
    issue_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> IssueDetailResponse:
    return pms_service.get_issue_detail(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.get_issue",
        ),
        user=current_user,
        issue_id=issue_id,
    )


@router.patch("/issues/{issue_id}", response_model=IssueListItem)
def update_issue(
    issue_id: str,
    payload: IssueUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> IssueListItem:
    return pms_service.update_issue(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.update_issue",
        ),
        user=current_user,
        issue_id=issue_id,
        provided_fields=set(payload.model_fields_set),
        title=payload.title,
        description=payload.description,
        description_blocks=payload.description_blocks,
        parent_id=payload.parent_id,
        status=payload.status,
        priority=payload.priority,
        assignee_id=payload.assignee_id,
        milestone_id=payload.milestone_id,
        start_date=payload.start_date,
        due_date=payload.due_date,
        board_position=payload.board_position,
        archived=payload.archived,
        estimate_hours=payload.estimate_hours,
        recurrence_rule=payload.recurrence_rule,
        label_ids=payload.label_ids,
    )


@router.patch("/lists/{list_id}/issues/bulk", response_model=BulkUpdateResponse)
def bulk_update_issues(
    list_id: str,
    payload: BulkUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BulkUpdateResponse:
    task_list, _role = _ensure_list_editor(db, current_user, list_id)
    issue_map = {
        issue.id: issue
        for issue in db.scalars(
            select(Issue)
            .options(
                selectinload(Issue.task_list),
                selectinload(Issue.label_links).selectinload(IssueLabel.label),
                selectinload(Issue.assignee),
            )
            .where(Issue.id.in_(payload.issue_ids), Issue.list_id == list_id)
        )
    }
    ordered_issues = [issue_map[issue_id] for issue_id in payload.issue_ids if issue_id in issue_map]
    if not ordered_issues:
        raise localized_http_exception(status_code=404, code="pms.no_matching_issues")

    if payload.delete:
        media_keys: list[str] = []
        for issue in ordered_issues:
            for child in getattr(issue, "subtasks", []):
                child.parent_id = None
            media_keys.extend(cleanup_media_for_resource(db, "issue", issue.id))
            enqueue_issue_rag_sync(
                db,
                issue=issue,
                operation=RagSyncOperation.DELETE,
            )
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

    label_map = {label.id: label for label in task_list.labels}
    updated = 0
    next_position = None
    if payload.status is not None:
        next_position = _next_issue_board_position(db, list_id, payload.status)

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
            _validate_issue_assignee(db, task_list, payload.assignee_id)
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
            enqueue_issue_rag_sync(
                db,
                issue=issue,
                operation=RagSyncOperation.UPSERT,
            )
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
    enqueue_issue_rag_sync(
        db,
        issue=issue,
        operation=RagSyncOperation.DELETE,
    )
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
    workspace: Workspace = Depends(require_current_workspace),
) -> IssueCommentItem:
    return pms_service.add_issue_comment(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.create_issue_comment",
        ),
        user=current_user,
        issue_id=issue_id,
        body=payload.body,
        body_blocks=payload.body_blocks,
    )


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
    predecessor_issue, predecessor_task_list = _get_issue_for_user(
        db, current_user, payload.predecessor_id, require_editor=True
    )
    successor_issue, successor_task_list = _get_issue_for_user(
        db, current_user, payload.successor_id, require_editor=True
    )
    if predecessor_task_list.id != successor_task_list.id:
        raise localized_http_exception(status_code=400, code="pms.dependencies_same_list_required")

    dependency = ScheduleDependency(
        id=new_id(),
        list_id=predecessor_task_list.id,
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
        raise localized_http_exception(status_code=404, code="pms.dependency_not_found")
    _ensure_list_editor(db, current_user, dependency.list_id)
    db.delete(dependency)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    list_id: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DashboardSummaryResponse:
    task_lists = list(
        db.scalars(
            _accessible_task_lists_query(db, current_user).options(
                selectinload(TaskList.milestones).selectinload(Milestone.issues),
                selectinload(TaskList.issues)
                .selectinload(Issue.comments),
                selectinload(TaskList.issues).selectinload(Issue.assignee),
                selectinload(TaskList.issues).selectinload(Issue.reporter),
            )
        )
    )
    if list_id:
        task_lists = [task_list for task_list in task_lists if task_list.id == list_id]
    issues = [issue for task_list in task_lists for issue in task_list.issues if not issue.archived]
    active_issues = [issue for issue in issues if issue.status not in {"done", "canceled"}]
    overdue_issues = [
        issue
        for issue in active_issues
        if issue.due_date is not None and issue.due_date < date.today()
    ]
    milestone_due_soon_count = sum(
        1
        for task_list in task_lists
        for milestone in task_list.milestones
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
            .options(selectinload(IssueActivityLog.actor), selectinload(IssueActivityLog.issue).selectinload(Issue.task_list))
            .where(Issue.list_id.in_([task_list.id for task_list in task_lists] or ["__none__"]))
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

    list_cards = []
    for task_list in task_lists:
        issue_progress_scope = [issue for issue in task_list.issues if not issue.archived]
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
        list_cards.append(
            DashboardTaskListItem(
                list_id=task_list.id,
                key=task_list.key,
                name=task_list.name,
                progress=_calculate_progress(issue_progress_scope),
                open_issue_count=open_issue_count,
                overdue_issue_count=overdue_issue_count,
                next_due_date=due_dates[0] if due_dates else None,
            )
        )

    return DashboardSummaryResponse(
        list_count=len(task_lists),
        active_issue_count=len(active_issues),
        overdue_issue_count=len(overdue_issues),
        my_issue_count=sum(1 for issue in active_issues if issue.assignee_id == current_user.id),
        milestone_due_soon_count=milestone_due_soon_count,
        status_counts=status_counts,
        priority_counts=priority_counts,
        lists=list_cards,
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
    issue, task_list = _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise localized_http_exception(status_code=413, code="pms.file_size_limit_exceeded", limit_mb=50)

    settings = get_settings()
    client = get_minio_client()
    attachment_id = new_id()
    storage_key = f"pms/{task_list.id}/{issue.id}/{attachment_id}/{file.filename}"
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
        raise localized_http_exception(status_code=404, code="pms.attachment_not_found")
    _ensure_issue_readable(db, current_user, attachment.issue_id)

    url = _build_attachment_download_url(attachment.storage_key)
    return RedirectResponse(url=url, status_code=302)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    attachment = db.scalar(
        select(Attachment).options(selectinload(Attachment.issue).selectinload(Issue.task_list)).where(Attachment.id == attachment_id)
    )
    if attachment is None:
        raise localized_http_exception(status_code=404, code="pms.attachment_not_found")
    _ensure_list_editor(db, current_user, attachment.issue.list_id)

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
                action_url=n.action_url,
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
        raise localized_http_exception(status_code=404, code="pms.notification_not_found")
    notification.is_read = True
    db.commit()
    return NotificationItem(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        body=notification.body,
        reference_type=notification.reference_type,
        reference_id=notification.reference_id,
        action_url=notification.action_url,
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
        .options(selectinload(ChecklistItem.issue).selectinload(Issue.task_list))
        .where(ChecklistItem.id == item_id)
    )
    if item is None:
        raise localized_http_exception(status_code=404, code="pms.checklist_item_not_found")
    _ensure_list_editor(db, current_user, item.issue.list_id)

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
        .options(selectinload(ChecklistItem.issue).selectinload(Issue.task_list))
        .where(ChecklistItem.id == item_id)
    )
    if item is None:
        raise localized_http_exception(status_code=404, code="pms.checklist_item_not_found")
    _ensure_list_editor(db, current_user, item.issue.list_id)
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
        .options(selectinload(TimeEntry.issue).selectinload(Issue.task_list), selectinload(TimeEntry.user))
        .where(TimeEntry.id == entry_id)
    )
    if entry is None:
        raise localized_http_exception(status_code=404, code="pms.time_entry_not_found")
    _ensure_list_editor(db, current_user, entry.issue.list_id)

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
        .options(selectinload(TimeEntry.issue).selectinload(Issue.task_list))
        .where(TimeEntry.id == entry_id)
    )
    if entry is None:
        raise localized_http_exception(status_code=404, code="pms.time_entry_not_found")
    _ensure_list_editor(db, current_user, entry.issue.list_id)
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


# ── Task List Statuses (Custom Workflow) ─────────────────────────────


def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "_")[:40]


def _serialize_status(s: TaskListStatus) -> TaskListStatusItem:
    return TaskListStatusItem(
        id=s.id,
        slug=s.slug,
        name=s.name,
        color=s.color,
        category=s.category,
        sort_order=s.sort_order,
    )


@router.get("/lists/{list_id}/statuses", response_model=TaskListStatusesResponse)
def list_task_list_statuses(
    list_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListStatusesResponse:
    task_list, _ = _ensure_list_member(db, current_user, list_id)
    statuses = list(
        db.scalars(
            select(TaskListStatus)
            .where(TaskListStatus.list_id == list_id)
            .order_by(TaskListStatus.sort_order)
        )
    )
    # Auto-seed default statuses for existing task lists that don't have any
    if not statuses:
        _create_default_statuses(db, list_id)
        db.commit()
        statuses = list(
            db.scalars(
                select(TaskListStatus)
                .where(TaskListStatus.list_id == list_id)
                .order_by(TaskListStatus.sort_order)
            )
        )
    return TaskListStatusesResponse(items=[_serialize_status(s) for s in statuses])


@router.post(
    "/lists/{list_id}/statuses",
    response_model=TaskListStatusItem,
    status_code=status.HTTP_201_CREATED,
)
def create_task_list_status(
    list_id: str,
    payload: TaskListStatusCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListStatusItem:
    _ensure_list_owner(db, current_user, list_id)
    slug = _slugify(payload.name)
    existing = db.scalar(
        select(TaskListStatus).where(
            TaskListStatus.list_id == list_id,
            TaskListStatus.slug == slug,
        )
    )
    if existing is not None:
        raise localized_http_exception(status_code=409, code="pms.status_name_exists")

    ps = TaskListStatus(
        id=new_id(),
        list_id=list_id,
        slug=slug,
        name=payload.name.strip(),
        color=payload.color,
        category=payload.category,
        sort_order=payload.sort_order,
    )
    db.add(ps)
    enqueue_task_list_status_issue_search_recompute(db, task_status=ps)
    db.commit()
    db.refresh(ps)
    return _serialize_status(ps)


@router.patch("/task-list-statuses/{status_id}", response_model=TaskListStatusItem)
def update_task_list_status(
    status_id: str,
    payload: TaskListStatusUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListStatusItem:
    ps = db.scalar(select(TaskListStatus).where(TaskListStatus.id == status_id))
    if ps is None:
        raise localized_http_exception(status_code=404, code="pms.status_not_found")
    _ensure_list_owner(db, current_user, ps.list_id)

    if payload.name is not None:
        normalized_name = payload.name.strip()
        existing = db.scalar(
            select(TaskListStatus).where(
                TaskListStatus.list_id == ps.list_id,
                TaskListStatus.id != ps.id,
                func.lower(TaskListStatus.name) == normalized_name.lower(),
            )
        )
        if existing is not None:
            raise localized_http_exception(status_code=409, code="pms.status_name_exists")
        ps.name = normalized_name
    if payload.color is not None:
        ps.color = payload.color
    if payload.category is not None:
        ps.category = payload.category
    if payload.sort_order is not None:
        ps.sort_order = payload.sort_order

    enqueue_task_list_status_issue_search_recompute(db, task_status=ps)
    db.commit()
    db.refresh(ps)
    return _serialize_status(ps)


@router.delete("/task-list-statuses/{status_id}")
def delete_task_list_status(
    status_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    ps = db.scalar(select(TaskListStatus).where(TaskListStatus.id == status_id))
    if ps is None:
        raise localized_http_exception(status_code=404, code="pms.status_not_found")
    _ensure_list_owner(db, current_user, ps.list_id)

    # Prevent deleting if issues use this status
    count = db.scalar(
        select(func.count())
        .select_from(Issue)
        .where(Issue.list_id == ps.list_id, Issue.status == ps.slug)
    )
    if count and count > 0:
        raise localized_http_exception(
            status_code=409,
            code="pms.status_in_use",
            count=count,
        )

    db.delete(ps)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── CSV Export ──────────────────────────────────────────────────────


@router.get("/lists/{list_id}/export")
def export_task_list_issues(
    list_id: str,
    format: str = Query(default="csv"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    task_list, _ = _ensure_list_member(db, current_user, list_id)

    issues = list(
        db.scalars(
            select(Issue)
            .options(
                selectinload(Issue.task_list),
                selectinload(Issue.assignee),
                selectinload(Issue.reporter),
                selectinload(Issue.milestone),
                selectinload(Issue.label_links).selectinload(IssueLabel.label),
                selectinload(Issue.comments),
                selectinload(Issue.checklist_items),
                selectinload(Issue.time_entries),
                selectinload(Issue.subtasks),
            )
            .where(Issue.list_id == list_id)
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
        ref = f"{task_list.key}-{issue.issue_number}"
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
            "Content-Disposition": f'attachment; filename="{task_list.key}_issues.csv"',
        },
    )


# ── Task Templates ──────────────────────────────────────────────────


def _serialize_template(t: TaskTemplate) -> TaskTemplateItem:
    return TaskTemplateItem(
        id=t.id,
        list_id=t.list_id,
        name=t.name,
        description=t.description,
        default_status=t.default_status,
        default_priority=t.default_priority,
        checklist_items=t.checklist_items,
        created_at=t.created_at,
    )


@router.get("/lists/{list_id}/templates", response_model=TaskTemplateListResponse)
def list_templates(
    list_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskTemplateListResponse:
    _ensure_list_member(db, current_user, list_id)
    templates = list(
        db.scalars(
            select(TaskTemplate)
            .where(TaskTemplate.list_id == list_id)
            .order_by(TaskTemplate.created_at.desc())
        )
    )
    return TaskTemplateListResponse(items=[_serialize_template(t) for t in templates])


@router.post(
    "/lists/{list_id}/templates",
    response_model=TaskTemplateItem,
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    list_id: str,
    payload: TaskTemplateCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskTemplateItem:
    _ensure_list_editor(db, current_user, list_id)
    t = TaskTemplate(
        id=new_id(),
        list_id=list_id,
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
        raise localized_http_exception(status_code=404, code="pms.template_not_found")
    _ensure_list_editor(db, current_user, t.list_id)

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
        raise localized_http_exception(status_code=404, code="pms.template_not_found")
    _ensure_list_editor(db, current_user, t.list_id)
    db.delete(t)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Custom Fields ───────────────────────────────────────────────────


@router.get("/lists/{list_id}/custom-fields", response_model=CustomFieldListResponse)
def list_custom_fields(
    list_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CustomFieldListResponse:
    _ensure_list_member(db, current_user, list_id)
    fields = list(
        db.scalars(
            select(CustomField)
            .where(CustomField.list_id == list_id)
            .order_by(CustomField.sort_order)
        )
    )
    return CustomFieldListResponse(
        items=[
            CustomFieldItem(
                id=f.id,
                list_id=f.list_id,
                name=f.name,
                field_type=f.field_type,
                options=f.options,
                sort_order=f.sort_order,
            )
            for f in fields
        ]
    )


@router.post(
    "/lists/{list_id}/custom-fields",
    response_model=CustomFieldItem,
    status_code=status.HTTP_201_CREATED,
)
def create_custom_field(
    list_id: str,
    payload: CustomFieldCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CustomFieldItem:
    _ensure_list_owner(db, current_user, list_id)
    f = CustomField(
        id=new_id(),
        list_id=list_id,
        name=payload.name.strip(),
        field_type=payload.field_type,
        options=payload.options,
        sort_order=payload.sort_order,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return CustomFieldItem(
        id=f.id, list_id=f.list_id, name=f.name,
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
        raise localized_http_exception(status_code=404, code="pms.custom_field_not_found")
    _ensure_list_owner(db, current_user, f.list_id)
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
        raise localized_http_exception(status_code=404, code="pms.issue_not_found")
    _ensure_issue_readable(db, current_user, issue)
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
        raise localized_http_exception(status_code=404, code="pms.issue_not_found")
    _ensure_list_editor(db, current_user, issue.list_id)

    # Validate field belongs to the same task list.
    field = db.scalar(select(CustomField).where(CustomField.id == payload.field_id))
    if field is None or field.list_id != issue.list_id:
        raise localized_http_exception(status_code=400, code="pms.custom_field_wrong_list")

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
    issue, task_list = _get_issue_for_user(db, current_user, issue_id, require_editor=True)
    if task_list.team_id is None:
        raise localized_http_exception(status_code=409, code="pms.task_list_space_missing")
    member_ids = _space_member_ids(db, task_list.team_id)

    # Clear existing assignee links
    for link in list(issue.assignee_links):
        db.delete(link)
    db.flush()

    # Add new ones (validate all users first)
    result: list[IssueAssigneeItem] = []
    validated_user_ids: list[str] = []
    for uid in payload.user_ids:
        if uid not in member_ids:
            raise localized_http_exception(status_code=400, code="pms.assignees_task_list_members_required")
        user = db.scalar(select(User).where(User.id == uid))
        if user is None:
            raise localized_http_exception(status_code=404, code="auth.user_not_found")
        db.add(IssueAssignee(id=new_id(), issue_id=issue_id, user_id=uid))
        result.append(IssueAssigneeItem(user_id=uid, full_name=user.full_name))
        validated_user_ids.append(uid)

    # Update primary assignee_id to the first validated user (or clear)
    issue.assignee_id = validated_user_ids[0] if validated_user_ids else None
    enqueue_issue_rag_sync(
        db,
        issue=issue,
        operation=RagSyncOperation.UPSERT,
    )

    db.commit()
    return result


# ── Folders ─────────────────────────────────────────────────────────


class FolderItem(BaseModel):
    id: str
    team_id: str | None
    name: str
    sort_order: int
    list_count: int = 0


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
    else:
        accessible_team_ids = _accessible_space_ids(db, current_user)
        if accessible_team_ids:
            q = q.where(Folder.team_id.in_(accessible_team_ids))
        else:
            q = q.where(Folder.id == "__none__")
    folders = list(db.scalars(q))

    # Count task lists per folder.
    folder_ids = [f.id for f in folders]
    list_counts: dict[str, int] = {}
    if folder_ids:
        for fid in folder_ids:
            cnt = db.scalar(
                select(func.count()).select_from(TaskList).where(TaskList.folder_id == fid)
            )
            list_counts[fid] = cnt or 0

    return FolderListResponse(
        items=[
            FolderItem(
                id=f.id, team_id=f.team_id, name=f.name,
                sort_order=f.sort_order,
                list_count=list_counts.get(f.id, 0),
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
        resolved_team_id = get_or_create_default_pms_space(
            db,
            workspace=_get_pms_workspace(db),
        ).id
    _ensure_space_editor(db, current_user, resolved_team_id)
    folder = Folder(
        id=new_id(),
        team_id=resolved_team_id,
        name=payload.name.strip(),
        sort_order=payload.sort_order,
    )
    db.add(folder)

    # Auto-create a default list inside the new folder
    default_key = _unique_key(db, "List")
    default_task_list = TaskList(
        id=new_id(),
        key=default_key,
        name="List",
        description="",
        status="active",
        team_id=resolved_team_id,
        folder_id=folder.id,
        created_by_id=current_user.id,
    )
    db.add(default_task_list)
    if not db.scalar(
        select(TeamMember.id).where(TeamMember.team_id == resolved_team_id, TeamMember.user_id == current_user.id)
    ):
        db.add(TeamMember(id=new_id(), team_id=resolved_team_id, user_id=current_user.id, role="owner"))
    _create_default_statuses(db, default_task_list.id)
    _create_default_labels(db, default_task_list.id)

    db.commit()
    db.refresh(folder)
    return FolderItem(
        id=folder.id, team_id=folder.team_id, name=folder.name,
        sort_order=folder.sort_order, list_count=1,
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
        raise localized_http_exception(status_code=404, code="pms.folder_not_found")
    if folder.team_id is None:
        raise localized_http_exception(status_code=409, code="pms.folder_space_missing")
    _ensure_space_manager(db, current_user, folder.team_id)
    if payload.name is not None:
        folder.name = payload.name.strip()
    if payload.sort_order is not None:
        folder.sort_order = payload.sort_order
    db.commit()
    db.refresh(folder)
    cnt = db.scalar(select(func.count()).select_from(TaskList).where(TaskList.folder_id == folder_id)) or 0
    return FolderItem(
        id=folder.id, team_id=folder.team_id, name=folder.name,
        sort_order=folder.sort_order, list_count=cnt,
    )


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    folder = db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        raise localized_http_exception(status_code=404, code="pms.folder_not_found")
    if folder.team_id is None:
        raise localized_http_exception(status_code=409, code="pms.folder_space_missing")
    _ensure_space_manager(db, current_user, folder.team_id)
    # Unlink task lists from this folder without deleting them.
    for p in db.scalars(select(TaskList).where(TaskList.folder_id == folder_id)):
        p.folder_id = None
    db.delete(folder)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
