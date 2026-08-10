from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NewType

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_alm_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalPartitionCandidateScope,
    RetrievalPartitionState,
)


RetrievalPartitionId = NewType("RetrievalPartitionId", str)

_SOURCE_NAMESPACE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")


class RetrievalPartitionError(RuntimeError):
    pass


class RetrievalPartitionInvalidTarget(RetrievalPartitionError):
    pass


class RetrievalPartitionNotFound(RetrievalPartitionError):
    pass


class RetrievalPartitionUnbound(RetrievalPartitionError):
    pass


class RetrievalPartitionConflict(RetrievalPartitionError):
    pass


@dataclass(frozen=True, slots=True)
class RetrievalSourcePartitions:
    source_namespace: str
    partition_ids: tuple[RetrievalPartitionId, ...]


@dataclass(frozen=True, slots=True)
class RetrievalReadScope:
    sources: tuple[RetrievalSourcePartitions, ...]

    @property
    def is_empty(self) -> bool:
        return not any(source.partition_ids for source in self.sources)

    def for_source(self, source_namespace: str) -> tuple[RetrievalPartitionId, ...]:
        normalized = normalize_source_namespace(source_namespace)
        for source in self.sources:
            if source.source_namespace == normalized:
                return source.partition_ids
        return ()


def normalize_source_namespace(value: object) -> str:
    normalized = str(value).strip().lower()
    if not _SOURCE_NAMESPACE_PATTERN.fullmatch(normalized):
        raise RetrievalPartitionInvalidTarget(
            "source_namespace must match [a-z0-9][a-z0-9_.-]{0,79}"
        )
    return normalized


def bind_projection(
    db: Session,
    *,
    resource_type: str,
    resource_id: str,
):
    from open_alm_api.domains.retrieval.partition_adapter_registry import (
        RetrievalProjectionBinding,
        get_retrieval_partition_adapter_for_resource,
    )

    normalized_resource_type = str(resource_type).strip()
    normalized_resource_id = str(resource_id).strip()
    if not normalized_resource_type or not normalized_resource_id:
        raise RetrievalPartitionUnbound(
            "retrieval projection requires resource_type and resource_id"
        )
    adapter = get_retrieval_partition_adapter_for_resource(normalized_resource_type)
    if adapter is None:
        raise RetrievalPartitionUnbound(
            f"retrieval partition adapter is not registered: {normalized_resource_type}"
        )
    binding = adapter.bind_resource_partition(
        db,
        resource_type=normalized_resource_type,
        resource_id=normalized_resource_id,
    )
    if not isinstance(binding, RetrievalProjectionBinding):
        raise RetrievalPartitionUnbound(
            f"retrieval partition adapter returned an invalid binding: {adapter.adapter_id}"
        )
    if (
        binding.resource_type != normalized_resource_type
        or binding.resource_id != normalized_resource_id
        or not binding.partition_id.strip()
    ):
        raise RetrievalPartitionUnbound(
            f"retrieval partition adapter returned a mismatched binding: {adapter.adapter_id}"
        )
    partition = db.get(RetrievalPartition, binding.partition_id)
    if partition is None:
        raise RetrievalPartitionUnbound(
            f"retrieval partition binding points to a missing partition: {binding.partition_id}"
        )
    if partition.source_namespace != adapter.source_namespace:
        raise RetrievalPartitionConflict(
            "retrieval partition namespace does not match its source adapter"
        )
    if partition.state != RetrievalPartitionState.ACTIVE.value:
        raise RetrievalPartitionConflict(f"retrieval partition is not active: {partition.id}")
    if partition.candidate_scope_kind not in adapter.allowed_candidate_scopes:
        raise RetrievalPartitionConflict(
            "retrieval partition candidate scope is not allowed by its source adapter"
        )
    return binding


