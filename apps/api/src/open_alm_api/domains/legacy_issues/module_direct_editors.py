from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.access import is_platform_admin_user, record_audit_log
from open_alm_api.domains.auth.models import User, Workspace, WorkspaceUserBinding, utcnow_naive
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.legacy_issues.module_access import LEGACY_ISSUE_MODULE_KEYS
from open_alm_api.domains.legacy_issues.models import LegacyIssueModuleAccessRule


DIRECT_EDIT_SUBJECT_TYPE = "user"
DIRECT_EDIT_MANAGED_ROLE = "editor"
DIRECT_EDIT_EFFECTIVE_ROLES = frozenset({"editor", "manager"})


@dataclass(frozen=True)
class LegacyIssueModuleDirectEditorDTO:
    id: str
    module_key: str
    user_id: str
    display_name: str
    email: str
    role: str
    can_revoke: bool
    active_member: bool
    created_at: Any
    updated_at: Any


def can_user_direct_edit_module(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    module_key: str,
) -> bool:
    normalized_module_key = normalize_direct_editor_module_key(module_key)
    if is_platform_admin_user(user, db):
        return True
    return (
        db.scalar(
            select(LegacyIssueModuleAccessRule.id)
            .join(
                WorkspaceUserBinding,
                (WorkspaceUserBinding.workspace_id == LegacyIssueModuleAccessRule.workspace_id)
                & (WorkspaceUserBinding.user_id == LegacyIssueModuleAccessRule.subject_id),
            )
            .join(User, User.id == LegacyIssueModuleAccessRule.subject_id)
            .where(
                LegacyIssueModuleAccessRule.workspace_id == workspace.id,
                LegacyIssueModuleAccessRule.module_key == normalized_module_key,
                LegacyIssueModuleAccessRule.subject_type == DIRECT_EDIT_SUBJECT_TYPE,
                LegacyIssueModuleAccessRule.subject_id == user.id,
                LegacyIssueModuleAccessRule.role.in_(DIRECT_EDIT_EFFECTIVE_ROLES),
                LegacyIssueModuleAccessRule.active.is_(True),
                User.status == "active",
                LegacyIssueModuleAccessRule.updated_at >= WorkspaceUserBinding.created_at,
            )
            .limit(1)
        )
        is not None
    )


def list_module_direct_editors(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    module_key: str | None = None,
) -> list[LegacyIssueModuleDirectEditorDTO]:
    require_platform_admin(db, user=actor)
    statement = (
        select(
            LegacyIssueModuleAccessRule,
            User,
            WorkspaceUserBinding.created_at.label("workspace_binding_created_at"),
        )
        .outerjoin(User, User.id == LegacyIssueModuleAccessRule.subject_id)
        .outerjoin(
            WorkspaceUserBinding,
            (WorkspaceUserBinding.workspace_id == LegacyIssueModuleAccessRule.workspace_id)
            & (WorkspaceUserBinding.user_id == LegacyIssueModuleAccessRule.subject_id),
        )
        .where(
            LegacyIssueModuleAccessRule.workspace_id == workspace.id,
            LegacyIssueModuleAccessRule.subject_type == DIRECT_EDIT_SUBJECT_TYPE,
            LegacyIssueModuleAccessRule.role.in_(DIRECT_EDIT_EFFECTIVE_ROLES),
            LegacyIssueModuleAccessRule.active.is_(True),
        )
    )
    if module_key is not None:
        statement = statement.where(
            LegacyIssueModuleAccessRule.module_key == normalize_direct_editor_module_key(module_key)
        )
    rows = db.execute(
        statement.order_by(
            LegacyIssueModuleAccessRule.module_key.asc(),
            func.coalesce(User.full_name, LegacyIssueModuleAccessRule.subject_id).asc(),
            User.email.asc().nullslast(),
        )
    ).all()
    return [
        module_direct_editor_dto(
            rule,
            user,
            active_member=bool(
                user is not None
                and user.status == "active"
                and workspace_binding_created_at is not None
                and rule.updated_at >= workspace_binding_created_at
            ),
        )
        for rule, user, workspace_binding_created_at in rows
    ]


