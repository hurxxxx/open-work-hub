from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from sqlalchemy import and_, false, or_, select, true
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import OrgUnit, Team, TeamMember


@dataclass(frozen=True)
class AccessScopeRules:
    workspace_id: str
    workspace_role: str | None
    user_id: str
    org_unit_ids: Sequence[str] = ()
    team_ids: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "org_unit_ids", tuple(str(item) for item in self.org_unit_ids if item)
        )
        object.__setattr__(self, "team_ids", tuple(str(item) for item in self.team_ids if item))

    def can_access(self, scope_kind: str | None, scope_id: str | None) -> bool:
        if self.workspace_role == "admin":
            return True
        if self.workspace_role is None:
            return False
        if scope_kind == "workspace":
            return scope_id in {None, self.workspace_id}
        if scope_kind == "org_unit":
            return bool(scope_id) and scope_id in set(self.org_unit_ids)
        if scope_kind == "team":
            return bool(scope_id) and scope_id in set(self.team_ids)
        if scope_kind == "user":
            return scope_id == self.user_id
        return False

    def predicate(self, scope_kind_column: Any, scope_id_column: Any):
        if self.workspace_role == "admin":
            return true()
        if self.workspace_role is None:
            return false()
        return or_(
            and_(
                scope_kind_column == "workspace",
                or_(scope_id_column == self.workspace_id, scope_id_column.is_(None)),
            ),
            and_(
                scope_kind_column == "org_unit",
                scope_id_column.in_(self.org_unit_ids) if self.org_unit_ids else false(),
            ),
            and_(
                scope_kind_column == "team",
                scope_id_column.in_(self.team_ids) if self.team_ids else false(),
            ),
            and_(
                scope_kind_column == "user",
                scope_id_column == self.user_id,
            ),
        )


@dataclass(frozen=True)
class AccessScopePolicy:
    db: Session
    workspace_id: str
    workspace_role: str | None
    user_id: str
    primary_org_unit_id: str | None

    @cached_property
    def rules(self) -> AccessScopeRules:
        return AccessScopeRules(
            workspace_id=self.workspace_id,
            workspace_role=self.workspace_role,
            user_id=self.user_id,
            org_unit_ids=self.accessible_org_unit_ids(),
            team_ids=self.accessible_team_ids(),
        )

    def can_access(self, scope_kind: str | None, scope_id: str | None) -> bool:
        if self.workspace_role == "admin":
            return True
        if self.workspace_role is None:
            return False
        if scope_kind == "workspace":
            return scope_id in {None, self.workspace_id}
        if scope_kind == "user":
            return scope_id == self.user_id
        if scope_kind == "org_unit":
            return AccessScopeRules(
                workspace_id=self.workspace_id,
                workspace_role=self.workspace_role,
                user_id=self.user_id,
                org_unit_ids=self.accessible_org_unit_ids(),
            ).can_access(scope_kind, scope_id)
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
        return query.join(TeamMember, TeamMember.team_id == Team.id).where(
            TeamMember.user_id == self.user_id
        )

    def accessible_team_ids(self) -> list[str]:
        return [
            str(team_id)
            for team_id in self.db.scalars(self.active_team_ids_query()).all()
            if team_id
        ]

    def accessible_org_unit_ids(self) -> list[str]:
        if self.workspace_role == "admin":
            return [
                str(org_unit_id)
                for org_unit_id in self.db.scalars(
                    select(OrgUnit.id).where(OrgUnit.active.is_(True))
                ).all()
                if org_unit_id
            ]
        org_unit_id = self.primary_org_unit_id
        if not org_unit_id:
            return []
        org_unit_ids: list[str] = []
        visited: set[str] = set()
        while org_unit_id and org_unit_id not in visited:
            visited.add(org_unit_id)
            row = self.db.execute(
                select(OrgUnit.id, OrgUnit.parent_id).where(
                    OrgUnit.id == org_unit_id,
                    OrgUnit.active.is_(True),
                )
            ).one_or_none()
            if row is None:
                break
            current_id, parent_id = row
            org_unit_ids.append(str(current_id))
            org_unit_id = parent_id
        return org_unit_ids
