from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import exists, or_, select

from open_work_hub_api.domains.pms.models import Task, TaskList, TaskUserAccess
from open_work_hub_api.domains.pms.space_models import Team
from open_work_hub_api.domains.retrieval.partition_adapter_ids import (
    PMS_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_work_hub_api.domains.source_access.resource_types import PMS_TASK_RESOURCE_TYPE


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def accessible_pms_task_query(policy):
    from open_work_hub_api.domains.pms.access import accessible_space_ids_query

    now = _utcnow()
    accessible_team_ids = accessible_space_ids_query(policy.db, user_id=policy.user.id)
    team_access = TaskList.team_id.in_(accessible_team_ids)
    task_grant = exists(
        select(TaskUserAccess.id).where(
            TaskUserAccess.task_id == Task.id,
            TaskUserAccess.user_id == policy.user.id,
            TaskUserAccess.access_level.in_(("read", "edit")),
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


class PmsTaskSourceAccessAdapter:
    app_id = "pms"
    adapter_id = PMS_RETRIEVAL_PARTITION_ADAPTER_ID
    partition_adapter_id = PMS_RETRIEVAL_PARTITION_ADAPTER_ID
    source_namespace = "pms"
    resource_types = (PMS_TASK_RESOURCE_TYPE,)
    allowed_candidate_scopes = ("company",)
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
        from open_work_hub_api.domains.retrieval.partition_adapter_registry import (
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
        team_ids = policy._accessible_team_ids()
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
]
