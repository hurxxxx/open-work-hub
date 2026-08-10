from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import case as sa_case
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import (
    is_valid_workspace_role,
    normalize_workspace_role,
)
from open_work_hub_api.domains.auth.models import User, Workspace, WorkspaceUserBinding
from open_work_hub_api.domains.auth.security import new_id

WorkspaceMemberBulkAction = Literal["add", "remove", "update_role"]
WorkspaceMemberSubjectType = Literal["user"]


@dataclass(frozen=True)
class WorkspaceMemberDirectoryItem:
    subject_id: str
    subject_type: WorkspaceMemberSubjectType
    subject_label: str
    subject_secondary: str | None = None
    role: str = "member"
    user_status: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class WorkspaceMemberDirectory:
    items: list[WorkspaceMemberDirectoryItem]
    total: int
    page: int
    page_size: int
    role_counts: dict[str, int]
    user_count: int
    pending_count: int


def workspace_role_storage_values(role: str) -> tuple[str, ...]:
    normalized_role = normalize_workspace_role(role)
    if normalized_role == "admin":
        return ("admin", "owner")
    if normalized_role == "member":
        return ("member", "viewer")
    return ()


def serialize_workspace_member_binding(
    binding: WorkspaceUserBinding,
) -> WorkspaceMemberDirectoryItem:
    return WorkspaceMemberDirectoryItem(
        subject_id=binding.user_id,
        subject_type="user",
        subject_label=binding.user.full_name or binding.user.email,
        subject_secondary=binding.user.email,
        role=normalize_workspace_role(binding.role) or binding.role,
        user_status=binding.user.status,
        last_login_at=binding.user.last_login_at,
        created_at=binding.created_at,
    )


def add_workspace_member_binding(
    db: Session,
    workspace: Workspace,
    *,
    subject_id: str,
    role: str,
    duplicate_code: str,
) -> WorkspaceUserBinding:
    if db.scalar(select(User.id).where(User.id == subject_id)) is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    existing = _load_workspace_member_binding(db, workspace.id, subject_id)
    if existing is not None:
        raise localized_http_exception(
            status_code=409,
            code=duplicate_code,
        )
    binding = WorkspaceUserBinding(
        id=new_id(),
        workspace_id=workspace.id,
        user_id=subject_id,
        role=role,
    )
    db.add(binding)
    db.flush()
    loaded = _load_workspace_member_binding(db, workspace.id, subject_id, include_user=True)
    assert loaded is not None
    return loaded


def update_workspace_member_binding_role(
    db: Session,
    workspace: Workspace,
    *,
    actor_user_id: str,
    subject_id: str,
    role: str,
) -> WorkspaceUserBinding:
    binding = _load_workspace_member_binding(db, workspace.id, subject_id, include_user=True)
    if binding is None:
        raise localized_http_exception(
            status_code=404,
            code="admin.workspace_member_not_found",
        )
    current_role = normalize_workspace_role(binding.role) or binding.role
    requested_role = normalize_workspace_role(role) or role
    if subject_id == actor_user_id and current_role != requested_role:
        raise localized_http_exception(
            status_code=409,
            code="admin.self_role_change_denied",
        )
    binding.role = requested_role
    db.add(binding)
    return binding


def remove_workspace_member_binding(
    db: Session,
    workspace: Workspace,
    *,
    actor_user_id: str,
    subject_id: str,
) -> None:
    binding = _load_workspace_member_binding(db, workspace.id, subject_id)
    if binding is None:
        raise localized_http_exception(
            status_code=404,
            code="admin.workspace_member_not_found",
        )
    if subject_id == actor_user_id:
        raise localized_http_exception(
            status_code=409,
            code="admin.self_workspace_remove_denied",
        )
    db.delete(binding)


def replace_workspace_member_bindings(
    db: Session,
    workspace: Workspace,
    *,
    actor_user_id: str,
    requested_roles_by_user_id: dict[str, str],
) -> None:
    requested_user_ids = set(requested_roles_by_user_id)
    existing_requested_user_ids = set(
        db.scalars(select(User.id).where(User.id.in_(requested_user_ids))).all()
    )
    if requested_user_ids - existing_requested_user_ids:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")

    current_bindings = list(workspace.user_bindings)
    current_user_ids = {binding.user_id for binding in current_bindings}
    actor_binding = next(
        (binding for binding in current_bindings if binding.user_id == actor_user_id),
        None,
    )
    if actor_binding is not None:
        if actor_user_id not in requested_user_ids:
            raise localized_http_exception(
                status_code=409,
                code="admin.self_workspace_remove_denied",
            )
        current_actor_role = normalize_workspace_role(actor_binding.role) or actor_binding.role
        requested_actor_role = (
            normalize_workspace_role(requested_roles_by_user_id[actor_user_id])
            or requested_roles_by_user_id[actor_user_id]
        )
        if current_actor_role != requested_actor_role:
            raise localized_http_exception(
                status_code=409,
                code="admin.self_role_change_denied",
            )

    requested_roles = {
        normalize_workspace_role(role) or role for role in requested_roles_by_user_id.values()
    }
    if "admin" not in requested_roles:
        raise localized_http_exception(
            status_code=409,
            code="admin.invalid_workspace_role",
        )

    for binding in current_bindings:
        if binding.user_id not in requested_user_ids:
            remove_workspace_member_binding(
                db,
                workspace,
                actor_user_id=actor_user_id,
                subject_id=binding.user_id,
            )
            continue
        update_workspace_member_binding_role(
            db,
            workspace,
            actor_user_id=actor_user_id,
            subject_id=binding.user_id,
            role=requested_roles_by_user_id[binding.user_id],
        )

    for user_id in requested_user_ids - current_user_ids:
        add_workspace_member_binding(
            db,
            workspace,
            subject_id=user_id,
            role=requested_roles_by_user_id[user_id],
            duplicate_code="admin.user_already_workspace_member",
        )


