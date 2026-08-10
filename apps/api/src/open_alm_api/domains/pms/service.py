from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from collections.abc import Sequence
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, status
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.principal import CallerPrincipal
from open_alm_api.core.settings import get_settings
from open_alm_api.core.storage import get_minio_client
from open_alm_api.domains.auth.access import (
    bind_current_workspace,
    get_or_create_default_pms_space,
    has_system_role,
    resolve_workspace_enabled_app_ids,
    resolve_workspaces,
    slugify,
)
from open_alm_api.domains.auth.models import Team, TeamMember, User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.media.service import cleanup_media_for_resource, sync_embedded_media
from open_alm_api.domains.pms.attachments import serialize_task_attachment
from open_alm_api.domains.pms.app_catalog import PMS_WORKSPACE_APP
from open_alm_api.domains.pms.access import (
    _active_accessible_task_lists_query,
    _accessible_task_lists_query,
    _ensure_space_access,
    _ensure_space_admin_change_allowed,
    _ensure_space_editor,
    _ensure_space_manager,
    _ensure_space_owner_survives,
    _ensure_list_editor,
    _ensure_list_member,
    _ensure_task_readable,
    _get_space_membership,
    _load_active_space,
    _load_space_members,
    resolve_pms_space_role,
    _space_member_ids,
    _space_query_for_user,
    _validate_space_member_user,
)
from open_alm_api.domains.pms.rag_sync import (
    enqueue_task_list_task_recompute,
    enqueue_task_rag_sync,
)
from open_alm_api.domains.pms.links import pms_task_path
from open_alm_api.domains.pms.models import (
    Attachment,
    Folder,
    Label,
    Task,
    TaskActivityLog,
    TaskAssignee,
    TaskComment,
    TaskFollower,
    TaskLabel,
    TaskDocLink,
    Notification,
    SpaceStatus,
    TaskList,
    TaskListStatus,
)
from open_alm_api.domains.pms.projections import (
    serialize_task_summary as _serialize_task_summary,
    task_assignee_ids as _task_assignee_ids,
    task_follower_ids as _task_follower_ids,
    task_reference as _task_reference,
)
from open_alm_api.domains.pms.status_lifecycle import (
    create_default_space_statuses as _create_default_space_statuses,
    ensure_space_statuses as _ensure_space_statuses,
)
from open_alm_api.domains.rag.contracts import RagSyncOperation
from open_alm_api.domains.retrieval.partitioning import assign_default_partition
from open_alm_api.domains.pms.task_update_plan import (
    effective_task_update_fields,
    plan_task_scalar_updates,
)
from open_alm_api.domains.pms.workflow import (
    TASK_STATUS_LABELS,
    calculate_progress,
    is_closed_status,
    is_completion_status,
    is_overdue_exempt_status,
    normalize_status_category,
    normalize_task_status,
    status_category,
    status_definitions,
    status_label,
)


def _normalize_task_status(status_value: str) -> str:
    return normalize_task_status(status_value)


def _normalize_status_category(category: str) -> str:
    return normalize_status_category(category)


def _status_definitions(task_list: TaskList | None) -> list[TaskListStatus | SpaceStatus]:
    return status_definitions(task_list)


def _status_label(status_value: str, task_list: TaskList | None = None) -> str:
    return status_label(status_value, task_list)


def _status_category(status_value: str, task_list: TaskList | None = None) -> str | None:
    return status_category(status_value, task_list)


def _bind_workspace_context(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
) -> None:
    bind_current_workspace(db, workspace)
    if principal.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="pms.principal_workspace_mismatch",
        )
    if principal.kind == "user" and principal.user_id not in {None, user.id}:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="pms.principal_user_mismatch",
        )


def _require_user_write_principal(principal: CallerPrincipal) -> None:
    if principal.kind != "user":
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="pms.write_user_principal_required",
        )


@dataclass(frozen=True)
class TaskReorderUpdate:
    task_id: str
    board_position: int
    parent_id: str | None = None
    parent_id_present: bool = False


def _stable_replay_id(approved_call_id: str, suffix: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pms:{approved_call_id}:{suffix}"))


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _paginate[T](items: list[T], page: int, page_size: int) -> tuple[list[T], int]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total


def _task_assignee_filter(user_id: str) -> Any:
    return or_(
        Task.assignee_id == user_id,
        exists().where(TaskAssignee.task_id == Task.id, TaskAssignee.user_id == user_id),
    )


def _task_label_filter(label_id: str) -> Any:
    return exists().where(TaskLabel.task_id == Task.id, TaskLabel.label_id == label_id)


def _ordered_task_statement(statement: Any, sort_by: str, sort_dir: str) -> Any:
    descending = sort_dir == "desc"
    if sort_by == "priority":
        priority_order = case(
            (Task.priority == "critical", 3),
            (Task.priority == "high", 2),
            (Task.priority == "medium", 1),
            (Task.priority == "low", 0),
            else_=1,
        )
        order_columns = (priority_order, Task.task_number)
    elif sort_by in {"completed_date", "due_date", "start_date"}:
        date_column = getattr(Task, sort_by)
        date_order = (
            date_column.desc().nulls_last() if descending else date_column.asc().nulls_last()
        )
        return statement.order_by(
            date_order,
            Task.task_number.desc() if descending else Task.task_number,
        )
    elif sort_by == "created_at":
        order_columns = (Task.created_at, Task.task_number)
    elif sort_by == "updated_at":
        order_columns = (Task.updated_at, Task.task_number)
    else:
        order_columns = (Task.board_position, Task.task_number)
    if descending:
        return statement.order_by(*(column.desc() for column in order_columns))
    return statement.order_by(*order_columns)


def _count_task_statement(db: Session, statement: Any) -> int:
    count_statement = select(func.count()).select_from(
        statement.with_only_columns(Task.id).order_by(None).subquery()
    )
    return int(db.scalar(count_statement) or 0)


def _serialize_space(team: Team, current_user_role: str | None) -> dict[str, Any]:
    return {
        "id": team.id,
        "workspace_id": team.workspace_id,
        "workspace_key": team.workspace.key,
        "key": team.key,
        "name": team.name,
        "description": team.description,
        "member_count": len(team.members),
        "current_user_role": current_user_role,
        "created_at": team.created_at,
        "updated_at": team.updated_at,
    }


def _serialize_space_member(db: Session, member: TeamMember) -> dict[str, Any]:
    return {
        "user_id": member.user_id,
        "email": member.user.email,
        "full_name": member.user.full_name,
        "is_admin": has_system_role(db, member.user, "platform_admin"),
        "role": member.role,
        "joined_at": member.created_at,
    }


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


def _auto_key_from_name(name: str) -> str:
    import re as _re
    import unicodedata as _ud

    cleaned = _ud.normalize("NFKD", name).encode("ascii", "ignore").decode()
    cleaned = _re.sub(r"[^A-Za-z0-9\\s]", "", cleaned).strip()
    if cleaned:
        words = cleaned.upper().split()
        key = "".join(word[0] for word in words if word)[:6]
        if len(key) >= 2:
            return key
        return cleaned[:6].upper()
    return "LS"


def _unique_key(db: Session, base_name: str) -> str:
    resolved = _auto_key_from_name(base_name)
    base = resolved
    counter = 1
    while db.scalar(select(TaskList).where(func.lower(TaskList.key) == resolved.lower())):
        resolved = f"{base}{counter}"
        counter += 1
    return resolved


def _validate_folder_membership(db: Session, team_id: str, folder_id: str | None) -> None:
    if folder_id is None:
        return

    folder = db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="pms.folder_not_found"
        )
    if folder.team_id != team_id:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST, code="pms.folder_same_space_required"
        )


