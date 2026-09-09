from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User, UserSystemRole
from open_work_hub_api.domains.groups.service import current_group_ids


@dataclass(frozen=True)
class AccessScopeRules:
    """Pure projection of source-owned grants; personal scope has no admin override."""

    user_id: str
    active: bool = False
    platform_admin: bool = False
    team_ids: Sequence[str] = ()
    group_ids: Sequence[str] = ()

    def can_access(self, scope_kind: str | None, scope_id: str | None) -> bool:
        if not self.active:
            return False
        if scope_kind == "company":
            return scope_id is None
        if scope_kind == "user":
            return bool(scope_id) and scope_id == self.user_id
        if scope_kind == "group":
            return bool(scope_id) and scope_id in self.group_ids
        if scope_kind == "team":
            return bool(scope_id) and scope_id in self.team_ids
        return False

    def predicate(self, scope_kind_column: Any, scope_id_column: Any):
        if not self.active:
            return false()
        return or_(
            and_(scope_kind_column == "company", scope_id_column.is_(None)),
            and_(scope_kind_column == "user", scope_id_column == self.user_id),
            and_(scope_kind_column == "group", scope_id_column.in_(self.group_ids)),
            and_(scope_kind_column == "team", scope_id_column.in_(self.team_ids)),
        )


@dataclass(frozen=True)
class AccessScopePolicy:
    db: Session
    user_id: str

    @property
    def rules(self) -> AccessScopeRules:
        active = (
            self.db.scalar(
                select(User.id).where(
                    User.id == self.user_id,
                    User.status == "active",
                    User.login_blocked.is_(False),
                    User.must_change_password.is_(False),
                )
            )
            is not None
        )
        admin = (
            self.db.scalar(
                select(UserSystemRole.id).where(
                    UserSystemRole.user_id == self.user_id, UserSystemRole.role == "platform_admin"
                )
            )
            is not None
        )
        return AccessScopeRules(
            user_id=self.user_id,
            active=active,
            platform_admin=admin,
            team_ids=self.accessible_team_ids(),
            group_ids=current_group_ids(self.db, self.user_id),
        )

    def can_access(self, scope_kind: str | None, scope_id: str | None) -> bool:
        return self.rules.can_access(scope_kind, scope_id)

    def predicate(self, scope_kind_column: Any, scope_id_column: Any):
        return self.rules.predicate(scope_kind_column, scope_id_column)

    def active_team_ids_query(self):
        from open_work_hub_api.domains.pms.access import accessible_space_ids_query

        return accessible_space_ids_query(self.db, user_id=self.user_id)

    def accessible_team_ids(self) -> list[str]:
        return list(self.db.scalars(self.active_team_ids_query()))
