from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.rag.contracts import RagVectorSearchHit
from open_work_hub_api.domains.source_access import SourceAclPolicy


class _UserRagPostFilter:
    """Partitions select candidates. Only live source authorization can release content."""

    def __init__(
        self,
        db: Session,
        *,
        user: User,
        authorized_partition_ids: Sequence[str] | None,
        source_kinds: Sequence[str] = (),
    ) -> None:
        self._db = db
        self._user_id = user.id
        self._partition_ids = (
            frozenset(authorized_partition_ids) if authorized_partition_ids is not None else None
        )
        self._source_kinds = frozenset(source_kinds)

    def __call__(self, hit: RagVectorSearchHit) -> bool:
        return bool(self.filter_many([hit]))

    def filter_many(self, hits: Sequence[RagVectorSearchHit]) -> list[RagVectorSearchHit]:
        user = self._db.scalar(
            select(User)
            .where(User.id == self._user_id, User.status == "active", User.login_blocked.is_(False))
            .execution_options(populate_existing=True)
        )
        if user is None:
            return []
        candidates = [
            hit
            for hit in hits
            if (
                self._partition_ids is None
                or hit.projection.retrieval_partition_id in self._partition_ids
            )
            and (not self._source_kinds or hit.projection.source_kind in self._source_kinds)
        ]
        policy = SourceAclPolicy.for_user(self._db, user=user)
        allowed = policy.authorize_many_rag_resources(
            (hit.projection.resource_type, hit.projection.resource_id) for hit in candidates
        )
        return [
            hit
            for hit in candidates
            if (hit.projection.resource_type, hit.projection.resource_id) in allowed
        ]


def build_user_rag_post_filter(
    db: Session, *, user: User, authorized_partition_ids: Sequence[str] | None = None
) -> _UserRagPostFilter:
    return _UserRagPostFilter(db, user=user, authorized_partition_ids=authorized_partition_ids)


def build_company_rag_post_filter(
    db: Session,
    *,
    user: User,
    source_kinds: Sequence[str],
    authorized_partition_ids: Sequence[str] | None = None,
) -> _UserRagPostFilter:
    return _UserRagPostFilter(
        db, user=user, source_kinds=source_kinds, authorized_partition_ids=authorized_partition_ids
    )


def can_user_access_hit(db: Session, *, user: User, hit: RagVectorSearchHit) -> bool:
    return can_user_access_resource(
        db,
        user=user,
        resource_type=hit.projection.resource_type,
        resource_id=hit.projection.resource_id,
    )


def can_user_access_resource(
    db: Session, *, user: User, resource_type: str, resource_id: str
) -> bool:
    return SourceAclPolicy.for_user(db, user=user).can_read_rag_resource(resource_type, resource_id)
