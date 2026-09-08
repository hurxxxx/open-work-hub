from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, exists, false, or_, select, true

from open_work_hub_api.domains.docs.models import (
    DocMeetingAccess,
    NativeDoc,
    NativeDocGroupShare,
    NativeDocTarget,
    NativeDocUserShare,
)
from open_work_hub_api.domains.retrieval.partition_adapter_ids import (
    DOCS_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_work_hub_api.domains.search.target_keys import (
    search_target_key,
    search_target_legacy_key,
)
from open_work_hub_api.domains.source_access.resource_types import NATIVE_DOC_RESOURCE_TYPE


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _target_acl_keys(*, app: str, target_type: str, target_id: str) -> list[str]:
    return list(
        dict.fromkeys(
            [
                search_target_key(
                    app=app,
                    target_type=target_type,
                    target_id=target_id,
                ),
                search_target_legacy_key(
                    target_type=target_type,
                    target_id=target_id,
                ),
            ]
        )
    )


def _target_space_ids_query(policy):
    from open_work_hub_api.domains.pms.access import accessible_space_ids_query

    return accessible_space_ids_query(policy.db, user_id=policy.user.id)


def native_doc_read_predicate(policy):
    from open_work_hub_api.domains.groups.service import user_group_ids_query

    now = _utcnow()
    return or_(
        NativeDoc.owner_id == policy.user.id,
        NativeDoc.company_visible.is_(True),
        and_(
            NativeDoc.ownership_kind == "company", true() if policy.is_platform_admin else false()
        ),
        exists().where(
            NativeDocUserShare.doc_id == NativeDoc.id,
            NativeDocUserShare.user_id == policy.user.id,
            NativeDocUserShare.access_level.in_(("read", "edit")),
        ),
        exists().where(
            NativeDocGroupShare.doc_id == NativeDoc.id,
            NativeDocGroupShare.group_id.in_(user_group_ids_query(policy.user.id)),
            NativeDocGroupShare.access_level.in_(("read", "edit")),
        ),
        exists().where(
            DocMeetingAccess.doc_id == NativeDoc.id,
            DocMeetingAccess.user_id == policy.user.id,
            DocMeetingAccess.access_level.in_(("read", "edit")),
            DocMeetingAccess.revoked_at.is_(None),
            or_(DocMeetingAccess.expires_at.is_(None), DocMeetingAccess.expires_at > now),
        ),
        exists().where(
            NativeDocTarget.doc_id == NativeDoc.id,
            NativeDocTarget.target_app == "pms",
            NativeDocTarget.target_type == "space",
            NativeDocTarget.target_id.in_(_target_space_ids_query(policy)),
        ),
    )


def restrict_visible_native_docs(policy, base):
    return base.where(native_doc_read_predicate(policy))


def visible_native_doc_source_kinds(policy) -> list[str]:
    return sorted(
        str(source_kind)
        for source_kind in policy.db.scalars(
            select(NativeDoc.source_kind)
            .where(
                NativeDoc.trashed_at.is_(None),
                NativeDoc.source_kind.is_not(None),
                native_doc_read_predicate(policy),
            )
            .distinct()
        ).all()
        if source_kind
    )


def visible_rag_native_doc_source_kinds(policy) -> list[str]:
    return sorted(
        str(source_kind)
        for source_kind in policy.db.scalars(
            select(NativeDoc.source_kind)
            .where(
                NativeDoc.trashed_at.is_(None),
                NativeDoc.rag_scope == "official",
                NativeDoc.source_kind.is_not(None),
                native_doc_read_predicate(policy),
            )
            .distinct()
        ).all()
        if source_kind
    )


def can_read_native_doc(policy, doc_id: str) -> bool:
    return (
        policy.db.scalar(
            select(NativeDoc.id)
            .where(
                NativeDoc.id == doc_id,
                NativeDoc.trashed_at.is_(None),
                native_doc_read_predicate(policy),
            )
            .limit(1)
        )
        is not None
    )


def can_read_official_native_doc(policy, doc_id: str) -> bool:
    return (
        policy.db.scalar(
            select(NativeDoc.id)
            .where(
                NativeDoc.id == doc_id,
                NativeDoc.trashed_at.is_(None),
                NativeDoc.rag_scope == "official",
                native_doc_read_predicate(policy),
            )
            .limit(1)
        )
        is not None
    )


class NativeDocSourceAccessAdapter:
    app_id = "docs"
    adapter_id = DOCS_RETRIEVAL_PARTITION_ADAPTER_ID
    partition_adapter_id = DOCS_RETRIEVAL_PARTITION_ADAPTER_ID
    source_namespace = "docs"
    resource_types = (NATIVE_DOC_RESOURCE_TYPE,)
    allowed_candidate_scopes = ("company", "personal")
    allowed_transitions: tuple[str, ...] = ()
    transition_mode = "source_owned"
    keyword_acl_entity_types = ("doc",)

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
            model=NativeDoc,
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
        return can_read_native_doc(policy, resource_id)

    def can_read_rag_resource(
        self,
        policy,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        del resource_type
        return can_read_official_native_doc(policy, resource_id)

    def has_accessible_source(
        self,
        policy,
        *,
        resource_type: str,
    ) -> bool:
        del resource_type
        return (
            policy.db.scalar(
                select(NativeDoc.id)
                .where(
                    NativeDoc.trashed_at.is_(None),
                    native_doc_read_predicate(policy),
                )
                .limit(1)
            )
            is not None
        )

    def keyword_acl_branches(self, policy):
        team_ids = policy._accessible_team_ids()
        clauses = [
            policy._keyword_acl_clause("visibility", "company"),
            policy._keyword_acl_clause("owner_user_id", policy.user.id),
            policy._keyword_acl_clause("shared_user_ids", policy.user.id),
            policy._keyword_acl_clause("granted_user_ids", policy.user.id),
        ]
        if policy.is_platform_admin:
            clauses.append(policy._keyword_acl_clause("ownership_kind", "company"))
        group_ids = policy._current_group_ids()
        if group_ids:
            clauses.append(policy._keyword_acl_clause("shared_group_ids", group_ids))
        if team_ids:
            clauses.append(policy._keyword_acl_clause("team_ids", team_ids))
        return [policy._keyword_entity_branch("doc", clauses)]


__all__ = [
    "DOCS_RETRIEVAL_PARTITION_ADAPTER_ID",
    "NativeDocSourceAccessAdapter",
    "can_read_native_doc",
    "can_read_official_native_doc",
    "native_doc_read_predicate",
    "restrict_visible_native_docs",
    "visible_native_doc_source_kinds",
    "visible_rag_native_doc_source_kinds",
]
