from __future__ import annotations

from sqlalchemy import select

from ai_do_api.domains.auth.workspace_app_gate import is_platform_app_enabled
from ai_do_api.domains.qna.app_catalog import QA_ASSISTANT_WORKSPACE_APP
from ai_do_api.domains.qna.constants import QNA_SCOPE_KIND
from ai_do_api.domains.qna.constants import QNA_DOCUMENT_RESOURCE_TYPE
from ai_do_api.domains.qna.models import QnaDocument
from ai_do_api.domains.retrieval.partition_adapter_ids import (
    QNA_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from ai_do_api.domains.retrieval.partition_adapter_registry import bind_model_partition


def _can_read(policy, resource_id: str) -> bool:
    # The Q&A corpus is company-public; authenticated access is enforced before
    # this adapter is consulted.
    if not is_platform_app_enabled(policy.db, QA_ASSISTANT_WORKSPACE_APP.app_id):
        return False
    return (
        policy.db.scalar(
            select(QnaDocument.id)
            .where(
                QnaDocument.id == resource_id,
                QnaDocument.scope_kind == QNA_SCOPE_KIND,
            )
            .limit(1)
        )
        is not None
    )


def _has_accessible_source(policy) -> bool:
    if not is_platform_app_enabled(policy.db, QA_ASSISTANT_WORKSPACE_APP.app_id):
        return False
    return (
        policy.db.scalar(
            select(QnaDocument.id).where(QnaDocument.scope_kind == QNA_SCOPE_KIND).limit(1)
        )
        is not None
    )


class QnaDocumentSourceAccessAdapter:
    adapter_id = QNA_RETRIEVAL_PARTITION_ADAPTER_ID
    partition_adapter_id = QNA_RETRIEVAL_PARTITION_ADAPTER_ID
    source_namespace = "qna"
    resource_types = (QNA_DOCUMENT_RESOURCE_TYPE,)
    allowed_candidate_scopes = ("company", "workspace")
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
            model=QnaDocument,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def can_read_resource(self, policy, *, resource_type: str, resource_id: str) -> bool:
        del resource_type
        return _can_read(policy, resource_id)

    def can_read_rag_resource(self, policy, *, resource_type: str, resource_id: str) -> bool:
        del resource_type
        return _can_read(policy, resource_id)

    def authorize_many_rag_resources(
        self,
        policy,
        *,
        resource_type: str,
        resource_ids: tuple[str, ...],
    ) -> set[str]:
        del resource_type
        if not resource_ids:
            return set()
        if not is_platform_app_enabled(policy.db, QA_ASSISTANT_WORKSPACE_APP.app_id):
            return set()
        return set(
            policy.db.scalars(
                select(QnaDocument.id).where(
                    QnaDocument.id.in_(resource_ids),
                    QnaDocument.scope_kind == QNA_SCOPE_KIND,
                )
            ).all()
        )

    def has_accessible_source(self, policy, *, resource_type: str) -> bool:
        del resource_type
        return _has_accessible_source(policy)

    def keyword_acl_branches(self, policy):
        del policy
        return []


__all__ = [
    "QNA_RETRIEVAL_PARTITION_ADAPTER_ID",
    "QnaDocumentSourceAccessAdapter",
]
