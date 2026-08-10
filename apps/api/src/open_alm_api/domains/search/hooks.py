from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from open_alm_api.domains.retrieval.projection_fencing import ProjectionEventRef
from open_alm_api.domains.search.default_index_hook_adapters import (
    ensure_search_index_hooks_registered,
)
from open_alm_api.domains.search.hook_registry import resolve_search_index_hook


def _call_hook(name: str, *args: Any, **kwargs: Any) -> Any:
    ensure_search_index_hooks_registered()
    return resolve_search_index_hook(name)(*args, **kwargs)


def _projection_event_kwargs(
    projection_event: ProjectionEventRef | None,
) -> dict[str, ProjectionEventRef]:
    # Keep compatibility with app-owned hooks that have not adopted the
    # additive versioned-event argument yet.
    return {"projection_event": projection_event} if projection_event is not None else {}


def enqueue_doc_search_index(
    db: Session,
    *,
    doc: Any,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    _call_hook(
        "docs.enqueue_doc_search_index",
        db,
        doc=doc,
        operation=operation,
        **_projection_event_kwargs(projection_event),
    )


def enqueue_doc_search_index_by_id(
    db: Session,
    *,
    doc_id: str,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    _call_hook(
        "docs.enqueue_doc_search_index_by_id",
        db,
        doc_id=doc_id,
        operation=operation,
        **_projection_event_kwargs(projection_event),
    )


def enqueue_meeting_search_index(
    db: Session,
    *,
    meeting: Any,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    _call_hook(
        "meeting.enqueue_meeting_search_index",
        db,
        meeting=meeting,
        operation=operation,
        **_projection_event_kwargs(projection_event),
    )


def enqueue_meeting_search_index_by_id(
    db: Session,
    *,
    meeting_id: str,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    _call_hook(
        "meeting.enqueue_meeting_search_index_by_id",
        db,
        meeting_id=meeting_id,
        operation=operation,
        **_projection_event_kwargs(projection_event),
    )


def enqueue_task_search_index(
    db: Session,
    *,
    task: Any,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    _call_hook(
        "pms.enqueue_task_search_index",
        db,
        task=task,
        operation=operation,
        **_projection_event_kwargs(projection_event),
    )


def enqueue_task_search_index_by_id(
    db: Session,
    *,
    task_id: str,
    operation: str = "upsert",
    projection_event: ProjectionEventRef | None = None,
) -> None:
    _call_hook(
        "pms.enqueue_task_search_index_by_id",
        db,
        task_id=task_id,
        operation=operation,
        **_projection_event_kwargs(projection_event),
    )


def enqueue_task_list_task_search_recompute(
    db: Session,
    *,
    task_list: Any,
    operation: str = "upsert",
) -> None:
    _call_hook(
        "pms.enqueue_task_list_task_search_recompute",
        db,
        task_list=task_list,
        operation=operation,
    )


def enqueue_label_task_search_recompute(
    db: Session,
    *,
    label: Any,
    task_ids: list[str] | None = None,
    operation: str = "upsert",
) -> None:
    _call_hook(
        "pms.enqueue_label_task_search_recompute",
        db,
        label=label,
        task_ids=task_ids,
        operation=operation,
    )


def enqueue_task_list_status_task_search_recompute(
    db: Session,
    *,
    task_status: Any,
    operation: str = "upsert",
) -> None:
    _call_hook(
        "pms.enqueue_task_list_status_task_search_recompute",
        db,
        task_status=task_status,
        operation=operation,
    )


__all__ = [
    "enqueue_doc_search_index",
    "enqueue_doc_search_index_by_id",
    "enqueue_label_task_search_recompute",
    "enqueue_meeting_search_index",
    "enqueue_meeting_search_index_by_id",
    "enqueue_task_list_status_task_search_recompute",
    "enqueue_task_list_task_search_recompute",
    "enqueue_task_search_index",
    "enqueue_task_search_index_by_id",
]
