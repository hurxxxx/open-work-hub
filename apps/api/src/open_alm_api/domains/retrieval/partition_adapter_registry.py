from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.retrieval.partitioning import (
    RetrievalPartitionUnbound,
    normalize_source_namespace,
)


@dataclass(frozen=True, slots=True)
class RetrievalProjectionBinding:
    resource_type: str
    resource_id: str
    partition_id: str


RetrievalPartitionTransitionMode = Literal["generic", "source_owned"]


class RetrievalPartitionAdapter(Protocol):
    adapter_id: str
    source_namespace: str
    resource_types: tuple[str, ...]
    allowed_candidate_scopes: tuple[str, ...]
    allowed_transitions: tuple[str, ...]
    transition_mode: RetrievalPartitionTransitionMode

    def bind_resource_partition(
        self,
        db: Session,
        *,
        resource_type: str,
        resource_id: str,
    ) -> RetrievalProjectionBinding: ...


_adapters_by_id: dict[str, RetrievalPartitionAdapter] = {}
_adapter_ids_by_resource_type: dict[str, str] = {}


def register_retrieval_partition_adapter(adapter: RetrievalPartitionAdapter) -> None:
    adapter_id = _normalize_identifier(adapter.adapter_id, label="adapter_id")
    source_namespace = normalize_source_namespace(adapter.source_namespace)
    resource_types = tuple(
        dict.fromkeys(
            _normalize_identifier(resource_type, label="resource_type")
            for resource_type in adapter.resource_types
        )
    )
    allowed_candidate_scopes = tuple(
        dict.fromkeys(
            _normalize_identifier(scope, label="allowed_candidate_scopes")
            for scope in adapter.allowed_candidate_scopes
        )
    )
    allowed_transitions = tuple(
        dict.fromkeys(
            _normalize_identifier(operation, label="allowed_transitions")
            for operation in adapter.allowed_transitions
        )
    )
    transition_mode = _normalize_identifier(
        getattr(adapter, "transition_mode", ""),
        label="transition_mode",
    )
    if not resource_types:
        raise ValueError(
            f"Retrieval partition adapter {adapter_id!r} must claim resource_types"
        )
    if not allowed_candidate_scopes:
        raise ValueError(
            f"Retrieval partition adapter {adapter_id!r} must allow candidate scopes"
        )
    unknown_scopes = sorted(
        set(allowed_candidate_scopes) - {"company", "workspace", "personal"}
    )
    if unknown_scopes:
        raise ValueError(
            f"Retrieval partition adapter {adapter_id!r} has unsupported candidate "
            f"scopes: {', '.join(unknown_scopes)}"
        )
    if transition_mode not in {"generic", "source_owned"}:
        raise ValueError(
            f"Retrieval partition adapter {adapter_id!r} has unsupported transition "
            f"mode: {transition_mode}"
        )
    if not callable(getattr(adapter, "bind_resource_partition", None)):
        raise ValueError(
            f"Retrieval partition adapter {adapter_id!r} must declare a binder"
        )
    if adapter.adapter_id != adapter_id or adapter.source_namespace != source_namespace:
        raise ValueError(
            "Retrieval partition adapter identifiers must already be normalized"
        )
    if tuple(adapter.resource_types) != resource_types:
        raise ValueError(
            f"Retrieval partition adapter {adapter_id!r} resource_types must be normalized"
        )
    if tuple(adapter.allowed_candidate_scopes) != allowed_candidate_scopes:
        raise ValueError(
            f"Retrieval partition adapter {adapter_id!r} candidate scopes must be "
            "normalized"
        )
    if tuple(adapter.allowed_transitions) != allowed_transitions:
        raise ValueError(
            f"Retrieval partition adapter {adapter_id!r} transitions must be normalized"
        )
    if adapter.transition_mode != transition_mode:
        raise ValueError(
            f"Retrieval partition adapter {adapter_id!r} transition mode must be normalized"
        )

    existing = _adapters_by_id.get(adapter_id)
    if existing is not None:
        if existing != adapter:
            raise ValueError(
                f"Retrieval partition adapter already registered: {adapter_id}"
            )
        return
    conflicts = {
        resource_type: _adapter_ids_by_resource_type[resource_type]
        for resource_type in resource_types
        if resource_type in _adapter_ids_by_resource_type
    }
    if conflicts:
        details = ", ".join(
            f"{resource_type}->{owner_id}"
            for resource_type, owner_id in sorted(conflicts.items())
        )
        raise ValueError(
            f"Retrieval partition resources already have adapters: {details}"
        )

    _adapters_by_id[adapter_id] = adapter
    for resource_type in resource_types:
        _adapter_ids_by_resource_type[resource_type] = adapter_id


def get_retrieval_partition_adapter(
    adapter_id: object,
) -> RetrievalPartitionAdapter | None:
    return _adapters_by_id.get(str(adapter_id).strip())


def get_retrieval_partition_adapter_for_resource(
    resource_type: object,
) -> RetrievalPartitionAdapter | None:
    normalized = str(resource_type).strip()
    adapter_id = _adapter_ids_by_resource_type.get(normalized)
    if adapter_id is None:
        return None
    return _adapters_by_id[adapter_id]


def has_retrieval_partition_adapter(adapter_id: object) -> bool:
    return str(adapter_id).strip() in _adapters_by_id


def retrieval_partition_adapters() -> tuple[RetrievalPartitionAdapter, ...]:
    return tuple(_adapters_by_id.values())


def reset_retrieval_partition_adapters() -> None:
    _adapters_by_id.clear()
    _adapter_ids_by_resource_type.clear()


def bind_model_partition(
    db: Session,
    *,
    model: Any,
    resource_type: str,
    resource_id: str,
) -> RetrievalProjectionBinding:
    partition_id = db.scalar(
        select(model.retrieval_partition_id).where(model.id == resource_id)
    )
    if partition_id is None:
        raise RetrievalPartitionUnbound(
            f"retrieval resource is missing a partition binding: "
            f"{resource_type}/{resource_id}"
        )
    return RetrievalProjectionBinding(
        resource_type=resource_type,
        resource_id=resource_id,
        partition_id=str(partition_id),
    )


def _normalize_identifier(value: object, *, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"Retrieval partition adapter must declare {label}")
    return normalized


__all__ = [
    "RetrievalPartitionAdapter",
    "RetrievalPartitionTransitionMode",
    "RetrievalProjectionBinding",
    "bind_model_partition",
    "get_retrieval_partition_adapter",
    "get_retrieval_partition_adapter_for_resource",
    "has_retrieval_partition_adapter",
    "register_retrieval_partition_adapter",
    "reset_retrieval_partition_adapters",
    "retrieval_partition_adapters",
]
