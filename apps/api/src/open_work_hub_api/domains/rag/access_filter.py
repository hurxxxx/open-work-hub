from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.rag.contracts import RagVectorSearchHit
from open_work_hub_api.domains.source_access import SourceAclPolicy


class _RagAccessResolver:
    def __init__(self, db: Session, *, user: User) -> None:
        self._db = db
        self._user = user
        self._policies_by_workspace: dict[str, SourceAclPolicy | None] = {}

    def can_read_resource(
        self,
        *,
        workspace_id: str,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        policy = self._policy_for_workspace_id(workspace_id)
        return policy is not None and policy.can_read_rag_resource(
            resource_type,
            resource_id,
        )

    def _policy_for_workspace_id(self, workspace_id: str) -> SourceAclPolicy | None:
        if workspace_id not in self._policies_by_workspace:
            try:
                self._policies_by_workspace[workspace_id] = SourceAclPolicy.for_workspace_id(
                    self._db,
                    workspace_id=workspace_id,
                    user=self._user,
                )
            except ValueError:
                self._policies_by_workspace[workspace_id] = None
        return self._policies_by_workspace[workspace_id]

    def filter_many(
        self,
        hits: Sequence[RagVectorSearchHit],
        *,
        workspace_id: str | None,
    ) -> list[RagVectorSearchHit]:
        hits_by_workspace: dict[str, list[RagVectorSearchHit]] = defaultdict(list)
        for hit in hits:
            hit_workspace_id = hit.projection.workspace_id
            if hit_workspace_id is None:
                continue
            if workspace_id is not None and hit_workspace_id != workspace_id:
                continue
            hits_by_workspace[hit_workspace_id].append(hit)

        allowed_keys: set[tuple[str, str, str]] = set()
        for hit_workspace_id, workspace_hits in hits_by_workspace.items():
            policy = self._policy_for_workspace_id(hit_workspace_id)
            if policy is None:
                continue
            allowed = policy.authorize_many_rag_resources(
                (
                    (hit.projection.resource_type, hit.projection.resource_id)
                    for hit in workspace_hits
                )
            )
            allowed_keys.update(
                (hit_workspace_id, resource_type, resource_id)
                for resource_type, resource_id in allowed
            )
        return [
            hit
            for hit in hits
            if (
                str(hit.projection.workspace_id or ""),
                hit.projection.resource_type,
                hit.projection.resource_id,
            )
            in allowed_keys
        ]


class _WorkspaceRagPostFilter:
    def __init__(
        self,
        db: Session,
        *,
        user: User,
        workspace_id: str | None,
        authorized_partition_ids: Sequence[str] | None,
    ) -> None:
        self._resolver = _RagAccessResolver(db, user=user)
        self._workspace_id = workspace_id
        self._authorized_partition_ids = (
            frozenset(authorized_partition_ids) if authorized_partition_ids is not None else None
        )

    def __call__(self, hit: RagVectorSearchHit) -> bool:
        return bool(self.filter_many([hit]))

    def filter_many(
        self,
        hits: Sequence[RagVectorSearchHit],
    ) -> list[RagVectorSearchHit]:
        if self._authorized_partition_ids is not None:
            if self._workspace_id is None:
                return []
            policy = self._resolver._policy_for_workspace_id(self._workspace_id)
            if policy is None:
                return []
            candidates = [
                hit
                for hit in hits
                if hit.projection.retrieval_partition_id in self._authorized_partition_ids
            ]
            allowed = policy.authorize_many_rag_resources(
                ((hit.projection.resource_type, hit.projection.resource_id) for hit in candidates)
            )
            return [
                hit
                for hit in candidates
                if (hit.projection.resource_type, hit.projection.resource_id) in allowed
            ]
        return self._resolver.filter_many(hits, workspace_id=self._workspace_id)


class _CompanyRagPostFilter:
    def __init__(
        self,
        db: Session,
        *,
        user: User,
        source_kinds: Sequence[str],
        authorized_partition_ids: Sequence[str] | None,
    ) -> None:
        self._policy = SourceAclPolicy.for_company(db, user=user)
        self._source_kinds = frozenset(source_kinds)
        self._authorized_partition_ids = (
            frozenset(authorized_partition_ids) if authorized_partition_ids is not None else None
        )

    def __call__(self, hit: RagVectorSearchHit) -> bool:
        return bool(self.filter_many([hit]))

    def filter_many(
        self,
        hits: Sequence[RagVectorSearchHit],
    ) -> list[RagVectorSearchHit]:
        candidates = [hit for hit in hits if self._is_company_candidate(hit)]
        allowed = self._policy.authorize_many_rag_resources(
            ((hit.projection.resource_type, hit.projection.resource_id) for hit in candidates)
        )
        return [
            hit
            for hit in candidates
            if (hit.projection.resource_type, hit.projection.resource_id) in allowed
        ]

    def _is_company_candidate(self, hit: RagVectorSearchHit) -> bool:
        projection = hit.projection
        if self._authorized_partition_ids is not None:
            return bool(
                projection.retrieval_partition_id in self._authorized_partition_ids
                and (not self._source_kinds or projection.source_kind in self._source_kinds)
            )
        return bool(
            projection.scope_kind == "company"
            and "company_public" in projection.visibility_refs
            and (not self._source_kinds or projection.source_kind in self._source_kinds)
        )


def build_user_rag_post_filter(
    db: Session,
    *,
    user: User,
    workspace_id: str | None = None,
    authorized_partition_ids: Sequence[str] | None = None,
) -> Callable[[RagVectorSearchHit], bool]:
    return _WorkspaceRagPostFilter(
        db,
        user=user,
        workspace_id=workspace_id,
        authorized_partition_ids=authorized_partition_ids,
    )


def build_company_rag_post_filter(
    db: Session,
    *,
    user: User,
    source_kinds: Sequence[str],
    authorized_partition_ids: Sequence[str] | None = None,
) -> Callable[[RagVectorSearchHit], bool]:
    return _CompanyRagPostFilter(
        db,
        user=user,
        source_kinds=source_kinds,
        authorized_partition_ids=authorized_partition_ids,
    )


def can_user_access_hit(
    db: Session,
    *,
    user: User,
    hit: RagVectorSearchHit,
) -> bool:
    return can_user_access_resource(
        db,
        user=user,
        workspace_id=hit.projection.workspace_id,
        resource_type=hit.projection.resource_type,
        resource_id=hit.projection.resource_id,
    )


def can_user_access_resource(
    db: Session,
    *,
    user: User,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
) -> bool:
    resolver = _RagAccessResolver(db, user=user)
    return resolver.can_read_resource(
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
