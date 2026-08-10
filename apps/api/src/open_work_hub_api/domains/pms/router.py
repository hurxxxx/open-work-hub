from __future__ import annotations

import csv
from dataclasses import asdict
from io import StringIO
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import user_principal
from open_work_hub_api.domains.auth.access import (
    get_or_create_default_pms_space,
    has_system_role,
    slugify,
)
from open_work_hub_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from open_work_hub_api.domains.auth.models import (
    Team,
    TeamMember,
    User,
    Workspace,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_work_hub_api.domains.pms.attachments import (
    TaskAttachmentDisposition,
    TaskAttachmentUpload,
    delete_task_attachment,
    get_task_attachment_download_url,
    open_task_attachment_content,
    upload_task_attachment,
)
from open_work_hub_api.domains.pms import task_doc_links as pms_task_doc_links
from open_work_hub_api.domains.pms.models import (
    Folder,
    Task,
    TaskActivityLog,
    TaskAssignee,
    TaskComment,
    TaskFollower,
    TaskLabel,
    Label,
    Milestone,
    Notification,
    SpaceStatus,
    TaskList,
    TaskListStatus,
)
from open_work_hub_api.domains.pms.access import (
    _active_accessible_task_lists_query,
    _accessible_space_ids,
    _ensure_space_access,
    _ensure_space_editor,
    _ensure_space_manager,
    _ensure_list_editor,
    _ensure_list_member,
    _ensure_list_owner,
    _ensure_task_list_active,
    _get_pms_workspace,
    _load_active_space,
    resolve_pms_space_role,
    _space_member_ids,
)
from open_work_hub_api.domains.pms.rag_sync import (
    collect_label_task_ids,
    enqueue_task_rag_sync,
    enqueue_label_task_recompute,
    enqueue_milestone_task_recompute,
)
from open_work_hub_api.domains.pms import board_configuration as pms_board_configuration
from open_work_hub_api.domains.pms import service as pms_service
from open_work_hub_api.domains.pms import task_list_customization as pms_task_list_customization
from open_work_hub_api.domains.pms import view_preferences as pms_view_preferences
from open_work_hub_api.domains.pms import task_work_items as pms_task_work_items
from open_work_hub_api.domains.pms.dashboard_summary import dashboard_summary_payload
from open_work_hub_api.domains.pms.links import normalize_pms_deep_link
from open_work_hub_api.domains.pms.app_catalog import PMS_WORKSPACE_APP
from open_work_hub_api.domains.pms.projections import (
    serialize_task_summary,
    task_reference as _task_reference,
)
from open_work_hub_api.domains.pms.status_lifecycle import (
    create_default_task_list_statuses as _create_default_statuses,
)
from open_work_hub_api.domains.pms.status_router import router as status_router
from open_work_hub_api.domains.rag.contracts import RagSyncOperation
from open_work_hub_api.domains.pms.workflow import (
    calculate_progress,
    is_closed_status,
    is_done_status,
    is_overdue_exempt_status,
    normalize_status_category,
    status_category,
    status_definitions,
    status_label,
)


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
NOISY_ACTIVITY_FIELD_NAMES = {"description_blocks"}


def _visible_activity_log_filter():
    return or_(
        TaskActivityLog.field_name.is_(None),
        TaskActivityLog.field_name.not_in(NOISY_ACTIVITY_FIELD_NAMES),
    )


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    q: str = ""


class PmsViewPreferencesResponse(BaseModel):
    task_list_group_by: Literal["none", "status", "assignee"]


class UpdatePmsViewPreferencesRequest(BaseModel):
    task_list_group_by: Literal["none", "status", "assignee"]


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


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=2, max_length=180)
    description: str = Field(default="", max_length=4000)
    description_blocks: list[dict] | None = None
    status: str = "todo"
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    assignee_id: str | None = None
    assignee_ids: list[str] | None = Field(default=None, max_length=20)
    milestone_id: str | None = None
    parent_id: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    completed_date: date | None = None
    recurrence_rule: str | None = None
    label_ids: list[str] = Field(default_factory=list)


class TaskUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    description_blocks: list[dict] | None = None
    parent_id: str | None = None
    status: str | None = None
    priority: Literal["low", "medium", "high", "critical"] | None = None
    assignee_id: str | None = None
    assignee_ids: list[str] | None = Field(default=None, max_length=20)
    milestone_id: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    completed_date: date | None = None
    board_position: int | None = None
    archived: bool | None = None
    recurrence_rule: str | None = None
    label_ids: list[str] | None = None


class TaskCommentCreateRequest(BaseModel):
    body: str = Field(default="", max_length=4000)
    body_blocks: list[dict] | None = None


class TaskDocAttachRequest(BaseModel):
    doc_id: str


class BulkUpdateRequest(BaseModel):
    task_ids: list[str] = Field(..., min_length=1, max_length=50)
    status: str | None = None
    priority: Literal["low", "medium", "high", "critical"] | None = None
    assignee_id: str | None = None
    add_label_ids: list[str] = Field(default_factory=list)
    remove_label_ids: list[str] = Field(default_factory=list)
    archived: bool | None = None
    delete: bool = False


class TaskReorderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    board_position: int = Field(..., ge=0)
    parent_id: str | None = None


class TaskReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TaskReorderItem] = Field(..., min_length=1, max_length=500)


class BulkUpdateResponse(BaseModel):
    updated_count: int
    deleted_count: int


