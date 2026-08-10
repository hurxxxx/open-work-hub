from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import (
    OrgUnit,
    Team,
    TeamMember,
    User,
    UserSystemRole,
    Workspace,
    WorkspaceUserBinding,
)
from ai_do_api.domains.auth.roles import SYSTEM_PLATFORM_ADMIN, normalize_system_role
from ai_do_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileAccessGrant,
    FileManagerFileSourceMetadata,
)


def is_current_platform_admin(db: Session, user_id: str) -> bool:
    """Return a current-state platform-admin decision, never a stale policy hint."""

    user = _load_current_active_user(db, user_id)
    if user is None:
        return False
    if user.is_admin:
        return True
    roles = db.scalars(select(UserSystemRole.role).where(UserSystemRole.user_id == user_id)).all()
    return any(normalize_system_role(role) == SYSTEM_PLATFORM_ADMIN for role in roles)


def authorize_explicit_file_ids(
    db: Session,
    *,
    file_ids: Iterable[str],
    user_id: str,
    workspace_id: str | None,
) -> set[str]:
    """Authorize explicit-grant files from current source-owned database state.

    Missing metadata, unresolved ACLs, and resolved-but-empty ACLs all fail closed.
    Workspace roles are deliberately absent: workspace admins receive no implicit
    bypass. Platform admins retain an explicit operational bypass.
    """

    normalized_ids = tuple(dict.fromkeys(str(value) for value in file_ids if value))
    if not normalized_ids:
        return set()
    user = _load_current_active_user(db, user_id)
    if user is None:
        return set()
    if is_current_platform_admin(db, user_id):
        return set(normalized_ids)

    grant_conditions = _current_grant_conditions(
        db,
        user=user,
        workspace_id=workspace_id,
    )
    if not grant_conditions:
        return set()
    return set(
        db.scalars(
            select(FileManagerFileAccessGrant.file_id)
            .join(
                FileManagerFileSourceMetadata,
                FileManagerFileSourceMetadata.file_id == FileManagerFileAccessGrant.file_id,
            )
            .where(
                FileManagerFileAccessGrant.file_id.in_(normalized_ids),
                FileManagerFileSourceMetadata.acl_resolved.is_(True),
                or_(*grant_conditions),
            )
            .distinct()
        ).all()
    )


def has_any_explicit_file_access(
    db: Session,
    *,
    user_id: str,
    workspace_id: str | None,
) -> bool:
    """Check whether at least one live, in-scope explicit-grant file is readable."""

    user = _load_current_active_user(db, user_id)
    if user is None:
        return False
    scope_condition = FileManagerCorpus.access_scope_kind == "company"
    if workspace_id is not None:
        scope_condition = or_(
            scope_condition,
            and_(
                FileManagerCorpus.access_scope_kind == "workspace",
                FileManagerCorpus.managed_workspace_id == workspace_id,
            ),
        )
    base = (
        select(FileManagerFile.id)
        .join(FileManagerCorpus, FileManagerCorpus.id == FileManagerFile.corpus_id)
        .where(
            FileManagerCorpus.authorization_mode == "explicit_grants",
            scope_condition,
            FileManagerFile.deleted_at.is_(None),
        )
    )
    explicit_candidate_exists = db.scalar(base.limit(1)) is not None
    if not explicit_candidate_exists:
        return False
    if is_current_platform_admin(db, user_id):
        return True

    grant_conditions = _current_grant_conditions(
        db,
        user=user,
        workspace_id=workspace_id,
    )
    if not grant_conditions:
        return False
    statement = (
        base.join(
            FileManagerFileSourceMetadata,
            FileManagerFileSourceMetadata.file_id == FileManagerFile.id,
        )
        .join(
            FileManagerFileAccessGrant,
            FileManagerFileAccessGrant.file_id == FileManagerFile.id,
        )
        .where(
            FileManagerFileSourceMetadata.acl_resolved.is_(True),
            or_(*grant_conditions),
        )
        .limit(1)
    )
    return db.scalar(statement) is not None


def _current_grant_conditions(
    db: Session,
    *,
    user: User,
    workspace_id: str | None,
) -> list[object]:
    conditions: list[object] = [
        FileManagerFileAccessGrant.grant_type == "company",
        and_(
            FileManagerFileAccessGrant.grant_type == "user",
            FileManagerFileAccessGrant.target_id == user.id,
        ),
    ]

    if user.primary_org_unit_id is not None:
        org_is_active = db.scalar(
            select(OrgUnit.id).where(
                OrgUnit.id == user.primary_org_unit_id,
                OrgUnit.active.is_(True),
            )
        )
        if org_is_active is not None:
            conditions.append(
                and_(
                    FileManagerFileAccessGrant.grant_type == "org_unit",
                    FileManagerFileAccessGrant.target_id == user.primary_org_unit_id,
                )
            )

    if workspace_id is not None:
        workspace_is_current = db.scalar(
            select(Workspace.id).where(
                Workspace.id == workspace_id,
                Workspace.active.is_(True),
            )
        )
        binding_exists = db.scalar(
            select(WorkspaceUserBinding.id).where(
                WorkspaceUserBinding.workspace_id == workspace_id,
                WorkspaceUserBinding.user_id == user.id,
            )
        )
        if workspace_is_current is not None and binding_exists is not None:
            conditions.append(
                and_(
                    FileManagerFileAccessGrant.grant_type == "workspace",
                    FileManagerFileAccessGrant.target_id == workspace_id,
                )
            )

    team_statement = (
        select(Team.id)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(
            TeamMember.user_id == user.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
        )
    )
    if workspace_id is not None:
        team_statement = team_statement.where(Team.workspace_id == workspace_id)
    team_ids = tuple(db.scalars(team_statement).all())
    if team_ids:
        conditions.append(
            and_(
                FileManagerFileAccessGrant.grant_type == "team",
                FileManagerFileAccessGrant.target_id.in_(team_ids),
            )
        )
    return conditions


def _load_current_active_user(db: Session, user_id: str) -> User | None:
    return db.scalar(
        select(User)
        .where(
            User.id == user_id,
            User.status == "active",
            User.login_blocked.is_(False),
        )
        .execution_options(populate_existing=True)
    )


__all__ = [
    "authorize_explicit_file_ids",
    "has_any_explicit_file_access",
    "is_current_platform_admin",
]
