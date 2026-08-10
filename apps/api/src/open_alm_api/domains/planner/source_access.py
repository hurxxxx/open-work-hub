from __future__ import annotations

from sqlalchemy import false

from open_alm_api.domains.planner.models import PlannerEvent
from open_alm_api.domains.retrieval.partition_adapter_ids import (
    PLANNER_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_alm_api.domains.retrieval.partition_adapter_registry import bind_model_partition
from open_alm_api.domains.source_access.resource_types import PLANNER_EVENT_RESOURCE_TYPE


def planner_event_read_predicate(policy):
    del policy
    return false()


def can_read_planner_event(policy, event_id: str) -> bool:
    del policy, event_id
    return False


def has_accessible_planner_event(policy) -> bool:
    del policy
    return False


class PlannerEventSourceAccessAdapter:
    adapter_id = PLANNER_RETRIEVAL_PARTITION_ADAPTER_ID
    partition_adapter_id = PLANNER_RETRIEVAL_PARTITION_ADAPTER_ID
    source_namespace = "planner"
    resource_types = (PLANNER_EVENT_RESOURCE_TYPE,)
    allowed_candidate_scopes = ("personal",)
    allowed_transitions: tuple[str, ...] = ()
    transition_mode = "source_owned"
    keyword_acl_entity_types: tuple[str, ...] = ()

    def bind_resource_partition(
        self,
        db,
        *,
        resource_type: str,
        resource_id: str,
    ):
        return bind_model_partition(
            db,
            model=PlannerEvent,
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
        return can_read_planner_event(policy, resource_id)

    def can_read_rag_resource(
        self,
        policy,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        del resource_type
        return can_read_planner_event(policy, resource_id)

    def has_accessible_source(
        self,
        policy,
        *,
        resource_type: str,
    ) -> bool:
        del resource_type
        return has_accessible_planner_event(policy)

    def keyword_acl_branches(self, policy):
        del policy
        return []


__all__ = [
    "PLANNER_RETRIEVAL_PARTITION_ADAPTER_ID",
    "PlannerEventSourceAccessAdapter",
    "can_read_planner_event",
    "has_accessible_planner_event",
    "planner_event_read_predicate",
]
