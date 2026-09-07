from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import Team, TeamMember
from open_work_hub_api.domains.auth.roles import team_role_allows_predicate


@dataclass(frozen=True)
class AccessScopeRules:
    workspace_id: str
    workspace_role: str | None
    user_id: str
    team_ids: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "team_ids", tuple(str(item) for item in self.team_ids if item))

    def can_access(self, scope_kind: str | None, scope_id: str | None) -> bool:
        if self.workspace_role not in {"member", "admin"}:
            return False
        if scope_kind == "workspace":
            return scope_id in {None, self.workspace_id}
        if scope_kind == "team":
            return bool(scope_id) and scope_id in set(self.team_ids)
        if scope_kind == "user":
            return bool(scope_id) and (self.workspace_role == "admin" or scope_id == self.user_id)
        return False

    def predicate(self, scope_kind_column: Any, scope_id_column: Any):
        if self.workspace_role not in {"member", "admin"}:
            return false()
        return or_(
            and_(
                scope_kind_column == "workspace",
                or_(scope_id_column == self.workspace_id, scope_id_column.is_(None)),
            ),
            and_(
                scope_kind_column == "team",
                scope_id_column.in_(self.team_ids) if self.team_ids else false(),
            ),
            and_(
                scope_kind_column == "user",
                and_(scope_id_column.is_not(None), scope_id_column != "")
                if self.workspace_role == "admin"
                else scope_id_column == self.user_id,
            ),
        )


@dataclass(frozen=True)
class AccessScopePolicy:
    db: Session
    workspace_id: str
    workspace_role: str | None
    user_id: str

    @cached_property
    def rules(self) -> AccessScopeRules:
        return AccessScopeRules(
            workspace_id=self.workspace_id,
            workspace_role=self.workspace_role,
            user_id=self.user_id,
            team_ids=self.accessible_team_ids(),
        )

    def can_access(self, scope_kind: str | None, scope_id: str | None) -> bool:
        if self.workspace_role not in {"member", "admin"}:
            return False
        if scope_kind == "workspace":
            return scope_id in {None, self.workspace_id}
        if scope_kind == "user":
            return bool(scope_id) and (self.workspace_role == "admin" or scope_id == self.user_id)
        if scope_kind == "team":
            return AccessScopeRules(
                workspace_id=self.workspace_id,
                workspace_role=self.workspace_role,
                user_id=self.user_id,
                team_ids=self.accessible_team_ids(),
            ).can_access(scope_kind, scope_id)
        return False

    def predicate(self, scope_kind_column: Any, scope_id_column: Any):
        return self.rules.predicate(scope_kind_column, scope_id_column)

    def active_team_ids_query(self):
        query = select(Team.id).where(
            Team.workspace_id == self.workspace_id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
        )
        if self.workspace_role == "admin":
            return query
        if self.workspace_role != "member":
            return query.where(false())
        return query.join(TeamMember, TeamMember.team_id == Team.id).where(
            TeamMember.user_id == self.user_id,
            team_role_allows_predicate(TeamMember.role),
        )

    def accessible_team_ids(self) -> list[str]:
        return [
            str(team_id)
            for team_id in self.db.scalars(self.active_team_ids_query()).all()
            if team_id
        ]