def grant_module_direct_editor(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    module_key: str,
    user_id: str,
) -> LegacyIssueModuleDirectEditorDTO:
    require_platform_admin(db, user=actor)
    normalized_module_key = normalize_direct_editor_module_key(module_key)
    target, membership_created_at = require_active_workspace_user(
        db,
        workspace=workspace,
        user_id=user_id,
    )
    row = _get_direct_editor_rule(
        db,
        workspace=workspace,
        module_key=normalized_module_key,
        user_id=user_id,
        lock=True,
    )
    changed = False
    if row is None:
        row = LegacyIssueModuleAccessRule(
            id=new_id(),
            workspace_id=workspace.id,
            module_key=normalized_module_key,
            subject_type=DIRECT_EDIT_SUBJECT_TYPE,
            subject_id=user_id,
            role=DIRECT_EDIT_MANAGED_ROLE,
            active=True,
            created_by_id=actor.id,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            row = _get_direct_editor_rule(
                db,
                workspace=workspace,
                module_key=normalized_module_key,
                user_id=user_id,
                lock=True,
            )
            if row is None:
                raise
        else:
            changed = True
    if row.role == "manager":
        if not row.active:
            raise_direct_editor_role_conflict()
        return module_direct_editor_dto(
            row,
            target,
            active_member=row.updated_at >= membership_created_at,
        )
    if row.role != DIRECT_EDIT_MANAGED_ROLE:
        raise_direct_editor_role_conflict()
    if not row.active or row.updated_at < membership_created_at:
        row.active = True
        row.updated_at = max(utcnow_naive(), membership_created_at)
        changed = True
    if changed:
        record_audit_log(
            db,
            action="legacy_issues.module_direct_editor.grant",
            entity_kind="legacy_issue_module_direct_editor",
            entity_id=row.id,
            actor_user_id=actor.id,
            summary="Granted legacy issue published-revision direct edit access",
            payload={
                "workspace_id": workspace.id,
                "module_key": normalized_module_key,
                "user_id": user_id,
            },
        )
    db.flush()
    return module_direct_editor_dto(row, target, active_member=True)


def revoke_module_direct_editor(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    module_key: str,
    user_id: str,
) -> None:
    require_platform_admin(db, user=actor)
    normalized_module_key = normalize_direct_editor_module_key(module_key)
    row = _get_direct_editor_rule(
        db,
        workspace=workspace,
        module_key=normalized_module_key,
        user_id=user_id,
        lock=True,
    )
    if row is None or not row.active:
        return
    if row.role != DIRECT_EDIT_MANAGED_ROLE:
        raise_direct_editor_role_conflict()
    row.active = False
    row.updated_at = utcnow_naive()
    record_audit_log(
        db,
        action="legacy_issues.module_direct_editor.revoke",
        entity_kind="legacy_issue_module_direct_editor",
        entity_id=row.id,
        actor_user_id=actor.id,
        summary="Revoked legacy issue published-revision direct edit access",
        payload={
            "workspace_id": workspace.id,
            "module_key": normalized_module_key,
            "user_id": user_id,
        },
    )
    db.flush()


def require_platform_admin(db: Session, *, user: User) -> None:
    if not is_platform_admin_user(user, db):
        raise localized_http_exception(
            status_code=403,
            code="admin.platform_admin_required",
        )


def require_active_workspace_user(
    db: Session,
    *,
    workspace: Workspace,
    user_id: str,
) -> tuple[User, Any]:
    result = db.execute(
        select(User, WorkspaceUserBinding.created_at)
        .join(WorkspaceUserBinding, WorkspaceUserBinding.user_id == User.id)
        .where(
            User.id == user_id,
            User.status == "active",
            WorkspaceUserBinding.workspace_id == workspace.id,
        )
        .limit(1)
    ).one_or_none()
    if result is None:
        raise localized_http_exception(
            status_code=404,
            code="admin.workspace_member_not_found",
        )
    return result[0], result[1]


def normalize_direct_editor_module_key(module_key: str) -> str:
    normalized = module_key.strip()
    if normalized not in LEGACY_ISSUE_MODULE_KEYS:
        raise localized_http_exception(
            status_code=404,
            code="legacy_issues.module_not_found",
        )
    return normalized


def module_direct_editor_dto(
    row: LegacyIssueModuleAccessRule,
    user: User | None,
    *,
    active_member: bool,
) -> LegacyIssueModuleDirectEditorDTO:
    return LegacyIssueModuleDirectEditorDTO(
        id=row.id,
        module_key=row.module_key,
        user_id=row.subject_id,
        display_name=(
            user.display_name or user.full_name or user.email
            if user is not None
            else row.subject_id
        ),
        email=user.email if user is not None else "",
        role=row.role,
        can_revoke=row.role == DIRECT_EDIT_MANAGED_ROLE,
        active_member=active_member,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _get_direct_editor_rule(
    db: Session,
    *,
    workspace: Workspace,
    module_key: str,
    user_id: str,
    lock: bool,
) -> LegacyIssueModuleAccessRule | None:
    statement = select(LegacyIssueModuleAccessRule).where(
        LegacyIssueModuleAccessRule.workspace_id == workspace.id,
        LegacyIssueModuleAccessRule.module_key == module_key,
        LegacyIssueModuleAccessRule.subject_type == DIRECT_EDIT_SUBJECT_TYPE,
        LegacyIssueModuleAccessRule.subject_id == user_id,
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def raise_direct_editor_role_conflict() -> None:
    raise localized_http_exception(
        status_code=409,
        code="legacy_issues.module_direct_editor_role_conflict",
    )