def _create_default_labels(db: Session, list_id: str) -> None:
    for name, color in [
        ("blocked", "#b45309"),
        ("customer", "#1d4ed8"),
        ("qa", "#0f766e"),
    ]:
        db.add(Label(id=new_id(), list_id=list_id, name=name, color=color))


def _serialize_task(task: Task) -> dict[str, Any]:
    return _serialize_task_summary(task)


def _is_closed_status(status_value: str, task_list: TaskList | None = None) -> bool:
    return is_closed_status(status_value, task_list)


def _is_overdue_exempt_status(status_value: str, task_list: TaskList | None = None) -> bool:
    return is_overdue_exempt_status(status_value, task_list)


def _calculate_progress(tasks: list[Task], task_list: TaskList | None = None) -> float:
    return calculate_progress(tasks, task_list)


def _task_list_role(
    db: Session, task_list: TaskList, user: User, team_lookup: dict[str, Team]
) -> str:
    if task_list.team_id is None:
        return "viewer"
    team = team_lookup.get(task_list.team_id)
    if team is None:
        return "viewer"
    return resolve_pms_space_role(db, user, team) or "viewer"


def _serialize_task_list(
    task_list: TaskList,
    role: str,
    team_name: str | None = None,
    member_count: int | None = None,
) -> dict[str, Any]:
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
    return {
        "id": task_list.id,
        "key": task_list.key,
        "name": task_list.name,
        "description": task_list.description,
        "status": task_list.status,
        "status_mode": task_list.status_mode,
        "archived": task_list.archived,
        "team_id": task_list.team_id,
        "team_name": team_name,
        "folder_id": task_list.folder_id,
        "folder_name": getattr(task_list.folder, "name", None) if task_list.folder_id else None,
        "sort_order": task_list.sort_order,
        "role": role,
        "progress": _calculate_progress(task_list.tasks, task_list),
        "member_count": member_count if member_count is not None else 0,
        "milestone_count": len(task_list.milestones),
        "task_count": len(task_list.tasks),
        "overdue_task_count": overdue_task_count,
        "created_at": task_list.created_at,
        "updated_at": task_list.updated_at,
    }


def _serialize_comment_item(comment: TaskComment) -> dict[str, Any]:
    return {
        "id": comment.id,
        "task_id": comment.task_id,
        "author_id": comment.author_id,
        "author_name": comment.author.full_name,
        "body": comment.body,
        "body_blocks": comment.body_blocks,
        "created_at": comment.created_at,
    }


def _serialize_comment(comment: TaskComment) -> dict[str, Any]:
    return _serialize_comment_item(comment)


def _serialize_task_doc_link(link: TaskDocLink) -> dict[str, Any]:
    doc = link.doc
    return {
        "id": link.id,
        "task_id": link.task_id,
        "doc_id": link.doc_id,
        "doc_title": doc.title if doc is not None else "",
        "doc_type": doc.doc_type if doc is not None else "general",
        "source_app": doc.source_app if doc is not None else "docs",
        "source_kind": doc.source_kind if doc is not None else "manual",
        "updated_at": doc.updated_at if doc is not None else link.created_at,
        "created_by_id": link.created_by_id,
        "created_at": link.created_at,
    }


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
    stable_key: str | None = None,
) -> None:
    if stable_key is not None and db.get(TaskActivityLog, stable_key) is not None:
        return
    db.add(
        TaskActivityLog(
            id=stable_key or new_id(),
            task_id=task_id,
            actor_id=actor_id,
            action=action,
            field_name=field_name,
            from_value=from_value,
            to_value=to_value,
            message=message,
        )
    )


def _set_missing_task_completed_date(
    db: Session,
    *,
    task: Task,
    actor: User,
    task_list: TaskList | None,
    message: str,
    stable_key: str | None = None,
) -> bool:
    if task.completed_date is not None or not is_completion_status(task.status, task_list):
        return False
    task.completed_date = _utcnow().date()
    _log_task_activity(
        db,
        task.id,
        actor.id,
        "updated",
        message,
        field_name="completed_date",
        from_value=None,
        to_value=task.completed_date.isoformat(),
        stable_key=stable_key,
    )
    return True


def _create_notification(
    db: Session,
    user_id: str,
    ntype: str,
    title: str,
    body: str,
    *,
    reference_type: str = "task",
    reference_id: str | None = None,
    action_url: str | None = None,
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
            action_url=action_url,
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
                props_value = content_item.get("props", {})
                attrs_value = content_item.get("attrs", {})
                props = props_value if isinstance(props_value, dict) else {}
                attrs = attrs_value if isinstance(attrs_value, dict) else {}
                user_id = (
                    props.get("userId")
                    or props.get("user_id")
                    or attrs.get("id")
                    or attrs.get("userId")
                    or attrs.get("user_id")
                )
                if user_id:
                    out.add(user_id)
            text = content_item.get("text", "")
            if text:
                out.update(re.findall(r"@([0-9a-f-]{36})", text))
        for child in block.get("children", []):
            if isinstance(child, dict):
                _extract_mentions_from_blocks([child], out)


def _task_action_url(workspace: Workspace, task: Task) -> str:
    return pms_task_path(workspace, task)


def _task_notification_label(task: Task) -> str:
    return task.title.strip() or _task_reference(task)


def _task_notification_label_with_reference(task: Task) -> str:
    label = _task_notification_label(task)
    ref = _task_reference(task)
    if not ref or ref == label or ref in label:
        return label
    return f"{label} ({ref})"


def _next_task_number(db: Session, list_id: str) -> int:
    current = db.scalar(select(func.max(Task.task_number)).where(Task.list_id == list_id))
    return int(current or 0) + 1


def _next_task_board_position(
    db: Session,
    list_id: str,
    parent_id: str | None = None,
) -> int:
    filters = [Task.list_id == list_id]
    filters.append(Task.parent_id.is_(None) if parent_id is None else Task.parent_id == parent_id)
    current = db.scalar(select(func.max(Task.board_position)).where(*filters))
    return int(current or 0) + 1


def _lock_task_list_order(db: Session, list_id: str) -> None:
    db.execute(select(TaskList.id).where(TaskList.id == list_id).with_for_update())


def _place_unlinked_task_after_former_parent(
    db: Session,
    *,
    task: Task,
    former_parent_id: str,
) -> None:
    root_siblings = list(
        db.scalars(
            select(Task)
            .where(
                Task.list_id == task.list_id,
                Task.parent_id.is_(None),
                Task.id != task.id,
            )
            .order_by(Task.board_position, Task.task_number)
            .with_for_update()
        )
    )
    former_parent_index = next(
        (index for index, sibling in enumerate(root_siblings) if sibling.id == former_parent_id),
        None,
    )
    insert_index = (
        former_parent_index + 1 if former_parent_index is not None else len(root_siblings)
    )
    reordered_roots = [
        *root_siblings[:insert_index],
        task,
        *root_siblings[insert_index:],
    ]
    for index, sibling in enumerate(reordered_roots, start=1):
        next_position = index * 1000
        if sibling.board_position != next_position:
            sibling.board_position = next_position


def _task_notification_user_ids(task: Task) -> set[str]:
    return {*_task_assignee_ids(task), *_task_follower_ids(task), task.reporter_id}


def _validate_task_assignee(db: Session, task_list: TaskList, assignee_id: str | None) -> None:
    if assignee_id is None:
        return
    if task_list.team_id is None or assignee_id not in _space_member_ids(db, task_list.team_id):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="pms.assignee_task_list_member_required",
        )


