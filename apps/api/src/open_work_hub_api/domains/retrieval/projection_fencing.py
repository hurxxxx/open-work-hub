from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.retrieval.models import (
    RetrievalProjectionChangeKind,
    RetrievalProjectionDesiredState,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.retrieval.projection_identity import canonical_resource_key


@dataclass(frozen=True, slots=True)
class ProjectionEventRef:
    event_sequence: int
    resource_type: str
    resource_id: str
    projection_version: int
    retrieval_partition_id: str
    change_kind: str
    desired_state: str
    content_checksum: str | None
    visibility_checksum: str | None
    diagnostic_workspace_id: str | None


def record_projection_event(
    db: Session,
    *,
    resource_type: str,
    resource_id: str,
    retrieval_partition_id: str,
    change_kind: str | RetrievalProjectionChangeKind,
    desired_state: str | RetrievalProjectionDesiredState,
    content_checksum: str | None = None,
    visibility_checksum: str | None = None,
    diagnostic_workspace_id: str | None = None,
    trace_context: Mapping[str, object] | None = None,
) -> ProjectionEventRef:
    """Advance one canonical resource stream without committing its outer transaction."""
    normalized_resource_type = _required_text(
        resource_type,
        field="resource_type",
        max_length=64,
    )
    normalized_resource_id = _required_text(
        resource_id,
        field="resource_id",
        max_length=255,
    )
    normalized_partition_id = _uuid_text(
        retrieval_partition_id,
        field="retrieval_partition_id",
    )
    normalized_change_kind = _enum_value(
        change_kind,
        enum_type=RetrievalProjectionChangeKind,
        field="change_kind",
    )
    normalized_desired_state = _enum_value(
        desired_state,
        enum_type=RetrievalProjectionDesiredState,
        field="desired_state",
    )
    normalized_content_checksum = _optional_text(
        content_checksum,
        field="content_checksum",
        max_length=128,
    )
    normalized_visibility_checksum = _optional_text(
        visibility_checksum,
        field="visibility_checksum",
        max_length=128,
    )
    normalized_workspace_id = _optional_text(
        diagnostic_workspace_id,
        field="diagnostic_workspace_id",
        max_length=36,
    )
    if normalized_change_kind == RetrievalProjectionChangeKind.DELETE.value:
        if normalized_desired_state != RetrievalProjectionDesiredState.DELETED.value:
            raise ValueError("delete projection events require desired_state='deleted'")
    elif normalized_desired_state == RetrievalProjectionDesiredState.DELETED.value:
        if normalized_change_kind != RetrievalProjectionChangeKind.REPAIR.value:
            raise ValueError("deleted projection state requires a delete or repair event")

    _lock_projection_stream(
        db,
        resource_type=normalized_resource_type,
        resource_id=normalized_resource_id,
    )
    head = db.scalar(
        select(RetrievalProjectionHead)
        .where(
            RetrievalProjectionHead.resource_type == normalized_resource_type,
            RetrievalProjectionHead.resource_id == normalized_resource_id,
        )
        .with_for_update()
    )
    now = utcnow_naive()
    if head is None:
        projection_version = 1
        head = RetrievalProjectionHead(
            resource_type=normalized_resource_type,
            resource_id=normalized_resource_id,
            projection_version=projection_version,
            retrieval_partition_id=normalized_partition_id,
            desired_state=normalized_desired_state,
            content_checksum=normalized_content_checksum,
            visibility_checksum=normalized_visibility_checksum,
            diagnostic_workspace_id=normalized_workspace_id,
            updated_at=now,
        )
        db.add(head)
    else:
        projection_version = head.projection_version + 1
        head.projection_version = projection_version
        head.retrieval_partition_id = normalized_partition_id
        head.desired_state = normalized_desired_state
        head.content_checksum = normalized_content_checksum
        head.visibility_checksum = normalized_visibility_checksum
        head.diagnostic_workspace_id = normalized_workspace_id
        head.updated_at = now

    event = RetrievalProjectionEvent(
        resource_type=normalized_resource_type,
        resource_id=normalized_resource_id,
        projection_version=projection_version,
        retrieval_partition_id=normalized_partition_id,
        change_kind=normalized_change_kind,
        desired_state=normalized_desired_state,
        content_checksum=normalized_content_checksum,
        visibility_checksum=normalized_visibility_checksum,
        diagnostic_workspace_id=normalized_workspace_id,
        trace_context=dict(trace_context) if trace_context is not None else None,
        created_at=now,
    )
    db.add(event)
    db.flush()

    return ProjectionEventRef(
        event_sequence=event.event_sequence,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        projection_version=event.projection_version,
        retrieval_partition_id=event.retrieval_partition_id,
        change_kind=event.change_kind,
        desired_state=event.desired_state,
        content_checksum=event.content_checksum,
        visibility_checksum=event.visibility_checksum,
        diagnostic_workspace_id=event.diagnostic_workspace_id,
    )


def _lock_projection_stream(
    db: Session,
    *,
    resource_type: str,
    resource_id: str,
) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    stream_identity = canonical_resource_key(
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:stream_identity, CAST(0 AS bigint)))"),
        {"stream_identity": stream_identity},
    )


def _required_text(value: object, *, field: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized) > max_length:
        raise ValueError(f"{field} exceeds {max_length} characters")
    return normalized


def _optional_text(value: object | None, *, field: str, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise ValueError(f"{field} exceeds {max_length} characters")
    return normalized


def _uuid_text(value: object, *, field: str) -> str:
    normalized = _required_text(value, field=field, max_length=36)
    try:
        return str(UUID(normalized))
    except ValueError as error:
        raise ValueError(f"{field} must be a UUID") from error


def _enum_value[EnumT: RetrievalProjectionChangeKind | RetrievalProjectionDesiredState](
    value: str | EnumT,
    *,
    enum_type: type[EnumT],
    field: str,
) -> str:
    normalized = str(value).strip()
    try:
        return enum_type(normalized).value
    except ValueError as error:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"{field} must be one of: {allowed}") from error


__all__ = ["ProjectionEventRef", "record_projection_event"]