class TaskListItem(BaseModel):
    id: str
    key: str
    name: str
    description: str
    status: str
    status_mode: str = "custom"
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
    task_count: int
    overdue_task_count: int
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
    task_count: int
    completed_task_count: int
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
    default_status: str = "todo"
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
    task_id: str
    text: str
    completed: bool
    sort_order: int
    created_at: datetime


class TaskItem(BaseModel):
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
    follower_ids: list[str] = []
    follower_names: list[str] = []
    reporter_id: str
    reporter_name: str
    milestone_id: str | None
    milestone_title: str | None
    start_date: date | None
    due_date: date | None
    completed_date: date | None
    board_position: int
    archived: bool
    progress: float | None
    comments_count: int
    checklist_total: int = 0
    checklist_done: int = 0
    recurrence_rule: str | None = None
    labels: list[LabelItem]
    updated_at: datetime


class TaskItemsResponse(BaseModel):
    items: list[TaskItem]
    total: int
    page: int
    page_size: int


class TaskReorderResponse(BaseModel):
    updated_count: int
    items: list[TaskItem]


class TaskDocLinkItem(BaseModel):
    id: str
    task_id: str
    doc_id: str
    doc_title: str
    doc_type: str
    source_app: str
    source_kind: str
    updated_at: datetime
    created_by_id: str
    created_at: datetime


class TaskDocLinksResponse(BaseModel):
    items: list[TaskDocLinkItem]


class TaskCommentItem(BaseModel):
    id: str
    task_id: str
    author_id: str
    author_name: str
    body: str
    body_blocks: list[dict] | None = None
    created_at: datetime


class ActivityLogItem(BaseModel):
    id: str
    task_id: str
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
    task_id: str
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


class TaskDetailResponse(BaseModel):
    task: TaskItem
    comments: list[TaskCommentItem]
    linked_docs: list[TaskDocLinkItem] = []
    subtasks: list[TaskItem] = []
    attachments: list[AttachmentItem] = []
    checklist_items: list[ChecklistItemResponse] = []


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
    task_id: str
    task_reference: str
    message: str
    actor_name: str | None
    created_at: datetime


class DashboardTaskListItem(BaseModel):
    list_id: str
    key: str
    name: str
    progress: float
    open_task_count: int
    overdue_task_count: int
    next_due_date: date | None


class DashboardSummaryResponse(BaseModel):
    list_count: int
    active_task_count: int
    overdue_task_count: int
    my_task_count: int
    milestone_due_soon_count: int
    status_counts: list[StatusCountItem]
    priority_counts: list[PriorityCountItem]
    lists: list[DashboardTaskListItem]
    recent_activity: list[RecentActivityItem]