def ensure_default_partition(
    db: Session,
    *,
    source_namespace: str,
    candidate_scope_kind: RetrievalPartitionCandidateScope | str,
    workspace_id: str | None = None,
    user_id: str | None = None,
) -> RetrievalPartition:
    namespace = normalize_source_namespace(source_namespace)
    scope_kind, candidate_workspace_id, candidate_user_id = _normalize_candidate_target(
        candidate_scope_kind,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    managed_workspace_id = (
        candidate_workspace_id if scope_kind == RetrievalPartitionCandidateScope.WORKSPACE else None
    )
    predicate = _default_partition_predicate(
        source_namespace=namespace,
        scope_kind=scope_kind,
        managed_workspace_id=managed_workspace_id,
        candidate_user_id=candidate_user_id,
    )
    existing = db.scalar(select(RetrievalPartition).where(*predicate))
    if existing is not None:
        return existing

    candidate = RetrievalPartition(
        source_namespace=namespace,
        managed_workspace_id=managed_workspace_id,
        candidate_scope_kind=scope_kind.value,
        candidate_workspace_id=candidate_workspace_id,
        candidate_user_id=candidate_user_id,
        state=RetrievalPartitionState.ACTIVE.value,
        metadata_version=1,
        is_default_ingest=True,
    )
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
    except IntegrityError:
        existing = db.scalar(select(RetrievalPartition).where(*predicate))
        if existing is None:
            raise
        return existing
    return candidate


def create_managed_partition(
    db: Session,
    *,
    source_namespace: str,
    managed_workspace_id: str,
    candidate_scope_kind: RetrievalPartitionCandidateScope | str,
    workspace_id: str | None = None,
    user_id: str | None = None,
) -> RetrievalPartition:
    """Create a source-owned, non-default partition for one managed aggregate."""

    namespace = normalize_source_namespace(source_namespace)
    normalized_managed_workspace_id = _normalize_optional_id(managed_workspace_id)
    if normalized_managed_workspace_id is None:
        raise RetrievalPartitionInvalidTarget("managed partition requires managed_workspace_id")
    try:
        requested_scope = RetrievalPartitionCandidateScope(str(candidate_scope_kind))
    except ValueError as exc:
        raise RetrievalPartitionInvalidTarget(
            f"unsupported retrieval partition candidate scope: {candidate_scope_kind}"
        ) from exc
    resolved_workspace_id = workspace_id
    if requested_scope == RetrievalPartitionCandidateScope.WORKSPACE and workspace_id is None:
        resolved_workspace_id = normalized_managed_workspace_id
    scope_kind, candidate_workspace_id, candidate_user_id = _normalize_candidate_target(
        requested_scope,
        workspace_id=resolved_workspace_id,
        user_id=user_id,
    )
    partition = RetrievalPartition(
        source_namespace=namespace,
        managed_workspace_id=normalized_managed_workspace_id,
        candidate_scope_kind=scope_kind.value,
        candidate_workspace_id=candidate_workspace_id,
        candidate_user_id=candidate_user_id,
        state=RetrievalPartitionState.ACTIVE.value,
        metadata_version=1,
        is_default_ingest=False,
    )
    db.add(partition)
    db.flush()
    return partition


def assign_default_partition(
    db: Session,
    *,
    target: object,
    source_namespace: str,
    candidate_scope_kind: RetrievalPartitionCandidateScope | str,
    workspace_id: str | None = None,
    user_id: str | None = None,
) -> RetrievalPartitionId:
    """Dual-write a source row binding in the caller's source transaction."""

    current = str(getattr(target, "retrieval_partition_id", None) or "").strip()
    if current:
        return RetrievalPartitionId(current)
    partition = ensure_default_partition(
        db,
        source_namespace=source_namespace,
        candidate_scope_kind=candidate_scope_kind,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    setattr(target, "retrieval_partition_id", partition.id)
    return RetrievalPartitionId(partition.id)


def resolve_read_scope(
    db: Session,
    *,
    source_namespaces: tuple[str, ...] | list[str],
    workspace_id: str | None,
    user_id: str | None,
) -> RetrievalReadScope:
    namespaces = tuple(
        dict.fromkeys(normalize_source_namespace(value) for value in source_namespaces)
    )
    if not namespaces:
        return RetrievalReadScope(sources=())

    access_predicates = [
        RetrievalPartition.candidate_scope_kind == RetrievalPartitionCandidateScope.COMPANY.value,
    ]
    if workspace_id is not None:
        access_predicates.append(
            and_(
                RetrievalPartition.candidate_scope_kind
                == RetrievalPartitionCandidateScope.WORKSPACE.value,
                RetrievalPartition.candidate_workspace_id == workspace_id,
            )
        )
    if user_id is not None:
        access_predicates.append(
            and_(
                RetrievalPartition.candidate_scope_kind
                == RetrievalPartitionCandidateScope.PERSONAL.value,
                RetrievalPartition.candidate_user_id == user_id,
            )
        )

    rows = db.scalars(
        select(RetrievalPartition)
        .where(
            RetrievalPartition.source_namespace.in_(namespaces),
            RetrievalPartition.state == RetrievalPartitionState.ACTIVE.value,
            or_(*access_predicates),
        )
        .order_by(RetrievalPartition.source_namespace, RetrievalPartition.id)
    ).all()
    ids_by_source: dict[str, list[RetrievalPartitionId]] = {
        namespace: [] for namespace in namespaces
    }
    for row in rows:
        ids_by_source[row.source_namespace].append(RetrievalPartitionId(row.id))
    return RetrievalReadScope(
        sources=tuple(
            RetrievalSourcePartitions(
                source_namespace=namespace,
                partition_ids=tuple(ids_by_source[namespace]),
            )
            for namespace in namespaces
        )
    )


def resolve_resource_read_scope(
    db: Session,
    *,
    resource_types: tuple[str, ...] | list[str],
    workspace_id: str | None,
    user_id: str | None,
) -> RetrievalReadScope:
    """Resolve trusted partition IDs from registered resource ownership."""

    from open_alm_api.domains.retrieval.default_partition_adapters import (
        ensure_retrieval_partition_adapters_registered,
    )
    from open_alm_api.domains.retrieval.partition_adapter_registry import (
        get_retrieval_partition_adapter_for_resource,
    )

    ensure_retrieval_partition_adapters_registered()
    source_namespaces: list[str] = []
    for resource_type in dict.fromkeys(
        str(resource_type).strip() for resource_type in resource_types if str(resource_type).strip()
    ):
        adapter = get_retrieval_partition_adapter_for_resource(resource_type)
        if adapter is None:
            raise RetrievalPartitionUnbound(
                f"retrieval partition adapter is not registered: {resource_type}"
            )
        if adapter.source_namespace not in source_namespaces:
            source_namespaces.append(adapter.source_namespace)
    return resolve_read_scope(
        db,
        source_namespaces=source_namespaces,
        workspace_id=workspace_id,
        user_id=user_id,
    )


def flatten_read_scope(scope: RetrievalReadScope) -> tuple[RetrievalPartitionId, ...]:
    return tuple(partition_id for source in scope.sources for partition_id in source.partition_ids)


def transition_partition_candidate_scope(
    db: Session,
    *,
    partition_id: str,
    adapter_id: str,
    transition_operation: str,
    expected_metadata_version: int,
    candidate_scope_kind: RetrievalPartitionCandidateScope | str,
    workspace_id: str | None = None,
    user_id: str | None = None,
) -> RetrievalPartition:
    from open_alm_api.domains.retrieval.partition_adapter_registry import (
        get_retrieval_partition_adapter,
    )

    adapter = get_retrieval_partition_adapter(adapter_id)
    if adapter is None:
        raise RetrievalPartitionConflict(
            f"retrieval partition adapter is not registered: {adapter_id}"
        )
    if adapter.transition_mode != "generic":
        raise RetrievalPartitionConflict(
            "retrieval partition candidate-scope transition is owned by its "
            f"source service: {adapter.adapter_id}"
        )
    normalized_operation = str(transition_operation or "").strip()
    if normalized_operation not in adapter.allowed_transitions:
        raise RetrievalPartitionConflict(
            f"retrieval partition transition is not allowed: {normalized_operation}"
        )
    scope_kind, candidate_workspace_id, candidate_user_id = _normalize_candidate_target(
        candidate_scope_kind,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    partition = db.scalar(
        select(RetrievalPartition)
        .where(RetrievalPartition.id == str(partition_id))
        .with_for_update()
    )
    if partition is None:
        raise RetrievalPartitionNotFound(str(partition_id))
    if partition.source_namespace != adapter.source_namespace:
        raise RetrievalPartitionConflict(
            "retrieval partition namespace does not match its source adapter"
        )
    if scope_kind.value not in adapter.allowed_candidate_scopes:
        raise RetrievalPartitionConflict(
            "retrieval partition candidate scope is not allowed by its source adapter"
        )
    if partition.is_default_ingest:
        raise RetrievalPartitionConflict(
            "default ingest partitions cannot be republished as a security cohort"
        )
    if partition.state != RetrievalPartitionState.ACTIVE.value:
        raise RetrievalPartitionConflict(f"retrieval partition is not active: {partition.id}")
    if partition.metadata_version != expected_metadata_version:
        raise RetrievalPartitionConflict("retrieval partition metadata version does not match")

    partition.candidate_scope_kind = scope_kind.value
    partition.candidate_workspace_id = candidate_workspace_id
    partition.candidate_user_id = candidate_user_id
    partition.metadata_version += 1
    db.flush()
    return partition


def _normalize_candidate_target(
    candidate_scope_kind: RetrievalPartitionCandidateScope | str,
    *,
    workspace_id: str | None,
    user_id: str | None,
) -> tuple[RetrievalPartitionCandidateScope, str | None, str | None]:
    try:
        scope_kind = RetrievalPartitionCandidateScope(str(candidate_scope_kind))
    except ValueError as exc:
        raise RetrievalPartitionInvalidTarget(
            f"unsupported retrieval partition candidate scope: {candidate_scope_kind}"
        ) from exc
    normalized_workspace_id = _normalize_optional_id(workspace_id)
    normalized_user_id = _normalize_optional_id(user_id)
    if scope_kind == RetrievalPartitionCandidateScope.COMPANY:
        if normalized_workspace_id is not None or normalized_user_id is not None:
            raise RetrievalPartitionInvalidTarget(
                "company partition cannot declare workspace_id or user_id"
            )
    elif scope_kind == RetrievalPartitionCandidateScope.WORKSPACE:
        if normalized_workspace_id is None or normalized_user_id is not None:
            raise RetrievalPartitionInvalidTarget("workspace partition requires only workspace_id")
    elif normalized_user_id is None or normalized_workspace_id is not None:
        raise RetrievalPartitionInvalidTarget("personal partition requires only user_id")
    return scope_kind, normalized_workspace_id, normalized_user_id


def _normalize_optional_id(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise RetrievalPartitionInvalidTarget("partition target id cannot be blank")
    return normalized


def _default_partition_predicate(
    *,
    source_namespace: str,
    scope_kind: RetrievalPartitionCandidateScope,
    managed_workspace_id: str | None,
    candidate_user_id: str | None,
) -> tuple[object, ...]:
    common: tuple[object, ...] = (
        RetrievalPartition.source_namespace == source_namespace,
        RetrievalPartition.is_default_ingest.is_(True),
        RetrievalPartition.state != RetrievalPartitionState.RETIRED.value,
    )
    if scope_kind == RetrievalPartitionCandidateScope.WORKSPACE:
        return (
            *common,
            RetrievalPartition.managed_workspace_id == managed_workspace_id,
            RetrievalPartition.candidate_user_id.is_(None),
        )
    if scope_kind == RetrievalPartitionCandidateScope.PERSONAL:
        return (
            *common,
            RetrievalPartition.candidate_scope_kind
            == RetrievalPartitionCandidateScope.PERSONAL.value,
            RetrievalPartition.candidate_user_id == candidate_user_id,
        )
    return (
        *common,
        RetrievalPartition.managed_workspace_id.is_(None),
        RetrievalPartition.candidate_scope_kind == RetrievalPartitionCandidateScope.COMPANY.value,
    )


__all__ = [
    "RetrievalPartitionConflict",
    "RetrievalPartitionError",
    "RetrievalPartitionId",
    "RetrievalPartitionInvalidTarget",
    "RetrievalPartitionNotFound",
    "RetrievalPartitionUnbound",
    "RetrievalReadScope",
    "RetrievalSourcePartitions",
    "assign_default_partition",
    "bind_projection",
    "create_managed_partition",
    "ensure_default_partition",
    "normalize_source_namespace",
    "resolve_read_scope",
    "transition_partition_candidate_scope",
]
