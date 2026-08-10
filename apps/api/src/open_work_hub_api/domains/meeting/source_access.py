from __future__ import annotations

from sqlalchemy import exists, or_, select

from open_work_hub_api.domains.meeting.models import Meeting, MeetingAttendee
from open_work_hub_api.domains.retrieval.partition_adapter_ids import (
    MEETING_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_work_hub_api.domains.retrieval.partition_adapter_registry import bind_model_partition
from open_work_hub_api.domains.source_access.resource_types import MEETING_RESOURCE_TYPE


def meeting_read_predicate(policy):
    return or_(
        Meeting.organizer_id == policy.user.id,
        exists(
            select(MeetingAttendee.id).where(
                MeetingAttendee.meeting_id == Meeting.id,
                MeetingAttendee.user_id == policy.user.id,
            )
        ),
    )


def can_read_meeting(policy, meeting_id: str) -> bool:
    return (
        policy.db.scalar(
            select(Meeting.id)
            .where(
                Meeting.id == meeting_id,
                Meeting.workspace_id == policy.workspace.id,
                meeting_read_predicate(policy),
            )
            .limit(1)
        )
        is not None
    )


def has_accessible_meeting(policy) -> bool:
    return (
        policy.db.scalar(
            select(Meeting.id)
            .where(
                Meeting.workspace_id == policy.workspace.id,
                meeting_read_predicate(policy),
            )
            .limit(1)
        )
        is not None
    )


class MeetingSourceAccessAdapter:
    adapter_id = MEETING_RETRIEVAL_PARTITION_ADAPTER_ID
    partition_adapter_id = MEETING_RETRIEVAL_PARTITION_ADAPTER_ID
    source_namespace = "meeting"
    resource_types = (MEETING_RESOURCE_TYPE,)
    allowed_candidate_scopes = ("workspace",)
    allowed_transitions: tuple[str, ...] = ()
    transition_mode = "source_owned"
    keyword_acl_entity_types = ("meeting",)

    def bind_resource_partition(
        self,
        db,
        *,
        resource_type: str,
        resource_id: str,
    ):
        return bind_model_partition(
            db,
            model=Meeting,
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
        return can_read_meeting(policy, resource_id)

    def can_read_rag_resource(
        self,
        policy,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        del resource_type
        return can_read_meeting(policy, resource_id)

    def has_accessible_source(
        self,
        policy,
        *,
        resource_type: str,
    ) -> bool:
        del resource_type
        return has_accessible_meeting(policy)

    def keyword_acl_branches(self, policy):
        return [
            policy._keyword_entity_branch(
                "meeting",
                [
                    policy._keyword_acl_clause("owner_user_id", policy.user.id),
                    policy._keyword_acl_clause("participant_user_ids", policy.user.id),
                ],
            )
        ]


__all__ = [
    "MEETING_RETRIEVAL_PARTITION_ADAPTER_ID",
    "MeetingSourceAccessAdapter",
    "can_read_meeting",
    "has_accessible_meeting",
    "meeting_read_predicate",
]
