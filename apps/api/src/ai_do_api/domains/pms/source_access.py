from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import exists, false, or_, select

from ai_do_api.domains.auth.models import Team, TeamMember
from ai_do_api.domains.pms.models import Task, TaskList, TaskUserAccess
from ai_do_api.domains.retrieval.partition_adapter_ids import (
    PMS_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from ai_do_api.domains.source_access.resource_types import PMS_TASK_RESOURCE_TYPE


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def accessible_pms_task_query(policy):
    if policy.workspace_role is None:
        return select(Task.id).where(false())

    now = _utcnow()
    accessible_team_ids = (
        select(Team.id)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(
            Team.workspace_id == policy.workspace.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            TeamMember.user_id == policy.user.id,
        )
    )
    team_access = TaskList.team_id.in_(accessible_team_ids)
    task_grant = exists(
        select(TaskUserAccess.id).where(
            TaskUserAccess.task_id == Task.id,
            TaskUserAccess.user_id == policy.user.id,
            TaskUserAccess.revoked_at.is_(None),
            or_(TaskUserAccess.expires_at.is_(None), TaskUserAccess.expires_at > now),
        )
    )
    return (
        select(Task.id)
        .join(TaskList, Task.list_id == TaskList.id)
        .join(Team, TaskList.team_id == Team.id)
        .where(
            Task.archived.is_(False),
            TaskList.archived.is_(False),
            Team.workspace_id == policy.workspace.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            or_(team_access, task_grant),
        )
    )


def can_read_pms_task(policy, task_id: str) -> bool:
    return (
        policy.db.scalar(accessible_pms_task_query(policy).where(Task.id == task_id).limit(1))
        is not None
    )


def has_accessible_pms_task(policy) -> bool:
    return policy.db.scalar(accessible_pms_task_query(policy).limit(1)) is not None


def resolve_pms_task_workspace_id(db, *, task_id: str) -> str | None:
    return db.scalar(
        select(Team.workspace_id)
        .join(TaskList, TaskList.team_id == Team.id)
        .join(Task, Task.list_id == TaskList.id)
        .where(Task.id == task_id)
    )


class PmsTaskSourceAccessAdapter:
    adapter_id = PMS_RETRIEVAL_PARTITION_ADAPTER_ID
    partition_adapter_id = PMS_RETRIEVAL_PARTITION_ADAPTER_ID
    source_namespace = "pms"
    resource_types = (PMS_TASK_RESOURCE_TYPE,)
    allowed_candidate_scopes = ("workspace",)
    allowed_transitions: tuple[str, ...] = ()
    transition_mode = "source_owned"
    keyword_acl_entity_types = ("pms_task",)

    def bind_resource_partition(
        self,
        db,
        *,
        resource_type: str,
        resource_id: str,
    ):
        from ai_do_api.domains.retrieval.partition_adapter_registry import (
            bind_model_partition,
        )

        return bind_model_partition(
            db,
            model=Task,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def can_read_resource(
        self,
        policy,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        del resource_type
        return can_read_pms_task(policy, resource_id)

    def can_read_rag_resource(
        self,
        policy,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        del resource_type
        return can_read_pms_task(policy, resource_id)

    def has_accessible_source(
        self,
        policy,
        *,
        resource_type: str,
    ) -> bool:
        del resource_type
        return has_accessible_pms_task(policy)

    def keyword_acl_branches(self, policy):
        if policy.workspace_role is None:
            return [
                policy._keyword_entity_branch(
                    "pms_task",
                    [policy._keyword_acl_clause("team_ids", "__no_pms_task_access__")],
                )
            ]
        if not hasattr(policy, "db"):
            team_ids = policy._accessible_team_ids()
        else:
            team_ids = [
                str(team_id)
                for team_id in policy.db.scalars(
                    select(Team.id)
                    .join(TeamMember, TeamMember.team_id == Team.id)
                    .where(
                        Team.workspace_id == policy.workspace.id,
                        Team.active.is_(True),
                        Team.trashed_at.is_(None),
                        TeamMember.user_id == policy.user.id,
                    )
                ).all()
                if team_id
            ]
        clauses = [policy._keyword_acl_clause("granted_user_ids", policy.user.id)]
        if team_ids:
            clauses.append(policy._keyword_acl_clause("team_ids", team_ids))
        return [policy._keyword_entity_branch("pms_task", clauses)]


__all__ = [
    "PMS_RETRIEVAL_PARTITION_ADAPTER_ID",
    "PmsTaskSourceAccessAdapter",
    "accessible_pms_task_query",
    "can_read_pms_task",
    "has_accessible_pms_task",
    "resolve_pms_task_workspace_id",
]