def list_workspace_member_directory(
    db: Session,
    workspace: Workspace,
    *,
    query: str,
    role_filters: list[str] | None,
    subject_type: WorkspaceMemberSubjectType | None,
    page: int,
    page_size: int,
    pending_only: bool,
) -> WorkspaceMemberDirectory:
    requested_role_values = _normalize_requested_role_filters(role_filters)
    user_filters = _workspace_member_user_filters(
        workspace_id=workspace.id,
        query=query,
        pending_only=pending_only,
    )
    role_counts, user_total = _load_role_distribution(db, user_filters)
    pending_total = _load_pending_count(db, workspace.id)
    user_items = _load_directory_items(
        db,
        user_filters=user_filters,
        requested_role_values=requested_role_values,
        subject_type=subject_type,
    )
    total = len(user_items)
    start = (page - 1) * page_size
    end = start + page_size
    return WorkspaceMemberDirectory(
        items=user_items[start:end],
        total=total,
        page=page,
        page_size=page_size,
        role_counts=role_counts,
        user_count=user_total,
        pending_count=pending_total,
    )


def apply_workspace_member_bulk_entry(
    db: Session,
    workspace: Workspace,
    *,
    actor_user_id: str,
    action: WorkspaceMemberBulkAction,
    subject_type: WorkspaceMemberSubjectType,
    subject_id: str,
    role: str | None,
) -> None:
    if action == "add":
        if role is None:
            raise localized_http_exception(
                status_code=422,
                code="admin.role_required_for_add",
            )
        if subject_type == "user":
            add_workspace_member_binding(
                db,
                workspace,
                subject_id=subject_id,
                role=role,
                duplicate_code="admin.subject_already_member",
            )
        return

    if action == "remove":
        if subject_type == "user":
            remove_workspace_member_binding(
                db,
                workspace,
                actor_user_id=actor_user_id,
                subject_id=subject_id,
            )
        return

    if action == "update_role":
        if role is None:
            raise localized_http_exception(
                status_code=422,
                code="admin.role_required_for_update_role",
            )
        if subject_type == "user":
            update_workspace_member_binding_role(
                db,
                workspace,
                actor_user_id=actor_user_id,
                subject_id=subject_id,
                role=role,
            )


def _load_workspace_member_binding(
    db: Session,
    workspace_id: str,
    user_id: str,
    *,
    include_user: bool = False,
) -> WorkspaceUserBinding | None:
    query = select(WorkspaceUserBinding).where(
        WorkspaceUserBinding.workspace_id == workspace_id,
        WorkspaceUserBinding.user_id == user_id,
    )
    if include_user:
        query = query.options(joinedload(WorkspaceUserBinding.user))
    return db.scalar(query)


def _normalize_requested_role_filters(role_filters: list[str] | None) -> set[str]:
    requested_role_values: set[str] = set()
    if not role_filters:
        return requested_role_values
    for value in role_filters:
        if not is_valid_workspace_role(value):
            raise localized_http_exception(
                status_code=422,
                code="admin.invalid_workspace_role_filter",
            )
        normalized = normalize_workspace_role(value)
        if normalized:
            requested_role_values.update(workspace_role_storage_values(normalized))
    return requested_role_values


def _workspace_member_user_filters(
    *,
    workspace_id: str,
    query: str,
    pending_only: bool,
) -> list:
    user_filters: list = [WorkspaceUserBinding.workspace_id == workspace_id]
    if query:
        like = f"%{query}%"
        user_filters.append(
            or_(
                User.email.ilike(like),
                User.full_name.ilike(like),
                User.display_name.ilike(like),
            )
        )
    if pending_only:
        user_filters.append(User.status == "invited")
    return user_filters


def _load_role_distribution(db: Session, user_filters: list) -> tuple[dict[str, int], int]:
    role_counts: dict[str, int] = {"admin": 0, "member": 0}
    user_total = 0
    rows = db.execute(
        select(WorkspaceUserBinding.role, func.count())
        .join(User, User.id == WorkspaceUserBinding.user_id)
        .where(*user_filters)
        .group_by(WorkspaceUserBinding.role)
    ).all()
    for role_value, count_value in rows:
        normalized = normalize_workspace_role(role_value) or role_value
        if normalized in role_counts:
            role_counts[normalized] += int(count_value)
        user_total += int(count_value)
    return role_counts, user_total


def _load_pending_count(db: Session, workspace_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(WorkspaceUserBinding)
            .join(User, User.id == WorkspaceUserBinding.user_id)
            .where(
                WorkspaceUserBinding.workspace_id == workspace_id,
                User.status == "invited",
            )
        )
        or 0
    )


def _load_directory_items(
    db: Session,
    *,
    user_filters: list,
    requested_role_values: set[str],
    subject_type: WorkspaceMemberSubjectType | None,
) -> list[WorkspaceMemberDirectoryItem]:
    if subject_type not in (None, "user"):
        return []
    user_role_priority = sa_case(
        {"admin": 0, "owner": 0, "member": 1, "viewer": 1},
        value=WorkspaceUserBinding.role,
        else_=99,
    )
    user_query = (
        select(WorkspaceUserBinding)
        .join(User, User.id == WorkspaceUserBinding.user_id)
        .options(joinedload(WorkspaceUserBinding.user))
        .where(*user_filters)
    )
    if requested_role_values:
        user_query = user_query.where(WorkspaceUserBinding.role.in_(requested_role_values))
    user_query = user_query.order_by(user_role_priority.asc(), User.full_name.asc())
    return [
        serialize_workspace_member_binding(binding)
        for binding in db.scalars(user_query).all()
    ]