def _validate_task_assignees(
    db: Session,
    task_list: TaskList,
    assignee_ids: list[str],
) -> list[User]:
    if not assignee_ids:
        return []
    if task_list.team_id is None:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="pms.task_list_space_missing",
        )

    member_ids = _space_member_ids(db, task_list.team_id)
    validated_users: list[User] = []
    seen_user_ids: set[str] = set()
    for assignee_id in assignee_ids:
        if assignee_id in seen_user_ids:
            continue
        seen_user_ids.add(assignee_id)
        if assignee_id not in member_ids:
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="pms.assignees_task_list_members_required",
            )
        assignee = db.scalar(select(User).where(User.id == assignee_id))
        if assignee is None:
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND, code="auth.user_not_found"
            )
        validated_users.append(assignee)
    return validated_users


def _validate_milestone(task_list: TaskList, milestone_id: str | None) -> None:
    if milestone_id is None:
        return
    if milestone_id not in {milestone.id for milestone in task_list.milestones}:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST, code="pms.milestone_wrong_list"
        )


def _validate_parent_task(
    db: Session,
    task_list: TaskList,
    parent_id: str | None,
    *,
    task_id: str | None = None,
) -> None:
    if parent_id is None:
        return

    parent = db.scalar(select(Task).where(Task.id == parent_id))
    if parent is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="pms.parent_task_not_found"
        )
    if parent.list_id != task_list.id:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="pms.parent_task_same_list_required",
        )
    if task_id is not None and parent.id == task_id:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="pms.task_cannot_be_own_parent",
        )

    visited: set[str] = set()
    ancestor: Task | None = parent
    while ancestor is not None:
        if ancestor.id in visited:
            raise localized_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                code="pms.task_parent_cycle",
            )
        visited.add(ancestor.id)
        if task_id is not None and ancestor.parent_id == task_id:
            raise localized_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                code="pms.task_parent_cycle",
            )
        if ancestor.parent_id is None:
            break
        ancestor = db.scalar(select(Task).where(Task.id == ancestor.parent_id))


def _set_task_labels(db: Session, task: Task, label_ids: list[str], task_list: TaskList) -> None:
    if not label_ids:
        task.label_links.clear()
        return

    allowed_labels = {label.id: label for label in task_list.labels}
    if any(label_id not in allowed_labels for label_id in label_ids):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="pms.labels_invalid_for_list",
        )

    existing_links = {link.label_id: link for link in task.label_links}
    task.label_links.clear()
    seen_label_ids: set[str] = set()
    for label_id in label_ids:
        if label_id in seen_label_ids:
            continue
        seen_label_ids.add(label_id)
        task.label_links.append(
            existing_links.get(label_id) or TaskLabel(id=new_id(), label_id=label_id)
        )


def _set_task_assignees(task: Task, assignees: list[User]) -> None:
    existing_links = {link.user_id: link for link in task.assignee_links}
    task.assignee_links.clear()
    for assignee in assignees:
        link = existing_links.get(assignee.id)
        if link is None:
            link = TaskAssignee(id=new_id(), user_id=assignee.id, user=assignee)
        else:
            link.user = assignee
        task.assignee_links.append(link)
    primary_assignee = assignees[0] if assignees else None
    task.assignee_id = primary_assignee.id if primary_assignee is not None else None
    task.assignee = primary_assignee


def _task_summary_load_options(*, include_doc_links: bool = False) -> tuple[Any, ...]:
    options: list[Any] = [
        selectinload(Task.task_list),
        selectinload(Task.task_list).selectinload(TaskList.statuses),
        selectinload(Task.task_list).selectinload(TaskList.space_statuses),
        selectinload(Task.milestone),
        selectinload(Task.assignee),
        selectinload(Task.reporter),
        selectinload(Task.comments),
        selectinload(Task.label_links).selectinload(TaskLabel.label),
        selectinload(Task.subtasks),
        selectinload(Task.checklist_items),
        selectinload(Task.assignee_links).selectinload(TaskAssignee.user),
        selectinload(Task.follower_links).selectinload(TaskFollower.user),
    ]
    if include_doc_links:
        options.append(selectinload(Task.doc_links).selectinload(TaskDocLink.doc))
    return tuple(options)


def _get_task_for_user(
    db: Session,
    user: User,
    task_id: str,
    *,
    require_editor: bool = False,
) -> tuple[Task, TaskList]:
    task_query = (
        select(Task)
        .options(
            selectinload(Task.task_list).selectinload(TaskList.labels),
            selectinload(Task.task_list).selectinload(TaskList.statuses),
            selectinload(Task.task_list).selectinload(TaskList.space_statuses),
            selectinload(Task.milestone),
            selectinload(Task.assignee),
            selectinload(Task.reporter),
            selectinload(Task.comments).selectinload(TaskComment.author),
            selectinload(Task.activity_logs).selectinload(TaskActivityLog.actor),
            selectinload(Task.label_links).selectinload(TaskLabel.label),
            selectinload(Task.subtasks).selectinload(Task.assignee),
            selectinload(Task.subtasks).selectinload(Task.reporter),
            selectinload(Task.subtasks).selectinload(Task.milestone),
            selectinload(Task.subtasks).selectinload(Task.comments),
            selectinload(Task.subtasks)
            .selectinload(Task.label_links)
            .selectinload(TaskLabel.label),
            selectinload(Task.subtasks).selectinload(Task.subtasks),
            selectinload(Task.subtasks).selectinload(Task.checklist_items),
            selectinload(Task.attachments).selectinload(Attachment.uploaded_by),
            selectinload(Task.checklist_items),
            selectinload(Task.assignee_links).selectinload(TaskAssignee.user),
            selectinload(Task.follower_links).selectinload(TaskFollower.user),
            selectinload(Task.doc_links).selectinload(TaskDocLink.doc),
        )
        .where(Task.id == task_id)
    )
    if require_editor:
        task_query = task_query.with_for_update()
    task = db.scalar(task_query)
    if task is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="pms.task_not_found"
        )

    if require_editor:
        task_list, _ = _ensure_list_editor(db, user, task.list_id)
    else:
        _ensure_task_readable(db, user, task)
        task_list = task.task_list
    return task, task_list


def list_spaces(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
) -> list[dict[str, Any]]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    spaces = list(db.scalars(_space_query_for_user(db, user).order_by(Team.name.asc())))
    return [_serialize_space(space, resolve_pms_space_role(db, user, space)) for space in spaces]


