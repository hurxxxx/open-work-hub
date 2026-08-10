from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.access import (
    normalize_team_role,
    resolve_workspace_role,
    team_role_allows,
    workspace_role_allows,
)
from open_work_hub_api.domains.auth.models import Team, TeamMember, User, Workspace


@dataclass(frozen=True)
class TargetRef:
    app: str
    type: str
    id: str


@dataclass(frozen=True)
class TargetAccessProjection:
    can_view: bool
    can_edit: bool
    can_manage: bool


class TargetRecord(Protocol):
    target_app: str
    target_type: str
    target_id: str


class TargetAccessAdapter(Protocol):
    def label_for(
        self,
        *,
        db: Session,
        workspace: Workspace,
        ref: TargetRef,
    ) -> str | None: ...

    def can_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: TargetRef,
    ) -> bool: ...

    def project_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: TargetRef,
    ) -> TargetAccessProjection: ...


_target_adapters: dict[str, TargetAccessAdapter] = {}


def _empty_projection() -> TargetAccessProjection:
    return TargetAccessProjection(False, False, False)


def _is_workspace_sidebar_ref(ref: TargetRef, workspace: Workspace) -> bool:
    return ref.type == "workspace_sidebar" and ref.id == workspace.id


def _project_workspace_role(role: str | None) -> TargetAccessProjection:
    return TargetAccessProjection(
        can_view=role is not None,
        can_edit=workspace_role_allows(role, "member"),
        can_manage=workspace_role_allows(role, "admin"),
    )


def _active_workspace_team(
    db: Session,
    *,
    workspace: Workspace,
    team_id: str,
) -> Team | None:
    return db.scalar(
        select(Team).where(
            Team.id == team_id,
            Team.workspace_id == workspace.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
        )
    )


def _project_team_role(role: str | None) -> TargetAccessProjection:
    return TargetAccessProjection(
        can_view=role is not None,
        can_edit=team_role_allows(role, "member"),
        can_manage=team_role_allows(role, "admin"),
    )


def _direct_team_member_role(db: Session, *, user: User, team: Team) -> str | None:
    role = db.scalar(
        select(TeamMember.role).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user.id,
        )
    )
    return normalize_team_role(role)


def register_target_access_adapter(
    app_id: str,
    adapter: TargetAccessAdapter,
) -> None:
    if app_id in _target_adapters:
        raise ValueError(f"Target access adapter already registered for {app_id}")
    _target_adapters[app_id] = adapter


def get_target_access_adapter(app_id: str) -> TargetAccessAdapter | None:
    return _target_adapters.get(app_id)


def has_target_access_adapter(app_id: str) -> bool:
    return app_id in _target_adapters


def target_access_app_ids() -> tuple[str, ...]:
    return tuple(sorted(_target_adapters))


def reset_target_access_adapters() -> None:
    _target_adapters.clear()


class _DocsTargetAdapter:
    def label_for(
        self,
        *,
        db: Session,
        workspace: Workspace,
        ref: TargetRef,
    ) -> str | None:
        if not _is_workspace_sidebar_ref(ref, workspace):
            return None
        return "Workspace Docs"

    def can_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: TargetRef,
    ) -> bool:
        if not _is_workspace_sidebar_ref(ref, workspace):
            return False
        return resolve_workspace_role(db, user, workspace.id) is not None

    def project_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: TargetRef,
    ) -> TargetAccessProjection:
        if not _is_workspace_sidebar_ref(ref, workspace):
            return _empty_projection()
        role = resolve_workspace_role(db, user, workspace.id)
        return _project_workspace_role(role)


class _PmsTargetAdapter:
    def label_for(
        self,
        *,
        db: Session,
        workspace: Workspace,
        ref: TargetRef,
    ) -> str | None:
        if ref.type != "space":
            return None
        team = _active_workspace_team(db, workspace=workspace, team_id=ref.id)
        return team.name if team is not None else None

    def can_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: TargetRef,
    ) -> bool:
        if ref.type != "space":
            return False
        team = _active_workspace_team(db, workspace=workspace, team_id=ref.id)
        if team is None:
            return False
        return _direct_team_member_role(db, user=user, team=team) is not None

    def project_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: TargetRef,
    ) -> TargetAccessProjection:
        if ref.type != "space":
            return _empty_projection()
        team = _active_workspace_team(db, workspace=workspace, team_id=ref.id)
        if team is None:
            return _empty_projection()
        role = _direct_team_member_role(db, user=user, team=team)
        return _project_team_role(role)


def ensure_builtin_target_access_adapters_registered() -> None:
    for app_id, adapter in (
        ("docs", _DocsTargetAdapter()),
        ("pms", _PmsTargetAdapter()),
    ):
        if has_target_access_adapter(app_id):
            continue
        register_target_access_adapter(app_id, adapter)


def resolve_target_label(
    *,
    db: Session,
    workspace: Workspace,
    target: TargetRecord | None,
) -> str:
    if target is None:
        return "Unfiled"
    ensure_builtin_target_access_adapters_registered()
    ref = _target_ref_from_record(target)
    adapter = get_target_access_adapter(ref.app)
    if adapter is None:
        return f"{ref.app}:{ref.type}"
    return adapter.label_for(db=db, workspace=workspace, ref=ref) or "Unfiled"


def _target_ref_from_record(target: TargetRecord) -> TargetRef:
    return TargetRef(
        app=target.target_app,
        type=target.target_type,
        id=target.target_id,
    )


def target_access_allowed(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: TargetRef,
) -> bool:
    ensure_builtin_target_access_adapters_registered()
    adapter = get_target_access_adapter(ref.app)
    if adapter is None:
        return False
    return adapter.can_access(db=db, user=user, workspace=workspace, ref=ref)


def project_target_access(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: TargetRef,
) -> TargetAccessProjection:
    ensure_builtin_target_access_adapters_registered()
    adapter = get_target_access_adapter(ref.app)
    if adapter is None:
        return _empty_projection()
    return adapter.project_access(db=db, user=user, workspace=workspace, ref=ref)


__all__ = [
    "TargetAccessAdapter",
    "TargetAccessProjection",
    "TargetRecord",
    "TargetRef",
    "ensure_builtin_target_access_adapters_registered",
    "get_target_access_adapter",
    "has_target_access_adapter",
    "project_target_access",
    "register_target_access_adapter",
    "reset_target_access_adapters",
    "resolve_target_label",
    "target_access_allowed",
    "target_access_app_ids",
]
