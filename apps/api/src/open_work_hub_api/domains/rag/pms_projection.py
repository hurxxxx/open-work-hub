from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.domains.auth.models import Team, Workspace
from open_work_hub_api.domains.pms.models import (
    Task,
    TaskAssignee,
    TaskComment,
    TaskFollower,
    TaskLabel,
    TaskUserAccess,
)
from open_work_hub_api.domains.rag.contracts import RagProjection
from open_work_hub_api.domains.rag.projection_builders import build_text_projection
from open_work_hub_api.domains.source_access.resource_types import PMS_TASK_RESOURCE_TYPE


PMS_TASK_SOURCE_KIND = "pms_task"


def load_task_projection(
    db: Session,
    *,
    task_id: str,
) -> RagProjection | None:
    task = db.scalar(
        select(Task)
        .options(
            selectinload(Task.task_list),
            selectinload(Task.milestone),
            selectinload(Task.assignee),
            selectinload(Task.reporter),
            selectinload(Task.assignee_links).selectinload(TaskAssignee.user),
            selectinload(Task.follower_links).selectinload(TaskFollower.user),
            selectinload(Task.comments).selectinload(TaskComment.author),
            selectinload(Task.label_links).selectinload(TaskLabel.label),
            selectinload(Task.user_access_grants).selectinload(TaskUserAccess.user),
        )
        .where(Task.id == task_id)
    )
    if task is None:
        return None
    task_list = task.task_list
    if task.archived or task_list is None or task_list.archived or task_list.team_id is None:
        return None
    team = db.scalar(
        select(Team).where(
            Team.id == task_list.team_id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
        )
    )
    if team is None:
        return None
    return build_task_projection(task, team=team)


def build_task_projection(task: Task, *, team: Team) -> RagProjection:
    comments_text = "\n\n".join(
        _comment_text(comment) for comment in task.comments if _comment_text(comment)
    )
    label_names = [link.label.name for link in task.label_links if link.label is not None]
    assignee_names = [link.user.full_name for link in task.assignee_links if link.user is not None]
    assignee_ids = [link.user_id for link in task.assignee_links]
    if not assignee_ids and task.assignee_id:
        assignee_ids = [task.assignee_id]
        assignee_names = [getattr(task.assignee, "full_name", None) or task.assignee_id]
    follower_names = [link.user.full_name for link in task.follower_links if link.user is not None]
    text_sections = [
        task.title.strip(),
        task.description.strip(),
        _extract_blocks_text(task.description_blocks),
        comments_text,
        " ".join(label_names),
        " ".join(assignee_names),
        " ".join(follower_names),
    ]

    return build_text_projection(
        workspace_id=team.workspace_id,
        resource_type=PMS_TASK_RESOURCE_TYPE,
        resource_id=task.id,
        source_kind=PMS_TASK_SOURCE_KIND,
        title=task.title,
        summary=_build_summary(task, label_names=label_names),
        text_sections=text_sections,
        owner_label=getattr(task.reporter, "full_name", None),
        visibility_refs=_build_visibility_refs(task, team=team),
        metadata={
            "team_id": team.id,
            "list_id": task.list_id,
            "task_number": task.task_number,
            "status": task.status,
            "priority": task.priority,
            "archived": task.archived,
            "milestone_title": getattr(task.milestone, "title", None),
            "assignee_id": task.assignee_id,
            "assignee_name": getattr(task.assignee, "full_name", None),
            "assignee_ids": assignee_ids,
            "assignee_names": assignee_names,
            "follower_ids": [link.user_id for link in task.follower_links],
            "follower_names": follower_names,
            "reporter_id": task.reporter_id,
            "list_name": getattr(task.task_list, "name", None),
            "list_key": getattr(task.task_list, "key", None),
            "label_names": label_names,
        },
    )


def _build_summary(task: Task, *, label_names: list[str]) -> str | None:
    parts = [
        task.description.strip(),
        f"status:{task.status}",
        f"priority:{task.priority}",
        getattr(task.milestone, "title", None),
        ",".join(label_names) if label_names else None,
    ]
    summary = " | ".join(part for part in parts if part)
    return summary or task.title.strip() or None


def _build_visibility_refs(task: Task, *, team: Team) -> list[str]:
    refs = {
        f"workspace:{team.workspace_id}",
        f"team:{team.id}",
        f"list:{task.list_id}",
    }
    for grant in task.user_access_grants:
        if grant.revoked_at is not None:
            continue
        refs.add(f"task_grant:{grant.user_id}")
        if grant.granted_by_meeting_id:
            refs.add(f"meeting_source:{grant.granted_by_meeting_id}")
    return sorted(refs)


def _comment_text(comment: TaskComment) -> str:
    parts = [
        getattr(comment.author, "full_name", None),
        comment.body.strip(),
        _extract_blocks_text(comment.body_blocks),
    ]
    return " ".join(part for part in parts if part).strip()


def _extract_blocks_text(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""

    parts: list[str] = []
    for block in blocks:
        _collect_text_parts(block, parts)
    return " ".join(part for part in parts if part).strip()


def _collect_text_parts(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        if normalized:
            parts.append(normalized)
        return

    if isinstance(value, list):
        for item in value:
            _collect_text_parts(item, parts)
        return

    if not isinstance(value, dict):
        return

    if isinstance(value.get("text"), str):
        normalized = " ".join(value["text"].split()).strip()
        if normalized:
            parts.append(normalized)

    for key in ("content", "children"):
        nested = value.get(key)
        if nested is not None:
            _collect_text_parts(nested, parts)
