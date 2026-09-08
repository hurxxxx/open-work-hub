from __future__ import annotations

from typing import Any

from open_work_hub_api.domains.rag.contracts import RagSyncOperation, RagTraceContext
from open_work_hub_api.domains.rag.job_publication import (
    RagJobPublishTarget,
)
from open_work_hub_api.domains.rag.job_publication import (
    resolve_publish_target as _resolve_publish_target,
)


def normalize_trace_context(
    value: RagTraceContext | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, RagTraceContext):
        return value.model_dump(mode="json")
    return dict(value)


def merge_sync_operation(
    existing: str,
    incoming: str,
    *,
    supersede_delete: bool = False,
) -> str:
    if (
        supersede_delete
        and existing == RagSyncOperation.DELETE.value
        and incoming == RagSyncOperation.UPSERT.value
    ):
        return incoming
    if existing == RagSyncOperation.DELETE.value:
        return existing
    if incoming == RagSyncOperation.DELETE.value:
        return incoming
    if incoming == RagSyncOperation.UPSERT.value:
        return incoming
    if existing == RagSyncOperation.UPSERT.value:
        return existing
    return RagSyncOperation.VISIBILITY_UPDATE.value


def merge_recompute_cursor(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if existing is None:
        return incoming
    if incoming is None:
        return existing

    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"doc_ids", "task_ids"}:
            merged[key] = sorted({*(merged.get(key) or []), *(value or [])})
            continue
        merged[key] = value
    return merged


def resolve_publish_target(*, kind: str, lane: str | None) -> RagJobPublishTarget:
    return _resolve_publish_target(kind=kind, lane=lane)