require_pms_app_enabled = require_workspace_app_enabled(
    PMS_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/pms",
    tags=["pms"],
    dependencies=[Depends(require_pms_app_enabled)],
)
public_router = APIRouter(
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
TASK_LIST_EDITOR_ROLES = {"member", "admin", "owner"}
TASK_LIST_MANAGER_ROLES = {"admin", "owner"}


def _is_pms_super_admin(db: Session, user: User) -> bool:
    return has_system_role(db, user, "platform_admin")


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
    team = _load_active_space(db, space_id)
    if team is None:
        return None
    return resolve_pms_space_role(db, user, team)


def _is_active_space_id(db: Session, space_id: str) -> bool:
    return _load_active_space(db, space_id) is not None


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


def _validate_folder_membership(db: Session, team_id: str, folder_id: str | None) -> None:
    if folder_id is None:
        return

    folder = db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        raise localized_http_exception(status_code=404, code="pms.folder_not_found")
    if folder.team_id != team_id:
        raise localized_http_exception(status_code=400, code="pms.folder_same_space_required")


def _normalize_status_category(category: str) -> str:
    return normalize_status_category(category)


def _status_definitions(task_list: TaskList | None) -> list[TaskListStatus | SpaceStatus]:
    return status_definitions(task_list)


def _status_label(status_value: str, task_list: TaskList | None = None) -> str:
    return status_label(status_value, task_list)


def _status_category(status_value: str, task_list: TaskList | None = None) -> str | None:
    return status_category(status_value, task_list)


def _is_closed_status(status_value: str, task_list: TaskList | None = None) -> bool:
    """Check if a status represents a final closed state."""
    return is_closed_status(status_value, task_list)


def _is_done_status(status_value: str, task_list: TaskList | None = None) -> bool:
    """Check if a status represents a completed state."""
    return is_done_status(status_value, task_list)


def _is_overdue_exempt_status(status_value: str, task_list: TaskList | None = None) -> bool:
    return is_overdue_exempt_status(status_value, task_list)


def _calculate_progress(tasks: list[Task], task_list: TaskList | None = None) -> float:
    return calculate_progress(tasks, task_list)


def _serialize_task(task: Task) -> TaskItem:
    return TaskItem.model_validate(serialize_task_summary(task))


def _serialize_task_list(
    task_list: TaskList,
    role: str,
    team_name: str | None = None,
    member_count: int | None = None,
) -> TaskListItem:
    overdue_task_count = sum(
        1
        for task in task_list.tasks
        if (
            not task.archived
            and not _is_overdue_exempt_status(task.status, task_list)
            and task.due_date is not None
            and task.due_date < date.today()
        )
    )
    return TaskListItem(
        id=task_list.id,
        key=task_list.key,
        name=task_list.name,
        description=task_list.description,
        status=task_list.status,
        status_mode=task_list.status_mode,
        archived=task_list.archived,
        team_id=task_list.team_id,
        team_name=team_name,
        folder_id=task_list.folder_id,
        folder_name=getattr(task_list.folder, "name", None) if task_list.folder_id else None,
        sort_order=task_list.sort_order,
        role=role,
        progress=_calculate_progress(task_list.tasks, task_list),
        member_count=member_count if member_count is not None else 0,
        milestone_count=len(task_list.milestones),
        task_count=len(task_list.tasks),
        overdue_task_count=overdue_task_count,
        created_at=task_list.created_at,
        updated_at=task_list.updated_at,
    )


def _serialize_milestone(milestone: Milestone) -> MilestoneItem:
    tasks = list(milestone.tasks)
    completed_task_count = sum(1 for task in tasks if _is_done_status(task.status))
    return MilestoneItem(
        id=milestone.id,
        list_id=milestone.list_id,
        title=milestone.title,
        description=milestone.description,
        status=milestone.status,
        start_date=milestone.start_date,
        due_date=milestone.due_date,
        sort_order=milestone.sort_order,
        progress=_calculate_progress(tasks),
        task_count=len(tasks),
        completed_task_count=completed_task_count,
        updated_at=milestone.updated_at,
    )


def _serialize_comment(comment: TaskComment) -> TaskCommentItem:
    return TaskCommentItem(
        id=comment.id,
        task_id=comment.task_id,
        author_id=comment.author_id,
        author_name=comment.author.full_name,
        body=comment.body,
        body_blocks=comment.body_blocks,
        created_at=comment.created_at,
    )


def _serialize_activity(log: TaskActivityLog, reference_lookup: dict[str, str]) -> ActivityLogItem:
    return ActivityLogItem(
        id=log.id,
        task_id=log.task_id,
        actor_id=log.actor_id,
        actor_name=getattr(log.actor, "full_name", None),
        action=log.action,
        field_name=log.field_name,
        from_value=log.from_value,
        to_value=log.to_value,
        message=log.message,
        created_at=log.created_at,
    )


def _task_list_role(
    db: Session, task_list: TaskList, user: User, team_lookup: dict[str, Team]
) -> str:
    if task_list.team_id is None:
        return "viewer"
    team = team_lookup.get(task_list.team_id)
    if team is None:
        return "viewer"
    return resolve_pms_space_role(db, user, team) or "viewer"


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


def _create_default_labels(db: Session, list_id: str) -> None:
    for name, color in [
        ("blocked", "#b45309"),
        ("priority", "#1d4ed8"),
        ("review", "#0f766e"),
    ]:
        db.add(Label(id=new_id(), list_id=list_id, name=name, color=color))


def _log_task_activity(
    db: Session,
    task_id: str,
    actor_id: str | None,
    action: str,
    message: str,
    *,
    field_name: str | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
) -> None:
    pms_service._log_task_activity(
        db,
        task_id,
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
    reference_type: str = "task",
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


def _next_task_number(db: Session, list_id: str) -> int:
    return pms_service._next_task_number(db, list_id)


def _next_task_board_position(
    db: Session,
    list_id: str,
    parent_id: str | None = None,
) -> int:
    return pms_service._next_task_board_position(db, list_id, parent_id)


def _validate_member_user(db: Session, task_list: TaskList, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    if task_list.team_id is None:
        raise localized_http_exception(status_code=409, code="pms.task_list_space_missing")
    if user_id in _space_member_ids(db, task_list.team_id):
        raise localized_http_exception(status_code=409, code="pms.user_already_task_list_member")
    return user


def _validate_task_assignee(db: Session, task_list: TaskList, assignee_id: str | None) -> None:
    pms_service._validate_task_assignee(db, task_list, assignee_id)


def _validate_milestone(task_list: TaskList, milestone_id: str | None) -> None:
    pms_service._validate_milestone(task_list, milestone_id)


def _validate_parent_task(
    db: Session,
    task_list: TaskList,
    parent_id: str | None,
    *,
    task_id: str | None = None,
) -> None:
    pms_service._validate_parent_task(db, task_list, parent_id, task_id=task_id)


def _set_task_labels(db: Session, task: Task, label_ids: list[str], task_list: TaskList) -> None:
    pms_service._set_task_labels(db, task, label_ids, task_list)


def _get_task_for_user(
    db: Session,
    user: User,
    task_id: str,
    *,
    require_editor: bool = False,
) -> tuple[Task, TaskList]:
    return pms_service._get_task_for_user(
        db,
        user,
        task_id,
        require_editor=require_editor,
    )


def _serialize_visible_task_doc_links(
    db: Session,
    *,
    user: User,
    task_id: str,
) -> TaskDocLinksResponse:
    return TaskDocLinksResponse(
        items=pms_task_doc_links.visible_task_doc_link_items(
            db,
            user=user,
            task_id=task_id,
        )
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
    workspace: Workspace = Depends(require_current_workspace),
) -> list[SpaceUserItem]:
    del current_user
    users = db.scalars(
        select(User)
        .join(WorkspaceUserBinding, WorkspaceUserBinding.user_id == User.id)
        .where(
            User.status == "active",
            WorkspaceUserBinding.workspace_id == workspace.id,
        )
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


@router.get("/view-preferences", response_model=PmsViewPreferencesResponse)
def get_view_preferences(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PmsViewPreferencesResponse:
    return PmsViewPreferencesResponse(
        task_list_group_by=pms_view_preferences.get_task_list_group_by(
            db,
            user=current_user,
            workspace=workspace,
        )
    )


@router.patch("/view-preferences", response_model=PmsViewPreferencesResponse)
def update_view_preferences(
    payload: UpdatePmsViewPreferencesRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PmsViewPreferencesResponse:
    return PmsViewPreferencesResponse(
        task_list_group_by=pms_view_preferences.update_task_list_group_by(
            db,
            user=current_user,
            workspace=workspace,
            group_by=payload.task_list_group_by,
        )
    )


@router.post("/spaces", response_model=SpaceItem, status_code=status.HTTP_201_CREATED)
def create_space(
    payload: SpaceCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SpaceItem:
    return SpaceItem.model_validate(
        pms_service.create_space(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=current_user.id,
                source="api.pms.create_space",
            ),
            user=current_user,
            name=payload.name,
            description=payload.description,
        )
    )


@router.patch("/spaces/{space_id}", response_model=SpaceItem)
def update_space(
    space_id: str,
    payload: SpaceUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SpaceItem:
    return SpaceItem.model_validate(
        pms_service.update_space(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=current_user.id,
                source="api.pms.update_space",
            ),
            user=current_user,
            space_id=space_id,
            name=payload.name,
            description=payload.description,
        )
    )


@router.delete("/spaces/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_space(
    space_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    pms_service.delete_space(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.delete_space",
        ),
        user=current_user,
        space_id=space_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/spaces/{space_id}/members", response_model=SpaceMemberListResponse)
def list_space_members(
    space_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SpaceMemberListResponse:
    return SpaceMemberListResponse.model_validate(
        pms_service.list_space_members(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=current_user.id,
                source="api.pms.list_space_members",
            ),
            user=current_user,
            space_id=space_id,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/spaces/{space_id}/members",
    response_model=SpaceMemberItem,
    status_code=status.HTTP_201_CREATED,
)
def add_space_member(
    space_id: str,
    payload: SpaceMemberCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SpaceMemberItem:
    return SpaceMemberItem.model_validate(
        pms_service.add_space_member(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=current_user.id,
                source="api.pms.add_space_member",
            ),
            user=current_user,
            space_id=space_id,
            target_user_id=payload.user_id,
            role=payload.role,
        )
    )


@router.patch("/spaces/{space_id}/members/{user_id}", response_model=SpaceMemberItem)
def update_space_member(
    space_id: str,
    user_id: str,
    payload: SpaceMemberRoleUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SpaceMemberItem:
    return SpaceMemberItem.model_validate(
        pms_service.update_space_member(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=current_user.id,
                source="api.pms.update_space_member",
            ),
            user=current_user,
            space_id=space_id,
            target_user_id=user_id,
            role=payload.role,
        )
    )


@router.delete("/spaces/{space_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_space_member(
    space_id: str,
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    pms_service.remove_space_member(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.remove_space_member",
        ),
        user=current_user,
        space_id=space_id,
        target_user_id=user_id,
    )
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
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskListItem:
    return TaskListItem.model_validate(
        pms_service.create_task_list(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=current_user.id,
                source="api.pms.create_task_list",
            ),
            user=current_user,
            name=payload.name,
            description=payload.description,
            key=payload.key,
            team_id=payload.team_id,
            folder_id=payload.folder_id,
        )
    )


@router.get("/lists/{list_id}", response_model=TaskListItem)
def get_task_list(
    list_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListItem:
    return TaskListItem.model_validate(
        pms_board_configuration.get_task_list(
            db,
            user=current_user,
            list_id=list_id,
        )
    )


@router.patch("/lists/{list_id}", response_model=TaskListItem)
def update_task_list(
    list_id: str,
    payload: TaskListUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskListItem:
    return TaskListItem.model_validate(
        pms_board_configuration.update_task_list(
            db,
            user=current_user,
            list_id=list_id,
            fields=pms_board_configuration.TaskListUpdateFields(
                provided_fields=set(payload.model_fields_set),
                name=payload.name,
                description=payload.description,
                status=payload.status,
                archived=payload.archived,
                folder_id=payload.folder_id,
                sort_order=payload.sort_order,
            ),
        )
    )


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_list(
    list_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    pms_board_configuration.delete_task_list(
        db,
        user=current_user,
        list_id=list_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/spaces/{space_id}/lists/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_space_lists(
    space_id: str,
    payload: TaskListReorderRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    pms_board_configuration.reorder_space_task_lists(
        db,
        user=current_user,
        space_id=space_id,
        items=[
            pms_board_configuration.TaskListReorderItem(
                id=item.id,
                folder_id=item.folder_id,
                sort_order=item.sort_order,
            )
            for item in payload.items
        ],
    )
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
    enqueue_milestone_task_recompute(db, milestone=milestone)
    db.commit()
    db.refresh(milestone)
    milestone = db.scalar(
        select(Milestone).options(selectinload(Milestone.tasks)).where(Milestone.id == milestone_id)
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


@router.post(
    "/lists/{list_id}/labels", response_model=LabelItem, status_code=status.HTTP_201_CREATED
)
def create_task_list_label(
    list_id: str,
    payload: LabelCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LabelItem:
    _ensure_list_owner(db, current_user, list_id)
    existing = db.scalar(
        select(Label).where(
            Label.list_id == list_id, func.lower(Label.name) == payload.name.strip().lower()
        )
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
    enqueue_label_task_recompute(db, label=label)
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
    affected_task_ids = collect_label_task_ids(db, label_id=label.id)
    enqueue_label_task_recompute(
        db,
        label=label,
        task_ids=affected_task_ids,
    )
    db.delete(label)
    db.commit()


@router.get("/lists/{list_id}/tasks", response_model=TaskItemsResponse)
def list_tasks(
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
) -> TaskItemsResponse:
    return pms_service.list_tasks(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.list_tasks",
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
    "/lists/{list_id}/tasks",
    response_model=TaskItem,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    list_id: str,
    payload: TaskCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskItem:
    return pms_service.create_task(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.create_task",
        ),
        user=current_user,
        list_id=list_id,
        title=payload.title,
        description=payload.description,
        description_blocks=payload.description_blocks,
        status=payload.status,
        priority=payload.priority,
        assignee_id=payload.assignee_id,
        assignee_ids=payload.assignee_ids,
        milestone_id=payload.milestone_id,
        parent_id=payload.parent_id,
        start_date=payload.start_date,
        due_date=payload.due_date,
        completed_date=payload.completed_date,
        recurrence_rule=payload.recurrence_rule,
        label_ids=payload.label_ids,
    )


@router.get("/tasks/assigned", response_model=TaskItemsResponse)
def list_assigned_tasks(
    limit: int | None = Query(default=10, ge=1, le=50),
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskItemsResponse:
    return pms_service.list_assigned_tasks(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.list_assigned_tasks",
        ),
        user=current_user,
        limit=limit,
        page=page,
        page_size=page_size,
    )


@router.get("/tasks/today-overdue", response_model=TaskItemsResponse)
def list_today_overdue_tasks(
    today: date = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskItemsResponse:
    return pms_service.list_today_overdue_tasks(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.list_today_overdue_tasks",
        ),
        user=current_user,
        today=today,
        page=page,
        page_size=page_size,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
def get_task(
    task_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskDetailResponse:
    return pms_service.get_task_detail(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.get_task",
        ),
        user=current_user,
        task_id=task_id,
    )


@router.patch("/tasks/{task_id}", response_model=TaskItem)
def update_task(
    task_id: str,
    payload: TaskUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskItem:
    return pms_service.update_task(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.update_task",
        ),
        user=current_user,
        task_id=task_id,
        provided_fields=set(payload.model_fields_set),
        title=payload.title,
        description=payload.description,
        description_blocks=payload.description_blocks,
        parent_id=payload.parent_id,
        status=payload.status,
        priority=payload.priority,
        assignee_id=payload.assignee_id,
        assignee_ids=payload.assignee_ids,
        milestone_id=payload.milestone_id,
        start_date=payload.start_date,
        due_date=payload.due_date,
        completed_date=payload.completed_date,
        board_position=payload.board_position,
        archived=payload.archived,
        recurrence_rule=payload.recurrence_rule,
        label_ids=payload.label_ids,
    )


@router.patch("/lists/{list_id}/tasks/reorder", response_model=TaskReorderResponse)
def reorder_task_list_tasks(
    list_id: str,
    payload: TaskReorderRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskReorderResponse:
    items = pms_service.reorder_task_list_tasks(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.reorder_tasks",
        ),
        user=current_user,
        list_id=list_id,
        updates=[
            pms_service.TaskReorderUpdate(
                task_id=item.task_id,
                board_position=item.board_position,
                parent_id=item.parent_id,
                parent_id_present="parent_id" in item.model_fields_set,
            )
            for item in payload.items
        ],
    )
    return TaskReorderResponse(updated_count=len(items), items=items)


@router.patch("/lists/{list_id}/tasks/bulk", response_model=BulkUpdateResponse)
def bulk_update_tasks(
    list_id: str,
    payload: BulkUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BulkUpdateResponse:
    task_list, _role = _ensure_list_editor(db, current_user, list_id)
    if payload.status is not None:
        pms_service._lock_task_list_order(db, list_id)
    task_map = {
        task.id: task
        for task in db.scalars(
            select(Task)
            .options(
                selectinload(Task.task_list),
                selectinload(Task.task_list).selectinload(TaskList.statuses),
                selectinload(Task.task_list).selectinload(TaskList.space_statuses),
                selectinload(Task.label_links).selectinload(TaskLabel.label),
                selectinload(Task.assignee),
                selectinload(Task.assignee_links).selectinload(TaskAssignee.user),
            )
            .where(Task.id.in_(payload.task_ids), Task.list_id == list_id)
            .order_by(Task.id)
            .with_for_update()
        )
    }
    ordered_tasks = [task_map[task_id] for task_id in payload.task_ids if task_id in task_map]
    if not ordered_tasks:
        raise localized_http_exception(status_code=404, code="pms.no_matching_tasks")

    if payload.delete:
        deleted_task_ids = pms_service.delete_loaded_tasks(db, ordered_tasks)
        return BulkUpdateResponse(updated_count=0, deleted_count=len(deleted_task_ids))

    updated = pms_service.bulk_update_loaded_tasks(
        db,
        task_list=task_list,
        tasks=ordered_tasks,
        actor=current_user,
        status_value=payload.status,
        priority=payload.priority,
        assignee_field_present="assignee_id" in payload.model_fields_set,
        assignee_id=payload.assignee_id,
        archived=payload.archived,
        add_label_ids=payload.add_label_ids,
        remove_label_ids=payload.remove_label_ids,
    )
    return BulkUpdateResponse(updated_count=updated, deleted_count=0)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> None:
    task, _project = _get_task_for_user(db, current_user, task_id, require_editor=True)
    pms_service.delete_loaded_tasks(db, [task])


@router.post(
    "/tasks/{task_id}/comments",
    response_model=TaskCommentItem,
    status_code=status.HTTP_201_CREATED,
)
def create_task_comment(
    task_id: str,
    payload: TaskCommentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> TaskCommentItem:
    return pms_service.add_task_comment(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.create_task_comment",
        ),
        user=current_user,
        task_id=task_id,
        body=payload.body,
        body_blocks=payload.body_blocks,
    )


@router.get("/tasks/{task_id}/activity-logs", response_model=ActivityLogListResponse)
def list_task_activity_logs(
    task_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ActivityLogListResponse:
    task, _ = _get_task_for_user(db, current_user, task_id)
    logs = list(
        db.scalars(
            select(TaskActivityLog)
            .options(selectinload(TaskActivityLog.actor))
            .where(TaskActivityLog.task_id == task.id, _visible_activity_log_filter())
            .order_by(TaskActivityLog.created_at.desc())
        )
    )
    reference_lookup = {task.id: _task_reference(task)}
    serialized = [_serialize_activity(log, reference_lookup) for log in logs]
    page_items, total = _paginate(serialized, page, page_size)
    return ActivityLogListResponse(items=page_items, total=total, page=page, page_size=page_size)


@router.get("/tasks/{task_id}/docs", response_model=TaskDocLinksResponse)
def list_task_docs(
    task_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskDocLinksResponse:
    _get_task_for_user(db, current_user, task_id)
    return _serialize_visible_task_doc_links(db, user=current_user, task_id=task_id)


@router.post(
    "/tasks/{task_id}/docs",
    response_model=TaskDocLinksResponse,
    status_code=status.HTTP_201_CREATED,
)
def attach_task_doc(
    task_id: str,
    payload: TaskDocAttachRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskDocLinksResponse:
    task, _task_list = _get_task_for_user(db, current_user, task_id, require_editor=True)
    pms_task_doc_links.attach_doc_to_task(
        db,
        user=current_user,
        task=task,
        doc_id=payload.doc_id,
    )
    return _serialize_visible_task_doc_links(db, user=current_user, task_id=task.id)


@router.delete("/tasks/{task_id}/docs/{doc_id}", response_model=TaskDocLinksResponse)
def detach_task_doc(
    task_id: str,
    doc_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskDocLinksResponse:
    task, _task_list = _get_task_for_user(db, current_user, task_id, require_editor=True)
    pms_task_doc_links.detach_doc_from_task(
        db,
        user=current_user,
        task=task,
        doc_id=doc_id,
    )
    return _serialize_visible_task_doc_links(db, user=current_user, task_id=task.id)


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    list_id: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DashboardSummaryResponse:
    task_lists = list(
        db.scalars(
            _active_accessible_task_lists_query(db, current_user).options(
                selectinload(TaskList.milestones).selectinload(Milestone.tasks),
                selectinload(TaskList.statuses),
                selectinload(TaskList.space_statuses),
                selectinload(TaskList.tasks).selectinload(Task.comments),
                selectinload(TaskList.tasks).selectinload(Task.assignee),
                selectinload(TaskList.tasks).selectinload(Task.reporter),
            )
        )
    )
    if list_id:
        task_lists = [task_list for task_list in task_lists if task_list.id == list_id]
    recent_logs = list(
        db.scalars(
            select(TaskActivityLog)
            .join(Task, Task.id == TaskActivityLog.task_id)
            .options(
                selectinload(TaskActivityLog.actor),
                selectinload(TaskActivityLog.task).selectinload(Task.task_list),
            )
            .where(
                Task.list_id.in_([task_list.id for task_list in task_lists] or ["__none__"]),
                _visible_activity_log_filter(),
            )
            .order_by(TaskActivityLog.created_at.desc())
            .limit(8)
        )
    )

    return DashboardSummaryResponse.model_validate(
        dashboard_summary_payload(
            task_lists=task_lists,
            recent_logs=recent_logs,
            current_user_id=current_user.id,
            today=date.today(),
        )
    )


@router.post(
    "/tasks/{task_id}/attachments",
    response_model=AttachmentItem,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    task_id: str,
    file: UploadFile,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> AttachmentItem:
    item = upload_task_attachment(
        db,
        workspace=current_workspace,
        user=current_user,
        task_id=task_id,
        upload=TaskAttachmentUpload(
            filename=file.filename,
            content_type=file.content_type,
            content=await file.read(),
        ),
    )
    return AttachmentItem(**asdict(item))


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RedirectResponse:
    url = get_task_attachment_download_url(
        db,
        user=current_user,
        attachment_id=attachment_id,
    )
    return RedirectResponse(url=url, status_code=302)


@public_router.get("/attachments/{attachment_id}/content")
def proxy_attachment_content(
    attachment_id: str,
    expires: int = Query(..., ge=1),
    signature: str = Query(..., min_length=1),
    disposition: TaskAttachmentDisposition = "attachment",
    db: Session = Depends(get_db_session),
) -> StreamingResponse:
    content = open_task_attachment_content(
        db,
        attachment_id=attachment_id,
        expires=expires,
        signature=signature,
        disposition=disposition,
    )
    return StreamingResponse(
        content.body,
        media_type=content.media_type,
        headers=content.headers,
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    delete_task_attachment(
        db,
        workspace=current_workspace,
        user=current_user,
        attachment_id=attachment_id,
    )
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
                action_url=normalize_pms_deep_link(n.action_url),
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
    count = (
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == current_user.id,
                Notification.is_read == False,  # noqa: E712
            )
        )
        or 0
    )
    return UnreadCountResponse(count=count)


@router.patch("/notifications/{notification_id}/read", response_model=NotificationItem)
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> NotificationItem:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == current_user.id
        )
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
        action_url=normalize_pms_deep_link(notification.action_url),
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


@router.post(
    "/tasks/{task_id}/checklist",
    response_model=ChecklistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_checklist_item(
    task_id: str,
    payload: ChecklistItemCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ChecklistItemResponse:
    item = pms_task_work_items.create_checklist_item(
        db,
        user=current_user,
        task_id=task_id,
        text=payload.text,
        sort_order=payload.sort_order,
    )
    return ChecklistItemResponse(**asdict(item))


@router.patch("/checklist/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_item(
    item_id: str,
    payload: ChecklistItemUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ChecklistItemResponse:
    item = pms_task_work_items.update_checklist_item(
        db,
        user=current_user,
        item_id=item_id,
        text=payload.text,
        completed=payload.completed,
        sort_order=payload.sort_order,
    )
    return ChecklistItemResponse(**asdict(item))


@router.delete("/checklist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    pms_task_work_items.delete_checklist_item(
        db,
        user=current_user,
        item_id=item_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/tasks/{task_id}/checklist/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_checklist(
    task_id: str,
    payload: ChecklistReorderRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    pms_task_work_items.reorder_checklist(
        db,
        user=current_user,
        task_id=task_id,
        item_ids=payload.item_ids,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Task List Statuses (Custom Workflow)
router.include_router(status_router)


# ── CSV Export ──────────────────────────────────────────────────────


@router.get("/lists/{list_id}/export")
def export_task_list_tasks(
    list_id: str,
    format: str = Query(default="csv"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    task_list, _ = _ensure_list_member(db, current_user, list_id)

    tasks = list(
        db.scalars(
            select(Task)
            .options(
                selectinload(Task.task_list),
                selectinload(Task.task_list).selectinload(TaskList.statuses),
                selectinload(Task.task_list).selectinload(TaskList.space_statuses),
                selectinload(Task.assignee),
                selectinload(Task.reporter),
                selectinload(Task.milestone),
                selectinload(Task.label_links).selectinload(TaskLabel.label),
                selectinload(Task.comments),
                selectinload(Task.checklist_items),
                selectinload(Task.subtasks),
            )
            .where(Task.list_id == list_id)
            .order_by(Task.task_number)
        )
    )

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Reference",
            "Title",
            "Status",
            "Priority",
            "Assignee",
            "Reporter",
            "Milestone",
            "Start Date",
            "Due Date",
            "Completed Date",
            "Labels",
            "Checklist Done/Total",
            "Comments",
            "Created",
            "Updated",
        ]
    )
    for task in tasks:
        ref = f"{task_list.key}-{task.task_number}"
        label_str = ", ".join(link.label.name for link in task.label_links)
        checklist_str = (
            f"{sum(1 for c in task.checklist_items if c.completed)}/{len(task.checklist_items)}"
            if task.checklist_items
            else ""
        )
        writer.writerow(
            [
                ref,
                task.title,
                task.status,
                task.priority,
                getattr(task.assignee, "full_name", ""),
                getattr(task.reporter, "full_name", ""),
                getattr(task.milestone, "title", ""),
                str(task.start_date or ""),
                str(task.due_date or ""),
                str(task.completed_date or ""),
                label_str,
                checklist_str,
                len(task.comments),
                task.created_at.isoformat(),
                task.updated_at.isoformat(),
            ]
        )

    content = buf.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{task_list.key}_tasks.csv"',
        },
    )


# ── Task Templates ──────────────────────────────────────────────────


@router.get("/lists/{list_id}/templates", response_model=TaskTemplateListResponse)
def list_templates(
    list_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskTemplateListResponse:
    templates = pms_task_list_customization.list_task_templates(
        db,
        user=current_user,
        list_id=list_id,
    )
    return TaskTemplateListResponse(items=[TaskTemplateItem(**asdict(t)) for t in templates])


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
    template = pms_task_list_customization.create_task_template(
        db,
        user=current_user,
        list_id=list_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        default_status=payload.default_status,
        default_priority=payload.default_priority,
        checklist_items=payload.checklist_items,
    )
    return TaskTemplateItem(**asdict(template))


@router.patch("/templates/{template_id}", response_model=TaskTemplateItem)
def update_template(
    template_id: str,
    payload: TaskTemplateUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> TaskTemplateItem:
    template = pms_task_list_customization.update_task_template(
        db,
        user=current_user,
        template_id=template_id,
        name=payload.name,
        description=payload.description,
        default_status=payload.default_status,
        default_priority=payload.default_priority,
        checklist_items=payload.checklist_items,
    )
    return TaskTemplateItem(**asdict(template))


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    pms_task_list_customization.delete_task_template(
        db,
        user=current_user,
        template_id=template_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Custom Fields ───────────────────────────────────────────────────


@router.get("/lists/{list_id}/custom-fields", response_model=CustomFieldListResponse)
def list_custom_fields(
    list_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CustomFieldListResponse:
    fields = pms_task_list_customization.list_custom_fields(
        db,
        user=current_user,
        list_id=list_id,
    )
    return CustomFieldListResponse(items=[CustomFieldItem(**asdict(f)) for f in fields])


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
    field = pms_task_list_customization.create_custom_field(
        db,
        user=current_user,
        list_id=list_id,
        name=payload.name.strip(),
        field_type=payload.field_type,
        options=payload.options,
        sort_order=payload.sort_order,
    )
    return CustomFieldItem(**asdict(field))


@router.delete("/custom-fields/{field_id}")
def delete_custom_field(
    field_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    pms_task_list_customization.delete_custom_field(
        db,
        user=current_user,
        field_id=field_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tasks/{task_id}/custom-field-values", response_model=list[CustomFieldValueItem])
def list_task_custom_field_values(
    task_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[CustomFieldValueItem]:
    values = pms_task_list_customization.list_task_custom_field_values(
        db,
        user=current_user,
        task_id=task_id,
    )
    return [CustomFieldValueItem(**asdict(v)) for v in values]


@router.put("/tasks/{task_id}/custom-field-values")
def set_task_custom_field_value(
    task_id: str,
    payload: SetCustomFieldValueRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CustomFieldValueItem:
    value = pms_task_list_customization.set_task_custom_field_value(
        db,
        user=current_user,
        task_id=task_id,
        field_id=payload.field_id,
        value=payload.value,
    )
    return CustomFieldValueItem(**asdict(value))


# ── Task Assignees (Multiple) ──────────────────────────────────────


class TaskAssigneeItem(BaseModel):
    user_id: str
    full_name: str


class TaskFollowerItem(BaseModel):
    user_id: str
    full_name: str


class SetTaskAssigneesRequest(BaseModel):
    user_ids: list[str] = Field(..., max_length=20)


class SetTaskFollowersRequest(BaseModel):
    user_ids: list[str] = Field(..., max_length=50)


def _validate_task_role_users(
    db: Session,
    task_list: TaskList,
    user_ids: list[str],
    *,
    invalid_member_code: str,
) -> list[User]:
    if not user_ids:
        return []
    if task_list.team_id is None:
        raise localized_http_exception(status_code=409, code="pms.task_list_space_missing")
    member_ids = _space_member_ids(db, task_list.team_id)
    users: list[User] = []
    seen_user_ids: set[str] = set()
    for user_id in user_ids:
        if user_id in seen_user_ids:
            continue
        seen_user_ids.add(user_id)
        if user_id not in member_ids:
            raise localized_http_exception(status_code=400, code=invalid_member_code)
        user = db.scalar(select(User).where(User.id == user_id))
        if user is None:
            raise localized_http_exception(status_code=404, code="auth.user_not_found")
        users.append(user)
    return users


@router.put("/tasks/{task_id}/assignees", response_model=list[TaskAssigneeItem])
def set_task_assignees(
    task_id: str,
    payload: SetTaskAssigneesRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> list[TaskAssigneeItem]:
    updated_task = pms_service.update_task(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.pms.set_task_assignees",
        ),
        user=current_user,
        task_id=task_id,
        provided_fields={"assignee_ids"},
        assignee_ids=payload.user_ids,
    )
    assignee_ids = updated_task.get("assignee_ids", [])
    assignee_names = updated_task.get("assignee_names", [])
    return [
        TaskAssigneeItem(
            user_id=user_id,
            full_name=assignee_names[index] if index < len(assignee_names) else user_id,
        )
        for index, user_id in enumerate(assignee_ids)
    ]


@router.put("/tasks/{task_id}/followers", response_model=list[TaskFollowerItem])
def set_task_followers(
    task_id: str,
    payload: SetTaskFollowersRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[TaskFollowerItem]:
    task, task_list = _get_task_for_user(db, current_user, task_id, require_editor=True)
    followers = _validate_task_role_users(
        db,
        task_list,
        payload.user_ids,
        invalid_member_code="pms.followers_task_list_members_required",
    )

    for link in list(task.follower_links):
        db.delete(link)
    db.flush()

    result: list[TaskFollowerItem] = []
    for follower in followers:
        db.add(TaskFollower(id=new_id(), task_id=task_id, user_id=follower.id))
        result.append(TaskFollowerItem(user_id=follower.id, full_name=follower.full_name))

    _log_task_activity(
        db,
        task.id,
        current_user.id,
        "updated",
        f"{current_user.full_name} updated followers for {_task_reference(task)}.",
        field_name="follower_ids",
        to_value=",".join(follower.id for follower in followers) if followers else None,
    )
    enqueue_task_rag_sync(
        db,
        task=task,
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
                id=f.id,
                team_id=f.team_id,
                name=f.name,
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
        select(TeamMember.id).where(
            TeamMember.team_id == resolved_team_id, TeamMember.user_id == current_user.id
        )
    ):
        db.add(
            TeamMember(id=new_id(), team_id=resolved_team_id, user_id=current_user.id, role="owner")
        )
    _create_default_statuses(db, default_task_list.id)
    _create_default_labels(db, default_task_list.id)

    db.commit()
    db.refresh(folder)
    return FolderItem(
        id=folder.id,
        team_id=folder.team_id,
        name=folder.name,
        sort_order=folder.sort_order,
        list_count=1,
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
    cnt = (
        db.scalar(select(func.count()).select_from(TaskList).where(TaskList.folder_id == folder_id))
        or 0
    )
    return FolderItem(
        id=folder.id,
        team_id=folder.team_id,
        name=folder.name,
        sort_order=folder.sort_order,
        list_count=cnt,
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
    task_lists = list(db.scalars(select(TaskList).where(TaskList.folder_id == folder_id)))
    for task_list in task_lists:
        _ensure_task_list_active(task_list)
    # Unlink task lists from this folder without deleting them.
    for task_list in task_lists:
        task_list.folder_id = None
    db.delete(folder)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
