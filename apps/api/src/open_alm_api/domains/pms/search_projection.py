from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_alm_api.domains.auth.models import Team, Workspace
from open_alm_api.domains.pms.app_catalog import PMS_WORKSPACE_APP
from open_alm_api.domains.pms.links import pms_task_path
from open_alm_api.domains.pms.models import (
    Task,
    TaskAssignee,
    TaskComment,
    TaskFollower,
    TaskLabel,
    TaskList,
    TaskListStatus,
    TaskUserAccess,
)
from open_alm_api.domains.retrieval.partition_adapter_ids import (
    PMS_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_alm_api.domains.search.index_document import (
    build_search_document,
    extract_blocks_text,
    search_person,
    trim_search_text,
)
from open_alm_api.domains.search.entity_adapter_registry import (
    SearchEntityAdapter,
    SearchIndexLifecycleHooks,
)
from open_alm_api.domains.search.schemas import SearchEntityType
from open_alm_api.domains.source_access.resource_types import PMS_TASK_RESOURCE_TYPE


DEFAULT_PMS_STATUS_LABELS = {
    "todo": "Todo",
    "in_progress": "In Progress",
    "done": "Done",
    "canceled": "Canceled",
}


def load_workspace_pms_task_search_documents(
    db: Session, *, workspace: Workspace
) -> list[dict[str, Any]]:
    tasks = db.scalars(
        select(Task)
        .options(
            selectinload(Task.task_list).selectinload(TaskList.statuses),
            selectinload(Task.assignee),
            selectinload(Task.assignee_links).selectinload(TaskAssignee.user),
            selectinload(Task.follower_links).selectinload(TaskFollower.user),
            selectinload(Task.reporter),
            selectinload(Task.comments).selectinload(TaskComment.author),
            selectinload(Task.label_links).selectinload(TaskLabel.label),
            selectinload(Task.user_access_grants),
        )
        .join(TaskList, Task.list_id == TaskList.id)
        .join(Team, TaskList.team_id == Team.id)
        .where(
            Team.workspace_id == workspace.id,
            Task.archived.is_(False),
            TaskList.archived.is_(False),
        )
    ).all()
    return [_pms_task_row(workspace=workspace, task=task) for task in tasks]


def load_pms_task_search_document(db: Session, *, task_id: str) -> dict[str, Any] | None:
    task = db.scalar(
        select(Task)
        .options(
            selectinload(Task.task_list).selectinload(TaskList.statuses),
            selectinload(Task.assignee),
            selectinload(Task.assignee_links).selectinload(TaskAssignee.user),
            selectinload(Task.follower_links).selectinload(TaskFollower.user),
            selectinload(Task.reporter),
            selectinload(Task.comments).selectinload(TaskComment.author),
            selectinload(Task.label_links).selectinload(TaskLabel.label),
            selectinload(Task.user_access_grants),
        )
        .join(TaskList, Task.list_id == TaskList.id)
        .join(Team, TaskList.team_id == Team.id)
        .where(
            Task.id == task_id,
            Task.archived.is_(False),
            TaskList.archived.is_(False),
        )
    )
    if task is None or task.task_list is None or task.task_list.team_id is None:
        return None
    workspace = db.scalar(
        select(Workspace)
        .join(Team, Team.workspace_id == Workspace.id)
        .where(Team.id == task.task_list.team_id, Workspace.active.is_(True))
    )
    if workspace is None:
        return None
    return _pms_task_row(workspace=workspace, task=task)


def load_pms_task_search_document_for_entity(
    db: Session,
    *,
    entity_type: SearchEntityType,
    entity_id: str,
) -> dict[str, Any] | None:
    if entity_type != SearchEntityType.PMS_TASK:
        return None
    return load_pms_task_search_document(db, task_id=entity_id)


def _pms_task_row(*, workspace: Workspace, task: Task) -> dict[str, Any]:
    task_list = task.task_list
    status_label = _pms_status_label(task.status, task_list.statuses if task_list else [])
    label_names = [link.label.name for link in task.label_links if link.label is not None]
    body = "\n".join(
        part
        for part in [
            task.description,
            extract_blocks_text(task.description_blocks),
            " ".join(comment.body for comment in task.comments),
            " ".join(label_names),
        ]
        if part
    )
    targets = [
        {
            "type": "list",
            "id": task.list_id,
            "label": getattr(task_list, "name", None) or task.list_id,
        }
    ]
    people = [search_person("owner", task.reporter_id, getattr(task.reporter, "full_name", None))]
    assignee_ids = [link.user_id for link in task.assignee_links] or (
        [task.assignee_id] if task.assignee_id else []
    )
    for link in task.assignee_links:
        people.append(
            search_person("assignee", link.user_id, getattr(link.user, "full_name", None))
        )
    if not task.assignee_links and task.assignee_id:
        people.append(
            search_person("assignee", task.assignee_id, getattr(task.assignee, "full_name", None))
        )
    follower_ids = [link.user_id for link in task.follower_links]
    for link in task.follower_links:
        people.append(
            search_person("follower", link.user_id, getattr(link.user, "full_name", None))
        )
    return build_search_document(
        workspace_id=workspace.id,
        entity_type=SearchEntityType.PMS_TASK,
        entity_id=task.id,
        title=task.title,
        summary=trim_search_text(task.description or " ".join(label_names), 240),
        body=body,
        keywords=" ".join(
            [
                task.status,
                task.priority,
                status_label,
                getattr(task_list, "name", "") or "",
                *label_names,
            ]
        ),
        status=task.status,
        status_label=status_label,
        visibility="workspace",
        people=people,
        targets=targets,
        owner_user_id=task.reporter_id,
        team_ids=[task_list.team_id] if task_list and task_list.team_id else [],
        participant_user_ids=[*assignee_ids, *follower_ids],
        shared_user_ids=[],
        granted_user_ids=_active_task_grant_user_ids(task.user_access_grants),
        date_markers={
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "due_date": task.due_date.isoformat() if task.due_date else None,
        },
        deep_link=pms_task_path(workspace, task),
        metadata={
            "list_id": task.list_id,
            "task_number": task.task_number,
            "priority": task.priority,
        },
        source_updated_at=task.updated_at,
    )


def _active_task_grant_user_ids(grants: list[TaskUserAccess]) -> list[str]:
    now = datetime.now(UTC).replace(tzinfo=None)
    return [
        grant.user_id
        for grant in grants
        if grant.revoked_at is None and (grant.expires_at is None or grant.expires_at > now)
    ]


def _pms_status_label(slug: str, statuses: list[TaskListStatus]) -> str:
    for task_status in statuses:
        if task_status.slug == slug:
            return task_status.name
    return DEFAULT_PMS_STATUS_LABELS.get(slug, _labelize(slug))


def _labelize(value: str) -> str:
    return value.replace("_", " ").title()


PMS_WORKSPACE_KEYWORD_SEARCH_ADAPTER = SearchEntityAdapter(
    owner_app=PMS_WORKSPACE_APP,
    entity_type=SearchEntityType.PMS_TASK.value,
    resource_type=PMS_TASK_RESOURCE_TYPE,
    label="PMS",
    label_key="ai.search.entityPms",
    workspace_loader=load_workspace_pms_task_search_documents,
    document_loader=load_pms_task_search_document_for_entity,
    partition_adapter_id=PMS_RETRIEVAL_PARTITION_ADAPTER_ID,
    index_hooks=SearchIndexLifecycleHooks(
        create=("pms.enqueue_task_search_index",),
        update=(
            "pms.enqueue_task_search_index",
            "pms.enqueue_task_search_index_by_id",
            "pms.enqueue_task_list_task_search_recompute",
            "pms.enqueue_label_task_search_recompute",
            "pms.enqueue_task_list_status_task_search_recompute",
        ),
        delete=("pms.enqueue_task_search_index",),
    ),
    date_fields=("due_date",),
    person_roles=("owner", "assignee"),
    sort_fields=("due_date",),
)


__all__ = [
    "PMS_WORKSPACE_KEYWORD_SEARCH_ADAPTER",
    "load_pms_task_search_document",
    "load_pms_task_search_document_for_entity",
    "load_workspace_pms_task_search_documents",
]