def create_space(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    name: str,
    description: str,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    _require_user_write_principal(principal)
    team = Team(
        id=new_id(),
        workspace_id=workspace.id,
        key=_unique_space_key(db, workspace.id, name),
        name=name.strip(),
        description=description.strip(),
        active=True,
    )
    db.add(team)
    db.flush()
    _create_default_space_statuses(db, team.id)
    db.add(
        TeamMember(
            id=new_id(),
            team_id=team.id,
            user_id=user.id,
            role="owner",
        )
    )
    db.commit()
    team = _load_active_space(db, team.id, include_members=True)
    assert team is not None
    return _serialize_space(team, "owner")


def update_space(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    space_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    _require_user_write_principal(principal)
    team, role = _ensure_space_manager(db, user, space_id)
    if name is not None:
        team.name = name.strip()
    if description is not None:
        team.description = description.strip()
    db.add(team)
    db.commit()
    team = _load_active_space(db, team.id, include_members=True)
    assert team is not None
    return _serialize_space(team, role)


def delete_space(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    space_id: str,
) -> None:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    _require_user_write_principal(principal)
    team, _role = _ensure_space_manager(db, user, space_id)
    team.trashed_at = _utcnow()
    db.add(team)
    for task_list in db.scalars(select(TaskList).where(TaskList.team_id == team.id)):
        enqueue_task_list_task_recompute(db, task_list=task_list)
    db.commit()


def list_space_members(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    space_id: str,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    _ensure_space_access(db, user, space_id)
    members = [
        _serialize_space_member(db, member)
        for member in sorted(
            _load_space_members(db, space_id),
            key=lambda item: (item.role not in {"owner", "admin"}, item.user.full_name.lower()),
        )
    ]
    page_items, total = _paginate(members, page, page_size)
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def add_space_member(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    space_id: str,
    target_user_id: str,
    role: str,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    _require_user_write_principal(principal)
    _ensure_space_admin_change_allowed(
        db,
        user,
        space_id,
        current_role=None,
        next_role=role,
    )
    target_user = _validate_space_member_user(db, space_id, target_user_id)
    membership = TeamMember(
        id=new_id(),
        team_id=space_id,
        user_id=target_user.id,
        role=role,
    )
    db.add(membership)
    db.commit()
    membership = _get_space_membership(db, space_id, target_user.id)
    assert membership is not None
    return _serialize_space_member(db, membership)


def update_space_member(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    space_id: str,
    target_user_id: str,
    role: str,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    _require_user_write_principal(principal)
    membership = _get_space_membership(db, space_id, target_user_id)
    if membership is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="pms.member_not_found"
        )
    _ensure_space_admin_change_allowed(
        db,
        user,
        space_id,
        current_role=membership.role,
        next_role=role,
    )
    members = _load_space_members(db, space_id)
    _ensure_space_owner_survives(members, target_user_id, next_role=role)
    membership.role = role
    db.add(membership)
    db.commit()
    membership = _get_space_membership(db, space_id, target_user_id)
    assert membership is not None
    return _serialize_space_member(db, membership)


def remove_space_member(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    space_id: str,
    target_user_id: str,
) -> None:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    _require_user_write_principal(principal)
    membership = _get_space_membership(db, space_id, target_user_id)
    if membership is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="pms.member_not_found"
        )
    _ensure_space_admin_change_allowed(
        db,
        user,
        space_id,
        current_role=membership.role,
        next_role=None,
    )
    members = _load_space_members(db, space_id)
    _ensure_space_owner_survives(members, target_user_id, next_role=None)
    db.delete(membership)
    db.commit()


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

    if team_id is not None:
        _ensure_space_access(db, user, team_id)

    task_lists = list(
        db.scalars(
            _accessible_task_lists_query(db, user).options(
                selectinload(TaskList.milestones),
                selectinload(TaskList.statuses),
                selectinload(TaskList.space_statuses),
                selectinload(TaskList.tasks).selectinload(Task.comments),
                selectinload(TaskList.tasks).selectinload(Task.subtasks),
                joinedload(TaskList.folder),
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
            key=lambda task_list: _calculate_progress(task_list.tasks),
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
                select(Team)
                .where(
                    Team.id.in_(team_ids),
                    Team.trashed_at.is_(None),
                )
                .options(joinedload(Team.workspace), selectinload(Team.members))
            )
        )
        team_names = {team.id: team.name for team in teams}
        team_lookup = {team.id: team for team in teams}
        team_member_counts = {team.id: len(team.members) for team in teams}

    serialized = [
        _serialize_task_list(
            task_list,
            _task_list_role(db, task_list, user, team_lookup),
            team_names.get(task_list.team_id, None) if task_list.team_id else None,
            team_member_counts.get(task_list.team_id or "", 0),
        )
        for task_list in task_lists
    ]
    page_items, total = _paginate(serialized, page, page_size)
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def create_task_list(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    name: str,
    description: str = "",
    key: str | None = None,
    team_id: str | None = None,
    folder_id: str | None = None,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    _require_user_write_principal(principal)
    resolved_key = key.upper() if key else _unique_key(db, name)

    resolved_team_id = team_id
    if resolved_team_id:
        team, _role = _ensure_space_editor(db, user, resolved_team_id)
    else:
        team = get_or_create_default_pms_space(db, workspace=workspace)
        resolved_team_id = team.id
    resolved_team_name = team.name

    _validate_folder_membership(db, resolved_team_id, folder_id)

    task_list = TaskList(
        id=new_id(),
        key=resolved_key,
        name=name.strip(),
        description=description.strip(),
        status="active",
        status_mode="inherit",
        team_id=resolved_team_id,
        folder_id=folder_id,
        created_by_id=user.id,
    )
    db.add(task_list)
    _ensure_space_statuses(db, resolved_team_id)
    if not db.scalar(
        select(TeamMember.id).where(
            TeamMember.team_id == resolved_team_id,
            TeamMember.user_id == user.id,
        )
    ):
        db.add(
            TeamMember(
                id=new_id(),
                team_id=resolved_team_id,
                user_id=user.id,
                role="owner",
            )
        )
    _create_default_labels(db, task_list.id)
    db.commit()
    db.refresh(task_list)
    loaded_task_list = db.scalar(
        select(TaskList)
        .options(
            selectinload(TaskList.milestones),
            selectinload(TaskList.statuses),
            selectinload(TaskList.space_statuses),
            selectinload(TaskList.tasks).selectinload(Task.comments),
            joinedload(TaskList.folder),
        )
        .where(TaskList.id == task_list.id)
    )
    assert loaded_task_list is not None
    member_count = len(_load_space_members(db, resolved_team_id))
    return _serialize_task_list(loaded_task_list, "owner", resolved_team_name, member_count)


def list_tasks(
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

    _ensure_list_member(db, user, list_id)
    statement = select(Task).options(*_task_summary_load_options()).where(Task.list_id == list_id)
    if archived is not None:
        statement = statement.where(Task.archived.is_(archived))
    if status_filter:
        statement = statement.where(Task.status.in_(status_filter))
    if assignee_id:
        statement = statement.where(_task_assignee_filter(assignee_id))
    if priority:
        statement = statement.where(Task.priority == priority)
    if label_id:
        statement = statement.where(_task_label_filter(label_id))
    if milestone_id:
        statement = statement.where(Task.milestone_id == milestone_id)
    if due_date_from:
        statement = statement.where(Task.due_date >= due_date_from)
    if due_date_to:
        statement = statement.where(Task.due_date <= due_date_to)
    if start_date_from:
        statement = statement.where(Task.start_date >= start_date_from)
    if start_date_to:
        statement = statement.where(Task.start_date <= start_date_to)
    q_lower = q.strip().lower()
    if not q_lower:
        total = _count_task_statement(db, statement)
        tasks = list(
            db.scalars(
                _ordered_task_statement(statement, sort_by, sort_dir)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return {
            "items": [_serialize_task(task) for task in tasks],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    tasks = list(db.scalars(statement))
    if q_lower:
        tasks = [
            task
            for task in tasks
            if q_lower in task.title.lower()
            or q_lower in task.description.lower()
            or q_lower in _task_reference(task).lower()
        ]

    reverse = sort_dir == "desc"
    if sort_by == "priority":
        order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        tasks.sort(key=lambda task: order[task.priority], reverse=reverse)
    elif sort_by in {"completed_date", "due_date", "start_date"}:
        tasks_with_date = [task for task in tasks if getattr(task, sort_by) is not None]
        tasks_without_date = [task for task in tasks if getattr(task, sort_by) is None]
        tasks_with_date.sort(
            key=lambda task: (getattr(task, sort_by), task.task_number),
            reverse=reverse,
        )
        tasks_without_date.sort(key=lambda task: task.task_number, reverse=reverse)
        tasks = [*tasks_with_date, *tasks_without_date]
    elif sort_by == "created_at":
        tasks.sort(
            key=lambda task: (task.created_at, task.task_number),
            reverse=reverse,
        )
    elif sort_by == "updated_at":
        tasks.sort(key=lambda task: task.updated_at, reverse=reverse)
    else:
        tasks.sort(key=lambda task: (task.board_position, task.task_number), reverse=reverse)

    serialized = [_serialize_task(task) for task in tasks]
    page_items, total = _paginate(serialized, page, page_size)
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def search_tasks(
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

    if list_id is not None:
        _ensure_list_member(db, user, list_id)

    accessible_list_ids_subquery = _active_accessible_task_lists_query(db, user).with_only_columns(
        TaskList.id
    )
    statement = (
        select(Task)
        .options(*_task_summary_load_options())
        .where(Task.list_id.in_(accessible_list_ids_subquery))
    )
    if list_id is not None:
        statement = statement.where(Task.list_id == list_id)
    if archived is not None:
        statement = statement.where(Task.archived.is_(archived))
    if status_filter:
        statement = statement.where(Task.status.in_(status_filter))
    if assignee_id:
        statement = statement.where(_task_assignee_filter(assignee_id))
    if not q.strip():
        statement = statement.order_by(Task.updated_at.desc()).limit(limit)
    tasks = list(db.scalars(statement))

    q_lower = q.strip().lower()
    if q_lower:
        tasks = [
            task
            for task in tasks
            if q_lower in task.title.lower()
            or q_lower in task.description.lower()
            or q_lower in _task_reference(task).lower()
        ]

    tasks.sort(key=lambda task: task.updated_at, reverse=True)
    serialized = [_serialize_task(task) for task in tasks[:limit]]
    return {
        "items": serialized,
        "total": len(serialized),
        "page": 1,
        "page_size": limit,
    }


def list_assigned_tasks(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    limit: int | None = 10,
    page: int | None = None,
    page_size: int = 50,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    accessible_list_ids_subquery = _active_accessible_task_lists_query(db, user).with_only_columns(
        TaskList.id
    )
    tasks = list(
        db.scalars(
            select(Task)
            .options(*_task_summary_load_options())
            .where(
                Task.archived.is_(False),
                Task.list_id.in_(accessible_list_ids_subquery),
                _task_assignee_filter(user.id),
            )
            .order_by(Task.due_date.asc(), Task.updated_at.desc())
        )
    )

    tasks = [task for task in tasks if not _is_overdue_exempt_status(task.status, task.task_list)]
    tasks.sort(
        key=lambda task: (
            task.due_date or date.max,
            -task.updated_at.timestamp(),
        )
    )
    serialized = [_serialize_task(task) for task in tasks]
    if page is None:
        effective_limit = limit or page_size
        return {
            "items": serialized[:effective_limit],
            "total": len(serialized),
            "page": 1,
            "page_size": effective_limit,
        }

    page_items, total = _paginate(serialized, page, page_size)
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def list_personal_widget_assigned_tasks(
    db: Session,
    *,
    user: User,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Return open assigned tasks across every PMS-enabled workspace for ``user``."""

    workspaces = resolve_workspaces(db, user)
    eligible_workspaces = [
        workspace
        for workspace in workspaces
        if PMS_WORKSPACE_APP.app_id in resolve_workspace_enabled_app_ids(db, str(workspace["id"]))
    ]
    if not eligible_workspaces:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "workspaces": [],
        }

    workspace_by_id = {str(item["id"]): item for item in eligible_workspaces}
    accessible_list_ids_subquery = (
        select(TaskList.id)
        .join(Team, Team.id == TaskList.team_id)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(
            TeamMember.user_id == user.id,
            TaskList.archived.is_(False),
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
            Team.workspace_id.in_(tuple(workspace_by_id)),
        )
    )
    rows = db.execute(
        select(Task, Team.workspace_id)
        .join(TaskList, TaskList.id == Task.list_id)
        .join(Team, Team.id == TaskList.team_id)
        .options(*_task_summary_load_options())
        .where(
            Task.archived.is_(False),
            Task.list_id.in_(accessible_list_ids_subquery),
            Team.workspace_id.in_(tuple(workspace_by_id)),
            _task_assignee_filter(user.id),
        )
        .order_by(Task.due_date.asc(), Task.updated_at.desc())
    ).all()

    items: list[dict[str, Any]] = []
    for task, workspace_id in rows:
        if _is_overdue_exempt_status(task.status, task.task_list):
            continue
        workspace = workspace_by_id[str(workspace_id)]
        items.append(
            {
                **_serialize_task(task),
                "workspace": {
                    "id": str(workspace["id"]),
                    "slug": str(workspace["slug"]),
                    "name": str(workspace["name"]),
                },
            }
        )

    items.sort(
        key=lambda item: (
            item["due_date"] or date.max,
            -item["updated_at"].timestamp(),
        )
    )
    page_items, total = _paginate(items, page, page_size)
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "workspaces": [
            {
                "id": str(workspace["id"]),
                "slug": str(workspace["slug"]),
                "name": str(workspace["name"]),
                "role": str(workspace["role"]),
            }
            for workspace in eligible_workspaces
        ],
    }


def list_today_overdue_tasks(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    today: date,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    accessible_list_ids_subquery = _active_accessible_task_lists_query(db, user).with_only_columns(
        TaskList.id
    )
    tasks = list(
        db.scalars(
            select(Task)
            .options(*_task_summary_load_options())
            .where(
                Task.archived.is_(False),
                Task.list_id.in_(accessible_list_ids_subquery),
                _task_assignee_filter(user.id),
                Task.due_date.is_not(None),
                Task.due_date <= today,
            )
            .order_by(Task.due_date.asc(), Task.updated_at.desc())
        )
    )

    tasks = [task for task in tasks if not _is_overdue_exempt_status(task.status, task.task_list)]
    tasks.sort(
        key=lambda task: (
            task.due_date or date.max,
            -task.updated_at.timestamp(),
        )
    )
    serialized = [_serialize_task(task) for task in tasks]
    page_items, total = _paginate(serialized, page, page_size)
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_task_detail(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    task_id: str,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    task, _task_list = _get_task_for_user(db, user, task_id)
    return {
        "task": _serialize_task(task),
        "comments": [
            _serialize_comment(comment)
            for comment in sorted(task.comments, key=lambda item: item.created_at)
        ],
        "linked_docs": [
            _serialize_task_doc_link(link)
            for link in sorted(task.doc_links, key=lambda item: item.created_at)
            if link.doc is not None and link.doc.trashed_at is None
        ],
        "subtasks": [
            _serialize_task(subtask)
            for subtask in sorted(task.subtasks, key=lambda item: item.created_at)
            if not subtask.archived
        ],
        "attachments": [
            asdict(serialize_task_attachment(attachment))
            for attachment in sorted(task.attachments, key=lambda item: item.created_at)
        ],
        "checklist_items": [
            {
                "id": checklist_item.id,
                "task_id": checklist_item.task_id,
                "text": checklist_item.text,
                "completed": checklist_item.completed,
                "sort_order": checklist_item.sort_order,
                "created_at": checklist_item.created_at,
            }
            for checklist_item in sorted(task.checklist_items, key=lambda item: item.sort_order)
        ],
    }


def _reload_task_summary(db: Session, *, task_id: str) -> Any:
    return db.scalar(
        select(Task)
        .options(*_task_summary_load_options(include_doc_links=True))
        .where(Task.id == task_id)
    )


def _reload_comment(db: Session, *, comment_id: str) -> Any:
    return db.scalar(
        select(TaskComment)
        .options(selectinload(TaskComment.author))
        .where(TaskComment.id == comment_id)
    )


def create_task(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    list_id: str,
    title: str,
    description: str = "",
    description_blocks: list[dict[str, Any]] | None = None,
    status: str = "todo",
    priority: str = "medium",
    assignee_id: str | None = None,
    assignee_ids: list[str] | None = None,
    milestone_id: str | None = None,
    parent_id: str | None = None,
    start_date: date | None = None,
    due_date: date | None = None,
    completed_date: date | None = None,
    recurrence_rule: str | None = None,
    label_ids: list[str] | None = None,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    if approved_call_id is not None:
        try:
            existing_task, _existing_task_list = _get_task_for_user(
                db,
                user,
                approved_call_id,
                require_editor=True,
            )
        except HTTPException as error:
            if error.status_code != 404:
                raise
        else:
            return _serialize_task_summary(existing_task)

    task_list, _ = _ensure_list_editor(db, user, list_id)
    validated_assignees: list[User] | None = None
    if assignee_ids is not None:
        validated_assignees = _validate_task_assignees(db, task_list, assignee_ids)
        assignee_id = validated_assignees[0].id if validated_assignees else None
    else:
        _validate_task_assignee(db, task_list, assignee_id)
        if assignee_id is not None:
            assignee = db.scalar(select(User).where(User.id == assignee_id))
            if assignee is None:
                raise localized_http_exception(
                    status_code=status.HTTP_404_NOT_FOUND, code="auth.user_not_found"
                )
            validated_assignees = [assignee]
    _validate_milestone(task_list, milestone_id)
    _validate_parent_task(db, task_list, parent_id)
    _lock_task_list_order(db, task_list.id)
    status = _normalize_task_status(status)
    if completed_date is None and is_completion_status(status, task_list):
        completed_date = _utcnow().date()
    next_position = _next_task_board_position(db, list_id, parent_id)
    task = Task(
        id=approved_call_id or new_id(),
        list_id=task_list.id,
        task_number=_next_task_number(db, task_list.id),
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
        completed_date=completed_date,
        recurrence_rule=recurrence_rule,
        board_position=next_position,
    )
    if task_list.team_id is None:
        raise ValueError("PMS task list must belong to a workspace team")
    task_workspace_id = db.scalar(
        select(Team.workspace_id).where(Team.id == task_list.team_id)
    )
    if task_workspace_id is None:
        raise ValueError("PMS task list team must belong to a workspace")
    assign_default_partition(
        db,
        target=task,
        source_namespace="pms",
        candidate_scope_kind="workspace",
        workspace_id=task_workspace_id,
    )
    db.add(task)
    db.flush()
    enqueue_task_rag_sync(
        db,
        task=task,
        operation=RagSyncOperation.UPSERT,
    )
    if validated_assignees is not None:
        _set_task_assignees(task, validated_assignees)
    _set_task_labels(db, task, label_ids or [], task_list)
    if description_blocks:
        sync_embedded_media(db, description_blocks, "task", task.id, user)
    _log_task_activity(
        db,
        task.id,
        user.id,
        "created",
        f"{user.full_name} created {_task_reference(task)}.",
        stable_key=(
            _stable_replay_id(approved_call_id, "activity.created")
            if approved_call_id is not None
            else None
        ),
    )
    db.commit()
    reloaded = _reload_task_summary(db, task_id=task.id)
    return _serialize_task_summary(reloaded)


def update_task(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    task_id: str,
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
    completed_date: date | None = None,
    board_position: int | None = None,
    archived: bool | None = None,
    recurrence_rule: str | None = None,
    label_ids: list[str] | None = None,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    effective_provided_fields = effective_task_update_fields(provided_fields)
    if {"board_position", "parent_id"} & effective_provided_fields:
        task_list_id = db.scalar(select(Task.list_id).where(Task.id == task_id))
        if task_list_id is None:
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                code="pms.task_not_found",
            )
        _ensure_list_editor(db, user, task_list_id)
        _lock_task_list_order(db, task_list_id)
    task, task_list = _get_task_for_user(db, user, task_id, require_editor=True)
    rag_operation: RagSyncOperation | None = None
    validated_assignees: list[User] | None = None
    if "assignee_ids" in effective_provided_fields:
        validated_assignees = _validate_task_assignees(db, task_list, assignee_ids or [])
        assignee_id = validated_assignees[0].id if validated_assignees else None
    elif "assignee_id" in effective_provided_fields:
        _validate_task_assignee(db, task_list, assignee_id)
        if assignee_id is None:
            validated_assignees = []
        else:
            assignee = db.scalar(select(User).where(User.id == assignee_id))
            if assignee is None:
                raise localized_http_exception(
                    status_code=status.HTTP_404_NOT_FOUND, code="auth.user_not_found"
                )
            validated_assignees = [assignee]
    previous_assignee_ids = _task_assignee_ids(task) if validated_assignees is not None else []
    if "milestone_id" in effective_provided_fields:
        _validate_milestone(task_list, milestone_id)
    if "parent_id" in effective_provided_fields:
        _validate_parent_task(db, task_list, parent_id, task_id=task.id)
    if "status" in effective_provided_fields and status is not None:
        status = _normalize_task_status(status)
    old_status = task.status
    proposed_scalar_values = {
        "title": title,
        "description": description,
        "status": status,
        "priority": priority,
        "assignee_id": assignee_id,
        "milestone_id": milestone_id,
        "start_date": start_date,
        "due_date": due_date,
        "completed_date": completed_date,
        "board_position": board_position,
        "archived": archived,
        "recurrence_rule": recurrence_rule,
    }
    current_scalar_values = {
        field_name: getattr(task, field_name) for field_name in proposed_scalar_values
    }
    for update in plan_task_scalar_updates(
        current_values=current_scalar_values,
        provided_fields=effective_provided_fields,
        proposed_values=proposed_scalar_values,
    ):
        setattr(task, update.field_name, update.next_value)
        rag_operation = RagSyncOperation.UPSERT
        _log_task_activity(
            db,
            task.id,
            user.id,
            "updated",
            f"{user.full_name} {update.activity_message} for {_task_reference(task)}.",
            field_name=update.field_name,
            from_value=str(update.previous_value) if update.previous_value is not None else None,
            to_value=str(update.next_value) if update.next_value is not None else None,
            stable_key=(
                _stable_replay_id(approved_call_id, f"activity.field.{update.field_name}")
                if approved_call_id is not None
                else None
            ),
        )

    if "parent_id" in effective_provided_fields:
        previous = task.parent_id
        if (
            previous is not None
            and parent_id is None
            and "board_position" not in effective_provided_fields
        ):
            _place_unlinked_task_after_former_parent(
                db,
                task=task,
                former_parent_id=previous,
            )
        task.parent_id = parent_id
        if previous != parent_id:
            rag_operation = RagSyncOperation.UPSERT
            _log_task_activity(
                db,
                task.id,
                user.id,
                "updated",
                f"{user.full_name} {'removed parent' if parent_id is None else 'changed parent'} for {_task_reference(task)}.",
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
        previous_blocks = task.description_blocks
        if previous_blocks != description_blocks:
            task.description_blocks = description_blocks
            sync_embedded_media(db, description_blocks, "task", task.id, user)
            rag_operation = RagSyncOperation.UPSERT

    if "label_ids" in effective_provided_fields and label_ids is not None:
        _set_task_labels(db, task, label_ids, task_list)
        rag_operation = RagSyncOperation.UPSERT
        _log_task_activity(
            db,
            task.id,
            user.id,
            "updated",
            f"{user.full_name} updated labels for {_task_reference(task)}.",
            field_name="label_ids",
            stable_key=(
                _stable_replay_id(approved_call_id, "activity.label_ids")
                if approved_call_id is not None
                else None
            ),
        )
    if validated_assignees is not None:
        new_assignee_ids = [assignee.id for assignee in validated_assignees]
        current_link_ids = [link.user_id for link in list(task.assignee_links)]
        if current_link_ids != new_assignee_ids:
            _set_task_assignees(task, validated_assignees)
            rag_operation = RagSyncOperation.UPSERT
        if (
            "assignee_ids" in effective_provided_fields
            and previous_assignee_ids != new_assignee_ids
        ):
            _log_task_activity(
                db,
                task.id,
                user.id,
                "updated",
                f"{user.full_name} updated assignees for {_task_reference(task)}.",
                field_name="assignee_ids",
                from_value=",".join(previous_assignee_ids) if previous_assignee_ids else None,
                to_value=",".join(new_assignee_ids) if new_assignee_ids else None,
                stable_key=(
                    _stable_replay_id(approved_call_id, "activity.assignee_ids")
                    if approved_call_id is not None
                    else None
                ),
            )

    if status is not None and status != old_status:
        completed_date_updated = _set_missing_task_completed_date(
            db,
            task=task,
            actor=user,
            task_list=task_list,
            message=f"{user.full_name} updated completion date for {_task_reference(task)}.",
            stable_key=(
                _stable_replay_id(approved_call_id, "activity.completed_date.auto")
                if approved_call_id is not None
                else None
            ),
        )
    else:
        completed_date_updated = False
    if completed_date_updated:
        rag_operation = RagSyncOperation.UPSERT

    task_label = _task_notification_label(task)
    task_label_with_reference = _task_notification_label_with_reference(task)
    action_url = _task_action_url(workspace, task)
    if "assignee_id" in effective_provided_fields:
        for notified_assignee_id in _task_assignee_ids(task):
            if notified_assignee_id == user.id:
                continue
            _create_notification(
                db,
                notified_assignee_id,
                "assigned",
                f"{task_label} assigned to you",
                f"{user.full_name} assigned {task_label_with_reference} to you.",
                reference_id=task.id,
                action_url=action_url,
                stable_key=(
                    _stable_replay_id(
                        approved_call_id, f"notification.assigned.{notified_assignee_id}"
                    )
                    if approved_call_id is not None
                    else None
                ),
            )
    if status is not None and status != old_status:
        notify_ids = _task_notification_user_ids(task)
        notify_ids.discard(user.id)
        for uid in notify_ids:
            _create_notification(
                db,
                uid,
                "status_changed",
                f"{task_label} status → {TASK_STATUS_LABELS.get(status, status)}",
                f"{user.full_name} changed status of {task_label_with_reference} to {TASK_STATUS_LABELS.get(status, status)}.",
                reference_id=task.id,
                action_url=action_url,
                stable_key=(
                    _stable_replay_id(approved_call_id, f"notification.status_changed.{uid}")
                    if approved_call_id is not None
                    else None
                ),
            )

    if rag_operation is not None:
        enqueue_task_rag_sync(
            db,
            task=task,
            operation=rag_operation,
        )
    db.commit()
    reloaded = _reload_task_summary(db, task_id=task.id)
    return _serialize_task_summary(reloaded)


def add_task_comment(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    task_id: str,
    body: str = "",
    body_blocks: list[dict[str, Any]] | None = None,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    if approved_call_id is not None:
        existing_comment = db.scalar(
            select(TaskComment)
            .options(selectinload(TaskComment.author))
            .where(TaskComment.id == approved_call_id)
        )
        if existing_comment is not None:
            _get_task_for_user(db, user, existing_comment.task_id, require_editor=True)
            return _serialize_comment_item(existing_comment)

    task, _ = _get_task_for_user(db, user, task_id, require_editor=True)
    comment = TaskComment(
        id=approved_call_id or new_id(),
        task_id=task.id,
        author_id=user.id,
        body=body.strip(),
        body_blocks=body_blocks,
    )
    db.add(comment)
    enqueue_task_rag_sync(
        db,
        task=task,
        operation=RagSyncOperation.UPSERT,
    )
    _log_task_activity(
        db,
        task.id,
        user.id,
        "commented",
        f"{user.full_name} added a comment to {_task_reference(task)}.",
        stable_key=(
            _stable_replay_id(approved_call_id, "activity.commented")
            if approved_call_id is not None
            else None
        ),
    )
    ref = _task_reference(task)
    action_url = _task_action_url(workspace, task)
    notify_ids = _task_notification_user_ids(task)
    notify_ids.discard(user.id)
    for uid in notify_ids:
        _create_notification(
            db,
            uid,
            "commented",
            f"New comment on {task.title}",
            f"{user.full_name} commented on {task.title} ({ref}).",
            reference_id=task.id,
            action_url=action_url,
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
                f"Mentioned in {task.title}",
                f"{user.full_name} mentioned you in a comment on {task.title} ({ref}).",
                reference_id=task.id,
                action_url=action_url,
                stable_key=(
                    _stable_replay_id(approved_call_id, f"notification.mentioned.{uid}")
                    if approved_call_id is not None
                    else None
                ),
            )

    db.commit()
    reloaded = _reload_comment(db, comment_id=comment.id)
    return _serialize_comment_item(reloaded)


def delete_task(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    task_id: str,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    del approved_call_id
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    task, _task_list = _get_task_for_user(db, user, task_id, require_editor=True)
    deleted_task_id = task.id
    delete_loaded_tasks(db, [task])
    return {"id": deleted_task_id, "deleted": True}


def delete_loaded_tasks(db: Session, tasks: Sequence[Task]) -> list[str]:
    deleted_task_ids: list[str] = []
    media_keys: list[str] = []
    for task in tasks:
        for child in task.subtasks:
            child.parent_id = None
        media_keys.extend(cleanup_media_for_resource(db, "task", task.id))
        enqueue_task_rag_sync(
            db,
            task=task,
            operation=RagSyncOperation.DELETE,
        )
        deleted_task_ids.append(task.id)
        db.delete(task)
    db.commit()
    if media_keys:
        settings = get_settings()
        client = get_minio_client()
        for key in media_keys:
            try:
                client.remove_object(settings.minio_bucket, key)
            except Exception:
                pass
    return deleted_task_ids


def reorder_task_list_tasks(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    list_id: str,
    updates: Sequence[TaskReorderUpdate],
) -> list[dict[str, Any]]:
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    task_list, _role = _ensure_list_editor(db, user, list_id)
    if task_list.team_id is None:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="pms.task_list_space_missing",
        )
    team = db.scalar(select(Team).where(Team.id == task_list.team_id))
    if team is None or team.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="pms.task_list_not_found",
        )
    _lock_task_list_order(db, list_id)

    task_ids = [update.task_id for update in updates]
    if len(task_ids) != len(set(task_ids)):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="pms.duplicate_task_ids",
        )

    task_map = {
        task.id: task
        for task in db.scalars(
            select(Task)
            .options(selectinload(Task.task_list))
            .where(Task.id.in_(task_ids), Task.list_id == list_id)
            .order_by(Task.id)
            .with_for_update()
        )
    }
    if len(task_map) != len(task_ids):
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="pms.no_matching_tasks",
        )
    parent_by_id = {
        task_id: parent_id
        for task_id, parent_id in db.execute(
            select(Task.id, Task.parent_id).where(Task.list_id == list_id)
        )
    }
    for update in updates:
        if not update.parent_id_present:
            continue
        if update.parent_id == update.task_id:
            raise localized_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                code="pms.task_cannot_be_own_parent",
            )
        if update.parent_id is not None and update.parent_id not in parent_by_id:
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                code="pms.parent_task_not_found",
            )
        parent_by_id[update.task_id] = update.parent_id

    for update in updates:
        visited: set[str] = set()
        parent_id = parent_by_id.get(update.task_id)
        while parent_id is not None:
            if parent_id == update.task_id or parent_id in visited:
                raise localized_http_exception(
                    status_code=status.HTTP_409_CONFLICT,
                    code="pms.task_parent_cycle",
                )
            visited.add(parent_id)
            parent_id = parent_by_id.get(parent_id)

    updated_ids: list[str] = []
    for update in updates:
        task = task_map[update.task_id]
        changed = False
        if task.board_position != update.board_position:
            task.board_position = update.board_position
            changed = True
        if update.parent_id_present:
            previous_parent_id = task.parent_id
            if previous_parent_id != update.parent_id:
                task.parent_id = update.parent_id
                _log_task_activity(
                    db,
                    task.id,
                    user.id,
                    "updated",
                    f"{user.full_name} {'removed parent' if update.parent_id is None else 'changed parent'} for {_task_reference(task)}.",
                    field_name="parent_id",
                    from_value=previous_parent_id,
                    to_value=update.parent_id,
                )
                changed = True
        if changed:
            updated_ids.append(task.id)

    if not updated_ids:
        return []

    db.commit()
    reloaded = {
        task.id: task
        for task in db.scalars(
            select(Task).options(*_task_summary_load_options()).where(Task.id.in_(updated_ids))
        )
    }
    return [
        _serialize_task_summary(reloaded[task_id]) for task_id in task_ids if task_id in reloaded
    ]


def bulk_update_loaded_tasks(
    db: Session,
    *,
    task_list: TaskList,
    tasks: Sequence[Task],
    actor: User,
    status_value: str | None = None,
    priority: str | None = None,
    assignee_field_present: bool = False,
    assignee_id: str | None = None,
    archived: bool | None = None,
    add_label_ids: Sequence[str] = (),
    remove_label_ids: Sequence[str] = (),
) -> int:
    label_map = {label.id: label for label in task_list.labels}
    updated = 0
    next_positions_by_parent: dict[str | None, int] = {}
    target_status = _normalize_task_status(status_value) if status_value is not None else None

    def next_position_for(parent_id: str | None) -> int:
        next_position = next_positions_by_parent.get(parent_id)
        if next_position is None:
            next_position = _next_task_board_position(db, task_list.id, parent_id)
        next_positions_by_parent[parent_id] = next_position + 1
        return next_position

    for task in tasks:
        changed = False
        if target_status is not None and task.status != target_status:
            previous_status = task.status
            _log_task_activity(
                db,
                task.id,
                actor.id,
                "updated",
                f"{actor.full_name} updated status.",
                field_name="status",
                from_value=previous_status,
                to_value=target_status,
            )
            task.status = target_status
            task.board_position = next_position_for(task.parent_id)
            _set_missing_task_completed_date(
                db,
                task=task,
                actor=actor,
                task_list=task.task_list,
                message=f"{actor.full_name} updated completion date.",
            )
            changed = True
        if priority is not None and task.priority != priority:
            _log_task_activity(
                db,
                task.id,
                actor.id,
                "updated",
                f"{actor.full_name} updated priority.",
                field_name="priority",
                from_value=task.priority,
                to_value=priority,
            )
            task.priority = priority
            changed = True
        if assignee_field_present:
            _validate_task_assignee(db, task_list, assignee_id)
            current_assignee_ids = [link.user_id for link in task.assignee_links] or (
                [task.assignee_id] if task.assignee_id else []
            )
            target_assignee_ids = [assignee_id] if assignee_id else []
            if task.assignee_id != assignee_id or current_assignee_ids != target_assignee_ids:
                old_name = getattr(task.assignee, "full_name", "Unassigned")
                if assignee_id is None:
                    _set_task_assignees(task, [])
                else:
                    assignee = db.scalar(select(User).where(User.id == assignee_id))
                    if assignee is None:
                        raise localized_http_exception(
                            status_code=status.HTTP_404_NOT_FOUND,
                            code="auth.user_not_found",
                        )
                    _set_task_assignees(task, [assignee])
                _log_task_activity(
                    db,
                    task.id,
                    actor.id,
                    "updated",
                    f"{actor.full_name} updated assignee.",
                    field_name="assignee",
                    from_value=old_name,
                    to_value=assignee_id or "Unassigned",
                )
                changed = True
        if archived is not None and task.archived != archived:
            task.archived = archived
            _log_task_activity(
                db,
                task.id,
                actor.id,
                "updated",
                f"{actor.full_name} {'archived' if archived else 'unarchived'} task.",
                field_name="archived",
                from_value=str(not archived),
                to_value=str(archived),
            )
            changed = True
        if add_label_ids:
            existing_ids = {link.label_id for link in task.label_links}
            for label_id in add_label_ids:
                if label_id not in existing_ids and label_id in label_map:
                    task.label_links.append(TaskLabel(id=new_id(), label_id=label_id))
                    changed = True
        if remove_label_ids:
            task.label_links = [
                link for link in task.label_links if link.label_id not in remove_label_ids
            ]
            changed = True
        if changed:
            enqueue_task_rag_sync(
                db,
                task=task,
                operation=RagSyncOperation.UPSERT,
            )
            updated += 1

    db.commit()
    return updated
