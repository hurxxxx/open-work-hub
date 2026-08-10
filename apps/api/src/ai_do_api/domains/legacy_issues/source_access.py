from __future__ import annotations

from sqlalchemy import select

from ai_do_api.domains.auth.access import workspace_role_allows
from ai_do_api.domains.legacy_issues.models import LegacyIssueRecord
from ai_do_api.domains.retrieval.partition_adapter_ids import (
    LEGACY_ISSUES_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from ai_do_api.domains.retrieval.partition_adapter_registry import bind_model_partition
from ai_do_api.domains.source_access.resource_types import (
    LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
)


def can_read_legacy_issue_record(policy, record_id: str) -> bool:
    if not workspace_role_allows(policy.workspace_role, "member"):
        return False
    return (
        policy.db.scalar(
            select(LegacyIssueRecord.id)
            .where(
                LegacyIssueRecord.id == record_id,
                LegacyIssueRecord.workspace_id == policy.workspace.id,
            )
            .limit(1)
        )
        is not None
    )


def has_accessible_legacy_issue_record(policy) -> bool:
    if not workspace_role_allows(policy.workspace_role, "member"):
        return False
    return (
        policy.db.scalar(
            select(LegacyIssueRecord.id)
            .where(LegacyIssueRecord.workspace_id == policy.workspace.id)
            .limit(1)
        )
        is not None
    )


class LegacyIssueRecordSourceAccessAdapter:
    adapter_id = LEGACY_ISSUES_RETRIEVAL_PARTITION_ADAPTER_ID
    partition_adapter_id = LEGACY_ISSUES_RETRIEVAL_PARTITION_ADAPTER_ID
    source_namespace = "legacy_issues"
    resource_types = (LEGACY_ISSUE_RECORD_RESOURCE_TYPE,)
    allowed_candidate_scopes = ("workspace",)
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
            model=LegacyIssueRecord,
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
        return can_read_legacy_issue_record(policy, resource_id)

    def can_read_rag_resource(
        self,
        policy,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        del resource_type
        return can_read_legacy_issue_record(policy, resource_id)

    def has_accessible_source(
        self,
        policy,
        *,
        resource_type: str,
    ) -> bool:
        del resource_type
        return has_accessible_legacy_issue_record(policy)

    def keyword_acl_branches(self, policy):
        del policy
        return []


__all__ = [
    "LEGACY_ISSUES_RETRIEVAL_PARTITION_ADAPTER_ID",
    "LegacyIssueRecordSourceAccessAdapter",
    "can_read_legacy_issue_record",
    "has_accessible_legacy_issue_record",
]
